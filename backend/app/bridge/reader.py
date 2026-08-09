from __future__ import annotations

import copy
import json
import threading
import time
from pathlib import Path
from typing import Any


_CACHE_LOCK = threading.RLock()
_LAST_KNOWN_GOOD: dict[str, Any] = {}


def read_json(path: Path, *, attempts: int = 4, retry_delay: float = 0.01) -> Any:
    """Read a bridge JSON file without exposing a producer's partial write.

    MT5 and Atlas are separate processes, so a reader can occasionally observe
    an empty or half-written file. Valid payloads are cached per path and used
    only after short retries are exhausted. Callers receive copies so cached
    state cannot be mutated accidentally.
    """
    path = Path(path)
    key = str(path.resolve(strict=False))
    if not path.exists():
        with _CACHE_LOCK:
            _LAST_KNOWN_GOOD.pop(key, None)
        return {}

    for attempt in range(max(1, attempts)):
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
            with _CACHE_LOCK:
                _LAST_KNOWN_GOOD[key] = copy.deepcopy(value)
            return value
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            if attempt + 1 < max(1, attempts):
                time.sleep(max(0.0, retry_delay))

    with _CACHE_LOCK:
        return copy.deepcopy(_LAST_KNOWN_GOOD.get(key, {}))
