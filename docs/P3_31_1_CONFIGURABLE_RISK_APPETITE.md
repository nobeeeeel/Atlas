# P3.31.1 — Configurable Portfolio Risk Appetite

Atlas exposes an operator-owned portfolio hard-risk ceiling on the Settings page.

- Range: 1%–20%
- Default: 1%
- Scope: selected Atlas symbol/current MT5 account
- Meaning: maximum aggregate strategy risk, not per-trade risk
- Atlas/Gemini may reduce effective operating risk but cannot raise the configured ceiling
- Scalp, zone, recovery, broker, structure, drawdown and loss-protection gates remain independent

API:

- `GET /api/v1/atlas/risk-appetite?symbol=<symbol>`
- `PUT /api/v1/atlas/risk-appetite?symbol=<symbol>` with `{ "portfolio_hard_risk_pct": 5, "actor": "Nobel" }`

The capital sizing response includes `risk_appetite`, and `maximum_total_strategy_risk_pct`/amount reflect the operator setting.
