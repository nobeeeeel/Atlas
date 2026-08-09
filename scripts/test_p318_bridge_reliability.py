from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from pydantic import BaseModel


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.bridge.reader import read_json  # noqa: E402
from backend.app.bridge.writer import write_json  # noqa: E402


class Payload(BaseModel):
    sequence: int
    state: str


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "bridge.json"
        write_json(Payload(sequence=1, state="READY"), path)
        assert read_json(path) == {"sequence": 1, "state": "READY"}

        # Simulate the brief empty-file window produced by a non-atomic peer.
        path.write_text("", encoding="utf-8")
        assert read_json(path, attempts=2, retry_delay=0) == {
            "sequence": 1,
            "state": "READY",
        }

        path.write_text(json.dumps({"sequence": 2, "state": "APPLIED"}), encoding="utf-8")
        assert read_json(path) == {"sequence": 2, "state": "APPLIED"}
        assert not list(path.parent.glob(".bridge.json.*.tmp"))

    print("P3.18 bridge reliability checks passed.")


if __name__ == "__main__":
    main()
