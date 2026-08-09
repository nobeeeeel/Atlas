from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.intelligence.parameter_evidence import (
    _association,
    _outcome_partition_signature,
)


def _row(a: object, b: object, pl: float) -> dict:
    return {
        "entry_context": {"runtime": {"runtime_a": a, "runtime_b": b}},
        "realized_net_pl": pl,
    }


def test_confounded_cohort_is_not_available_as_parameter_evidence() -> None:
    rows = [
        _row(False, 2, -2.0),
        _row(False, 2, -1.0),
        _row(False, 2, -3.0),
        _row(True, 5, 3.0),
        _row(True, 5, 4.0),
        _row(True, 5, 5.0),
    ]
    parameter_a = {"name": "a", "status_key": "runtime_a"}
    parameter_b = {"name": "b", "status_key": "runtime_b"}
    assert _outcome_partition_signature(rows, parameter_a) == (
        _outcome_partition_signature(rows, parameter_b)
    )

    groups = {
        "False": {"value": False, "outcome_count": 3, "mean_pl": -2.0},
        "True": {"value": True, "outcome_count": 3, "mean_pl": 4.0},
    }
    association = _association(groups, confounded_with=["b"])
    assert association["available"] is False
    assert association["strength"] == "CONFOUNDED"
    assert association["raw_strength"] == "STRONG"


if __name__ == "__main__":
    test_confounded_cohort_is_not_available_as_parameter_evidence()
    print("P2.2 parameter-evidence checks passed.")
