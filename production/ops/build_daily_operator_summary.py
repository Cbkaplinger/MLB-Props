"""Build one-page daily operator summary from KPI, calibration, gate, and PnL artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
ODDS_DIR = ROOT / "artifacts" / "odds_log"
SUMMARY_JSON = ODDS_DIR / "daily_operator_summary.json"
SUMMARY_CSV = ODDS_DIR / "daily_operator_summary_latest.csv"

SCORECARD_PATH = ODDS_DIR / "model_health_scorecard_daily.parquet"
DECOMP_DAILY_PATH = ODDS_DIR / "k_error_decomposition_daily.parquet"
GATE_PATH = ODDS_DIR / "gate_next_n_comparison.parquet"
LEDGER_PATH = ODDS_DIR / "ledger.parquet"
VALIDATION_PATH = ODDS_DIR / "validation_ops_daily.json"
CHECKLIST_PATH = ODDS_DIR / "go_no_go_checklist_daily.json"
REPLAY_PATH = ODDS_DIR / "policy_replay_daily.json"


def _latest_row(path: Path, sort_col: str) -> dict[str, object]:
    if not path.exists():
        return {}
    df = pl.read_parquet(path)
    if df.is_empty() or sort_col not in df.columns:
        return {}
    return df.sort(sort_col).tail(1).to_dicts()[0]


def _ledger_snapshot() -> dict[str, object]:
    if not LEDGER_PATH.exists():
        return {}
    led = pl.read_parquet(LEDGER_PATH)
    if led.is_empty():
        return {}
    settled = led.filter(
        (pl.col("status") == "settled")
        & (pl.col("stake").cast(pl.Float64).fill_null(0.0) > 0.0)
    ).with_columns(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gdate"))
    if settled.is_empty():
        return {}
    latest_date = settled.select(pl.col("gdate").max()).item()
    latest_day = settled.filter(pl.col("gdate") == latest_date)
    over = latest_day.filter(pl.col("side") == "over")
    under = latest_day.filter(pl.col("side") == "under")
    return {
        "latest_settled_date": latest_date,
        "daily_n_bets": int(latest_day.height),
        "daily_stake": float(latest_day["stake"].cast(pl.Float64).sum()),
        "daily_pnl": float(latest_day["pnl"].cast(pl.Float64).sum()),
        "daily_roi": (
            float(latest_day["pnl"].cast(pl.Float64).sum())
            / float(latest_day["stake"].cast(pl.Float64).sum())
            if float(latest_day["stake"].cast(pl.Float64).sum()) > 0
            else None
        ),
        "daily_over_roi": (
            float(over["pnl"].cast(pl.Float64).sum()) / float(over["stake"].cast(pl.Float64).sum())
            if over.height and float(over["stake"].cast(pl.Float64).sum()) > 0
            else None
        ),
        "daily_under_roi": (
            float(under["pnl"].cast(pl.Float64).sum()) / float(under["stake"].cast(pl.Float64).sum())
            if under.height and float(under["stake"].cast(pl.Float64).sum()) > 0
            else None
        ),
    }


def main() -> None:
    score = _latest_row(SCORECARD_PATH, "snapshot_utc")
    decomp = _latest_row(DECOMP_DAILY_PATH, "snapshot_utc")
    gate = _latest_row(GATE_PATH, "snapshot_utc")
    ledger = _ledger_snapshot()
    validation = {}
    if VALIDATION_PATH.exists():
        try:
            validation = json.loads(VALIDATION_PATH.read_text(encoding="utf-8"))
        except Exception:
            validation = {}
    checklist = {}
    if CHECKLIST_PATH.exists():
        try:
            checklist = json.loads(CHECKLIST_PATH.read_text(encoding="utf-8"))
        except Exception:
            checklist = {}
    replay = {}
    if REPLAY_PATH.exists():
        try:
            replay = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
        except Exception:
            replay = {}
    replay_flat = None
    for scen in replay.get("scenarios", []):
        if isinstance(scen, dict) and scen.get("scenario") == "current_policy_flat_1u":
            replay_flat = scen
            break

    row = {
        "snapshot_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_warn": score.get("n_warn"),
        "mae_err_k_rate": score.get("mae_err_k_rate"),
        "under_bias_tbf": score.get("under_bias_tbf"),
        "worst_matchup_tier_mae_err_k_rate": score.get("worst_matchup_tier_mae_err_k_rate"),
        "daily_mae_err_k_rate": decomp.get("mae_err_k_rate"),
        "daily_bias_tbf_under": decomp.get("bias_tbf_under"),
        "gate_pnl_delta": gate.get("gate_pnl_delta"),
        "gate_actual_roi": gate.get("actual_roi"),
        "gate_baseline_roi": gate.get("baseline_roi"),
        "benchmark_primary": validation.get("primary_benchmark"),
        "benchmark_secondary": validation.get("secondary_benchmark"),
        "promotion_ci_gate_pass": validation.get("promotion_ci_gate_pass"),
        "profit_lock_auto_downgrade": validation.get("profit_lock_auto_downgrade"),
        "dq_alerts": ",".join(validation.get("data_quality", {}).get("alerts", []))
        if isinstance(validation.get("data_quality", {}), dict)
        else None,
        "go_no_go_status": checklist.get("status"),
        "go_no_go_failed_gates": checklist.get("n_failed_gates"),
        "go_no_go_failed_critical": checklist.get("n_failed_critical_gates"),
        "go_no_go_failed_advisory": checklist.get("n_failed_advisory_gates"),
        "replay_current_policy_n": replay_flat.get("n")
        if isinstance(replay_flat, dict)
        else None,
        "replay_current_policy_roi": replay_flat.get("roi")
        if isinstance(replay_flat, dict)
        else None,
        "replay_current_policy_roi_ci_lo": replay_flat.get("roi_ci_lo")
        if isinstance(replay_flat, dict)
        else None,
        "replay_current_policy_clv_ci_lo": replay_flat.get("clv_ci_lo")
        if isinstance(replay_flat, dict)
        else None,
        "replay_current_policy_geo_growth_log_mean": replay_flat.get("geo_growth_log_mean")
        if isinstance(replay_flat, dict)
        else None,
        "replay_current_policy_mc_prob_bankroll_floor_breach": replay_flat.get("mc_prob_bankroll_floor_breach")
        if isinstance(replay_flat, dict)
        else None,
        "replay_current_policy_mc_prob_drawdown_breach": replay_flat.get("mc_prob_drawdown_breach")
        if isinstance(replay_flat, dict)
        else None,
        **ledger,
    }

    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(row, indent=2), encoding="utf-8")
    pl.DataFrame([row]).write_csv(SUMMARY_CSV)

    print(f"wrote {SUMMARY_JSON}")
    print(f"wrote {SUMMARY_CSV}")


if __name__ == "__main__":
    main()
