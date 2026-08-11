from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.intelligence.policy_bootstrap import evaluate_policy_bootstrap
from backend.app.intelligence.risk_governor import assess_risk
from backend.app.intelligence.risk_appetite import get_risk_appetite
from backend.app.intelligence.risk_units import build_risk_units


SIZING_VERSION = "atlas-capital-regime-v2.2"
OPPORTUNITY_ALLOCATION_VERSION = "atlas-adaptive-opportunity-risk-v1"

DEMO_CAPITAL_SIMULATION_ENV = "ATLAS_DEMO_CAPITAL_SIMULATION"
DEMO_RISK_CAPITAL_ENV = "ATLAS_DEMO_RISK_CAPITAL"

#
# MT5 ENUM_ACCOUNT_TRADE_MODE
#
# ACCOUNT_TRADE_MODE_DEMO = 0
#
MT5_DEMO_TRADE_MODE = 0

LOSS_PROTECTION_INITIAL_MINUTES = 15
LOSS_PROTECTION_SECOND_MINUTES = 30
LOSS_PROTECTION_MAX_MINUTES = 60
RECOVERY_PROBE_SCALP_RISK_PCT = 0.05
# A recovery probe may be lifted only to the broker minimum executable volume,
# and only while that minimum remains beneath this deterministic equity-risk cap.
# This keeps micro-account probes usable on instruments such as XAUUSD without
# turning the operator portfolio ceiling into per-trade authority.
RECOVERY_PROBE_MAX_EXECUTABLE_RISK_PCT = 0.30
LOSS_PROTECTION_THRESHOLD = 4
LOSS_PROTECTION_STATE_VERSION = 5
PROJECT_ROOT = Path(__file__).resolve().parents[3]
AUTONOMOUS_EVENT_FILE = PROJECT_ROOT / "data" / "autonomous_policy_events.json"

# A runtime-confirmed autonomous policy may release only the loss timer, and only
# when it materially changes fresh-entry behavior. Deterministic drawdown/risk/
# broker/exposure gates remain authoritative.
FRESH_ENTRY_MATERIAL_CONTROLS = {
    "enable_buy_orders",
    "enable_sell_orders",
    "enable_new_bar_entry_only",
    "enable_max_spread_filter",
    "max_spread_points",
    "max_spread_atr_ratio",
    "max_open_orders",
    "max_trades_per_candle",
    "enable_duplicate_distance_filter",
    "zone_points",
    "buy_duplicate_multiplier",
    "sell_duplicate_multiplier",
    "min_buy_signal_score",
    "min_sell_signal_score",
    "enable_limit_entry",
    "limit_entry_anchor",
    "limit_entry_atr_fraction",
    "limit_entry_expiry_bars",
    "limit_entry_cancel_on_flip",
    "directional_body_lookback",
    "ema_fast_period",
    "ema_slow_period",
    "slope_lookback",
    "rsi_period",
    "atr_period",
    "atr_avg_lookback",
    "min_vol_ratio_to_trade",
    "impulse_lookback",
    "impulse_boost_weight",
    "signal_smoothing_candles",
    "current_candle_blend",
    "velocity_window",
    "rsi_overbought",
    "rsi_oversold",
    "rsi_momentum_buy",
    "rsi_momentum_sell",
    "trend_weight",
    "slope_weight",
    "momentum_base_weight",
    "momentum_trigger_weight",
    "body_momentum_weight",
    "chop_score_high",
    "chop_score_med",
    "chop_score_low",
    "volatility_score_high",
    "volatility_score_low",
    "peak_score_weight",
    "wick_rejection_weight",
    "min_body_ratio",
}


CAPITAL_REGIMES: tuple[dict[str, Any], ...] = (
    {
        "name": "MICRO",
        "minimum_capital": 0.0,
        "maximum_capital": 750.0,
        "scalp_base_risk_pct": 0.35,
        "zone_base_risk_pct": 0.50,
        "maximum_total_strategy_risk_pct": 1.00,
        "description": (
            "Small-capital growth regime. Atlas receives slightly more "
            "risk flexibility while drawdown, account-loss and deterministic "
            "risk protections remain active."
        ),
    },
    {
        "name": "GROWTH",
        "minimum_capital": 750.0,
        "maximum_capital": 1500.0,
        "scalp_base_risk_pct": 0.30,
        "zone_base_risk_pct": 0.45,
        "maximum_total_strategy_risk_pct": 0.90,
        "description": (
            "Early account-growth regime. Percentage risk begins contracting "
            "as the capital base becomes more meaningful."
        ),
    },
    {
        "name": "BUILD",
        "minimum_capital": 1500.0,
        "maximum_capital": 3000.0,
        "scalp_base_risk_pct": 0.275,
        "zone_base_risk_pct": 0.40,
        "maximum_total_strategy_risk_pct": 0.85,
        "description": (
            "Capital-building regime. Atlas increasingly prioritizes "
            "preservation while retaining measured growth capacity."
        ),
    },
    {
        "name": "STANDARD",
        "minimum_capital": 3000.0,
        "maximum_capital": 7500.0,
        "scalp_base_risk_pct": 0.25,
        "zone_base_risk_pct": 0.35,
        "maximum_total_strategy_risk_pct": 0.80,
        "description": (
            "Standard Atlas capital-preservation regime."
        ),
    },
    {
        "name": "CAPITAL",
        "minimum_capital": 7500.0,
        "maximum_capital": None,
        "scalp_base_risk_pct": 0.30,
        "zone_base_risk_pct": 0.45,
        "maximum_total_strategy_risk_pct": 1.00,
        "description": (
            "Higher-capital regime. Atlas uses a measured 0.30% scalp and "
            "0.45% zone campaign base budget while deterministic drawdown, loss "
            "protection and portfolio caps remain authoritative."
        ),
    },
)


def _f(
    data: dict[str, Any],
    key: str,
    default: float = 0.0,
) -> float:
    try:
        return float(
            data.get(
                key,
                default,
            )
            or default
        )
    except (TypeError, ValueError):
        return default


