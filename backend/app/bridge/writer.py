from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def write_json(model: BaseModel | dict[str, Any], path: Path) -> None:
    """Atomically publish a JSON bridge payload."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    value = model.model_dump(mode="json") if isinstance(model, BaseModel) else model
    descriptor, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=4, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
