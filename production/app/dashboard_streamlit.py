"""Streamlit operator dashboard for daily MLB props decisions.

Run:
  streamlit run production/app/dashboard_streamlit.py
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any
from datetime import datetime, timedelta

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import seaborn as sns
import polars as pl
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
ODDS_DIR = ROOT / "artifacts" / "odds_log"
PROJ_DIR = ROOT / "artifacts" / "projection_log"
MODELS_DIR = ROOT / "artifacts" / "models"

PATHS = {
    "daily_summary": ODDS_DIR / "daily_operator_summary.json",
    "kpi_loop": ODDS_DIR / "daily_kpi_loop_last_run.json",
    "cal_snapshot": ODDS_DIR / "calibration_snapshot_latest.json",
    "cal_history": ODDS_DIR / "calibration_snapshot_history.parquet",
    "scorecard_daily": ODDS_DIR / "model_health_scorecard_daily.parquet",
    "decomp_daily": ODDS_DIR / "k_error_decomposition_daily.parquet",
    "policy_sweep": ODDS_DIR / "policy_scenario_sweep.parquet",
    "policy_profile": ODDS_DIR / "policy_side_profile_scan.parquet",
    "decision_scoreboard": ODDS_DIR / "decision_scoreboard_daily.parquet",
    "validation_ops": ODDS_DIR / "validation_ops_daily.json",
    "go_no_go": ODDS_DIR / "go_no_go_checklist_daily.json",
    "policy_replay": ODDS_DIR / "policy_replay_daily.json",
    "ledger": ODDS_DIR / "ledger.parquet",
    "graded": PROJ_DIR / "graded.parquet",
    "recommendations": ODDS_DIR / "recommendations.parquet",
    "calibration_pointer": MODELS_DIR / "prob_calibration_production.json",
    "kpi_policy": ROOT / "production" / "ops" / "kpi_policy.json",
    "runtime_snapshot": ODDS_DIR / "runtime_monitoring_snapshot.json",
    "runtime_floor_calibration": ODDS_DIR / "runtime_floor_calibration.csv",
    "runtime_slippage": ODDS_DIR / "runtime_slippage_by_segment.csv",
    "runtime_regime_monthly": ODDS_DIR / "runtime_regime_monthly.csv",
    "runtime_edge_deciles": ODDS_DIR / "runtime_edge_deciles.csv",
    "runtime_decision_diag": ODDS_DIR / "runtime_decision_diagnostics.csv",
    "runtime_ops_slo": ODDS_DIR / "runtime_ops_slo_snapshot.json",
    "morning_alert": ODDS_DIR / "morning_alert_latest.json",
    "aux_shadow_summary_csv": ODDS_DIR / "aux_market_shadow_summary.csv",
    "aux_shadow_summary_json": ODDS_DIR / "aux_market_shadow_summary.json",
    "automation_self_check": ODDS_DIR / "automation_self_check_latest.json",
}

THEME = {
    "font_family": "Inter, Segoe UI, Roboto, Arial, sans-serif",
    "card_bg": "#ffffff",
    "card_border": "#e5e7eb",
    "text_primary": "#111827",
    "text_muted": "#6b7280",
    "text_subtle": "#4b5563",
    "status_good": "#0f766e",
    "status_watch": "#b45309",
    "status_risk": "#b91c1c",
    "status_neutral": "#374151",
    "radius": "12px",
    "pad_y": "10px",
    "pad_x": "12px",
}

THRESHOLDS = {
    "action": {"good": {"ACCUMULATE", "RUN_DASHBOARD"}, "watch": {"GATE_CAUTION", "RECALIBRATE"}},
    "chrono_coverage": {"good_min_ratio": 1.0},
    "warning_count": {"good_max": 0, "watch_max": 2},
    "refresh_age_hours": {"good_max": 4, "watch_max": 24},
    "stale_artifacts": {"good_max": 0, "watch_max": 2},
    "settled_rows": {"good_min": 500, "watch_min": 100},
    "k_rate_mae_delta": {"good_max": -0.0005, "risk_min": 0.001, "invert": False},
    "tbf_bias_abs_delta": {"good_max": 0.01, "risk_min": 0.03, "invert": False},
    "warning_delta": {"good_max": -1, "risk_min": 1, "invert": False},
    "dates_delta": {"good_max": 1, "risk_min": -1, "invert": True},
    "roi_daily": {"good_max": 0.0, "risk_min": 0.03, "invert": True},
    "max_drawdown_abs": {"good_max": 50, "risk_min": 150, "invert": False},
    "pnl_7d": {"good_max": 0, "risk_min": 0, "invert": True},
    "roi_7d": {"good_max": 0.0, "risk_min": 0.02, "invert": True},
}

KPI_HELP = {
    "daily_action": "Model governance action from latest KPI gate policy.",
    "promotion_ready": "Requires chronology coverage and drift gate pass.",
    "chrono_dates": "Observed dates vs minimum required for promotion evidence.",
    "warning_count": "Active warnings from calibration and drift diagnostics.",
    "last_refresh": "Timestamp of most recent successful daily KPI loop run.",
    "artifact_coverage": "Count of expected artifacts currently available.",
    "stale_artifacts": "Artifacts older than the staleness threshold.",
    "settled_rows": "Rows eligible for settled performance analytics.",
    "k_rate_mae_delta": "Day-over-day change in k-rate calibration MAE.",
    "tbf_delta": "Day-over-day change in under-side TBF bias (closer to 0 is better).",
    "warn_delta": "Change in warning count from prior snapshot.",
    "dates_delta": "Change in chronology evidence count from prior snapshot.",
    "daily_roi": "Realized ROI on today's settled cohort.",
    "side_over_roi": "Realized ROI for over-side positions.",
    "side_under_roi": "Realized ROI for under-side positions.",
    "daily_bets": "Settled bets counted in the daily summary.",
    "max_drawdown": "Largest peak-to-trough cumulative PnL decline.",
    "pnl_7d": "Net PnL over the trailing 7 settled dates.",
    "roi_7d": "ROI over the trailing 7 settled dates.",
}


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _active_operating_profile(policy: dict[str, Any]) -> dict[str, Any]:
    oper = policy.get("operating_profile", {}) if isinstance(policy, dict) else {}
    profiles = oper.get("profiles", {}) if isinstance(oper.get("profiles", {}), dict) else {}
    name = str(oper.get("name", "unknown"))
    prof = profiles.get(name, {}) if isinstance(profiles, dict) else {}
    return {
        "name": name,
        "edge_min": _to_float(prof.get("edge_min")),
        "edge_min_over": _to_float(prof.get("edge_min_over")),
        "edge_min_under": _to_float(prof.get("edge_min_under")),
    }


def _read_parquet(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    return pl.read_parquet(path)


def _read_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    return pl.read_csv(path)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return None


def _fmt_number(value: Any, *, digits: int = 2, signed: bool = False, suffix: str = "") -> str:
    num = _to_float(value)
    if num is None:
        return "n/a"
    body = f"{num:+.{digits}f}" if signed else f"{num:.{digits}f}"
    return f"{body}{suffix}"


def _fmt_int(value: Any, *, signed: bool = False) -> str:
    num = _to_int(value)
    if num is None:
        return "n/a"
    return f"{num:+d}" if signed else f"{num:d}"


def _fmt_pct(value: Any, *, digits: int = 1, signed: bool = False) -> str:
    num = _to_float(value)
    if num is None:
        return "n/a"
    if signed:
        return f"{num:+.{digits}%}"
    return f"{num:.{digits}%}"


def _status_chip(label: str, level: str) -> str:
    palette = {
        "good": THEME["status_good"],
        "watch": THEME["status_watch"],
        "risk": THEME["status_risk"],
        "neutral": THEME["status_neutral"],
    }
    color = palette.get(level, palette["neutral"])
    return (
        "<span style='display:inline-block;padding:2px 8px;border-radius:999px;"
        f"font-size:0.78rem;font-weight:600;color:white;background:{color};'>{label}</span>"
    )


def _status_by_threshold(
    value: Any,
    *,
    good_max: float | None = None,
    risk_min: float | None = None,
    invert: bool = False,
) -> str:
    v = _to_float(value)
    if v is None:
        return "neutral"
    if invert:
        if risk_min is not None and v <= risk_min:
            return "risk"
        if good_max is not None and v >= good_max:
            return "good"
    else:
        if good_max is not None and v <= good_max:
            return "good"
        if risk_min is not None and v >= risk_min:
            return "risk"
    return "watch"


def _metric_card(
    title: str,
    value: str,
    *,
    delta: str | None = None,
    status_label: str | None = None,
    status_level: str = "neutral",
    help_text: str | None = None,
) -> None:
    status_html = _status_chip(status_label, status_level) if status_label else ""
    delta_html = f"<div class='kpi-delta'>{delta}</div>" if delta else ""
    help_html = f"<div class='kpi-help'>{help_text}</div>" if help_text else ""
    st.markdown(
        (
            "<div class='kpi-card'>"
            f"<div class='kpi-title-row'><div class='kpi-title'>{title}</div>{status_html}</div>"
            f"<div class='kpi-value'>{value}</div>"
            f"{delta_html}{help_html}</div>"
        ),
        unsafe_allow_html=True,
    )


def _kpi_card(
    title: str,
    value: str,
    *,
    metric_key: str | None = None,
    status_value: Any | None = None,
    status_label: str | None = None,
    delta: str | None = None,
    help_key: str | None = None,
) -> None:
    status_level = _status_for(metric_key, status_value if status_value is not None else value) if metric_key else "neutral"
    _metric_card(
        title,
        value,
        delta=delta,
        status_label=status_label,
        status_level=status_level,
        help_text=KPI_HELP.get(help_key or "", None),
    )


def _section_caption(text: str) -> None:
    st.caption(f"Decision focus: {text}")


def _dedupe_frame(df: pl.DataFrame, keys: list[str]) -> tuple[pl.DataFrame, int]:
    present = [k for k in keys if k in df.columns]
    if df.is_empty() or not present:
        return df, 0
    before = df.height
    out = df.unique(subset=present, keep="last", maintain_order=True)
    removed = max(before - out.height, 0)
    return out, removed


def _yesterday_settled_date(settled_eval: pl.DataFrame, now_local: datetime) -> str | None:
    if settled_eval.is_empty() or "gdate" not in settled_eval.columns:
        return None
    yesterday = (now_local.date() - timedelta(days=1)).isoformat()
    days = settled_eval.select("gdate").unique().sort("gdate")
    vals = [str(v) for v in days["gdate"].to_list()]
    if yesterday in vals:
        return yesterday
    prior = [d for d in vals if d < now_local.date().isoformat()]
    return prior[-1] if prior else None


def _daily_summary_from_settled_date(settled_eval: pl.DataFrame, gdate: str | None) -> dict[str, Any]:
    if gdate is None or settled_eval.is_empty() or "gdate" not in settled_eval.columns:
        return {}
    day = settled_eval.filter(pl.col("gdate") == gdate)
    if day.is_empty():
        return {}
    stake = float(day["stake"].cast(pl.Float64).sum()) if "stake" in day.columns else 0.0
    pnl = float(day["pnl"].cast(pl.Float64).sum()) if "pnl" in day.columns else 0.0
    roi = (pnl / stake) if stake > 0 else None
    out: dict[str, Any] = {
        "latest_settled_date": gdate,
        "daily_stake": stake,
        "daily_pnl": pnl,
        "daily_roi": roi,
        "daily_n_bets": int(day.height),
    }
    if "side" in day.columns:
        by_side = day.group_by("side").agg(
            pl.col("stake").cast(pl.Float64).sum().alias("stake"),
            pl.col("pnl").cast(pl.Float64).sum().alias("pnl"),
        )
        for row in by_side.to_dicts():
            side = str(row.get("side", "")).lower()
            stv = float(row.get("stake") or 0.0)
            pnv = float(row.get("pnl") or 0.0)
            side_roi = (pnv / stv) if stv > 0 else None
            if side == "over":
                out["daily_over_roi"] = side_roi
            elif side == "under":
                out["daily_under_roi"] = side_roi
    return out


def _action_gate_reasons(kpi_action: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    action = str(kpi_action.get("action", "UNKNOWN"))
    ready = bool(kpi_action.get("recalibration_promote_ready"))
    n_warn = _to_int(kpi_action.get("n_warn"))
    n_dates = _to_int(kpi_action.get("n_dates"))
    n_min = _to_int(kpi_action.get("chrono_min_dates"))
    blockers = kpi_action.get("recalibration_promote_blockers", [])

    reasons.append(f"Action state: {action}.")
    reasons.append(f"Promotion gate: {'PASS' if ready else 'HOLD'}.")
    if n_dates is not None and n_min is not None:
        reasons.append(f"Chronology coverage: {n_dates}/{n_min} dates.")
    if n_warn is not None:
        reasons.append(f"Warning load: {n_warn}.")
    if blockers:
        reasons.append("Blockers: " + " | ".join(str(x) for x in blockers[:2]))
    else:
        reasons.append("Blockers: none.")
    return reasons[:5]


def _policy_snapshot(latest_sweep: pl.DataFrame) -> dict[str, Any]:
    if latest_sweep.is_empty():
        return {}
    cols = set(latest_sweep.columns)
    if not {"scope", "edge_floor", "roi", "n_bets"}.issubset(cols):
        return {}
    focus = latest_sweep.filter(pl.col("scope") == "all")
    if focus.is_empty():
        focus = latest_sweep
    best = focus.sort(["roi", "n_bets"], descending=[True, True]).head(1)
    if best.is_empty():
        return {}
    row = best.to_dicts()[0]
    return {
        "edge_floor": row.get("edge_floor"),
        "roi": row.get("roi"),
        "n_bets": row.get("n_bets"),
    }


def _continuation_confidence(settled_eval: pl.DataFrame) -> tuple[str, str, str]:
    if settled_eval.is_empty():
        return ("Low", "No settled BET rows available yet.", "risk")
    n = settled_eval.height
    clv_msg = "CLV unavailable."
    clv_quality = 0
    if "clv_pp" in settled_eval.columns:
        clv = settled_eval.filter(pl.col("clv_pp").is_not_null())
        if not clv.is_empty():
            mean_clv = float(clv["clv_pp"].cast(pl.Float64).mean())
            beat = float((clv["clv_pp"].cast(pl.Float64) > 0).mean())
            clv_msg = f"mean CLV {mean_clv:+.3f} pp, beat-close {beat:.1%}."
            if mean_clv > 0 and beat >= 0.5:
                clv_quality = 2
            elif mean_clv > -0.002 and beat >= 0.45:
                clv_quality = 1
    if n >= 200 and clv_quality == 2:
        return ("High", f"Strong sample ({n}) with stable CLV; {clv_msg}", "good")
    if n >= 80 and clv_quality >= 1:
        return ("Medium", f"Moderate sample ({n}); monitor drift while scaling. {clv_msg}", "watch")
    return ("Low", f"Limited confidence from current sample ({n}) or CLV quality; {clv_msg}", "risk")


def _staleness_level(age_hours: float | None) -> str:
    if age_hours is None:
        return "risk"
    if age_hours <= float(THRESHOLDS["refresh_age_hours"]["good_max"]):
        return "good"
    if age_hours <= float(THRESHOLDS["refresh_age_hours"]["watch_max"]):
        return "watch"
    return "risk"


def _status_for(metric: str, value: Any) -> str:
    cfg = THRESHOLDS.get(metric, {})
    if "good" in cfg and "watch" in cfg:
        token = str(value)
        if token in cfg["good"]:
            return "good"
        if token in cfg["watch"]:
            return "watch"
        return "risk"
    if metric == "chrono_coverage":
        if not isinstance(value, tuple):
            return "watch"
        n_dates, n_min = value
        if n_dates is None or n_min is None or n_min <= 0:
            return "watch"
        ratio = n_dates / n_min
        return "good" if ratio >= float(cfg.get("good_min_ratio", 1.0)) else "watch"
    if metric == "warning_count":
        v = _to_int(value)
        if v is None:
            return "watch"
        if v <= int(cfg.get("good_max", 0)):
            return "good"
        if v <= int(cfg.get("watch_max", 2)):
            return "watch"
        return "risk"
    if metric == "refresh_age_hours":
        v = _to_float(value)
        if v is None:
            return "risk"
        if v <= float(cfg.get("good_max", 4)):
            return "good"
        if v <= float(cfg.get("watch_max", 24)):
            return "watch"
        return "risk"
    if metric == "stale_artifacts":
        v = _to_int(value)
        if v is None:
            return "risk"
        if v <= int(cfg.get("good_max", 0)):
            return "good"
        if v <= int(cfg.get("watch_max", 2)):
            return "watch"
        return "risk"
    if metric == "settled_rows":
        v = _to_int(value)
        if v is None:
            return "risk"
        if v >= int(cfg.get("good_min", 500)):
            return "good"
        if v >= int(cfg.get("watch_min", 100)):
            return "watch"
        return "risk"
    return _status_by_threshold(
        value,
        good_max=cfg.get("good_max"),
        risk_min=cfg.get("risk_min"),
        invert=bool(cfg.get("invert", False)),
    )


def _inject_theme() -> None:
    st.markdown(
        f"""
