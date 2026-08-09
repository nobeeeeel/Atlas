from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


DEFAULT_MT5_FILES = Path(
    "/Users/nobel/Library/Application Support/"
    "net.metaquotes.wine.metatrader5/drive_c/Program Files/"
    "MetaTrader 5/MQL5/Files"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def safe_symbol(symbol: str) -> str:
    value = symbol.strip()
    for char in ('\\', '/', ':', '*', '?', '"', '<', '>', '|'):
        value = value.replace(char, "_")
    return value


def copy_if_exists(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        if destination.exists():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed Atlas v1.1 symbol namespaces without deleting legacy state."
    )
    parser.add_argument("--gold-symbol", default="XAUUSD")
    parser.add_argument("--mt5-files", default=str(DEFAULT_MT5_FILES))
    args = parser.parse_args()

    symbol = args.gold_symbol
    safe = safe_symbol(symbol)

    mt5_files = Path(args.mt5_files)
    legacy_bridge = mt5_files / "Atlas"
    gold_bridge = legacy_bridge / safe
    gold_bridge.mkdir(parents=True, exist_ok=True)

    copied_bridge = []
    for name in (
        "commands.json",
        "trailing_policy_epochs.csv",
        "management_policy_epochs.csv",
        "recovery_policy_epochs.csv",
        "managed_position_identity.csv",
    ):
        if copy_if_exists(legacy_bridge / name, gold_bridge / name):
            copied_bridge.append(name)

    # Only copy legacy status if it actually belongs to the chosen gold symbol.
    legacy_status = legacy_bridge / "status.json"
    if legacy_status.exists():
        try:
            status = json.loads(legacy_status.read_text(encoding="utf-8"))
        except Exception:
            status = {}
        if str(status.get("symbol") or "") == symbol:
            shutil.copy2(legacy_status, gold_bridge / "status.json")
            copied_bridge.append("status.json")

    legacy_data = PROJECT_ROOT / "data"
    gold_data = legacy_data / "symbols" / safe
    gold_data.mkdir(parents=True, exist_ok=True)

    copied_data = []
    if legacy_data.exists():
        for item in legacy_data.iterdir():
            if item.name == "symbols":
                continue
            destination = gold_data / item.name
            if copy_if_exists(item, destination):
                copied_data.append(item.name)

    print("Atlas v1.1 symbol migration complete.")
    print(f"Gold namespace: {symbol}")
    print(f"Bridge folder: {gold_bridge}")
    print(f"Copied bridge state: {copied_bridge or 'none'}")
    print(f"Gold data folder: {gold_data}")
    print(f"Copied Atlas data entries: {len(copied_data)}")
    print("Legacy files were NOT deleted.")


if __name__ == "__main__":
    main()
