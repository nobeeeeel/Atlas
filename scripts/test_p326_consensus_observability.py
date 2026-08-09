from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN = PROJECT_ROOT / "backend" / "app" / "main.py"


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")

    assert 'version="1.30.2"' in source, "Expected Atlas 1.30.2"
    assert 'id="consensus-card"' in source
    assert 'id="consensus-controls"' in source
    assert 'id="consensus-observations"' in source
    assert 'id="consensus-qualified"' in source
    assert 'id="consensus-threshold"' in source
    assert 'id="consensus-epoch"' in source
    assert "function renderAutonomousConsensus()" in source
    assert "renderLlmCycle();renderAutonomousConsensus();renderResponsiveness()" in source

    # Per-control observability must expose current value, consensus value,
    # support count/ratio, current gate requirement, and readiness.
    for needle in [
        "row.baseline",
        "row.selected",
        "row.support_count",
        "row.support_ratio",
        "requiredNow",
        'trulyReady?"QUALIFIED"',
        "consensus-meter",
    ]:
        assert needle in source, f"Missing consensus observability element: {needle}"

    # Do not revert to latest-proposal-wins language in the operator UI.
    assert "the latest proposal never wins by itself" in source

    script_match = re.search(r"<script>(.*?)</script>", source, re.S)
    assert script_match, "Dashboard <script> block not found"

    node = shutil.which("node")
    if node:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".js", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(script_match.group(1))
            temp_path = Path(handle.name)
        try:
            result = subprocess.run(
                [node, "--check", str(temp_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, result.stderr or result.stdout
        finally:
            temp_path.unlink(missing_ok=True)

    print("P3.26 autonomous consensus observability tests passed")


if __name__ == "__main__":
    main()