<style>
html, body, [class*="css"] {{
  font-family: {THEME["font_family"]};
}}
.kpi-card {{
  border: 1px solid {THEME["card_border"]};
  border-radius: {THEME["radius"]};
  padding: {THEME["pad_y"]} {THEME["pad_x"]};
  background: {THEME["card_bg"]};
}}
.kpi-title-row {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}}
.kpi-title {{
  font-size: 0.82rem;
  color: {THEME["text_muted"]};
  font-weight: 600;
}}
.kpi-value {{
  font-size: 1.45rem;
  font-weight: 700;
  color: {THEME["text_primary"]};
  margin-top: 4px;
}}
.kpi-delta {{
  font-size: 0.85rem;
  color: {THEME["text_subtle"]};
  margin-top: 4px;
}}
.kpi-help {{
  font-size: 0.78rem;
  color: {THEME["text_muted"]};
  margin-top: 6px;
}}
</style>
""",
        unsafe_allow_html=True,
    )


def _mpl_axes(ax: Any, *, x_title: str, y_title: str, legend_title: str = "Series") -> None:
    ax.set_xlabel(x_title, color="#111827")
    ax.set_ylabel(y_title, color="#111827")
    ax.tick_params(axis="both", colors="#111827", labelsize=11)
    ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    for spine in ax.spines.values():
        spine.set_color("#111827")
    leg = ax.get_legend()
    if leg is not None:
        leg.set_title(legend_title)
        leg.set_bbox_to_anchor((1.0, 1.0))
        leg._loc = 1


def _render_chart(fig: Any) -> None:
    st.pyplot(fig, clear_figure=True, width="stretch")


def _infer_unit_dollars(settled: pl.DataFrame, default_unit: float = 50.0) -> float:
    if settled.is_empty() or not {"stake", "units"}.issubset(set(settled.columns)):
        return default_unit
    base = (
        settled.with_columns(
            pl.col("stake").cast(pl.Float64).alias("stake_f"),
            pl.col("units").cast(pl.Float64).alias("units_f"),
        )
        .filter((pl.col("stake_f") > 0) & (pl.col("units_f") > 0))
        .with_columns((pl.col("stake_f") / pl.col("units_f")).alias("unit_dollars"))
    )
    if base.is_empty():
        return default_unit
    med = float(base["unit_dollars"].median())
    if med <= 0:
        return default_unit
    return med


def _daily_takeaways(cal_latest: dict, daily_summary: dict) -> list[str]:
    """Rule-based takeaways (local logic only, no LLM/API calls)."""
    out: list[str] = []
    kpi = cal_latest.get("kpi_action", {})
    compare = cal_latest.get("compare", {})

    d_mae = _to_float(compare.get("delta_mae_err_k_rate"))
    if d_mae is None:
        out.append("First compare snapshot captured; day-over-day calibration delta starts tomorrow.")
    elif d_mae < -0.001:
        out.append(f"Calibration improved day-over-day: mae_err_k_rate moved {d_mae:+.4f}.")
    elif d_mae > 0.001:
        out.append(f"Calibration worsened day-over-day: mae_err_k_rate moved {d_mae:+.4f}.")
    else:
        out.append(f"Calibration is flat: mae_err_k_rate change {d_mae:+.4f}.")

    n_dates = _to_int(kpi.get("n_dates"))
    n_min = _to_int(kpi.get("chrono_min_dates"))
    if n_dates is not None and n_min is not None:
        out.append(f"Chrono evidence coverage is {n_dates}/{n_min} dates for promotion readiness.")
    else:
        out.append("Chrono evidence coverage fields are missing from the latest snapshot.")

    over_roi = _to_float(daily_summary.get("daily_over_roi"))
    under_roi = _to_float(daily_summary.get("daily_under_roi"))
    if over_roi is not None and under_roi is not None:
        if over_roi < under_roi:
            out.append(
                f"Side asymmetry persists: over ROI {over_roi:+.3f} vs under ROI {under_roi:+.3f}; keep over-side guardrails tight."
            )
        else:
            out.append(
                f"Side mix flipped: over ROI {over_roi:+.3f} vs under ROI {under_roi:+.3f}; verify if this is durable."
            )
    else:
        out.append("Not enough side-level settled ROI to form a side-mix takeaway today.")
    return out[:3]


def _topline_sections(
    *,
    kpi_action: dict[str, Any],
    cmp: dict[str, Any],
    daily_summary: dict[str, Any],
    settled: pl.DataFrame,
    unit_dollars: float,
) -> dict[str, list[str]]:
    current_posture: list[str] = []
    today_results: list[str] = []
    forward_watch: list[str] = []

    action = str(kpi_action.get("action", "UNKNOWN"))
    current_posture.append(f"Decision posture: {action}.")

    ready = bool(kpi_action.get("recalibration_promote_ready"))
    current_posture.append(f"Promotion readiness: {'ready' if ready else 'not ready'}.")

    n_warn = _to_int(kpi_action.get("n_warn"))
    current_posture.append(
        "Current warning load: n/a." if n_warn is None else f"Current warning load: {n_warn} active warnings."
    )
    n_dates = _to_int(kpi_action.get("n_dates"))
    n_min = _to_int(kpi_action.get("chrono_min_dates"))
    if n_dates is not None and n_min is not None:
        current_posture.append(f"Chrono evidence: {n_dates}/{n_min} dates collected.")

    d_mae = _to_float(cmp.get("delta_mae_err_k_rate"))
    d_tbf = _to_float(cmp.get("delta_under_bias_tbf"))
    if d_mae is None:
        forward_watch.append("K-rate calibration delta: first snapshot or unavailable.")
    else:
        forward_watch.append(f"K-rate calibration delta: {d_mae:+.4f} day-over-day.")
    if d_tbf is not None:
        forward_watch.append(f"TBF under-bias delta: {d_tbf:+.3f} day-over-day.")

    d_roi = _to_float(daily_summary.get("daily_roi"))
    over_roi = _to_float(daily_summary.get("daily_over_roi"))
    under_roi = _to_float(daily_summary.get("daily_under_roi"))
    d_pnl = _to_float(daily_summary.get("daily_pnl"))
    d_stake = _to_float(daily_summary.get("daily_stake"))
    gate_delta = _to_float(daily_summary.get("gate_pnl_delta"))
    today_results.append("Daily ROI: n/a." if d_roi is None else f"Daily ROI: {d_roi:+.2f}.")
    d_pnl_units = (d_pnl / unit_dollars) if (d_pnl is not None and unit_dollars > 0) else None
    d_stake_units = (d_stake / unit_dollars) if (d_stake is not None and unit_dollars > 0) else None
    gate_delta_units = (gate_delta / unit_dollars) if (gate_delta is not None and unit_dollars > 0) else None
    today_results.append("Daily PnL: n/a." if d_pnl_units is None else f"Daily PnL: {d_pnl_units:+.2f}u.")
    if over_roi is not None and under_roi is not None:
        today_results.append(f"Side split ROI: over {over_roi:+.2f}, under {under_roi:+.2f}.")
    else:
        today_results.append("Side split ROI: unavailable.")
    d_n_bets = _to_int(daily_summary.get("daily_n_bets"))
    if d_n_bets is not None:
        today_results.append(f"Settled bets: {d_n_bets}.")
    if d_stake_units is not None:
        today_results.append(f"Daily stake: {d_stake_units:+.2f}u.")
    if gate_delta_units is not None:
        today_results.append(f"Gate delta (PnL): {gate_delta_units:+.2f}u.")

    if not settled.is_empty():
        roll = (
            settled.group_by("gdate")
            .agg(
                pl.col("stake").cast(pl.Float64).sum().alias("stake"),
                pl.col("pnl").cast(pl.Float64).sum().alias("pnl"),
            )
            .sort("gdate")
            .tail(7)
        )
        if not roll.is_empty():
            wk_pnl = float(roll["pnl"].sum())
            wk_stake = float(roll["stake"].sum())
            wk_roi = (wk_pnl / wk_stake) if wk_stake > 0 else None
            forward_watch.append("7-day ROI: n/a." if wk_roi is None else f"7-day ROI: {wk_roi:+.2f}.")
            wk_pnl_units = (wk_pnl / unit_dollars) if unit_dollars > 0 else None
            forward_watch.append("7-day PnL: n/a." if wk_pnl_units is None else f"7-day PnL: {wk_pnl_units:+.2f}u.")
            forward_watch.append(f"7-day settled rows: {roll.height}.")
    else:
        forward_watch.append("7-day performance window: unavailable.")

    if "clv_pp" in settled.columns and not settled.is_empty():
        clv = settled.filter(pl.col("clv_pp").is_not_null())
        if not clv.is_empty():
            mean_clv = float(clv["clv_pp"].cast(pl.Float64).mean())
            beat = float((clv["clv_pp"].cast(pl.Float64) > 0).mean())
            forward_watch.append(f"Mean CLV: {mean_clv:+.3f} pp.")
            forward_watch.append(f"Beat-close rate: {beat:.1%}.")
            forward_watch.append(f"CLV sample size: {clv.height}.")
        else:
            forward_watch.append("CLV signal: unavailable.")
    else:
        forward_watch.append("CLV signal: unavailable.")

    return {
        "current_posture": current_posture[:5],
        "today_results": today_results[:6],
        "forward_watch": forward_watch[:6],
    }


def _action_legend() -> dict[str, str]:
    return {
        "ACCUMULATE": "Keep gathering settled evidence; no promotion changes yet.",
        "RECALIBRATE": "Compare calibration mappings and drift diagnostics; hold promotion until gates pass.",
        "TBF_FIX": "Prioritize workload/TBF bias stabilization before broad model changes.",
        "GATE_CAUTION": "Operate with tighter filters while drift pockets are monitored.",
        "GATE_STRICT": "Apply strict risk controls and block known weak slices.",
        "RUN_DASHBOARD": "Artifacts missing or stale; refresh the ops pipeline first.",
    }


def _latest_scenario_rows(sweep: pl.DataFrame) -> pl.DataFrame:
    if sweep.is_empty() or "snapshot_utc" not in sweep.columns:
        return pl.DataFrame()
    latest = sweep.select(pl.col("snapshot_utc").max()).item()
    return sweep.filter(pl.col("snapshot_utc") == latest)


def _styled_table(df: pl.DataFrame, *, limit: int = 100) -> None:
    if df.is_empty():
        st.caption("No rows available.")
        return
    st.dataframe(df.head(limit).to_pandas(), width="stretch", hide_index=True)


def _plot_line(df: pl.DataFrame, x: str, y_cols: list[str], title: str) -> None:
    if df.is_empty() or x not in df.columns:
        return
    pdf = df.select([x, *[c for c in y_cols if c in df.columns]]).to_pandas()
    if pdf.empty:
        return
    if x in {"snapshot_utc", "gdate", "game_date"}:
        try:
            pdf[x] = pl.Series(pdf[x]).str.to_datetime(strict=False).to_pandas()
        except Exception:
            pass
    long = pdf.melt(id_vars=[x], var_name="metric", value_name="value")
    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots(figsize=(11, 4))
    sns.lineplot(data=long, x=x, y="value", hue="metric", marker="o", ax=ax)
    ax.set_title(title, color="#111827", fontsize=13)
    _mpl_axes(ax, x_title=x.replace("_", " ").title(), y_title="Metric Value", legend_title="Metric")
    if x in {"snapshot_utc", "gdate", "game_date"}:
        locator = mdates.AutoDateLocator()
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        fig.autofmt_xdate(rotation=25, ha="right")
    fig.tight_layout()
    _render_chart(fig)


def _edge_bin_expr(col: str = "edge") -> pl.Expr:
    return (
        pl.when(pl.col(col) < 0.08)
        .then(pl.lit("<0.08"))
        .when(pl.col(col) < 0.10)
        .then(pl.lit("0.08-0.10"))
        .when(pl.col(col) < 0.12)
        .then(pl.lit("0.10-0.12"))
        .when(pl.col(col) < 0.14)
        .then(pl.lit("0.12-0.14"))
        .when(pl.col(col) < 0.16)
        .then(pl.lit("0.14-0.16"))
        .otherwise(pl.lit(">=0.16"))
        .alias("edge_bin")
    )


def _artifact_health(paths: dict[str, Path]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for key, path in paths.items():
        exists = path.exists()
        rows.append(
            {
                "artifact": key,
                "exists": exists,
                "path": str(path),
                "last_modified": path.stat().st_mtime if exists else None,
                "size_mb": round(path.stat().st_size / (1024 * 1024), 2) if exists else None,
            }
        )
    out = pl.DataFrame(rows)
    if not out.is_empty():
        out = out.with_columns(
            pl.when(pl.col("last_modified").is_not_null())
            .then(pl.from_epoch("last_modified", time_unit="s"))
            .otherwise(None)
            .alias("last_modified_utc")
        ).drop("last_modified")
    return out


def _artifact_health_with_age(paths: dict[str, Path]) -> pl.DataFrame:
    out = _artifact_health(paths)
    if out.is_empty():
        return out
    now = datetime.now().timestamp()
    return out.with_columns(
        pl.when(pl.col("exists"))
        .then(((pl.lit(now) - pl.col("last_modified_utc").dt.epoch("s")) / 3600).round(2))
        .otherwise(None)
        .alias("age_hours")
    )


def _run_daily_pipeline_now() -> tuple[bool, str]:
    """Run the daily pipeline script and return status plus tail output."""
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        return False, f"Python not found at {python}"
    cmd = [str(python), "production/ops/run_daily_kpi_loop.py"]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return proc.returncode == 0, out[-4000:]


def _run_command(cmd: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return proc.returncode == 0, out[-4000:]


def _auto_remediate_stale_artifacts() -> tuple[bool, str]:
    """Refresh stale artifacts via daily loop + calibration/policy updates."""
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        return False, f"Python not found at {python}"
    steps = [
        [str(python), "production/ops/run_daily_kpi_loop.py"],
        [str(python), "production/ops/calibration_snapshot.py", "--compare"],
        [
            str(python),
            "production/ops/policy_simulator.py",
            "--thresholds",
            "0.08,0.10,0.12,0.14,0.16,0.18",
            "--profile-over-floors",
            "0.12,0.14,0.16,0.18",
            "--profile-under-floors",
            "0.10,0.12,0.14",
            "--profile-min-bets",
            "25",
        ],
    ]
    logs: list[str] = []
    ok_all = True
    for step in steps:
        ok, out = _run_command(step)
        logs.append(f"$ {' '.join(step)}\n{out or '(no output)'}")
        if not ok:
            ok_all = False
            break
    return ok_all, "\n\n".join(logs)[-12000:]


def _scheduled_task_status(task_name: str) -> dict[str, str]:
    """Read basic schtasks state for an existing task."""
    cmd = ["schtasks", "/Query", "/TN", task_name, "/FO", "LIST", "/V"]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        return {"task": task_name, "found": "no"}
    lines = (proc.stdout or "").splitlines()
    row = {"task": task_name, "found": "yes"}
    for line in lines:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip().lower()
        val = v.strip()
        if key == "status":
            row["status"] = val
        elif key == "last run time":
            row["last_run_time"] = val
        elif key == "next run time":
            row["next_run_time"] = val
        elif key == "last result":
            row["last_result"] = val
    return row


def _missed_morning_run_note(kpi_loop: dict, expected_hour: int = 8, expected_minute: int = 30) -> str | None:
    """Warn if today's expected morning run appears missing."""
    ran_utc = kpi_loop.get("ran_utc")
    if not ran_utc:
        return "No daily pipeline run recorded yet."
    try:
        ran = datetime.fromisoformat(str(ran_utc).replace("Z", "+00:00")).astimezone()
    except Exception:  # noqa: BLE001
        return None
    now_local = datetime.now().astimezone()
    expected_today = now_local.replace(hour=expected_hour, minute=expected_minute, second=0, microsecond=0)
    # Only warn after the expected run window has passed.
    if now_local < expected_today + timedelta(minutes=15):
        return None
    if ran.date() < now_local.date():
        return f"Expected a run today around {expected_hour:02d}:{expected_minute:02d}, but latest run is from {ran.strftime('%Y-%m-%d %H:%M')}."
    if ran.date() == now_local.date() and ran < expected_today - timedelta(minutes=30):
        return f"Latest run today ({ran.strftime('%H:%M')}) is earlier than the expected morning schedule ({expected_hour:02d}:{expected_minute:02d})."
    return None


