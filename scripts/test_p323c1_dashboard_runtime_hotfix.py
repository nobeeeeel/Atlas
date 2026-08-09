from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")

assert 'version="1.29.3"' in text
assert 'function renderAnalysis(){\n  const s=state.status||{}, i=state.intelligence||{}, p=state.proposal||{}, r=state.responsiveness||{};\n  const zonePlan=state.zonePlan||{};' in text
assert 'const analysisZoneAware=Boolean(zonePlan?.zone_aware_scalping_active' in text
print("P3.23C.1 dashboard runtime hotfix checks passed.")
