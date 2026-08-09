from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def repair(path: Path, *, expected_plan_id: str, risk_pct: float) -> Path:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Zone directive is not a JSON object.")
    if not payload.get("campaign_locked"):
        raise RuntimeError("Refusing repair: zone campaign is not locked.")
    if str(payload.get("plan_id") or "") != expected_plan_id:
        raise RuntimeError("Refusing repair: active plan identifier changed.")
    if not (0.0 < risk_pct <= 1.0):
        raise RuntimeError("Refusing repair: risk must be above 0 and at most 1%.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.stem}.{stamp}.before-risk-repair.json")
    shutil.copy2(path, backup)

    payload["account_risk_pct"] = risk_pct
    payload["campaign_risk_repaired"] = True
    payload["campaign_risk_repair_source"] = "OPERATOR_CONFIRMED_PRIOR_DASHBOARD"
    payload["campaign_risk_repaired_at_epoch"] = int(
        datetime.now(timezone.utc).timestamp()
    )

    handle, temporary_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=4)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return backup


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair one explicitly identified locked Atlas zone campaign."
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--expected-plan-id", required=True)
    parser.add_argument("--risk-pct", required=True, type=float)
    args = parser.parse_args()
    backup = repair(
        args.path,
        expected_plan_id=args.expected_plan_id,
        risk_pct=args.risk_pct,
    )
    print(f"Repaired {args.path}; backup={backup}")


if __name__ == "__main__":
    main()