def _automation_health_row(row: dict[str, str]) -> tuple[str, str]:
    status = str(row.get("status", "")).lower()
    last_result = str(row.get("last_result", "")).lower()
    if row.get("found") != "yes":
        return "Missing task", "risk"
    if "running" in status:
        return "Running", "good"
    if "ready" in status and ("0x0" in last_result or "success" in last_result):
        return "Healthy", "good"
    if "ready" in status:
        return "Needs review", "watch"
    return "At risk", "risk"


st.set_page_config(page_title="MLB Props Operator Dashboard", layout="wide")
_inject_theme()
st.title("MLB Props - Operator Dashboard")
st.caption("Internal daily cockpit for calibration, policy, and performance monitoring.")

daily_summary = _read_json(PATHS["daily_summary"])
kpi_loop = _read_json(PATHS["kpi_loop"])
cal_latest = _read_json(PATHS["cal_snapshot"])
cal_hist = _read_parquet(PATHS["cal_history"])
scorecard_daily = _read_parquet(PATHS["scorecard_daily"])
decomp_daily = _read_parquet(PATHS["decomp_daily"])
policy_sweep = _read_parquet(PATHS["policy_sweep"])
policy_profile = _read_parquet(PATHS["policy_profile"])
decision_scoreboard = _read_parquet(PATHS["decision_scoreboard"])
validation_ops = _read_json(PATHS["validation_ops"])
go_no_go = _read_json(PATHS["go_no_go"])
policy_replay = _read_json(PATHS["policy_replay"])
ledger = _read_parquet(PATHS["ledger"])
graded = _read_parquet(PATHS["graded"])
recommendations = _read_parquet(PATHS["recommendations"])
policy_config = _read_json(PATHS["kpi_policy"])
active_profile = _active_operating_profile(policy_config)
runtime_snapshot = _read_json(PATHS["runtime_snapshot"])
runtime_floor = _read_csv(PATHS["runtime_floor_calibration"])
runtime_slip = _read_csv(PATHS["runtime_slippage"])
runtime_month = _read_csv(PATHS["runtime_regime_monthly"])
runtime_edge = _read_csv(PATHS["runtime_edge_deciles"])
runtime_decision = _read_csv(PATHS["runtime_decision_diag"])
runtime_slo = _read_json(PATHS["runtime_ops_slo"])
morning_alert = _read_json(PATHS["morning_alert"])
aux_shadow_summary = _read_csv(PATHS["aux_shadow_summary_csv"])
aux_shadow_meta = _read_json(PATHS["aux_shadow_summary_json"])
automation_self_check = _read_json(PATHS["automation_self_check"])