def _env_bool(
    name: str,
    default: bool = False,
) -> bool:
    raw = os.getenv(
        name
    )

    if raw is None:
        return default

    return raw.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _env_positive_float(
    name: str,
) -> float | None:
    raw = os.getenv(
        name
    )

    if raw is None:
        return None

    try:
        value = float(
            raw
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    if value <= 0:
        return None

    return value


def _closed_result(
    trade: dict[str, Any],
) -> float:
    if trade.get(
        "exact_realized_pl_available"
    ):
        return _f(
            trade,
            "realized_net_pl",
        )

    observed = str(
        trade.get(
            "observed_result_class"
        )
        or ""
    ).upper()

    if observed.startswith(
        "NEGATIVE"
    ):
        return -1.0

    if observed.startswith(
        "POSITIVE"
    ):
        return 1.0

    return 0.0


def _consecutive_losses(
    outcomes: dict[str, Any] | None,
) -> int:
    # Strategic loss protection operates on completed RISK UNITS, not tickets.
    # A recovery chain or zone campaign is one unit and remains provisional
    # while any child/leg is still active.
    report = build_risk_units(outcomes)
    return int(report.get("consecutive_completed_loss_units") or 0)


def _parse_trade_close_time(trade: dict[str, Any]) -> datetime | None:
    """Best available authoritative/observed close timestamp for protection timing."""
    close_msc = trade.get("close_time_msc")
    try:
        if close_msc not in (None, "", 0):
            return datetime.fromtimestamp(float(close_msc) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        pass
    close_epoch = trade.get("close_time_epoch")
    try:
        if close_epoch not in (None, "", 0):
            return datetime.fromtimestamp(float(close_epoch), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        pass
    for key in ("disappeared_at", "last_seen_at", "first_seen_at"):
        raw = trade.get(key)
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
    return None


def _loss_protection_state_file(outcomes: dict[str, Any] | None) -> Path | None:
    raw = str((outcomes or {}).get("file") or "").strip()
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve().with_name("capital_recovery.json")
    except (OSError, RuntimeError, ValueError):
        return None


def _read_loss_protection_state(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_loss_protection_state(path: Path | None, value: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".atlas-capital-recovery-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latest_loss_close_time(outcomes: dict[str, Any] | None) -> datetime | None:
    report = build_risk_units(outcomes)
    raw = report.get("latest_completed_loss_at")
    return _parse_iso(raw) if raw else None


def _active_recovery_probe_position(status: dict[str, Any], outcomes: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return broker-survivable recovery-probe evidence after Atlas/Nyao restart."""
    for position in list(status.get("positions") or []):
        if not isinstance(position, dict):
            continue
        if bool(position.get("recovery_probe_entry")) or str(position.get("order_origin") or "").upper() == "RECOVERY_PROBE":
            return position
    for trade in list((outcomes or {}).get("active") or []):
        if not isinstance(trade, dict):
            continue
        if bool(trade.get("recovery_probe_entry")) or str(trade.get("order_origin") or trade.get("origin_guess") or "").upper() == "RECOVERY_PROBE":
            return trade
    return None


def _active_recovery_probe_lifecycle(outcomes: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return an unresolved composite whose immutable root is a recovery probe.

    This survives the root ticket closing before a child because risk_units owns
    the composite lifecycle. It is the atomicity boundary for loss protection
    and fresh-risk admission.
    """
    report = build_risk_units(outcomes)
    for unit in list(report.get("units") or []):
        if not isinstance(unit, dict):
            continue
        if (
            str(unit.get("unit_type") or "").upper() == "RECOVERY_CHAIN"
            and str(unit.get("state") or "").upper() == "ACTIVE"
            and str(unit.get("trading_mode") or "").upper() == "RECOVERY_PROBE"
        ):
            return unit
    return None

def _active_recovery_lifecycles(outcomes: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return every unresolved recovery composite, not only RECOVERY_PROBE.

    Risk-unit lineage is the authoritative lifecycle boundary after a hedge child
    closes and the surviving live position has been graduated back to chain_id=0.
    """
    report = build_risk_units(outcomes)
    return [
        unit for unit in list(report.get("units") or [])
        if isinstance(unit, dict)
        and str(unit.get("unit_type") or "").upper() == "RECOVERY_CHAIN"
        and str(unit.get("state") or "").upper() == "ACTIVE"
    ]


def _material_fresh_entry_patch(patch: dict[str, Any]) -> dict[str, Any]:
    return {
        str(name): value
        for name, value in patch.items()
        if str(name) in FRESH_ENTRY_MATERIAL_CONTROLS
    }


def _runtime_patch_matches_status(
    status: dict[str, Any],
    patch: dict[str, Any],
) -> bool:
    """Verify material command values against Nyao's live runtime telemetry when exposed."""
    checked = 0
    for name, expected in patch.items():
        key = f"runtime_{name}"
        if key not in status:
            continue
        checked += 1
        actual = status.get(key)
        if isinstance(expected, bool):
            if bool(actual) != expected:
                return False
            continue
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            try:
                if abs(float(actual) - float(expected)) > 1e-9:
                    return False
            except (TypeError, ValueError):
                return False
            continue
        if str(actual) != str(expected):
            return False
    # Epoch/command ACK remains authoritative when a control has no published
    # runtime_* field. When fields do exist, every exposed value must match.
    return True


def _latest_runtime_confirmed_material_policy_after_protection(
    status: dict[str, Any],
    *,
    protection_anchor: datetime | None,
) -> dict[str, Any] | None:
    """Find a newer material policy applied after the current protection stage began.

    Do not compare autonomous event timestamps with MT5 DEAL_TIME epochs here. Broker
    server timestamps can use a different clock basis from Atlas UTC wall time. The
    durable protection stage timestamp is generated by Atlas itself and is therefore
    the safe causal ordering anchor for policy-release decisions.
    """
    if protection_anchor is None:
        return None
    try:
        store = json.loads(AUTONOMOUS_EVENT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    runtime_epoch = int(status.get("policy_epoch") or 0)
    runtime_command = int(status.get("applied_command_version") or 0)
    runtime_symbol = str(status.get("symbol") or "")
    runtime_account = str(status.get("account_fingerprint") or "")
    for row in reversed(list((store or {}).get("events") or [])):
        if not isinstance(row, dict) or row.get("action") != "AUTO_POLICY_APPLIED":
            continue
        event_time = _parse_iso(row.get("timestamp"))
        if event_time is None or event_time <= protection_anchor:
            continue
        event_epoch = int(row.get("policy_epoch") or 0)
        event_command = int(row.get("command_version") or 0)
        if event_epoch <= 0 or event_epoch > runtime_epoch:
            continue
        if event_command > 0 and runtime_command > 0 and event_command > runtime_command:
            continue
        event_symbol = str(row.get("symbol") or "")
        event_account = str(row.get("account_fingerprint") or "")
        # Legacy P3.28/P3.28.1 events were not symbol/account annotated. Accept
        # those only through epoch+runtime confirmation; future events are scoped.
        if event_symbol and runtime_symbol and event_symbol != runtime_symbol:
            continue
        if event_account and runtime_account and event_account != runtime_account:
            continue
        material_patch = _material_fresh_entry_patch(dict(row.get("consensus_patch") or {}))
        if not material_patch:
            continue
        if not _runtime_patch_matches_status(status, material_patch):
            continue
        return {
            "policy_epoch": event_epoch,
            "command_version": event_command,
            "applied_at": event_time.isoformat(),
            "material_controls": sorted(material_patch),
            "material_patch": material_patch,
            "runtime_confirmed": True,
        }
    return None


def _loss_protection_state(
    status: dict[str, Any],
    outcomes: dict[str, Any] | None,
    streak: int,
) -> dict[str, Any]:
    """Event-driven loss review state.

    P3.54 removes punitive 15/30/60-minute loss-streak timeouts and the automatic
    reduced-risk recovery probe. Reaching the loss threshold now creates a
    BRAIN_REVIEW_PENDING event. Fresh risk pauses only while Gemini/Atlas Brain
    reviews the new evidence. Once a successful Brain cycle returns -- whether
    it applies changes or deliberately HOLDs -- the current strategy may resume
    under the ordinary deterministic drawdown, risk-state, broker, exposure and
    recovery-chain gates.

    Legacy RECOVERY_PROBE positions/lifecycles are still restored atomically so
    an upgrade cannot orphan a live recovery unit. Legacy HARD_VETO state files
    are migrated into BRAIN_REVIEW_PENDING on first read.
    """
    state_file = _loss_protection_state_file(outcomes)
    stored = _read_loss_protection_state(state_file)
    now = datetime.now(timezone.utc)
    latest_loss_time = _latest_loss_close_time(outcomes)
    account_fingerprint = str((outcomes or {}).get("account_fingerprint") or status.get("account_fingerprint") or "")
    symbol = str(status.get("symbol") or "")
    active_probe_position = _active_recovery_probe_position(status, outcomes)
    active_probe_lifecycle = _active_recovery_probe_lifecycle(outcomes)

    def base_fields() -> dict[str, Any]:
        return {
            "version": LOSS_PROTECTION_STATE_VERSION,
            "timeout_minutes": 0,
            "elapsed_seconds": 0.0,
            "remaining_seconds": 0.0,
            "next_review_at": None,
            "recovery_probe_scalp_risk_pct": RECOVERY_PROBE_SCALP_RISK_PCT,
            "recovery_probe_max_executable_risk_pct": RECOVERY_PROBE_MAX_EXECUTABLE_RISK_PCT,
            "account_fingerprint": account_fingerprint,
            "symbol": symbol,
            "state_file": str(state_file) if state_file else None,
            "latest_loss_close_at": latest_loss_time.isoformat() if latest_loss_time else None,
        }

    def inactive(reason: str) -> dict[str, Any]:
        value = {
            **base_fields(),
            "active": False,
            "state": "INACTIVE",
            "consecutive_losses": streak,
            "triggered_at": None,
            "recovery_probe": False,
            "dwell_override_eligible": False,
            "escalation_level": 0,
            "failed_recovery_probes": 0,
            "brain_review_required": False,
            "brain_review_pending": False,
            "brain_review_requested_at": None,
            "brain_review_requested_streak": None,
            "brain_review_completed_at": None,
            "brain_reviewed_streak": 0,
            "reason": reason,
        }
        _write_loss_protection_state(state_file, value)
        return value

    if streak < LOSS_PROTECTION_THRESHOLD:
        return inactive("Loss streak is below the Brain review threshold.")

    same_scope = (
        isinstance(stored, dict)
        and (not stored.get("account_fingerprint") or str(stored.get("account_fingerprint")) == account_fingerprint)
        and (not stored.get("symbol") or str(stored.get("symbol")) == symbol)
    )

    # Never orphan a legacy recovery probe that is actually live at the broker or
    # still represented by an unresolved composite risk unit.
    if active_probe_position is not None or active_probe_lifecycle is not None:
        if not same_scope:
            stored = {}
        root_ticket = int((active_probe_position or active_probe_lifecycle or {}).get("ticket") or (active_probe_lifecycle or {}).get("root_ticket") or 0)
        stored.update({
            **base_fields(),
            "active": True,
            "state": "RECOVERY_PROBE",
            "consecutive_losses": streak,
            "recovery_probe": True,
            "recovery_probe_started_at": stored.get("recovery_probe_started_at") or now.isoformat(),
            "recovery_probe_ticket": root_ticket or stored.get("recovery_probe_ticket"),
            "streak_at_probe_start": int(stored.get("streak_at_probe_start") or streak),
            "dwell_override_eligible": False,
            "brain_review_required": False,
            "brain_review_pending": False,
            "release_reason": stored.get("release_reason") or "LEGACY_RECOVERY_PROBE_RESTORED",
        })
        _write_loss_protection_state(state_file, stored)
        return dict(stored)

    mode = str(stored.get("state") or "").upper() if same_scope else ""

    # Migration from P3.41/P3.52 timer protection: the old timeout becomes an
    # immediate Brain review request. No remaining wall-clock penalty is kept.
    if mode in {"HARD_VETO", "RECOVERY_PROBE"}:
        mode = "BRAIN_REVIEW_PENDING"
        stored = {
            **stored,
            **base_fields(),
            "version": LOSS_PROTECTION_STATE_VERSION,
            "active": True,
            "state": mode,
            "consecutive_losses": streak,
            "brain_review_required": True,
            "brain_review_pending": True,
            "brain_review_requested_at": now.isoformat(),
            "brain_review_requested_streak": streak,
            "brain_review_completed_at": None,
            "brain_reviewed_streak": int(stored.get("brain_reviewed_streak") or 0),
            "recovery_probe": False,
            "dwell_override_eligible": True,
            "release_reason": "LEGACY_TIMER_PROTECTION_MIGRATED_TO_BRAIN_REVIEW",
            "triggered_at": now.isoformat(),
        }

    reviewed_streak = int(stored.get("brain_reviewed_streak") or 0) if same_scope else 0
    requested_streak = int(stored.get("brain_review_requested_streak") or 0) if same_scope else 0

    # A new loss after the last completed Brain review is itself a new reasoning
    # event. This is deliberately event-count based, not time based.
    if not same_scope or not mode or streak > max(reviewed_streak, requested_streak):
        stored = {
            **base_fields(),
            "active": True,
            "state": "BRAIN_REVIEW_PENDING",
            "consecutive_losses": streak,
            "protection_started_at": stored.get("protection_started_at") if same_scope else now.isoformat(),
            "stage_started_at": now.isoformat(),
            "protected_policy_epoch": int(status.get("policy_epoch") or 0),
            "streak_at_activation": int(stored.get("streak_at_activation") or streak) if same_scope else streak,
            "streak_at_stage_start": streak,
            "failed_recovery_probes": int(stored.get("failed_recovery_probes") or 0) if same_scope else 0,
            "recovery_probe": False,
            "dwell_override_eligible": True,
            "brain_review_required": True,
            "brain_review_pending": True,
            "brain_review_requested_at": now.isoformat(),
            "brain_review_requested_streak": streak,
            "brain_review_completed_at": stored.get("brain_review_completed_at") if same_scope else None,
            "brain_reviewed_streak": reviewed_streak,
            "brain_review_trigger": "LOSS_STREAK_THRESHOLD" if reviewed_streak == 0 else "ADDITIONAL_COMPLETED_LOSS",
            "release_reason": None,
            "triggered_at": now.isoformat(),
        }
        mode = "BRAIN_REVIEW_PENDING"

    elif mode == "REVIEW_COMPLETE" and streak <= reviewed_streak:
        stored.update({
            **base_fields(),
            "version": LOSS_PROTECTION_STATE_VERSION,
            "active": False,
            "state": "REVIEW_COMPLETE",
            "consecutive_losses": streak,
            "recovery_probe": False,
            "dwell_override_eligible": False,
            "brain_review_required": False,
            "brain_review_pending": False,
        })

    elif mode == "BRAIN_REVIEW_PENDING":
        stored.update({
            **base_fields(),
            "version": LOSS_PROTECTION_STATE_VERSION,
            "active": True,
            "state": "BRAIN_REVIEW_PENDING",
            "consecutive_losses": streak,
            "recovery_probe": False,
            "dwell_override_eligible": True,
            "brain_review_required": True,
            "brain_review_pending": True,
        })

    _write_loss_protection_state(state_file, stored)
    return dict(stored)


def acknowledge_loss_streak_brain_review(
    status: dict[str, Any],
    outcomes: dict[str, Any] | None,
    *,
    llm_proposal_id: str | None = None,
    advisory_proposal_id: str | None = None,
    cycle_status: str | None = None,
) -> dict[str, Any]:
    """Release a pending loss-streak review after a successful Brain response.

    If another completed loss arrived after the reviewed snapshot was requested,
    the newer streak is re-armed instead of being accidentally released by stale
    reasoning.
    """
    report = build_risk_units(outcomes)
    live_streak = int(report.get("consecutive_completed_loss_units") or 0)
    state_file = _loss_protection_state_file(outcomes)
    current = _read_loss_protection_state(state_file)
    now = datetime.now(timezone.utc)
    requested_streak = int(current.get("brain_review_requested_streak") or 0)

    if str(current.get("state") or "").upper() != "BRAIN_REVIEW_PENDING":
        return {**dict(current or {}), "acknowledged": False, "ack_reason": "NO_PENDING_BRAIN_REVIEW"}

    if live_streak > requested_streak:
        current.update({
            "version": LOSS_PROTECTION_STATE_VERSION,
            "active": True,
            "state": "BRAIN_REVIEW_PENDING",
            "consecutive_losses": live_streak,
            "brain_review_required": True,
            "brain_review_pending": True,
            "brain_review_requested_at": now.isoformat(),
            "brain_review_requested_streak": live_streak,
            "brain_review_trigger": "ADDITIONAL_COMPLETED_LOSS_DURING_REVIEW",
            "last_completed_review_streak": requested_streak,
            "last_completed_review_at": now.isoformat(),
            "last_completed_review_llm_proposal_id": llm_proposal_id,
            "last_completed_review_advisory_proposal_id": advisory_proposal_id,
            "last_completed_review_cycle_status": cycle_status,
            "dwell_override_eligible": True,
            "recovery_probe": False,
        })
        _write_loss_protection_state(state_file, current)
        return {**current, "acknowledged": False, "ack_reason": "NEWER_LOSS_REARMED"}

    current.update({
        "version": LOSS_PROTECTION_STATE_VERSION,
        "active": False,
        "state": "REVIEW_COMPLETE",
        "consecutive_losses": live_streak,
        "brain_review_required": False,
        "brain_review_pending": False,
        "brain_review_completed_at": now.isoformat(),
        "brain_reviewed_streak": max(requested_streak, live_streak),
        "brain_review_llm_proposal_id": llm_proposal_id,
        "brain_review_advisory_proposal_id": advisory_proposal_id,
        "brain_review_cycle_status": cycle_status,
        "dwell_override_eligible": False,
        "recovery_probe": False,
        "release_reason": "BRAIN_REVIEW_COMPLETED",
        "remaining_seconds": 0.0,
        "timeout_minutes": 0,
        "next_review_at": None,
    })
    _write_loss_protection_state(state_file, current)
    return {**current, "acknowledged": True, "ack_reason": "BRAIN_REVIEW_COMPLETED"}



def release_loss_protection_test_probe(
    status: dict[str, Any],
    outcomes: dict[str, Any] | None,
    *,
    actor: str = "operator",
    reason: str = "Execution-path testing",
) -> dict[str, Any]:
    """Operator-only P3.54 test bypass for a pending Brain review.

    Kept under the legacy function/API name for compatibility with existing
    dashboard tooling. It no longer arms a reduced-risk recovery probe and does
    not create a timer. Production flow should let the LOSS_STREAK_REVIEW event
    complete normally.
    """
    positions = [p for p in list(status.get("positions") or []) if isinstance(p, dict)]
    if positions:
        raise ValueError("Brain-review test bypass requires the account to be flat.")
    if _active_recovery_lifecycles(outcomes):
        raise ValueError("Cannot bypass Brain review while a recovery composite is unresolved.")

    report = build_risk_units(outcomes)
    streak = int(report.get("consecutive_completed_loss_units") or 0)
    current = _loss_protection_state(status, outcomes, streak)
    if str(current.get("state") or "").upper() != "BRAIN_REVIEW_PENDING":
        raise ValueError(f"Loss review is not pending (current={current.get('state')}).")

    released = acknowledge_loss_streak_brain_review(
        status,
        outcomes,
        cycle_status="OPERATOR_TEST_BYPASS",
    )
    released.update({
        "release_reason": "OPERATOR_TEST_BRAIN_REVIEW_BYPASS",
        "release_actor": str(actor or "operator"),
        "release_note": str(reason or "Execution-path testing")[:500],
    })
    state_file = _loss_protection_state_file(outcomes)
    _write_loss_protection_state(state_file, released)
    return released


def _drawdown_multiplier(
    drawdown_pct: float,
) -> float:
    """P3.55 risk-efficiency rule.

    Ordinary drawdown is evidence for Atlas Brain, not a deterministic lot-size
    punishment. Cutting every subsequent winner after losses creates negative
    recovery convexity: large pre-drawdown losses can overpower many artificially
    tiny wins. The Risk Governor remains the hard safety authority and vetoes new
    risk at emergency drawdown (currently >=8%) or other account-danger states.
    """
    return 1.0


def _loss_multiplier(
    streak: int,
) -> float:
    return {
        0: 1.0,
        1: 0.75,
        2: 0.50,
        3: 0.25,
    }.get(
        streak,
        0.0,
    )


def _volatility_multiplier(
    ratio: float,
) -> float:
    if ratio <= 0:
        return 0.85

    if ratio < 0.55:
        return 0.70

    if ratio > 2.0:
        return 0.50

    if ratio > 1.5:
        return 0.70

    return 1.0


def _base_risk_capital(
    status: dict[str, Any],
) -> dict[str, float]:
    """
    Conservative real-account capital basis.

    Until dedicated owned-capital treatment is added for broker bonuses,
    Atlas uses the lower positive value of balance and equity.
    """

    balance = max(
        0.0,
        _f(
            status,
            "balance",
        ),
    )

    equity = max(
        0.0,
        _f(
            status,
            "equity",
            balance,
        ),
    )

    positive_values = [
        value
        for value in (
            balance,
            equity,
        )
        if value > 0
    ]

    risk_capital = (
        min(
            positive_values
        )
        if positive_values
        else 0.0
    )

    return {
        "balance": balance,
        "equity": equity,
        "risk_capital": risk_capital,
    }


def _demo_capital_simulation(
    status: dict[str, Any],
    *,
    real_risk_capital: float,
) -> dict[str, Any]:
    """
    Development-only capital simulation.

    This changes Atlas's RISK DECISION CAPITAL only.

    It does not modify:

        MT5 account balance
        MT5 account equity
        free margin
        broker margin
        broker leverage
        position P/L
        OrderCalcProfit()

    Safety rule:
        Simulation may only activate when MT5 explicitly reports
        ACCOUNT_TRADE_MODE_DEMO (0).

    If simulation is requested on anything other than an explicit demo
    account, it is rejected and the caller must veto new risk.
    """

    requested = _env_bool(
        DEMO_CAPITAL_SIMULATION_ENV,
        False,
    )

    requested_capital = (
        _env_positive_float(
            DEMO_RISK_CAPITAL_ENV
        )
    )

    trade_mode_raw = status.get(
        "account_trade_mode"
    )

    try:
        trade_mode = int(
            trade_mode_raw
        )
    except (
        TypeError,
        ValueError,
    ):
        trade_mode = None

    if not requested:
        return {
            "requested": False,
            "active": False,
            "accepted": True,
            "reason": (
                "Demo capital simulation is disabled."
            ),
            "requested_risk_capital": (
                requested_capital
            ),
            "effective_risk_capital": (
                real_risk_capital
            ),
            "account_trade_mode": (
                trade_mode
            ),
        }

    if requested_capital is None:
        return {
            "requested": True,
            "active": False,
            "accepted": False,
            "reason": (
                "Demo capital simulation was requested but "
                "ATLAS_DEMO_RISK_CAPITAL is missing or invalid."
            ),
            "requested_risk_capital": None,
            "effective_risk_capital": (
                real_risk_capital
            ),
            "account_trade_mode": (
                trade_mode
            ),
        }

    if trade_mode != MT5_DEMO_TRADE_MODE:
        return {
            "requested": True,
            "active": False,
            "accepted": False,
            "reason": (
                "Demo capital simulation is permitted only when MT5 "
                "explicitly reports ACCOUNT_TRADE_MODE_DEMO."
            ),
            "requested_risk_capital": (
                requested_capital
            ),
            "effective_risk_capital": (
                real_risk_capital
            ),
            "account_trade_mode": (
                trade_mode
            ),
        }

    return {
        "requested": True,
        "active": True,
        "accepted": True,
        "reason": (
            "Demo capital simulation is active. Atlas risk decisions use "
            "the simulated capital while MT5 broker calculations continue "
            "using the real demo account."
        ),
        "requested_risk_capital": (
            requested_capital
        ),
        "effective_risk_capital": (
            requested_capital
        ),
        "account_trade_mode": (
            trade_mode
        ),
    }


def _capital_regime(
    risk_capital: float,
) -> dict[str, Any]:
    for regime in CAPITAL_REGIMES:
        upper = regime[
            "maximum_capital"
        ]

        if (
            upper is None
            or risk_capital
            < float(
                upper
            )
        ):
            return dict(
                regime
            )

    return dict(
        CAPITAL_REGIMES[-1]
    )


def _next_capital_regime(
    current_name: str,
) -> dict[str, Any] | None:
    names = [
        str(
            regime["name"]
        )
        for regime
        in CAPITAL_REGIMES
    ]

    try:
        index = names.index(
            current_name
        )
    except ValueError:
        return None

    next_index = (
        index + 1
    )

    if next_index >= len(
        CAPITAL_REGIMES
    ):
        return None

    return dict(
        CAPITAL_REGIMES[
            next_index
        ]
    )


def _execution_equivalent_pct(
    *,
    monetary_budget: float,
    actual_equity: float,
) -> float:
    """
    Convert Atlas monetary risk into the percentage of actual MT5 equity
    Nyao must use to reproduce the same dollar risk.
    """

    if (
        monetary_budget <= 0
        or actual_equity <= 0
    ):
        return 0.0

    return (
        monetary_budget
        / actual_equity
        * 100.0
    )



def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _score_ratio(status: dict[str, Any], side: str) -> float:
    side = side.lower()
    score = max(0.0, _f(status, f"{side}_adjusted_score", _f(status, f"{side}_score")))
    threshold = max(0.0, _f(status, f"{side}_effective_threshold", _f(status, f"runtime_min_{side}_signal_score")))
    if threshold <= 0:
        return 0.0
    return score / threshold


def _signal_tier(ratio: float) -> str:
    if ratio >= 1.20:
        return "STRONG"
    if ratio >= 1.0:
        return "QUALIFIED"
    if ratio >= 0.75:
        return "NEAR_THRESHOLD"
    return "DEVELOPING"


def _adaptive_opportunity_allocation(
    status: dict[str, Any],
    *,
    risk_capital: float,
    operating_risk_amount: float,
    remaining_operating_risk_amount: float,
    regime_scalp_floor_amount: float,
    regime_zone_floor_amount: float,
    recovery_probe: bool,
) -> dict[str, Any]:
    """Allocate bounded risk from the live operating envelope to each opportunity.

    The capital-regime budgets remain conservative floors. A larger operator-owned
    portfolio envelope can therefore be used efficiently without turning the
    portfolio ceiling into per-trade risk.
    """
    if recovery_probe:
        return {
            "version": OPPORTUNITY_ALLOCATION_VERSION,
            "scalp": {
                "signal_tier": "RECOVERY_PROBE",
                "directional_score_ratio": 0.0,
                "quality_strength": 0.0,
                "operating_share_pct": 0.0,
                "regime_floor_amount": round(regime_scalp_floor_amount, 2),
                "envelope_amount": round(regime_scalp_floor_amount, 2),
                "absolute_equity_cap_pct": RECOVERY_PROBE_SCALP_RISK_PCT,
                "absolute_equity_cap_amount": round(risk_capital * RECOVERY_PROBE_SCALP_RISK_PCT / 100.0, 2),
                "pre_capacity_amount": round(regime_scalp_floor_amount, 2),
            },
            "zone": {
                "signal_tier": "DISABLED_DURING_RECOVERY_PROBE",
                "quality_strength": 0.0,
                "operating_share_pct": 0.0,
                "regime_floor_amount": 0.0,
                "envelope_amount": 0.0,
                "absolute_equity_cap_pct": 0.0,
                "absolute_equity_cap_amount": 0.0,
                "pre_capacity_amount": 0.0,
            },
        }

    buy_ratio = _score_ratio(status, "buy")
    sell_ratio = _score_ratio(status, "sell")
    scalp_ratio = max(buy_ratio, sell_ratio)
    scalp_strength = _clamp((scalp_ratio - 0.55) / 0.75, 0.0, 1.0)
    scalp_share = 0.06 + 0.04 * scalp_strength
    scalp_envelope = max(0.0, operating_risk_amount) * scalp_share
    scalp_equity_cap_pct = 2.0
    scalp_equity_cap = max(0.0, risk_capital) * scalp_equity_cap_pct / 100.0
    scalp_pre_capacity = min(
        max(regime_scalp_floor_amount, scalp_envelope),
        scalp_equity_cap,
    )

    confirmation = max(0.0, _f(status, "zone_confirmation_score"))
    confirmation_threshold = max(0.0, _f(status, "zone_confirmation_threshold"))
    directional = max(0.0, _f(status, "zone_directional_score"))
    directional_threshold = max(0.0, _f(status, "zone_minimum_directional_score"))
    confirmation_ratio = confirmation / confirmation_threshold if confirmation_threshold > 0 else 0.0
    directional_ratio = directional / directional_threshold if directional_threshold > 0 else 0.0
    zone_ratio = 0.65 * confirmation_ratio + 0.35 * directional_ratio
    zone_strength = _clamp((zone_ratio - 0.45) / 0.75, 0.0, 1.0)
    zone_share = 0.09 + 0.06 * zone_strength
    zone_envelope = max(0.0, operating_risk_amount) * zone_share
    zone_equity_cap_pct = 3.0
    zone_equity_cap = max(0.0, risk_capital) * zone_equity_cap_pct / 100.0
    zone_pre_capacity = min(
        max(regime_zone_floor_amount, zone_envelope),
        zone_equity_cap,
    )

    return {
        "version": OPPORTUNITY_ALLOCATION_VERSION,
        "scalp": {
            "signal_tier": _signal_tier(scalp_ratio),
            "directional_score_ratio": round(scalp_ratio, 4),
            "quality_strength": round(scalp_strength, 4),
            "operating_share_pct": round(scalp_share * 100.0, 4),
            "regime_floor_amount": round(regime_scalp_floor_amount, 2),
            "envelope_amount": round(scalp_envelope, 2),
            "absolute_equity_cap_pct": scalp_equity_cap_pct,
            "absolute_equity_cap_amount": round(scalp_equity_cap, 2),
            "pre_capacity_amount": round(scalp_pre_capacity, 2),
        },
        "zone": {
            "signal_tier": _signal_tier(zone_ratio),
            "confirmation_ratio": round(confirmation_ratio, 4),
            "directional_ratio": round(directional_ratio, 4),
            "quality_strength": round(zone_strength, 4),
            "operating_share_pct": round(zone_share * 100.0, 4),
            "regime_floor_amount": round(regime_zone_floor_amount, 2),
            "envelope_amount": round(zone_envelope, 2),
            "absolute_equity_cap_pct": zone_equity_cap_pct,
            "absolute_equity_cap_amount": round(zone_equity_cap, 2),
            "pre_capacity_amount": round(zone_pre_capacity, 2),
        },
        "rules": [
            "Capital-regime percentages are conservative opportunity floors, not permanent ceilings.",
            "A larger operator portfolio appetite may increase individual opportunity size only through a bounded share of the current operating envelope.",
            "Scalp opportunity risk is capped at 2% of risk capital and zone-campaign risk at 3% regardless of the aggregate portfolio ceiling.",
            "Opportunity allocation never overrides signal, execution-economics, broker, concentration, recovery, drawdown, or protection gates.",
        ],
    }



def _position_stop_risk_usd(status: dict[str, Any], position: dict[str, Any]) -> float | None:
    """Estimate remaining downside to the broker stop; None means risk is unobservable."""
    entry = _f(position, "entry_price")
    stop = _f(position, "sl")
    volume = max(0.0, _f(position, "volume"))
    if entry <= 0 or stop <= 0 or volume <= 0:
        return None

    side = str(position.get("type") or "").upper()
    if side == "BUY" and stop >= entry:
        return 0.0
    if side == "SELL" and stop <= entry:
        return 0.0

    tick_size = max(0.0, _f(status, "symbol_tick_size"))
    tick_value_loss = max(0.0, _f(status, "symbol_tick_value_loss"), _f(status, "symbol_tick_value"))
    if tick_size > 0 and tick_value_loss > 0:
        return abs(entry - stop) / tick_size * tick_value_loss * volume

    contract_size = max(0.0, _f(status, "symbol_contract_size"))
    if contract_size > 0:
        return abs(entry - stop) * contract_size * volume
    return None


def _recovery_ledger_events(outcomes: dict[str, Any] | None) -> list[dict[str, Any]]:
    raw = str((outcomes or {}).get("file") or "").strip()
    if not raw:
        return []
    path = Path(raw).parent / "recovery_risk_ledger.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    events = payload.get("events") if isinstance(payload, dict) else None
    return [item for item in (events or []) if isinstance(item, dict)]


def _active_risk_reservations(
    status: dict[str, Any],
    outcomes: dict[str, Any] | None,
    *,
    default_scalp_risk_amount: float,
    default_zone_risk_amount: float,
) -> dict[str, Any]:
    """Reserve risk by active risk unit instead of treating any exposure as a global lock."""
    positions = [item for item in (status.get("positions") or []) if isinstance(item, dict)]
    events = _recovery_ledger_events(outcomes)
    # P3.43: live chain_id is a mutable management flag and is cleared when a
    # survivor graduates. Risk-units preserve the immutable composite lifecycle,
    # so use them to map still-open members back to the correct recovery unit.
    lifecycle_chain_by_ticket: dict[int, int] = {}
    for unit in _active_recovery_lifecycles(outcomes):
        try:
            chain = int(unit.get("chain_id") or unit.get("root_ticket") or 0)
        except (TypeError, ValueError):
            chain = 0
        if chain <= 0:
            continue
        for ticket in list(unit.get("member_tickets") or []):
            try:
                lifecycle_chain_by_ticket[int(ticket)] = chain
            except (TypeError, ValueError):
                pass

    latest_recovery_by_chain: dict[int, dict[str, Any]] = {}
    for event in events:
        try:
            chain_id = int(event.get("chain_id") or 0)
        except (TypeError, ValueError):
            chain_id = 0
        if chain_id > 0:
            latest_recovery_by_chain[chain_id] = event

    rows: list[dict[str, Any]] = []
    reserved = 0.0
    unresolved_recovery_chains: list[int] = []
    chain_groups: dict[int, list[dict[str, Any]]] = {}
    zone_groups: dict[str, list[dict[str, Any]]] = {}
    standalone: list[dict[str, Any]] = []

    for position in positions:
        try:
            chain_id = int(position.get("chain_id") or 0)
        except (TypeError, ValueError):
            chain_id = 0
        if chain_id <= 0:
            try:
                chain_id = lifecycle_chain_by_ticket.get(int(position.get("ticket") or 0), 0)
            except (TypeError, ValueError):
                chain_id = 0
        zone_plan = str(position.get("zone_plan_id") or "").strip()
        if chain_id > 0:
            chain_groups.setdefault(chain_id, []).append(position)
        elif zone_plan:
            zone_groups.setdefault(zone_plan, []).append(position)
        else:
            standalone.append(position)

    for chain_id, members in chain_groups.items():
        event = latest_recovery_by_chain.get(chain_id) or {}
        ceiling = max(0.0, _f(event, "chain_budget_usd"))
        mtm = sum(_f(item, "net_pl") for item in members)
        current_loss = max(0.0, -mtm)
        if ceiling <= 0:
            unresolved_recovery_chains.append(chain_id)
            ceiling = max(current_loss, default_scalp_risk_amount)
        reserved += ceiling
        rows.append({
            "unit_id": f"recovery:{chain_id}",
            "unit_type": "RECOVERY_CHAIN",
            "member_count": len(members),
            "reserved_risk_amount": round(ceiling, 2),
            "reservation_basis": "FROZEN_CHAIN_CEILING" if event.get("chain_budget_usd") else "UNRESOLVED_CONSERVATIVE_FALLBACK",
            "current_mark_to_market": round(mtm, 2),
        })

    for plan_id, members in zone_groups.items():
        observed = [_position_stop_risk_usd(status, item) for item in members]
        observed_ready = all(value is not None for value in observed)
        known = sum(float(value or 0.0) for value in observed) if observed_ready else 0.0
        ceiling = known if observed_ready else default_zone_risk_amount
        reserved += ceiling
        rows.append({
            "unit_id": f"zone:{plan_id}",
            "unit_type": "ZONE_CAMPAIGN",
            "member_count": len(members),
            "reserved_risk_amount": round(ceiling, 2),
            "reservation_basis": "BROKER_STOP_RISK" if observed_ready else "ZONE_BUDGET_FALLBACK",
            "current_mark_to_market": round(sum(_f(item, "net_pl") for item in members), 2),
        })

    for position in standalone:
        known = _position_stop_risk_usd(status, position)
        ceiling = float(known) if known is not None else default_scalp_risk_amount
        reserved += ceiling
        rows.append({
            "unit_id": f"trade:{int(position.get('ticket') or 0)}",
            "unit_type": "STANDALONE_TRADE",
            "member_count": 1,
            "reserved_risk_amount": round(ceiling, 2),
            "reservation_basis": "BROKER_STOP_RISK" if known is not None else "SCALP_BUDGET_FALLBACK",
            "current_mark_to_market": round(_f(position, "net_pl"), 2),
        })

    working_orders = max(0, int(status.get("working_limit_orders") or 0))
    if working_orders:
        zone_mode = bool(status.get("zone_mode_active") and status.get("zone_plan_id"))
        already_reserved_zone = bool(zone_groups)
        if not (zone_mode and already_reserved_zone):
            pending = default_zone_risk_amount if zone_mode else default_scalp_risk_amount * working_orders
            reserved += pending
            rows.append({
                "unit_id": "working-orders",
                "unit_type": "WORKING_ORDER_RESERVATION",
                "member_count": working_orders,
                "reserved_risk_amount": round(pending, 2),
                "reservation_basis": "ZONE_CAMPAIGN_BUDGET" if zone_mode else "SCALP_BUDGET_PER_ORDER",
                "current_mark_to_market": 0.0,
            })

    return {
        "reserved_risk_amount": round(reserved, 2),
        "active_risk_unit_count": len(rows),
        "reservations": rows,
        "unresolved_recovery_chain_ids": unresolved_recovery_chains,
    }

def build_capital_sizing_plan(
    status: dict[str, Any],
    outcomes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    real_capital = (
        _base_risk_capital(
            status
        )
    )

    balance = real_capital[
        "balance"
    ]

    equity = real_capital[
        "equity"
    ]

    real_risk_capital = real_capital[
        "risk_capital"
    ]

    simulation = (
        _demo_capital_simulation(
            status,
            real_risk_capital=(
                real_risk_capital
            ),
        )
    )

    risk_capital = float(
        simulation[
            "effective_risk_capital"
        ]
    )

    regime = _capital_regime(
        risk_capital
    )

    regime_name = str(
        regime[
            "name"
        ]
    )

    next_regime = (
        _next_capital_regime(
            regime_name
        )
    )

    drawdown = max(
        0.0,
        _f(
            status,
            "equity_drawdown_pct",
        ),
    )

    loss_streak = (
        _consecutive_losses(
            outcomes
        )
    )
    loss_protection = _loss_protection_state(status, outcomes, loss_streak)
    policy_bootstrap = evaluate_policy_bootstrap(status, outcomes)

    risk = assess_risk(
        status
    )

    risk_state = str(
        risk.get(
            "state"
        )
        or "LOW"
    ).upper()

    # P3.55: do not double-penalize opportunity size merely because drawdown
    # contributed to a MODERATE/ELEVATED classification. The governor's actual
    # veto_new_risk flag remains authoritative for basket risk, margin, emergency
    # drawdown and stressed recovery conditions. Non-veto risk states therefore
    # keep full opportunity sizing; volatility/capacity still constrain independently.
    risk_multiplier = {
        "LOW": 1.0,
        "MODERATE": 1.0,
        "ELEVATED": 1.0,
        "HIGH": 0.0,
        "CRITICAL": 0.0,
    }.get(
        risk_state,
        1.0,
    )

    exposure_count = (
        int(status.get("strategy_open_positions") or 0)
        + int(status.get("working_limit_orders") or 0)
    )

    continuing_zone_campaign = bool(
        status.get("zone_mode_active")
        and status.get("zone_plan_id")
        and exposure_count > 0
    )

    modifiers = {
        "drawdown": _drawdown_multiplier(drawdown),
        # Loss streaks are reasoning events, not automatic size decay. Drawdown,
        # volatility and deterministic risk state still contract risk normally.
        # Fresh risk pauses only while the Brain review itself is outstanding.
        "loss_streak": (
            0.0 if loss_protection["state"] == "BRAIN_REVIEW_PENDING" else 1.0
        ),
        "risk_state": risk_multiplier,
        "volatility": _volatility_multiplier(_f(status, "volatility_ratio")),
    }

    combined = min(modifiers.values())

    veto_reasons = list(risk.get("veto_reasons") or [])

    if not simulation["accepted"]:
        veto_reasons.append(str(simulation["reason"]))

    if risk_capital <= 0:
        veto_reasons.append("Usable account risk capital is unavailable.")

    if loss_protection["state"] == "BRAIN_REVIEW_PENDING":
        veto_reasons.append(
            "Loss-streak Brain review is pending; fresh risk resumes immediately "
            "after Gemini returns a successful reviewed cycle, with or without policy changes."
        )

    if bool(policy_bootstrap.get("fresh_trading_pause_required")):
        veto_reasons.append(
            "Initial Nyao seed policy has not yet been Gemini+Critic qualified for this new account/symbol. "
            "Fresh autonomous risk remains paused only until the one-time live-market baseline qualification completes."
        )

    # A recovery probe is deliberately a single experimental risk unit. Once it
    # is in flight, concurrent fresh risk would invalidate the probe evidence.
    recovery_probe_in_flight = bool(
        loss_protection["state"] == "RECOVERY_PROBE"
        and int(status.get("strategy_open_positions") or 0) > 0
    )
    if recovery_probe_in_flight:
        veto_reasons.append(
            "Recovery probe is in flight; independent fresh risk waits for the composite probe result."
        )

    active_probe_lifecycle = _active_recovery_probe_lifecycle(outcomes)
    if active_probe_lifecycle is not None:
        veto_reasons.append(
            "Immutable recovery-probe lifecycle is unresolved; independent FRESH_MARKET and zone risk are locked until the composite unit is flat."
        )

    active_recovery_lifecycles = _active_recovery_lifecycles(outcomes)
    if active_recovery_lifecycles and active_probe_lifecycle is None:
        veto_reasons.append(
            "Recovery lifecycle is unresolved; independent FRESH_MARKET and zone risk are locked until the composite recovery unit is flat."
        )

    scalp_base = float(regime["scalp_base_risk_pct"])
    zone_base = float(regime["zone_base_risk_pct"])
    risk_appetite = get_risk_appetite()
    max_total_base = float(risk_appetite["portfolio_hard_risk_pct"])

    # Raw per-opportunity budgets before concurrent portfolio reservations.
    if loss_protection["state"] == "RECOVERY_PROBE":
        raw_scalp_capital_pct = min(
            RECOVERY_PROBE_SCALP_RISK_PCT,
            scalp_base * min(value for key, value in modifiers.items() if key != "loss_streak"),
        )
        raw_zone_capital_pct = 0.0
    else:
        raw_scalp_capital_pct = scalp_base * combined
        raw_zone_capital_pct = zone_base * combined

    raw_scalp_risk_amount = risk_capital * raw_scalp_capital_pct / 100.0
    raw_zone_risk_amount = risk_capital * raw_zone_capital_pct / 100.0
    max_total_risk_amount = risk_capital * max_total_base / 100.0

    # The operating envelope contracts with current risk/drawdown/volatility,
    # while maximum_total remains the absolute outer ceiling. Opportunity
    # authority is computed before reservations so an unobservable active stop
    # can conservatively fall back to the same adaptive budget that could have
    # admitted that position.
    operating_total_risk_amount = max_total_risk_amount * combined
    opportunity_allocation = _adaptive_opportunity_allocation(
        status,
        risk_capital=risk_capital,
        operating_risk_amount=operating_total_risk_amount,
        remaining_operating_risk_amount=operating_total_risk_amount,
        regime_scalp_floor_amount=raw_scalp_risk_amount,
        regime_zone_floor_amount=raw_zone_risk_amount,
        recovery_probe=loss_protection["state"] == "RECOVERY_PROBE",
    )
    adaptive_scalp_amount = max(0.0, _f(opportunity_allocation.get("scalp") or {}, "pre_capacity_amount"))
    adaptive_zone_amount = max(0.0, _f(opportunity_allocation.get("zone") or {}, "pre_capacity_amount"))

    reservations = _active_risk_reservations(
        status,
        outcomes,
        default_scalp_risk_amount=adaptive_scalp_amount,
        default_zone_risk_amount=adaptive_zone_amount,
    )
    reserved_risk_amount = float(reservations["reserved_risk_amount"])
    remaining_operating_risk_amount = max(0.0, operating_total_risk_amount - reserved_risk_amount)
    remaining_hard_risk_amount = max(0.0, max_total_risk_amount - reserved_risk_amount)

    unresolved_recovery = list(reservations.get("unresolved_recovery_chain_ids") or [])
    if unresolved_recovery:
        veto_reasons.append(
            "Active recovery chain risk authority is unresolved; no independent fresh risk is permitted until adoption completes."
        )

    hard_veto = bool(veto_reasons) or combined <= 0

    if hard_veto:
        scalp_risk_amount = 0.0
        zone_risk_amount = 0.0
    else:
        scalp_risk_amount = min(adaptive_scalp_amount, remaining_operating_risk_amount)
        zone_risk_amount = min(adaptive_zone_amount, remaining_operating_risk_amount)

    scalp_capital_pct = (scalp_risk_amount / risk_capital * 100.0) if risk_capital > 0 else 0.0
    zone_capital_pct = (zone_risk_amount / risk_capital * 100.0) if risk_capital > 0 else 0.0

    capacity_exhausted = bool(
        not hard_veto
        and remaining_operating_risk_amount <= 1e-9
    )
    veto = bool(hard_veto or capacity_exhausted)
    if capacity_exhausted:
        veto_reasons.append("Portfolio operating risk capacity is fully allocated.")

    execution_scalp_pct = (
        _execution_equivalent_pct(
            monetary_budget=(
                scalp_risk_amount
            ),
            actual_equity=equity,
        )
    )

    execution_zone_pct = (
        _execution_equivalent_pct(
            monetary_budget=(
                zone_risk_amount
            ),
            actual_equity=equity,
        )
    )

    execution_max_total_pct = (
        _execution_equivalent_pct(
            monetary_budget=(
                max_total_risk_amount
            ),
            actual_equity=equity,
        )
    )

    next_threshold = (
        float(
            next_regime[
                "minimum_capital"
            ]
        )
        if next_regime
        else None
    )

    amount_to_next_regime = (
        max(
            0.0,
            next_threshold
            - risk_capital,
        )
        if next_threshold
        is not None
        else None
    )

    capacity_limited = bool(
        scalp_risk_amount + 1e-9 < adaptive_scalp_amount
        or zone_risk_amount + 1e-9 < adaptive_zone_amount
    )
    decision = (
        "VETO" if veto else (
            "RECOVERY_PROBE" if loss_protection["state"] == "RECOVERY_PROBE"
            else ("REDUCE" if combined < 1.0 or capacity_limited else "ALLOW")
        )
    )

    risk_capital_method = (
        "DEMO_SIMULATED_RISK_CAPITAL"
        if simulation[
            "active"
        ]
        else (
            "MIN_POSITIVE_BALANCE_OR_EQUITY"
        )
    )

    risk_units = build_risk_units(outcomes)

    return {
        "version": (
            SIZING_VERSION
        ),

        "risk_units": {
            "version": risk_units.get("version"),
            "completed_unit_count": risk_units.get("completed_unit_count"),
            "active_unit_count": risk_units.get("active_unit_count"),
            "consecutive_completed_loss_units": risk_units.get("consecutive_completed_loss_units"),
            "active_composite_units": [
                unit for unit in (risk_units.get("units") or [])
                if unit.get("state") == "ACTIVE" and unit.get("unit_type") != "STANDALONE_TRADE"
            ],
        },

        "authority": (
            "ATLAS_CAPITAL_REGIME_ENGINE"
        ),

        "decision": (
            decision
        ),

        "balance": round(
            balance,
            2,
        ),

        "equity": round(
            equity,
            2,
        ),

        "real_risk_capital": round(
            real_risk_capital,
            2,
        ),

        "risk_capital": round(
            risk_capital,
            2,
        ),

        "risk_capital_method": (
            risk_capital_method
        ),

        #
        # P3.22 demo simulation observability.
        #
        "demo_capital_simulation": {
            "requested": bool(
                simulation[
                    "requested"
                ]
            ),

            "active": bool(
                simulation[
                    "active"
                ]
            ),

            "accepted": bool(
                simulation[
                    "accepted"
                ]
            ),

            "requested_risk_capital": (
                simulation[
                    "requested_risk_capital"
                ]
            ),

            "effective_risk_capital": round(
                float(
                    simulation[
                        "effective_risk_capital"
                    ]
                ),
                2,
            ),

            "account_trade_mode": (
                simulation[
                    "account_trade_mode"
                ]
            ),

            "reason": (
                simulation[
                    "reason"
                ]
            ),
        },

        "capital_regime": (
            regime_name
        ),

        "capital_regime_description": (
            regime[
                "description"
            ]
        ),

        "capital_regime_minimum": (
            regime[
                "minimum_capital"
            ]
        ),

        "capital_regime_maximum": (
            regime[
                "maximum_capital"
            ]
        ),

        "next_capital_regime": (
            next_regime[
                "name"
            ]
            if next_regime
            else None
        ),

        "next_capital_regime_threshold": (
            next_threshold
        ),

        "amount_to_next_capital_regime": (
            round(
                amount_to_next_regime,
                2,
            )
            if amount_to_next_regime
            is not None
            else None
        ),

        "drawdown_pct": round(
            drawdown,
            4,
        ),

        "current_account_closed_trades": int(
            (outcomes or {}).get(
                "closed_count"
            )
            or 0
        ),

        "consecutive_losses": (
            loss_streak
        ),
        "loss_protection": loss_protection,
        "policy_bootstrap": policy_bootstrap,

        "risk_state": (
            risk_state
        ),

        "risk_appetite": risk_appetite,

        "base_risk_pct": {
            "scalp": round(
                scalp_base,
                4,
            ),

            "zone": round(
                zone_base,
                4,
            ),

            "maximum_total": round(
                max_total_base,
                4,
            ),
        },

        "capital_basis_scalp_risk_pct": round(
            scalp_capital_pct,
            6,
        ),

        "capital_basis_zone_risk_pct": round(
            zone_capital_pct,
            6,
        ),

        "capital_basis_maximum_total_risk_pct": round(
            max_total_base,
            6,
        ),

        #
        # These are percentages of REAL MT5 EQUITY.
        #
        "approved_scalp_risk_pct": round(
            execution_scalp_pct,
            6,
        ),

        "approved_zone_risk_pct": round(
            execution_zone_pct,
            6,
        ),

        "maximum_total_strategy_risk_pct": round(
            execution_max_total_pct,
            6,
        ),

        "execution_scalp_risk_pct_of_equity": round(
            execution_scalp_pct,
            6,
        ),

        "execution_zone_risk_pct_of_equity": round(
            execution_zone_pct,
            6,
        ),

        "execution_maximum_total_risk_pct_of_equity": round(
            execution_max_total_pct,
            6,
        ),

        "approved_scalp_risk_amount": round(
            scalp_risk_amount,
            2,
        ),

        "recovery_probe_active": loss_protection["state"] == "RECOVERY_PROBE",
        "recovery_probe_target_risk_pct": RECOVERY_PROBE_SCALP_RISK_PCT,
        "recovery_probe_max_executable_risk_pct": RECOVERY_PROBE_MAX_EXECUTABLE_RISK_PCT,

        "approved_zone_risk_amount": round(
            zone_risk_amount,
            2,
        ),

        "maximum_total_strategy_risk_amount": round(
            max_total_risk_amount,
            2,
        ),

        "portfolio_allocation": {
            "version": "atlas-concurrent-risk-allocation-v1",
            "portfolio_hard_ceiling_amount": round(max_total_risk_amount, 2),
            "operating_risk_ceiling_amount": round(operating_total_risk_amount, 2),
            "reserved_active_risk_amount": round(reserved_risk_amount, 2),
            "remaining_operating_risk_amount": round(remaining_operating_risk_amount, 2),
            "remaining_hard_risk_amount": round(remaining_hard_risk_amount, 2),
            "active_risk_unit_count": int(reservations.get("active_risk_unit_count") or 0),
            "capacity_limited": capacity_limited,
            "allocation_state": (
                "HARD_VETO" if hard_veto
                else "FULLY_ALLOCATED" if capacity_exhausted
                else "PARTIALLY_ALLOCATED" if reserved_risk_amount > 0
                else "AVAILABLE"
            ),
            "reservations": list(reservations.get("reservations") or []),
            "unresolved_recovery_chain_ids": unresolved_recovery,
            "concentration_policy": (
                "Same-symbol active risk receives no diversification credit; every active "
                "risk unit reserves its full deterministic ceiling before new risk is allocated."
            ),
        },

        "raw_candidate_risk": {
            "scalp_amount": round(raw_scalp_risk_amount, 2),
            "zone_amount": round(raw_zone_risk_amount, 2),
            "scalp_pct_of_risk_capital": round(raw_scalp_capital_pct, 6),
            "zone_pct_of_risk_capital": round(raw_zone_capital_pct, 6),
        },

        "opportunity_allocation": opportunity_allocation,

        "risk_efficiency": {
            "version": "atlas-drawdown-risk-efficiency-v1",
            "mode": "EVENT_DRIVEN_NO_SIZE_DECAY",
            "drawdown_pct": round(drawdown, 6),
            "ordinary_drawdown_size_multiplier": 1.0,
            "loss_streak_size_multiplier": 1.0 if loss_protection["state"] != "BRAIN_REVIEW_PENDING" else 0.0,
            "emergency_drawdown_veto_pct": 8.0,
            "brain_review_band": (
                "EMERGENCY" if drawdown >= 8.0
                else "ELEVATED" if drawdown >= 5.0
                else "REVIEW" if drawdown >= 3.0
                else "NORMAL"
            ),
            "principle": (
                "Ordinary drawdown informs Brain reasoning but does not automatically shrink the next opportunity. "
                "Only genuine deterministic safety vetoes can stop fresh risk."
            ),
        },

        "modifiers": {
            key: round(
                value,
                4,
            )
            for key, value
            in modifiers.items()
        },

        "combined_multiplier": round(
            combined,
            4,
        ),

        "veto_new_risk": (
            veto
        ),

        "continuing_zone_campaign": (
            continuing_zone_campaign
        ),

        "veto_reasons": (
            veto_reasons
        ),

        "execution_gate_snapshot": {
            "scalp_spread_within_limit": bool(
                status.get(
                    "spread_within_limit",
                    True,
                )
            ),

            "zone_spread_within_limit": bool(
                status.get(
                    "zone_spread_within_limit",
                    True,
                )
            ),

            "note": (
                "Spread gates are strategy execution constraints and do "
                "not alter the Capital Regime Engine's monetary risk budget."
            ),
        },

        "broker_minimum_preflight": {
            "implemented": True,

            "status": (
                "P3_21_BROKER_FEASIBILITY_AVAILABLE"
            ),

            "note": (
                "Atlas performs broker minimum-volume preflight. "
                "Nyao OrderCalcProfit remains final execution authority."
            ),
        },

        "rules": [
            (
                "Capital regime changes the maximum permitted risk envelope "
                "according to conservative usable account capital."
            ),
            (
                "Demo capital simulation is permitted only on an account "
                "explicitly identified by MT5 as a demo account."
            ),
            (
                "Demo simulation changes Atlas risk-decision capital only; "
                "it never changes real MT5 equity, margin or broker P/L."
            ),
            (
                "Smaller capital may receive a somewhat larger percentage "
                "risk allowance, but losses and drawdown can only reduce "
                "or veto risk."
            ),
            (
                "Atlas computes monetary risk from its deterministic "
                "risk-capital basis."
            ),
            (
                "Atlas converts monetary risk into an equivalent percentage "
                "of live MT5 equity before sending sizing authority to Nyao."
            ),
            (
                "Scalp and zone spread gates are separate execution controls "
                "and are not owned by the Capital Regime Engine."
            ),
            (
                "High leverage affects margin feasibility but does not "
                "increase Atlas's permitted monetary loss."
            ),
            (
                "Nyao remains the final broker-volume calculator using "
                "actual entry, stop and OrderCalcProfit."
            ),
            (
                "Existing exposure reserves risk capacity but does not automatically veto "
                "independent new opportunities while deterministic portfolio capacity remains."
            ),
            (
                "Recovery chains reserve their frozen chain ceiling; new recovery legs remain "
                "inside that same chain ceiling and cannot borrow unallocated portfolio capacity."
            ),
            (
                "Same-symbol concurrent units receive no diversification credit, preventing "
                "Atlas from double-counting risk while still allowing efficient concurrency."
            ),
            (
                "Gemini may reason about capital conditions but cannot "
                "override this deterministic risk envelope."
            ),
        ],
    }
