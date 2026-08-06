import json
from pathlib import Path
from pydantic import BaseModel


def write_json(model: BaseModel, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(
            model.model_dump(mode="json"),
            f,
            indent=4,
            default=str,
        )