kpi_action = kpi_loop.get("kpi_action", {})
action = str(kpi_action.get("action", "UNKNOWN"))
ready = bool(kpi_action.get("recalibration_promote_ready"))
blockers = kpi_action.get("recalibration_promote_blockers", [])
legend = _action_legend()

settled = pl.DataFrame()
if not ledger.is_empty() and {"game_date", "status", "stake", "pnl"}.issubset(set(ledger.columns)):
    settled = (
        ledger.with_columns(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gdate"))
        .filter((pl.col("status") == "settled") & (pl.col("stake").cast(pl.Float64).fill_null(0.0) > 0.0))
    )
settled, removed_settled_dupes = _dedupe_frame(
    settled,
    ["gdate", "player_name", "book", "line", "side"],
)
recommendations, removed_reco_dupes = _dedupe_frame(
    recommendations,
    ["game_date", "player_name", "book", "line", "best_side", "best_price"],
)

st.sidebar.markdown("### View Controls")
show_internal_ops = st.sidebar.checkbox(
    "Internal Ops Mode",
    value=False,
    help="Shows run controls and command-level operations intended for internal operators.",
)

settled_eval = settled
if not settled.is_empty() and "recommendation" in settled.columns:
    settled_eval = settled.filter(pl.col("recommendation").cast(pl.Utf8).str.to_uppercase() == "BET")
elif not settled.is_empty() and "recommendation" not in settled.columns:
    st.caption("Scope note: ledger has no `recommendation` field; using all settled rows.")
now_local = datetime.now().astimezone()
completed_gdate = _yesterday_settled_date(settled_eval, now_local)
daily_summary_eval = _daily_summary_from_settled_date(settled_eval, completed_gdate)
if daily_summary_eval:
    daily_summary = {**daily_summary, **daily_summary_eval}
unit_dollars = _infer_unit_dollars(settled_eval, default_unit=50.0)

cmp = cal_latest.get("compare", {}) if isinstance(cal_latest, dict) else {}
artifact_health = _artifact_health_with_age(PATHS)

hero1, hero2, hero3, hero4 = st.columns(4)
with hero1:
    _kpi_card(
        "Daily Action",
        action,
        metric_key="action",
        status_value=action,
        status_label=action.replace("_", " ").title(),
        help_key="daily_action",
    )
with hero2:
    _metric_card(
        "Promotion Ready",
        "Yes" if ready else "No",
        status_label="Ready" if ready else "Blocked",
        status_level="good" if ready else "watch",
        help_text=KPI_HELP["promotion_ready"],
    )
with hero3:
    n_dates_cur = _to_int(kpi_action.get("n_dates"))
    n_dates_min = _to_int(kpi_action.get("chrono_min_dates"))
    _kpi_card(
        "Chrono Dates",
        f"{kpi_action.get('n_dates', '?')} / {kpi_action.get('chrono_min_dates', '?')}",
        metric_key="chrono_coverage",
        status_value=(n_dates_cur, n_dates_min),
        status_label="Coverage",
        help_key="chrono_dates",
    )
with hero4:
    warn_count = _to_int(kpi_action.get("n_warn"))
    _kpi_card(
        "Warning Count",
        _fmt_int(warn_count),
        metric_key="warning_count",
        status_value=warn_count,
        status_label="Warnings",
        help_key="warning_count",
    )

st.caption(f"Action meaning: {legend.get(action, 'No legend entry available.')}")
if blockers:
    st.caption("Current blockers: " + " | ".join(str(x) for x in blockers))
else:
    st.caption("Current blockers: none")
if show_internal_ops and (removed_settled_dupes > 0 or removed_reco_dupes > 0):
    st.caption(
        f"Internal data hygiene: removed duplicates (settled={removed_settled_dupes}, recommendations={removed_reco_dupes})."
    )

fresh_col1, fresh_col2, fresh_col3, fresh_col4 = st.columns(4)
latest_run = kpi_loop.get("ran_utc")
run_ts = None
if latest_run:
    try:
        run_ts = datetime.fromisoformat(str(latest_run).replace("Z", "+00:00")).astimezone()
    except Exception:  # noqa: BLE001
        run_ts = None

age_hours = None
if run_ts is not None:
    age_hours = (now_local - run_ts).total_seconds() / 3600

existing_artifacts = 0
stale_artifacts = 0
if not artifact_health.is_empty():
    existing_artifacts = artifact_health.filter(pl.col("exists") == True).height  # noqa: E712
    stale_artifacts = artifact_health.filter(
        (pl.col("exists") == True) & (pl.col("age_hours").is_not_null()) & (pl.col("age_hours") > 24)
    ).height

with fresh_col1:
    _kpi_card(
        "Last Pipeline Refresh",
        run_ts.strftime("%Y-%m-%d %H:%M") if run_ts else "n/a",
        metric_key="refresh_age_hours",
        status_value=age_hours,
        delta=f"Age: {_fmt_number(age_hours, digits=1)}h" if age_hours is not None else None,
        status_label="Freshness",
        help_key="last_refresh",
    )
with fresh_col2:
    _metric_card(
        "Artifacts Present",
        f"{existing_artifacts} / {len(PATHS)}",
        status_label="Coverage",
        status_level="good" if existing_artifacts == len(PATHS) else "watch",
        help_text=KPI_HELP["artifact_coverage"],
    )
with fresh_col3:
    _kpi_card(
        "Stale Artifacts (>24h)",
        str(stale_artifacts),
        metric_key="stale_artifacts",
        status_value=stale_artifacts,
        status_label="Staleness",
        help_key="stale_artifacts",
    )
with fresh_col4:
    settled_n = settled_eval.height
    _kpi_card(
        "Evaluated Settled Rows",
        f"{settled_n:,}",
        metric_key="settled_rows",
        status_value=settled_n,
        status_label="Completeness",
        help_key="settled_rows",
    )

with st.expander("Operational Signals (freshness + day-over-day)", expanded=False):
    st.markdown("### Daily Change Signals")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        mae_delta = _to_float(cmp.get("delta_mae_err_k_rate"))
        _kpi_card(
            "K-rate MAE Delta",
            _fmt_number(mae_delta, digits=4, signed=True),
            metric_key="k_rate_mae_delta",
            status_value=mae_delta,
            status_label="Lower better",
            help_key="k_rate_mae_delta",
        )
    with d2:
        tbf_delta = _to_float(cmp.get("delta_under_bias_tbf"))
        _kpi_card(
            "TBF Bias Delta",
            _fmt_number(tbf_delta, digits=2, signed=True),
            metric_key="tbf_bias_abs_delta",
            status_value=abs(tbf_delta) if tbf_delta is not None else None,
            status_label="Near zero",
            help_key="tbf_delta",
        )
    with d3:
        warn_delta = _to_int(cmp.get("delta_n_warn"))
        _kpi_card(
            "Warnings Delta",
            _fmt_int(warn_delta, signed=True),
            metric_key="warning_delta",
            status_value=warn_delta,
            status_label="Lower better",
            help_key="warn_delta",
        )
    with d4:
        dates_delta = _to_int(cmp.get("delta_n_dates"))
        _kpi_card(
            "Dates Delta",
            _fmt_int(dates_delta, signed=True),
            metric_key="dates_delta",
            status_value=dates_delta,
            status_label="Higher better",
            help_key="dates_delta",
        )

sections = _topline_sections(
    kpi_action=kpi_action,
    cmp=cmp,
    daily_summary=daily_summary,
    settled=settled_eval,
    unit_dollars=unit_dollars,
)
st.markdown("### Topline Intelligence")
s1, s2, s3 = st.columns(3)
latest_settled_label = str(completed_gdate or daily_summary.get("latest_settled_date") or "Latest Settled Date")
with s1:
    st.markdown("#### Current Posture")
    for line in sections["current_posture"]:
        st.markdown(f"- {line}")
with s2:
    st.markdown(f"#### Yesterday's Results ({latest_settled_label})")
    for line in sections["today_results"]:
        st.markdown(f"- {line}")
with s3:
    st.markdown("#### Forward Watch")
    for line in sections["forward_watch"]:
        st.markdown(f"- {line}")
    st.caption("Scope: forward watch uses recommended BET-only settled rows.")
if sections["current_posture"] and sections["today_results"] and sections["forward_watch"]:
    st.caption(
        "Operator takeaway: keep the current posture aligned with action gates, validate today's side-level outcomes, and prioritize forward drift/CLV signals before changing promotion decisions."
    )

conf_label, conf_note, conf_level = _continuation_confidence(settled_eval)
conf_col1, conf_col2 = st.columns([1, 2])
with conf_col1:
    _metric_card(
        "Continuation Confidence",
        conf_label,
        status_label="Forward Signal",
        status_level=conf_level,
        help_text="Deterministic signal from sample size + CLV stability.",
    )
with conf_col2:
    st.caption(conf_note)

st.markdown("### Executive Decision Strip")
st.caption("Governance snapshot: why the current action is active and whether promotion constraints are satisfied.")
gate_reasons = _action_gate_reasons(kpi_action)
g1, g2 = st.columns([2, 1])
with g1:
    for reason in gate_reasons:
        st.markdown(f"- {reason}")
with g2:
    _metric_card(
        "Action Decision",
        action,
        status_label="Gate Outcome",
        status_level=_status_for("action", action),
        help_text="Deterministic KPI policy output.",
    )

st.markdown("### Quant Audit Strip")
st.caption("Stability diagnostics: cohort breadth, calibration movement, and current policy operating point.")
latest_sweep_global = _latest_scenario_rows(policy_sweep)
policy_snap = _policy_snapshot(latest_sweep_global)
applied_floor = None
if not recommendations.is_empty() and {"recommendation", "edge"}.issubset(set(recommendations.columns)):
    bet_edges = recommendations.filter(pl.col("recommendation") == "BET").select(pl.col("edge").cast(pl.Float64))
    if not bet_edges.is_empty():
        applied_floor = float(bet_edges["edge"].min())
settled_days = (
    settled_eval.group_by("gdate").agg(pl.len().alias("n_bets")).sort("gdate").tail(7)
    if (not settled_eval.is_empty() and "gdate" in settled_eval.columns)
    else pl.DataFrame()
)
avg_bets_7d = float(settled_days["n_bets"].mean()) if not settled_days.is_empty() else None
d_mae = _to_float(cmp.get("delta_mae_err_k_rate"))
q1, q2, q3, q4 = st.columns(4)
with q1:
    _metric_card(
        "7d Avg BETs/Day",
        _fmt_number(avg_bets_7d, digits=2),
        status_label="Cohort Breadth",
        status_level="good" if (avg_bets_7d is not None and avg_bets_7d >= 8) else "watch",
        help_text="Trailing settled BET opportunity rate.",
    )
with q2:
    _metric_card(
        "K-rate MAE D/D",
        _fmt_number(d_mae, digits=4, signed=True),
        status_label="Calibration",
        status_level=_status_for("k_rate_mae_delta", d_mae),
        help_text="Day-over-day calibration movement.",
    )
with q3:
    _metric_card(
        "Applied Floor (BETs)",
        _fmt_number(applied_floor, digits=2),
        status_label="Operating Point",
        status_level="neutral",
        help_text="Minimum edge among current BET recommendations.",
    )
with q4:
    _metric_card(
        "Policy ROI (all)",
        _fmt_number(policy_snap.get("roi"), digits=2, signed=True),
        status_label="Policy Fit",
        status_level=_status_for("roi_daily", _to_float(policy_snap.get("roi"))),
        help_text="All-scope ROI at best sweep floor.",
    )

tab_names = [
    "Overview",
    "Past History PnL",
    "Risk & Bankroll",
    "Bet & CLV Analysis",
    "Recommended Bets Today",
    "Calibration",
    "Policy",
    "Runtime Monitors",
]
if show_internal_ops:
    tab_names.append("Ops Health")
tabs = st.tabs(tab_names)
tab_overview, tab_hist, tab_risk, tab_clv, tab_reco, tab_cal, tab_policy, tab_runtime = tabs[:8]
tab_ops = tabs[8] if len(tabs) > 8 else None

with tab_overview:
    st.subheader("Today at a Glance")
    _section_caption("Confirm whether daily outcomes, recommendation flow, and pipeline freshness support today's operating posture.")
    st.caption(
        f"PnL math: realized PnL is shown in units (u), derived from settled BET rows using inferred unit size ${unit_dollars:.2f}; ROI = total_pnl / total_stake."
    )
    if daily_summary:
        c1, c2, c3, c4 = st.columns(4)
        day_roi = _to_float(daily_summary.get("daily_roi"))
        over_roi = _to_float(daily_summary.get("daily_over_roi"))
        under_roi = _to_float(daily_summary.get("daily_under_roi"))
        with c1:
            _kpi_card("Daily ROI", _fmt_number(day_roi, digits=2, signed=True), metric_key="roi_daily", status_value=day_roi, status_label="ROI", help_key="daily_roi")
        with c2:
            _kpi_card("Over ROI", _fmt_number(over_roi, digits=2, signed=True), metric_key="roi_daily", status_value=over_roi, status_label="Over", help_key="side_over_roi")
        with c3:
            _kpi_card("Under ROI", _fmt_number(under_roi, digits=2, signed=True), metric_key="roi_daily", status_value=under_roi, status_label="Under", help_key="side_under_roi")
        with c4:
            _metric_card("Daily Bets", _fmt_int(daily_summary.get("daily_n_bets")), status_label="Volume", status_level="neutral", help_text=KPI_HELP["daily_bets"])

        summary_rows = pl.DataFrame(
            [
                {"metric": "Latest settled date", "value": daily_summary.get("latest_settled_date")},
                {
                    "metric": "Daily stake (u)",
                    "value": (
                        (_to_float(daily_summary.get("daily_stake")) / unit_dollars)
                        if (_to_float(daily_summary.get("daily_stake")) is not None and unit_dollars > 0)
                        else None
                    ),
                },
                {
                    "metric": "Daily PnL (u)",
                    "value": (
                        (_to_float(daily_summary.get("daily_pnl")) / unit_dollars)
                        if (_to_float(daily_summary.get("daily_pnl")) is not None and unit_dollars > 0)
                        else None
                    ),
                },
                {"metric": "Gate actual ROI", "value": daily_summary.get("gate_actual_roi")},
                {"metric": "Gate baseline ROI", "value": daily_summary.get("gate_baseline_roi")},
                {
                    "metric": "Gate delta (u)",
                    "value": (
                        (_to_float(daily_summary.get("gate_pnl_delta")) / unit_dollars)
                        if (_to_float(daily_summary.get("gate_pnl_delta")) is not None and unit_dollars > 0)
                        else None
                    ),
                },
            ]
        )
        _styled_table(summary_rows, limit=20)

    st.markdown("#### Run Pipeline Now")
    if show_internal_ops:
        st.caption("Manual refresh runs the full daily loop and updates dashboard artifacts.")
        if st.button("Run Daily Pipeline Now", type="primary"):
            with st.spinner("Running production/ops/run_daily_kpi_loop.py ..."):
                ok, output = _run_daily_pipeline_now()
            if ok:
                st.success("Daily pipeline run completed successfully. Refresh the page to load new artifacts.")
            else:
                st.error("Daily pipeline run failed. See output below.")
            with st.expander("Pipeline execution log", expanded=not ok):
                st.code(output or "(no output)")
    else:
        st.caption("Automation mode is active. Internal run controls are hidden in this view.")

with tab_hist:
    st.subheader("Past History PnL")
    _section_caption("Assess profitability trend persistence and whether cumulative performance remains on plan.")
    if not settled_eval.is_empty():
        agg_exprs = [
            pl.len().alias("n"),
            pl.col("stake").cast(pl.Float64).sum().alias("stake"),
            pl.col("pnl").cast(pl.Float64).sum().alias("pnl"),
            (pl.col("pnl").cast(pl.Float64).sum() / pl.col("stake").cast(pl.Float64).sum()).alias("roi"),
        ]
        if "edge" in settled_eval.columns:
            agg_exprs.append(
                (
                    (pl.col("edge").cast(pl.Float64) * pl.col("stake").cast(pl.Float64)).sum()
                    / pl.col("stake").cast(pl.Float64).sum()
                ).alias("expected_roi")
            )
        by_day = settled_eval.group_by("gdate").agg(agg_exprs).sort("gdate").with_columns(
            (pl.col("pnl") / unit_dollars).alias("pnl_u"),
            (pl.col("pnl") / unit_dollars).cum_sum().alias("cum_pnl_u"),
        )
        if "expected_roi" in by_day.columns:
            by_day = by_day.with_columns(
                ((pl.col("expected_roi").cast(pl.Float64) * pl.col("stake").cast(pl.Float64)) / unit_dollars).alias(
                    "expected_pnl_u"
                )
            ).with_columns(pl.col("expected_pnl_u").cum_sum().alias("cum_expected_pnl_u"))
        pdf = by_day.to_pandas()
        sns.set_theme(style="whitegrid")
        fig, ax = plt.subplots(figsize=(11, 4))
        sns.barplot(data=pdf, x="gdate", y="roi", color="#3b82f6", ax=ax)
        ax.axhline(0, color="#9ca3af", linestyle="--", linewidth=1)
        ax.set_title("Settled BET ROI by Date", color="#111827", fontsize=13)
        _mpl_axes(ax, x_title="Date", y_title="ROI", legend_title="Metric")
        for lbl in ax.get_xticklabels():
            lbl.set_rotation(45)
            lbl.set_ha("right")
        fig.tight_layout()
        _render_chart(fig)
        st.caption("Interpretation: bars above zero are profitable settled BET days; below zero are losing days.")
        fig2, ax2 = plt.subplots(figsize=(11, 4))
        sns.lineplot(data=pdf, x="gdate", y="cum_pnl_u", marker="o", color="#1d4ed8", label="Cumulative PnL (u)", ax=ax2)
        ax2.set_title("Cumulative Settled BET PnL (Units)", color="#111827", fontsize=13)
        _mpl_axes(ax2, x_title="Date", y_title="Cumulative PnL (u)", legend_title="Series")
        for lbl in ax2.get_xticklabels():
            lbl.set_rotation(45)
            lbl.set_ha("right")
        fig2.tight_layout()
        _render_chart(fig2)
        st.caption("Interpretation: upward cumulative slope indicates persistent profitability over settled dates.")
        if "cum_expected_pnl_u" in pdf.columns:
            fig3, ax3 = plt.subplots(figsize=(11, 4))
            sns.lineplot(
                data=pdf,
                x="gdate",
                y="cum_pnl_u",
                marker="o",
                color="#1d4ed8",
                label="Actual cumulative PnL (u)",
                ax=ax3,
            )
            sns.lineplot(
                data=pdf,
                x="gdate",
                y="cum_expected_pnl_u",
                marker="o",
                color="#0f766e",
                label="Expected cumulative PnL (u)",
                ax=ax3,
            )
            ax3.set_title("Actual vs Expected Cumulative PnL (Units)", color="#111827", fontsize=13)
            _mpl_axes(ax3, x_title="Date", y_title="Cumulative PnL (u)", legend_title="Series")
            for lbl in ax3.get_xticklabels():
                lbl.set_rotation(45)
                lbl.set_ha("right")
            fig3.tight_layout()
            _render_chart(fig3)
            st.caption("Interpretation: persistent gap between expected and actual flags either variance or model edge degradation.")
        with st.expander("Daily PnL detail table"):
            _styled_table(by_day.sort("gdate", descending=True), limit=45)
    else:
        st.info("No settled historical PnL rows yet. Run the daily loop and end-of-day settle workflow to populate history.")

with tab_risk:
    st.subheader("Risk and Bankroll")
    _section_caption("Check drawdown profile and exposure concentration before expanding stake or loosening gates.")
    if settled_eval.is_empty():
        st.caption("No settled rows yet for risk analytics.")
    else:
        by_day_risk = (
            settled_eval.group_by("gdate")
            .agg(
                pl.col("stake").cast(pl.Float64).sum().alias("stake"),
                pl.col("pnl").cast(pl.Float64).sum().alias("pnl"),
            )
            .sort("gdate")
            .with_columns(
                pl.col("pnl").cum_sum().alias("cum_pnl"),
            )
            .with_columns(
                pl.col("cum_pnl").cum_max().alias("cum_peak_pnl"),
            )
            .with_columns(
                (pl.col("cum_pnl") - pl.col("cum_peak_pnl")).alias("drawdown"),
            )
        )
        max_dd = float(by_day_risk["drawdown"].min()) if by_day_risk.height else 0.0
        max_dd_units = (max_dd / unit_dollars) if unit_dollars > 0 else None
        weekly = by_day_risk.tail(7)
        week_pnl = float(weekly["pnl"].sum()) if weekly.height else 0.0
        week_stake = float(weekly["stake"].sum()) if weekly.height else 0.0
        week_roi = (week_pnl / week_stake) if week_stake > 0 else None

        r1, r2, r3 = st.columns(3)
        with r1:
            _metric_card(
                "Max Drawdown (to date, u)",
                _fmt_number(max_dd_units, digits=2, signed=True),
                status_label="Risk",
                status_level=_status_for("max_drawdown_abs", abs(max_dd)),
                help_text=KPI_HELP["max_drawdown"],
            )
        with r2:
            week_pnl_units = (week_pnl / unit_dollars) if unit_dollars > 0 else None
            _metric_card(
                "Last 7d PnL (u)",
                _fmt_number(week_pnl_units, digits=2, signed=True),
                status_label="PnL",
                status_level=_status_for("pnl_7d", week_pnl),
                help_text=KPI_HELP["pnl_7d"],
            )
        with r3:
            _metric_card("Last 7d ROI", _fmt_number(week_roi, digits=2, signed=True), status_label="Trend", status_level=_status_for("roi_7d", week_roi), help_text=KPI_HELP["roi_7d"])
        st.caption("Risk note: drawdown is tracked in KPIs; chart removed to reduce redundancy.")

        if "game_pk" in settled_eval.columns:
            game_conc = (
                settled_eval.group_by("game_pk")
                .agg(
                    pl.col("stake").cast(pl.Float64).sum().alias("stake"),
                    pl.col("pnl").cast(pl.Float64).sum().alias("pnl"),
                    pl.len().alias("n_bets"),
                )
                .with_columns((pl.col("pnl") / pl.col("stake")).alias("roi"))
                .sort("stake", descending=True)
            )
            total_stake = float(game_conc["stake"].sum()) if game_conc.height else 0.0
            if total_stake > 0:
                game_conc = game_conc.with_columns(
                    (pl.col("stake") / total_stake).alias("stake_share")
                )
            st.markdown("#### Max Stake Concentration by Game")
            with st.expander("Game concentration detail table"):
                _styled_table(game_conc, limit=15)

with tab_clv:
    st.subheader("Bet and CLV Analysis")
    _section_caption("Validate whether realized outcomes align with expected edge and market-closing quality.")
    if not settled_eval.is_empty() and "clv_pp" in settled_eval.columns:
        clv_rows = settled_eval.filter(pl.col("clv_pp").is_not_null())
        if not clv_rows.is_empty():
            roll_window = st.selectbox(
                "Rolling window (days)",
                options=[7, 14, 21, 30],
                index=1,
                help="Used for smoothed CLV quality overlays.",
            )
            st.caption("Dates are settled game dates; rolling lines use the selected trailing window.")
            by_day_clv = (
                clv_rows.group_by("gdate")
                .agg(
                    pl.len().alias("n_clv"),
                    pl.col("clv_pp").cast(pl.Float64).mean().alias("mean_clv_pp"),
                    (pl.col("clv_pp") > 0).mean().alias("beat_clv_rate"),
                    (pl.col("clv_pp") > 0).sum().alias("beat_n"),
                )
                .sort("gdate")
            )
            by_day_clv = by_day_clv.with_columns(
                pl.col("mean_clv_pp").rolling_mean(window_size=roll_window, min_samples=3).alias("mean_clv_roll"),
                pl.col("beat_clv_rate").rolling_mean(window_size=roll_window, min_samples=3).alias("beat_rate_roll"),
            )
            clv_pdf = by_day_clv.to_pandas()

            fig_clv_mean, ax_clv = plt.subplots(figsize=(11, 4))
            sns.lineplot(data=clv_pdf, x="gdate", y="mean_clv_pp", marker="o", label="Daily mean CLV (pp)", ax=ax_clv)
            sns.lineplot(
                data=clv_pdf,
                x="gdate",
                y="mean_clv_roll",
                label=f"{roll_window}d rolling mean CLV",
                ax=ax_clv,
            )
            ax_clv.axhline(0, color="#9ca3af", linestyle="--", linewidth=1)
            ax_clv.set_title("CLV Mean by Settled Date", color="#111827", fontsize=13)
            _mpl_axes(ax_clv, x_title="Date", y_title="Mean CLV (pp)", legend_title="CLV")
            for lbl in ax_clv.get_xticklabels():
                lbl.set_rotation(45)
                lbl.set_ha("right")
            fig_clv_mean.tight_layout()
            _render_chart(fig_clv_mean)
            st.caption("Interpretation: positive mean CLV suggests pricing edge versus market close.")

            fig_beat, ax_beat = plt.subplots(figsize=(11, 4))
            sns.lineplot(data=clv_pdf, x="gdate", y="beat_clv_rate", marker="o", label="Daily beat-close rate", ax=ax_beat)
            sns.lineplot(data=clv_pdf, x="gdate", y="beat_rate_roll", label=f"{roll_window}d rolling beat rate", ax=ax_beat)
            ax_beat.axhline(0.5, color="#9ca3af", linestyle="--", linewidth=1)
            ax_beat.set_title("Beat-Close Rate by Settled Date", color="#111827", fontsize=13)
            _mpl_axes(ax_beat, x_title="Date", y_title="Beat-Close Rate", legend_title="Beat Rate")
            for lbl in ax_beat.get_xticklabels():
                lbl.set_rotation(45)
                lbl.set_ha("right")
            fig_beat.tight_layout()
            _render_chart(fig_beat)
            st.caption("Interpretation: beat-close rate above 50% is generally favorable.")
            clv_n = clv_rows.height
            st.caption(f"Rigor note: CLV diagnostics are based on {clv_n:,} settled rows with non-null close data.")
            if "gdate" in clv_rows.columns:
                gmin = clv_rows["gdate"].min()
                gmax = clv_rows["gdate"].max()
                st.caption(f"Date window: {gmin} through {gmax}.")

            if {"edge", "stake", "pnl"}.issubset(set(clv_rows.columns)):
                edge_perf = (
                    clv_rows.with_columns(
                        pl.col("edge").cast(pl.Float64),
                        pl.col("stake").cast(pl.Float64),
                        pl.col("pnl").cast(pl.Float64),
                        _edge_bin_expr("edge"),
                    )
                    .group_by("edge_bin")
                    .agg(
                        pl.len().alias("n_clv"),
                        (pl.col("clv_pp").cast(pl.Float64) > 0).sum().alias("beat_n"),
                        pl.col("stake").sum().alias("stake"),
                        pl.col("pnl").sum().alias("pnl"),
                        (pl.col("pnl").sum() / pl.col("stake").sum()).alias("roi"),
                        (
                            (pl.col("edge") * pl.col("stake")).sum() / pl.col("stake").sum()
                        ).alias("expected_roi"),
                        pl.col("clv_pp").cast(pl.Float64).mean().alias("mean_clv_pp"),
                        (pl.col("clv_pp").cast(pl.Float64) > 0).mean().alias("beat_clv_rate"),
                    )
                    .sort("edge_bin")
                )
                st.markdown("#### Edge-Bin Quality")
                edge_pdf = edge_perf.to_pandas().melt(
                    id_vars=["edge_bin"], value_vars=["roi", "expected_roi"], var_name="series", value_name="roi_value"
                )
                fig_edge, ax_edge = plt.subplots(figsize=(11, 4))
                sns.barplot(data=edge_pdf, x="edge_bin", y="roi_value", hue="series", ax=ax_edge)
                ax_edge.axhline(0, color="#9ca3af", linestyle="--", linewidth=1)
                ax_edge.set_title("Realized vs Expected ROI by Edge Bin", color="#111827", fontsize=13)
                _mpl_axes(ax_edge, x_title="Edge Bin", y_title="ROI", legend_title="ROI Series")
                fig_edge.tight_layout()
                _render_chart(fig_edge)
                st.caption("Interpretation: realized vs expected ROI by edge bucket tests model calibration quality.")
                edge_beat_pdf = edge_perf.to_pandas()
                fig_edge_beat, ax_edge_beat = plt.subplots(figsize=(11, 4))
                sns.barplot(data=edge_beat_pdf, x="edge_bin", y="beat_clv_rate", color="#3b82f6", ax=ax_edge_beat)
                ax_edge_beat.axhline(0.5, color="#9ca3af", linestyle="--", linewidth=1)
                ax_edge_beat.set_title("Beat-Close Rate by Edge Bin", color="#111827", fontsize=13)
                _mpl_axes(ax_edge_beat, x_title="Edge Bin", y_title="Beat-Close Rate", legend_title="Beat Rate")
                fig_edge_beat.tight_layout()
                _render_chart(fig_edge_beat)
                st.caption("Interpretation: percent of bets beating close by edge bucket.")
                with st.expander("Detailed diagnostics table: edge-bin quality"):
                    _styled_table(edge_perf, limit=30)

            if "side" in clv_rows.columns:
                side_clv = (
                    clv_rows.group_by("side")
                    .agg(
                        pl.col("clv_pp").cast(pl.Float64).mean().alias("mean_clv_pp"),
                        (pl.col("clv_pp") > 0).mean().alias("beat_clv_rate"),
                        pl.col("pnl").cast(pl.Float64).sum().alias("pnl"),
                    )
                    .sort("side")
                )
                side_pdf = side_clv.to_pandas().melt(
                    id_vars=["side"], value_vars=["mean_clv_pp", "beat_clv_rate"], var_name="metric", value_name="value"
                )
                fig_side, ax_side = plt.subplots(figsize=(11, 4))
                sns.barplot(data=side_pdf, x="side", y="value", hue="metric", ax=ax_side)
                ax_side.set_title("Side-Level CLV Quality", color="#111827", fontsize=13)
                _mpl_axes(ax_side, x_title="Side", y_title="Metric Value", legend_title="CLV Metric")
                fig_side.tight_layout()
                _render_chart(fig_side)
                st.caption("Interpretation: side-level CLV quality helps diagnose structural bias by direction.")
                with st.expander("Detailed diagnostics table: side CLV quality"):
                    _styled_table(side_clv, limit=20)

            if {"edge", "stake", "pnl", "side"}.issubset(set(clv_rows.columns)):
                side_expect = (
                    clv_rows.with_columns(
                        pl.col("edge").cast(pl.Float64),
                        pl.col("stake").cast(pl.Float64),
                        pl.col("pnl").cast(pl.Float64),
                    )
                    .group_by("side")
                    .agg(
                        pl.col("stake").sum().alias("stake"),
                        pl.col("pnl").sum().alias("pnl"),
                        (pl.col("pnl").sum() / pl.col("stake").sum()).alias("roi"),
                        (
                            (pl.col("edge") * pl.col("stake")).sum() / pl.col("stake").sum()
                        ).alias("expected_roi"),
                        pl.col("clv_pp").cast(pl.Float64).mean().alias("mean_clv_pp"),
                    )
                    .sort("side")
                )
                st.markdown("#### Side-Level Realized vs Expected")
                st.caption("Summary across the full settled-date window above; use date window and edge-bin charts for time dynamics.")
                with st.expander("Detailed diagnostics table: side realized vs expected"):
                    _styled_table(side_expect, limit=10)
        else:
            st.info("No CLV-tagged settled rows available yet. Ensure close-price ingestion is running before settlement.")
    else:
        st.info("CLV analysis is unavailable until ledger rows include settled `clv_pp` values.")

    if not graded.is_empty() and {"game_date", "residual_K", "residual_TBF", "residual_k_rate"}.issubset(set(graded.columns)):
        g = (
            graded.with_columns(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gdate"))
            .group_by("gdate")
            .agg(
                pl.col("residual_K").abs().mean().alias("mae_K"),
                pl.col("residual_TBF").abs().mean().alias("mae_TBF"),
                pl.col("residual_k_rate").abs().mean().alias("mae_k_rate"),
            )
            .sort("gdate")
        )
        _plot_line(g, "gdate", ["mae_K", "mae_TBF", "mae_k_rate"], "Projection Error MAE by Date")

with tab_reco:
    st.subheader("Recommended Bets of the Day")
    _section_caption("Review today's actionable bet slate and understand filtering reasons behind excluded candidates.")
    st.caption("Stakeholder view: this section intentionally reports only actionable BET recommendations.")
    if not recommendations.is_empty():
        show = recommendations
        if "recommendation" in show.columns:
            show = show.filter(pl.col("recommendation") == "BET")
        if show.is_empty():
            st.caption("No BET recommendations currently. Check skip reasons and policy settings.")
        else:
            edge_cols = [
                c
                for c in (
                    "recommendation",
                    "pitcher_team",
                    "player_name",
                    "away_team",
                    "home_team",
                    "expected_K",
                    "book",
                    "line",
                    "best_side",
                    "best_price",
                    "edge",
                    "units",
                    "days_rest",
                )
                if c in show.columns
            ]
            view = show.select(edge_cols)
            if "edge" in view.columns:
                view = view.sort("edge", descending=True).drop("edge")
            if "expected_K" in view.columns:
                view = view.with_columns(pl.col("expected_K").cast(pl.Float64).round(3))
            _styled_table(view, limit=200)
        if "oos_reason" in recommendations.columns:
            skipped = recommendations.filter(
                (pl.col("recommendation") != "BET") & pl.col("oos_reason").is_not_null()
            )
            if show_internal_ops and not skipped.is_empty():
                reason_counts = skipped.group_by("oos_reason").agg(pl.len().alias("n")).sort("n", descending=True)
                with st.expander("Internal: skip reason counts"):
                    _styled_table(reason_counts, limit=20)
    else:
        st.caption("No recommendations artifact found yet.")

with tab_cal:
    st.subheader("Calibration and Drift")
    _section_caption("Check model reliability drift before trusting expanded policy scope or promotions.")
    _plot_line(
        scorecard_daily.sort("snapshot_utc"),
        "snapshot_utc",
        ["mae_err_k_rate", "under_bias_tbf", "n_warn"],
        "Calibration Scorecard Metrics by Snapshot Date",
    )
    _plot_line(
        decomp_daily.sort("snapshot_utc"),
        "snapshot_utc",
        ["mae_err_k_rate", "mae_full_k", "bias_tbf_under", "bias_tbf_over"],
        "K Error Decomposition Metrics by Snapshot Date",
    )
    _plot_line(
        cal_hist.sort("snapshot_utc"),
        "snapshot_utc",
        ["mae_err_k_rate", "under_bias_tbf", "n_warn", "n_dates"],
        "Calibration Snapshot History by Date",
    )
    if {"side", "pnl"}.issubset(set(settled_eval.columns)) and not settled_eval.is_empty():
        conf = (
            settled_eval.with_columns(
                pl.col("side").cast(pl.Utf8).str.to_lowercase().alias("pred_side"),
                pl.when(pl.col("pnl").cast(pl.Float64) > 0)
                .then(pl.lit("Win"))
                .otherwise(pl.lit("Loss"))
                .alias("outcome"),
            )
            .filter(pl.col("pred_side").is_in(["over", "under"]))
            .group_by(["pred_side", "outcome"])
            .agg(pl.len().alias("n"))
            .sort(["pred_side", "outcome"])
        )
        if not conf.is_empty():
            conf_pd = conf.to_pandas().pivot(index="pred_side", columns="outcome", values="n").fillna(0)
            fig_conf, ax_conf = plt.subplots(figsize=(6, 3.8))
            sns.heatmap(conf_pd, annot=True, fmt=".0f", cmap="Blues", cbar=False, ax=ax_conf)
            ax_conf.set_title("Outcome Matrix by Recommended Side", color="#111827", fontsize=12)
            _mpl_axes(ax_conf, x_title="Settled Outcome", y_title="Recommended Side", legend_title="Count")
            fig_conf.tight_layout()
            _render_chart(fig_conf)
            st.caption("Interpretation: highlights side-specific win/loss concentration for quick directional diagnostics.")
    if not scorecard_daily.is_empty():
        with st.expander("Latest calibration rows"):
            _styled_table(scorecard_daily.sort("snapshot_utc", descending=True), limit=15)
    else:
        st.info("Calibration trend artifacts are empty. Re-run the calibration snapshot command to restore this view.")

with tab_policy:
    st.subheader("Policy Sweep and Side Guardrails")
    _section_caption("Identify edge-floor settings that balance ROI opportunity and side-risk asymmetry.")
    p0, p1, p2 = st.columns(3)
    with p0:
        _metric_card(
            "Active Operating Profile",
            str(active_profile.get("name") or "n/a"),
            status_label="Live Policy",
            status_level="watch" if action == "RECALIBRATE" else "good",
            help_text="Current profile loaded from production/ops/kpi_policy.json.",
        )
    with p1:
        over_floor = active_profile.get("edge_min_over")
        _metric_card(
            "Over Edge Floor",
            _fmt_number(over_floor, digits=2) if over_floor is not None else _fmt_number(active_profile.get("edge_min"), digits=2),
            status_label="Guardrail",
            status_level="watch" if action == "RECALIBRATE" else "good",
            help_text="Side-specific minimum edge for over recommendations under the active profile.",
        )
    with p2:
        under_floor = active_profile.get("edge_min_under")
        _metric_card(
            "Under Edge Floor",
            _fmt_number(under_floor, digits=2) if under_floor is not None else _fmt_number(active_profile.get("edge_min"), digits=2),
            status_label="Guardrail",
            status_level="watch" if action == "RECALIBRATE" else "good",
            help_text="Side-specific minimum edge for under recommendations under the active profile.",
        )
    if action == "RECALIBRATE":
        blocker_text = ", ".join(str(b) for b in blockers) if blockers else "promotion gate not cleared"
        st.warning(f"Recalibration mode active: thresholds are provisional ({blocker_text}).")
    st.caption(
        "How to read: this section compares threshold policies; goal is positive ROI with enough bet count to remain deployable."
    )
    st.markdown("#### Decision Scoreboard (all vs balanced vs profit_lock)")
    if not decision_scoreboard.is_empty():
        latest_scoreboard = decision_scoreboard.sort("snapshot_utc").tail(3)
        view_cols = [
            c
            for c in (
                "policy",
                "n",
                "realized_roi",
                "xroi_close_ref",
                "xroi_model",
                "mean_clv_pp",
                "pct_positive_clv",
                "roi_ci_lo",
                "roi_ci_hi",
                "clv_ci_lo",
                "clv_ci_hi",
                "rolling_roi_50",
                "max_drawdown_dollars",
            )
            if c in latest_scoreboard.columns
        ]
        _styled_table(latest_scoreboard.select(view_cols), limit=10)
        if validation_ops:
            st.caption(
                f"Promotion CI gate: {validation_ops.get('promotion_ci_gate_pass')} | "
                f"Profit-lock auto-downgrade: {validation_ops.get('profit_lock_auto_downgrade')} | "
                f"Primary benchmark: {validation_ops.get('primary_benchmark', 'xroi_close_ref')}"
            )
            dq_alerts = validation_ops.get("data_quality", {}).get("alerts", [])
            if dq_alerts:
                st.warning(f"Data quality alerts: {', '.join(str(a) for a in dq_alerts)}")
    else:
        st.info("Decision scoreboard is not available yet. Run production/ops/build_validation_ops_report.py.")

    st.markdown("#### Why CAUTION/NO-GO (actionable)")
    if go_no_go:
        status = str(go_no_go.get("status", "n/a"))
        failed_crit = int(go_no_go.get("n_failed_critical_gates") or 0)
        failed_adv = int(go_no_go.get("n_failed_advisory_gates") or 0)
        g0, g1, g2 = st.columns(3)
        g0.metric("Current governance status", status)
        g1.metric("Failed critical gates", failed_crit)
        g2.metric("Failed advisory gates", failed_adv)

        fix_map = {
            "ledger_sync": "Run poll_open from recommendations and verify rec BET count equals ledger BET count for today.",
            "unspecified_segments": "Review UNSPECIFIED segment keys and either map them in deploy matrix or explicitly tolerate them.",
            "data_quality_alerts": "Backfill missing closes and re-run settle so close-reference metrics are trustworthy.",
            "policy_ci_gate": "Keep sizing conservative until ROI and CLV lower CIs improve with more stable settled sample.",
            "volume_gate": "Do not overreact to one slate; accumulate additional slates before changing thresholds.",
            "replay_ci_gate": "Use replay report to test threshold/sizing changes; only promote when ROI lower CI turns non-negative.",
        }
        gate_rows: list[dict[str, Any]] = []
        for gate in go_no_go.get("gates", []):
            if not isinstance(gate, dict):
                continue
            name = str(gate.get("name") or "unknown")
            gate_rows.append(
                {
                    "gate": name,
                    "severity": str(gate.get("severity") or "advisory"),
                    "pass": bool(gate.get("pass")),
                    "detail": json.dumps(gate.get("detail", {})),
                    "next_step": fix_map.get(name, "Review gate detail and re-run governance report."),
                }
            )
        if gate_rows:
            _styled_table(pl.DataFrame(gate_rows), limit=20)
        st.caption(
            "Interpretation: critical gate failures are process blockers (NO-GO); advisory failures indicate confidence/sizing caution, not necessarily no edge."
        )
    else:
        st.info("Governance checklist not available yet. Run production/ops/build_policy_governance_report.py.")

    if policy_replay:
        replay_rows = [
            r
            for r in policy_replay.get("scenarios", [])
            if isinstance(r, dict)
        ]
        if replay_rows:
            st.markdown("#### Counterfactual replay scenarios")
            _styled_table(pl.DataFrame(replay_rows), limit=10)

    latest_sweep = _latest_scenario_rows(policy_sweep)
    if not latest_sweep.is_empty():
        best_row = latest_sweep.sort(["roi", "n_bets"], descending=[True, True]).head(1)
        if not best_row.is_empty():
            br = best_row.to_dicts()[0]
            p1, p2, p3 = st.columns(3)
            p1.metric("Best Sweep ROI", _fmt_number(br.get("roi"), digits=2, signed=True))
            p2.metric("Best Sweep Edge Floor", _fmt_number(br.get("edge_floor"), digits=2))
            p3.metric("Best Sweep Bet Count", _fmt_int(br.get("n_bets")))
        pdf = latest_sweep.to_pandas()
        if "edge_floor" in pdf.columns and len(set(pdf["edge_floor"].tolist())) <= 1:
            st.warning("Policy sweep has only one edge-floor point in this snapshot; run policy simulator sweep to compare thresholds.")
        fig, ax = plt.subplots(figsize=(11, 4))
        sns.lineplot(data=pdf, x="edge_floor", y="roi", hue="scope", marker="o", ax=ax)
        if {"edge_floor", "n_bets", "scope"}.issubset(set(pdf.columns)):
            ax_bets = ax.twinx()
            sns.lineplot(
                data=pdf,
                x="edge_floor",
                y="n_bets",
                hue="scope",
                linestyle="--",
                alpha=0.35,
                legend=False,
                ax=ax_bets,
            )
            ax_bets.set_ylabel("Bet Count", color="#6b7280")
            ax_bets.tick_params(axis="y", colors="#6b7280", labelsize=10)
        ax.axhline(0, color="#9ca3af", linestyle="--", linewidth=1)
        ax.set_title("Policy Sweep: ROI by Edge Floor and Scope", color="#111827", fontsize=13)
        _mpl_axes(ax, x_title="Edge Floor", y_title="ROI", legend_title="Scope")
        fig.tight_layout()
        _render_chart(fig)
        st.caption("Interpretation: pick threshold zones where ROI remains positive without collapsing bet volume.")
        with st.expander("Latest sweep table"):
            _styled_table(latest_sweep.sort(["scope", "edge_floor"]), limit=100)

    if not policy_profile.is_empty():
        prof = policy_profile.sort("snapshot_utc", descending=True).head(50).to_pandas()
        if "n_bets" in prof.columns and not prof.empty:
            st.caption(f"Rigor note: side profile scan uses top {len(prof)} recent profiles; marker size reflects bet count.")
        if show_internal_ops:
            fig2, ax2 = plt.subplots(figsize=(11, 4))
            sns.scatterplot(data=prof, x="over_roi", y="under_roi", hue="is_eligible", size="n_bets", ax=ax2)
            ax2.axvline(0, color="#9ca3af", linestyle="--", linewidth=1)
            ax2.set_title("Policy Side Profile: Over ROI vs Under ROI", color="#111827", fontsize=13)
            _mpl_axes(ax2, x_title="Over ROI", y_title="Under ROI", legend_title="Eligibility")
            fig2.tight_layout()
            _render_chart(fig2)
            st.caption("Interpretation: top-right quadrant indicates both sides profitable; size reflects sample stability.")
        with st.expander("Side profile table"):
            _styled_table(policy_profile.sort(["snapshot_utc", "roi"], descending=[True, True]), limit=50)

with tab_runtime:
    st.subheader("Runtime monitors and automation")
    _section_caption("Track watcher heartbeat, floor calibration, slippage realism, regime stability, and morning alert delivery.")

    watcher = runtime_snapshot.get("watcher", {}) if isinstance(runtime_snapshot, dict) else {}
    watcher_age = _to_float(watcher.get("watcher_heartbeat_age_minutes"))
    w1, w2, w3, w4 = st.columns(4)
    with w1:
        _metric_card(
            "Watcher health",
            "Healthy" if watcher.get("watcher_healthy") else "At risk",
            status_label="Close watcher",
            status_level="good" if watcher.get("watcher_healthy") else "risk",
            help_text="Based on latest close_watcher.log heartbeat age.",
        )
    with w2:
        _metric_card(
            "Watcher heartbeat age",
            f"{watcher_age:.1f}m" if watcher_age is not None else "n/a",
            status_label="Freshness",
            status_level="good" if watcher_age is not None and watcher_age <= 90 else "risk",
            help_text="Minutes since last close watcher log line.",
        )
    with w3:
        _metric_card(
            "Watcher last log",
            str(watcher.get("watcher_last_log_utc") or "n/a"),
            status_label="Timestamp",
            status_level="neutral",
            help_text="UTC timestamp of latest watcher heartbeat.",
        )
    with w4:
        _metric_card(
            "Morning alert",
            "Sent" if morning_alert.get("results") else "Preview/none",
            status_label="Notification",
            status_level="good" if morning_alert.get("results") else "watch",
            help_text="Morning alert output from send_morning_alert.py.",
        )
    aux_hist_rows = _to_int(watcher.get("aux_quote_history_rows")) if isinstance(watcher, dict) else None
    aux_last = str(watcher.get("aux_quote_last_logged_utc") or "n/a") if isinstance(watcher, dict) else "n/a"
    st.caption(
        f"Aux quote history rows: {_fmt_int(aux_hist_rows)} | last logged: {aux_last}"
    )

    aux_probe = watcher.get("aux_market_probe", {}) if isinstance(watcher, dict) else {}
    aux_markets = aux_probe.get("markets", {}) if isinstance(aux_probe, dict) else {}
    if aux_markets:
        st.markdown("#### Non-K market quote coverage (watcher probe)")
        a1, a2, a3 = st.columns(3)
        outs_rows = _to_int((aux_markets.get("outs") or {}).get("quote_rows")) if isinstance(aux_markets, dict) else None
        hits_rows = _to_int((aux_markets.get("hits_allowed") or {}).get("quote_rows")) if isinstance(aux_markets, dict) else None
        walks_rows = _to_int((aux_markets.get("walks_allowed") or {}).get("quote_rows")) if isinstance(aux_markets, dict) else None
        with a1:
            _metric_card(
                "Outs quotes",
                _fmt_int(outs_rows),
                status_label="Coverage",
                status_level="good" if (outs_rows or 0) > 0 else "watch",
                help_text="Latest watcher probe row count for pitcher-outs markets.",
            )
        with a2:
            _metric_card(
                "Hits allowed quotes",
                _fmt_int(hits_rows),
                status_label="Coverage",
                status_level="good" if (hits_rows or 0) > 0 else "watch",
                help_text="Latest watcher probe row count for pitcher-hits-allowed markets.",
            )
        with a3:
            _metric_card(
                "Walks allowed quotes",
                _fmt_int(walks_rows),
                status_label="Coverage",
                status_level="good" if (walks_rows or 0) > 0 else "watch",
                help_text="Latest watcher probe row count for pitcher-walks-allowed markets.",
            )
        st.caption(f"Latest aux probe: {aux_probe.get('probed_utc', 'n/a')} | book={aux_probe.get('book', 'all')}")

    st.markdown("#### Floor calibration (settled rows since 2026-07-31)")
    if not runtime_floor.is_empty():
        _styled_table(runtime_floor.sort(["policy_mode", "edge_floor"], descending=[False, False], nulls_last=True), limit=20)
    else:
        st.info("No runtime floor calibration artifact yet. Run build_runtime_monitoring_snapshot.py.")

    st.markdown("#### Slippage realism by segment")
    if not runtime_slip.is_empty():
        _styled_table(runtime_slip.sort("n", descending=True), limit=40)
    else:
        st.info("No slippage segment artifact yet.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Regime stability by month")
        if not runtime_month.is_empty():
            _styled_table(runtime_month.sort("year_month"), limit=24)
        else:
            st.caption("No monthly regime table yet.")
    with c2:
        st.markdown("#### Edge-decile stability")
        if not runtime_edge.is_empty():
            _styled_table(runtime_edge.sort("edge_decile"), limit=20)
        else:
            st.caption("No edge-decile table yet.")

    st.markdown("#### Decision diagnostics (why BET / NO_BET)")
    if not runtime_decision.is_empty():
        _styled_table(runtime_decision, limit=200)
    else:
        st.caption("No decision diagnostics artifact yet.")

    st.markdown("#### Ops SLO snapshot")
    if runtime_slo:
        st.json(runtime_slo)
    else:
        st.caption("No runtime_ops_slo_snapshot.json found yet.")

    st.markdown("#### Shadow scorer (outs/hits/walks)")
    if aux_shadow_meta:
        st.caption(f"Shadow scorer status: {aux_shadow_meta.get('status', 'n/a')}")
    if not aux_shadow_summary.is_empty():
        _styled_table(aux_shadow_summary, limit=20)
    else:
        st.caption("No aux_market_shadow_summary.csv found yet.")
    if automation_self_check:
        st.markdown("#### Automation self-check")
        st.json(automation_self_check)

if tab_ops is not None:
    with tab_ops:
        st.subheader("Ops Artifact Health")
        _section_caption("Confirm automation and artifact integrity so business and model conclusions are operationally trustworthy.")
        _styled_table(artifact_health, limit=50)

        st.markdown("#### Automation Status")
        task_names = [
            "MLBProps_MorningWorkflow",
            "MLBProps_MiddayRefresh",
            "MLBProps_SecondRefresh",
            "MLBProps_CloseWatcherStart",
            "MLBProps_CloseWatcherWatchdog",
            "MLBProps_EndOfDaySettle",
            "MLBProps_MorningAlert",
            "MLBProps_AutomationSelfCheck",
        ]
        task_rows = pl.DataFrame([_scheduled_task_status(t) for t in task_names])
        if not task_rows.is_empty():
            task_rows = task_rows.with_columns(
                pl.struct(task_rows.columns)
                .map_elements(
                    lambda r: _automation_health_row(dict(r))[0],
                    return_dtype=pl.Utf8,
                )
                .alias("health"),
                pl.struct(task_rows.columns)
                .map_elements(
                    lambda r: _automation_health_row(dict(r))[1],
                    return_dtype=pl.Utf8,
                )
                .alias("health_level"),
            )
        _styled_table(task_rows, limit=10)

        missed_note = _missed_morning_run_note(kpi_loop, expected_hour=8, expected_minute=30)
        if missed_note:
            st.caption(f"Schedule note: {missed_note}")
        else:
            st.caption("Schedule note: morning run check looks on track.")

        stale_keys: list[str] = []
        if not artifact_health.is_empty() and {"artifact", "age_hours", "exists"}.issubset(set(artifact_health.columns)):
            stale_keys = (
                artifact_health.filter(
                    (pl.col("exists") == True) & (pl.col("age_hours").is_not_null()) & (pl.col("age_hours") > 24)
                )
                .get_column("artifact")
                .to_list()
            )
        if stale_keys:
            st.warning(f"Stale artifacts detected: {', '.join(str(x) for x in stale_keys)}")
        if st.button("Auto-Remediate Stale Artifacts", type="primary"):
            with st.spinner("Refreshing artifacts (daily loop + calibration + policy) ..."):
                ok, output = _auto_remediate_stale_artifacts()
            if ok:
                st.success("Stale artifact remediation completed. Refresh dashboard to see updated health.")
            else:
                st.error("Remediation encountered an error. Review logs below.")
            with st.expander("Remediation execution log", expanded=not ok):
                st.code(output or "(no output)")
