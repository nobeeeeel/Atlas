from pathlib import Path
import re, subprocess, tempfile

ROOT=Path(__file__).resolve().parents[1]
ea=(ROOT/'external/nyao/nyao_scalper.mq5').read_text()
main=(ROOT/'backend/app/main.py').read_text()

assert 'AtlasBuildOrdinaryMarketGeometry' in ea
assert 'SYMBOL_TRADE_TICK_SIZE' in ea
assert 'SYMBOL_TRADE_STOPS_LEVEL' in ea
assert 'SYMBOL_TRADE_FREEZE_LEVEL' in ea
assert 'OrderCheck(request, check)' in ea
assert 'ORDER_PREFLIGHT_REJECTED_' in ea
assert 'LOCAL_STOP_PREFLIGHT_' in ea
assert 'currentLot = CalculateDynamicLotSize(signalScore, orderType, price, stopPrice);' in ea
assert 'No opposite-direction fallback' not in ea  # prose belongs in UI, execution flow stays single-side
assert 'SIGNAL QUALIFIED · NOT SELECTED' in main
assert 'directional arbitration' in main
assert 'it does not fall back into the opposite direction' in main
assert 'version="1.30.3"' in main

# Check embedded dashboard JS parses.
m=re.search(r'DASHBOARD_TEMPLATE\s*=\s*r?"""(.*?)"""', main, re.S)
assert m, 'dashboard template not found'
html=m.group(1)
scripts=re.findall(r'<script>(.*?)</script>', html, re.S)
assert scripts, 'dashboard script not found'
js='\n'.join(scripts).replace('__CONTROL_CONFIG__','[]')
with tempfile.NamedTemporaryFile('w',suffix='.js',delete=False) as f:
    f.write(js); path=f.name
r=subprocess.run(['node','--check',path],capture_output=True,text=True)
assert r.returncode==0, r.stderr
print('P3.27 scalp stop preflight + arbitration UI tests passed')
