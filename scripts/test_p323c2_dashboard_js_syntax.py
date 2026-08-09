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

    assert 'version="1.30.19"' in source, "Expected current Atlas dashboard version"

    match = re.search(r"function renderAnalysis\(\)\{(.*?)\n\}\n\nfunction latestAckState", source, re.S)
    assert match, "Could not isolate renderAnalysis()"
    render_analysis = match.group(1)

    declarations = re.findall(r"\b(?:const|let|var)\s+zonePlan\b", render_analysis)
    assert len(declarations) == 1, (
        f"renderAnalysis() must declare zonePlan exactly once; found {len(declarations)}"
    )

    assert "const zonePlan=state.zonePlan||{}, activePlan=zonePlan.zone_plan||null;" in render_analysis

    script_match = re.search(r"<script>(.*?)</script>", source, re.S)
    assert script_match, "Dashboard <script> block not found"

    node = shutil.which("node")
    if node:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
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

    print("P3.23C.2 dashboard JavaScript syntax regression test passed")


if __name__ == "__main__":
    main()
