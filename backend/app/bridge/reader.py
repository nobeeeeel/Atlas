import json
from pathlib import Path


def read_json(path: Path):

    if not path.exists():
        return {}

    with open(path, "r") as f:
        return json.load(f)