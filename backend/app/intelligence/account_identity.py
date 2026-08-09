from __future__ import annotations

import hashlib
import re
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator


_ACCOUNT_FINGERPRINT: ContextVar[str | None] = ContextVar(
    "atlas_account_fingerprint", default=None
)


def account_identity(status: dict[str, Any] | None) -> dict[str, Any]:
    status = status or {}
    try:
        login = int(status.get("account_login") or 0)
    except (TypeError, ValueError):
        login = 0
    server = str(status.get("account_server") or "").strip()
    company = str(status.get("account_company") or "").strip()
    currency = str(status.get("account_currency") or "").strip()
    try:
        trade_mode = int(status.get("account_trade_mode") or 0)
    except (TypeError, ValueError):
        trade_mode = 0

    fingerprint = None
    if login > 0 and server:
        material = f"{server.casefold()}|{login}".encode("utf-8")
        fingerprint = hashlib.sha256(material).hexdigest()[:20]

    return {
        "ready": fingerprint is not None,
        "fingerprint": fingerprint,
        "login": login,
        "server": server,
        "company": company,
        "currency": currency,
        "trade_mode": trade_mode,
        "performance_scope": "CURRENT_MT5_ACCOUNT_ONLY",
    }


@contextmanager
def scoped_account_performance(status: dict[str, Any] | None) -> Iterator[dict[str, Any]]:
    identity = account_identity(status)
    token = _ACCOUNT_FINGERPRINT.set(identity.get("fingerprint"))
    try:
        yield identity
    finally:
        _ACCOUNT_FINGERPRINT.reset(token)


def current_account_fingerprint() -> str | None:
    return _ACCOUNT_FINGERPRINT.get()


def current_account_outcomes_file(symbol_outcomes_file: Path) -> Path:
    fingerprint = _ACCOUNT_FINGERPRINT.get()
    safe_key = (
        re.sub(r"[^a-zA-Z0-9._-]+", "_", fingerprint)
        if fingerprint
        else "UNIDENTIFIED_ACCOUNT"
    )
    return symbol_outcomes_file.parent / "accounts" / safe_key / "trade_outcomes.json"
