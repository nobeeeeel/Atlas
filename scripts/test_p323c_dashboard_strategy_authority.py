from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")

required = [
    "ZONE-AWARE SCALP",
    "Execution authority",
    "Gemini scalp policy",
    "capital-risk-base",
    "SCALP + ZONE CONTEXT",
    "ZONE-CONTEXT BLOCKED",
    "Gemini receives this as read-only scalp context",
]
for item in required:
    assert item in text, item

assert 'version="1.29.3"' in text
assert 'const zoneModeLive=Boolean(s.zone_mode_active&&!analysisZoneAware);' in text
print("P3.23C dashboard strategy-authority checks passed.")
