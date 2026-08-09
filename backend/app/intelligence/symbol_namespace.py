from __future__ import annotations

import json
import re
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[3]
LEGACY_DATA_DIR = PROJECT_ROOT / "data"
SYMBOL_DATA_ROOT = LEGACY_DATA_DIR / "symbols"

_SCOPE_LOCK = threading.RLock()
_SAFE_SYMBOL_RE = re.compile(r"^[A-Za-z0-9._#-]+$")


def safe_symbol(symbol: str) -> str:
    """
    Preserve broker symbols such as XAUUSD, #BTCUSD, BTCUSD.a, etc.,
    while rejecting path traversal and filesystem separators.
    """
    value = str(symbol or "").strip()
    if not value:
        raise ValueError("Symbol is required.")
    if value in {".", ".."}:
        raise ValueError("Invalid symbol namespace.")
    if not _SAFE_SYMBOL_RE.fullmatch(value):
        raise ValueError(
            "Invalid symbol namespace. Allowed characters: "
            "A-Z a-z 0-9 . _ # -"
        )
    return value


def symbol_data_dir(symbol: str) -> Path:
    root = SYMBOL_DATA_ROOT.resolve()
    target = (root / safe_symbol(symbol)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Symbol namespace escapes data root.") from exc
    return target


def symbol_bridge_dir(atlas_bridge_dir: Path, symbol: str) -> Path:
    root = Path(atlas_bridge_dir).resolve()
    target = (root / safe_symbol(symbol)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Symbol namespace escapes bridge root.") from exc
    return target


def symbol_bridge_paths(
    atlas_bridge_dir: Path,
    symbol: str,
) -> tuple[Path, Path, Path]:
    root = symbol_bridge_dir(atlas_bridge_dir, symbol)
    return root / "commands.json", root / "status.json", root / "runtime.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def discover_bridge_symbols(atlas_bridge_dir: Path) -> list[dict[str, Any]]:
    atlas_bridge_dir = Path(atlas_bridge_dir)
    found: list[dict[str, Any]] = []

    if atlas_bridge_dir.exists():
        for child in atlas_bridge_dir.iterdir():
            if not child.is_dir():
                continue

            try:
                safe_symbol(child.name)
            except ValueError:
                continue

            status_file = child / "status.json"
            command_file = child / "commands.json"
            if not status_file.exists() and not command_file.exists():
                continue

            status = _read_json(status_file) or {}
            exact_symbol = str(status.get("symbol") or child.name)

            # The reported symbol must resolve to the same namespace directory.
            try:
                expected_namespace = safe_symbol(exact_symbol)
            except ValueError:
                continue
            if expected_namespace != child.name:
                continue

            try:
                mtime = status_file.stat().st_mtime
            except OSError:
                mtime = 0.0

            found.append({
                "symbol": exact_symbol,
                "namespace": child.name,
                "connected": bool(status.get("connected")),
                "status_file": str(status_file),
                "command_file": str(command_file),
                "status_mtime": mtime,
                "applied_command_version": status.get("applied_command_version"),
                "policy_epoch": status.get("policy_epoch"),
                "strategy_open_positions": status.get("strategy_open_positions"),
                "strategy_floating_pl": status.get("strategy_floating_pl"),
            })

    found.sort(
        key=lambda item: (item.get("status_mtime") or 0.0),
        reverse=True,
    )
    return found


def resolve_default_symbol(
    atlas_bridge_dir: Path,
    legacy_status_file: Path | None = None,
) -> str | None:
    symbols = discover_bridge_symbols(atlas_bridge_dir)
    if symbols:
        return str(symbols[0]["symbol"])

    if legacy_status_file is not None:
        legacy = _read_json(Path(legacy_status_file)) or {}
        if legacy.get("symbol"):
            return str(legacy["symbol"])

    return None


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


@contextmanager
def scoped_symbol_storage(symbol: str) -> Iterator[Path]:
    """
    Redirect Atlas intelligence persistence to:
        data/symbols/<SYMBOL>/

    Important:
    - shared analytical code is unchanged;
    - persisted evidence/state is symbol-specific;
    - the symbol_namespace module itself is deliberately NOT patched;
    - a stable local legacy_root is captured before any module globals change.

    This compatibility layer is process-wide, so Atlas v1.1.x must run with
    one uvicorn worker.
    """
    target_root = symbol_data_dir(symbol)
    target_root.mkdir(parents=True, exist_ok=True)

    # NEVER use mutable module globals as the comparison root while patching.
    legacy_root = (PROJECT_ROOT / "data").resolve()
    this_module_name = __name__

    patched: list[tuple[object, str, Path]] = []

    with _SCOPE_LOCK:
        # Snapshot module list before mutation.
        modules = [
            (module_name, module)
            for module_name, module in list(sys.modules.items())
            if module_name.startswith("backend.app.intelligence.")
            and module_name != this_module_name
        ]

        for module_name, module in modules:
            namespace = vars(module)
            for name, value in list(namespace.items()):
                if not isinstance(value, Path):
                    continue
                if not _is_under(value, legacy_root):
                    continue

                try:
                    relative = value.resolve().relative_to(legacy_root)
                except (ValueError, OSError):
                    continue

                replacement = (
                    target_root
                    if str(relative) == "."
                    else target_root / relative
                )
                patched.append((module, name, value))
                setattr(module, name, replacement)

        try:
            yield target_root
        finally:
            for module, name, original in reversed(patched):
                setattr(module, name, original)
