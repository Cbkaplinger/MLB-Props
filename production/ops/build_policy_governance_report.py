"""Build counterfactual replay + daily go/no-go governance artifacts.

Outputs:
- artifacts/odds_log/policy_replay_daily.json
- artifacts/odds_log/policy_replay_scenarios_latest.csv
- artifacts/odds_log/go_no_go_checklist_daily.json
- artifacts/odds_log/go_no_go_checklist_latest.csv
"""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path
import sys

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.kpi_policy import DEFAULT_POLICY_PATH, load_kpi_policy  # noqa: E402
from Python.market import bankroll_from_unit, bootstrap_mean_ci, devig_two_way  # noqa: E402
from Python.notebook_analysis_utils import keep_best_available_lines  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"
LEDGER_PATH = ODDS_DIR / "ledger.parquet"
RECS_PATH = ODDS_DIR / "recommendations.parquet"
VALIDATION_PATH = ODDS_DIR / "validation_ops_daily.json"
LINE_FLOOR_PATH = (
    ROOT / "production" / "ops" / "market_research" / "line_floor_policy.json"
)

REPLAY_JSON = ODDS_DIR / "policy_replay_daily.json"
REPLAY_CSV = ODDS_DIR / "policy_replay_scenarios_latest.csv"
CHECKLIST_JSON = ODDS_DIR / "go_no_go_checklist_daily.json"
CHECKLIST_CSV = ODDS_DIR / "go_no_go_checklist_latest.csv"

UNIT_DOLLARS_DEFAULT = 50.0
MC_PATH_SIMS = 2000
MC_PATH_BETS = 250
MC_DRAWDOWN_RUIN_PCT = 0.50
MC_BANKROLL_RUIN_FLOOR = 0.10


def _safe_float(v: object) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _load_line_floors() -> tuple[dict[str, float], float]:
    if not LINE_FLOOR_PATH.exists():
        return {}, 0.12
    try:
        payload = json.loads(LINE_FLOOR_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}, 0.12
    raw = payload.get("line_edge_floors", {}) if isinstance(payload, dict) else {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        fv = _safe_float(v)
        if fv is not None:
            out[str(k)] = float(fv)
    fallback = _safe_float(payload.get("default_fallback_edge_floor")) if isinstance(payload, dict) else None
    return out, float(fallback if fallback is not None else 0.12)


def _line_key(v: object) -> str:
    fv = _safe_float(v)
    return f"{float(fv):.1f}" if fv is not None else ""


def _result_to_y_from_value(res: object) -> float | None:
    s = str(res or "").strip().lower()
    if s == "win":
        return 1.0
    if s == "loss":
        return 0.0
    return None


def _price_payout_ratio(price: float) -> float | None:
    if price == 0:
        return None
    if price > 0:
        return price / 100.0
    return 100.0 / abs(price)


def _returns_per_dollar(row: dict[str, object]) -> float | None:
    y = _result_to_y_from_value(row.get("result"))
    if y is None:
        return None
    price = _safe_float(row.get("bet_price"))
    if price is None:
        return None
    b = _price_payout_ratio(price)
    if b is None:
        return None
    if y >= 1.0:
        return float(b)
    return -1.0


def _close_side_prob(row: dict[str, object]) -> float | None:
    over = _safe_float(row.get("close_over"))
    under = _safe_float(row.get("close_under"))
    side = str(row.get("side") or "")
    if over is None or under is None or side not in {"over", "under"}:
        return None
    try:
        p_over, p_under = devig_two_way(over, under)
    except Exception:
        return None
    return float(p_over if side == "over" else p_under)


def _result_to_y_from_row(row: dict[str, object]) -> float | None:
    return _result_to_y_from_value(row.get("result"))


def _bootstrap_ci(vals: list[float], *, min_n: int = 25) -> tuple[float | None, float | None, float | None]:
    if len(vals) < min_n:
        return None, None, None
    mean, lo, hi = bootstrap_mean_ci(vals, n_boot=1200, seed=11)
    return float(mean), float(lo), float(hi)


def _mc_ruin_proxy(
    returns_on_bankroll: list[float],
    *,
    n_sims: int = MC_PATH_SIMS,
    n_bets: int = MC_PATH_BETS,
    ruin_floor: float = MC_BANKROLL_RUIN_FLOOR,
    drawdown_ruin_pct: float = MC_DRAWDOWN_RUIN_PCT,
) -> dict[str, float | int | None]:
    if not returns_on_bankroll:
        return {
            "mc_n_sims": int(n_sims),
            "mc_n_bets": int(n_bets),
            "mc_ruin_floor": float(ruin_floor),
            "mc_drawdown_ruin_pct": float(drawdown_ruin_pct),
            "mc_prob_bankroll_floor_breach": None,
            "mc_prob_drawdown_breach": None,
            "mc_median_terminal_bankroll": None,
            "mc_p10_terminal_bankroll": None,
        }

    rng = random.Random(17)
    floor_hits = 0
    dd_hits = 0
    terminals: list[float] = []
    dd_floor = 1.0 - float(drawdown_ruin_pct)

    for _ in range(int(n_sims)):
        br = 1.0
        peak = 1.0
        hit_floor = False
        hit_dd = False
        for _ in range(int(n_bets)):
            r = returns_on_bankroll[rng.randrange(len(returns_on_bankroll))]
            br = br * (1.0 + float(r))
            if br <= float(ruin_floor):
                hit_floor = True
            if br > peak:
                peak = br
            if peak > 0 and (br / peak) <= dd_floor:
                hit_dd = True
        terminals.append(br)
        if hit_floor:
            floor_hits += 1
        if hit_dd:
            dd_hits += 1

    terminals_sorted = sorted(terminals)
    if terminals_sorted:
        med_i = len(terminals_sorted) // 2
        p10_i = max(0, int(0.10 * len(terminals_sorted)) - 1)
        med = float(terminals_sorted[med_i])
        p10 = float(terminals_sorted[p10_i])
    else:
        med = None
        p10 = None

    return {
        "mc_n_sims": int(n_sims),
        "mc_n_bets": int(n_bets),
        "mc_ruin_floor": float(ruin_floor),
        "mc_drawdown_ruin_pct": float(drawdown_ruin_pct),
        "mc_prob_bankroll_floor_breach": float(floor_hits) / float(n_sims),
        "mc_prob_drawdown_breach": float(dd_hits) / float(n_sims),
        "mc_median_terminal_bankroll": med,
        "mc_p10_terminal_bankroll": p10,
    }


def _score_scenario(frame: pl.DataFrame, stake_expr: pl.Expr, label: str) -> dict[str, object]:
    if frame.is_empty():
        return {"scenario": label, "n": 0}
    scored = frame.with_columns(stake_expr.alias("stake_scenario")).filter(
        pl.col("stake_scenario").cast(pl.Float64) > 0
    )
    if scored.is_empty():
        return {"scenario": label, "n": 0}
    scored = scored.with_columns(
        (pl.col("stake_scenario") * pl.col("rpd")).alias("pnl_scenario"),
        (pl.col("stake_scenario") * pl.col("rpd")).cast(pl.Float64).alias("pnl_scenario_f"),
        pl.when(pl.col("clv_pp").is_not_null())
        .then(pl.col("clv_pp").cast(pl.Float64))
        .otherwise(None)
        .alias("clv_pp_f"),
    )
    stake = float(scored["stake_scenario"].cast(pl.Float64).sum())
    pnl = float(scored["pnl_scenario"].cast(pl.Float64).sum())
    roi = (pnl / stake) if stake > 0 else None
    clv_vals = [float(v) for v in scored["clv_pp_f"].to_list() if v is not None]
    roi_vals = [float(v) for v in scored["rpd"].to_list() if v is not None]
    roi_mean, roi_lo, roi_hi = _bootstrap_ci(roi_vals)
    clv_mean, clv_lo, clv_hi = _bootstrap_ci(clv_vals)
    bankroll_anchor = bankroll_from_unit(UNIT_DOLLARS_DEFAULT)
    returns_on_bankroll = [
        float(v) / float(bankroll_anchor)
        for v in scored["pnl_scenario_f"].to_list()
        if v is not None
    ]
    log_returns = [math.log1p(r) for r in returns_on_bankroll if (1.0 + float(r)) > 0.0]
    geom_growth = (sum(log_returns) / len(log_returns)) if log_returns else None
    ruin_proxy = _mc_ruin_proxy(returns_on_bankroll)
    return {
        "scenario": label,
        "n": int(scored.height),
        "stake": stake,
        "pnl": pnl,
        "roi": roi,
        "roi_ci_mean": roi_mean,
        "roi_ci_lo": roi_lo,
        "roi_ci_hi": roi_hi,
        "clv_mean_pp": (sum(clv_vals) / len(clv_vals)) if clv_vals else None,
        "clv_pos_rate": (
            sum(1 for v in clv_vals if v > 0) / len(clv_vals)
            if clv_vals
            else None
        ),
        "clv_ci_mean": clv_mean,
        "clv_ci_lo": clv_lo,
        "clv_ci_hi": clv_hi,
        "bankroll_anchor_for_growth": float(bankroll_anchor),
        "geo_growth_log_mean": float(geom_growth) if geom_growth is not None else None,
        **ruin_proxy,
    }


def _calibration_metrics(frame: pl.DataFrame) -> dict[str, object]:
    out: dict[str, object] = {}
    if frame.is_empty():
        return out
    for pcol in ("p_model", "p_market", "p_close"):
        if pcol not in frame.columns:
            continue
        scoped = frame.filter(
            pl.col(pcol).is_not_null()
            & pl.col("y").is_not_null()
            & pl.col(pcol).cast(pl.Float64).is_between(1e-6, 1 - 1e-6, closed="both")
        )
        if scoped.is_empty():
            continue
        probs = pl.col(pcol).cast(pl.Float64)
        y = pl.col("y").cast(pl.Float64)
        brier = float(scoped.select(((probs - y) ** 2).mean().alias("m")).item())
        logloss = float(
            scoped.select(
                (
                    -(
                        y * probs.clip(1e-6, 1 - 1e-6).log()
                        + (1.0 - y) * (1.0 - probs.clip(1e-6, 1 - 1e-6)).log()
                    )
                )
                .mean()
                .alias("m")
            ).item()
        )
        out[pcol] = {
            "n": int(scoped.height),
            "brier": brier,
            "logloss": logloss,
            "mean_prob": float(scoped.select(pl.col(pcol).cast(pl.Float64).mean()).item()),
            "hit_rate": float(scoped.select(pl.col("y").cast(pl.Float64).mean()).item()),
        }
    return out


def _eligible_current_policy(
    ledger: pl.DataFrame,
    *,
    roi_mode: str,
    line_floors: dict[str, float],
    fallback_floor: float,
) -> pl.DataFrame:
    base_by_mode = {
        "aggressive": 0.12,
        "balanced": 0.16,
        "conservative": 0.18,
        "profit_lock": 0.18,
    }
    base_floor = float(base_by_mode.get(roi_mode, 0.16))
    side_floor_over = 0.22 if roi_mode == "profit_lock" else None
    side_floor_under = 0.18 if roi_mode == "profit_lock" else None

    out = ledger.with_columns(
        pl.col("line").map_elements(_line_key, return_dtype=pl.Utf8).alias("line_key"),
        pl.col("line")
        .map_elements(lambda v: float(line_floors.get(_line_key(v), fallback_floor)), return_dtype=pl.Float64)
        .alias("line_floor_current"),
        pl.lit(base_floor).alias("base_floor_current"),
    ).with_columns(
        pl.max_horizontal("line_floor_current", "base_floor_current").alias("floor_current")
    )
    if side_floor_over is not None and side_floor_under is not None and "side" in out.columns:
        out = out.with_columns(
            pl.when(pl.col("side") == "over")
            .then(pl.lit(float(side_floor_over)))
            .otherwise(pl.lit(float(side_floor_under)))
            .alias("side_floor_current")
        ).with_columns(
            pl.max_horizontal("floor_current", "side_floor_current").alias("floor_current")
        )
    return out.with_columns(
        (pl.col("edge").cast(pl.Float64) >= pl.col("floor_current").cast(pl.Float64)).alias(
            "passes_current_policy"
        )
    )


def _checklist(
    *,
    replay: dict[str, object],
    validation: dict[str, object],
    recs: pl.DataFrame,
    ledger: pl.DataFrame,
    sparse_min_bets: int = 1,
    max_unspecified_segments: int = 4,
) -> dict[str, object]:
    today = None
    if not recs.is_empty() and "game_date" in recs.columns:
        today = str(recs.select(pl.col("game_date").cast(pl.Utf8).max()).item())[:10]
    rec_today = (
        recs.with_columns(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gdate"))
        .filter(pl.col("gdate") == today)
        if today is not None and not recs.is_empty()
        else pl.DataFrame()
    )
    rec_bets = (
        int(rec_today.filter(pl.col("recommendation") == "BET").height)
        if not rec_today.is_empty() and "recommendation" in rec_today.columns
        else 0
    )
    led_today = (
        ledger.with_columns(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gdate"))
        .filter(
            (pl.col("gdate") == today)
            & (pl.col("snapshot").cast(pl.Utf8).is_in(["open", "bet"]))
        )
        if today is not None and not ledger.is_empty() and "snapshot" in ledger.columns
        else pl.DataFrame()
    )
    led_bets = (
        int(
            led_today.filter(
                pl.col("passes_floor").cast(pl.Boolean).fill_null(False)
                & (pl.col("stake").cast(pl.Float64).fill_null(0.0) > 0)
            ).height
        )
        if not led_today.is_empty()
        else 0
    )
    sync_ok = rec_bets == led_bets

    unspec = (
        int(rec_today.filter(pl.col("segment_state").cast(pl.Utf8) == "UNSPECIFIED").height)
        if not rec_today.is_empty() and "segment_state" in rec_today.columns
        else 0
    )
    dq_alerts = (
        validation.get("data_quality", {}).get("alerts", [])
        if isinstance(validation.get("data_quality", {}), dict)
        else []
    )
    ci_pass = bool(validation.get("promotion_ci_gate_pass"))
    bet_volume_ok = rec_bets >= int(sparse_min_bets)

    replay_scenarios = replay.get("scenarios", []) if isinstance(replay.get("scenarios"), list) else []
    current = next((s for s in replay_scenarios if s.get("scenario") == "current_policy_flat_1u"), None)
    roi_ci_lo = current.get("roi_ci_lo") if isinstance(current, dict) else None
    clv_ci_lo = current.get("clv_ci_lo") if isinstance(current, dict) else None
    replay_ci_ok = (
        roi_ci_lo is not None
        and clv_ci_lo is not None
        and float(roi_ci_lo) > 0.0
        and float(clv_ci_lo) > 0.0
    )

    # Critical = process integrity blockers. Advisory = confidence/sizing guidance.
    dq_critical = [a for a in dq_alerts if a in {"stale_quotes", "unmatched_rate_high"}]
    gates = [
        {
            "name": "ledger_sync",
            "severity": "critical",
            "pass": bool(sync_ok),
            "detail": {"recs_bets": rec_bets, "ledger_bets": led_bets},
        },
        {
            "name": "unspecified_segments",
            "severity": "advisory",
            "pass": bool(unspec <= int(max_unspecified_segments)),
            "detail": {"count": unspec, "max_allowed": int(max_unspecified_segments)},
        },
        {
            "name": "data_quality_alerts",
            "severity": "critical",
            "pass": bool(len(dq_critical) == 0),
            "detail": {
                "alerts_all": dq_alerts,
                "alerts_critical": dq_critical,
            },
        },
        {
            "name": "policy_ci_gate",
            "severity": "advisory",
            "pass": bool(ci_pass),
            "detail": {"promotion_ci_gate_pass": ci_pass},
        },
        {
            "name": "volume_gate",
            "severity": "advisory",
            "pass": bool(bet_volume_ok),
            "detail": {"n_bets_today": rec_bets, "min_required": sparse_min_bets},
        },
        {
            "name": "replay_ci_gate",
            "severity": "advisory",
            "pass": bool(replay_ci_ok),
            "detail": {"roi_ci_lo": roi_ci_lo, "clv_ci_lo": clv_ci_lo},
        },
    ]
    critical_fails = sum(
        1 for g in gates if (g.get("severity") == "critical" and not g["pass"])
    )
    advisory_fails = sum(
        1 for g in gates if (g.get("severity") != "critical" and not g["pass"])
    )
    n_fail = critical_fails + advisory_fails
    status = "NO_GO" if critical_fails > 0 else ("CAUTION" if advisory_fails > 0 else "GO")
    return {
        "status": status,
        "n_failed_gates": n_fail,
        "n_failed_critical_gates": critical_fails,
        "n_failed_advisory_gates": advisory_fails,
        "today": today,
        "gates": gates,
    }


def main() -> None:
    policy = load_kpi_policy(DEFAULT_POLICY_PATH)
    ops = policy.get("ops_validation", {})
    roi_mode = str(ops.get("default_roi_mode", "balanced"))
    line_floors, fallback_floor = _load_line_floors()

    if not LEDGER_PATH.exists():
        raise SystemExit(f"missing ledger: {LEDGER_PATH}")
    ledger = pl.read_parquet(LEDGER_PATH)
    if ledger.is_empty():
        raise SystemExit("ledger is empty")

    core = ledger.filter(
        (pl.col("snapshot").cast(pl.Utf8) == "bet")
        & pl.col("edge").is_not_null()
        & pl.col("bet_price").is_not_null()
        & pl.col("result").is_not_null()
    )
    core = keep_best_available_lines(core)
    core = _eligible_current_policy(
        core, roi_mode=roi_mode, line_floors=line_floors, fallback_floor=fallback_floor
    )
    core = core.with_columns(
        pl.struct(pl.all()).map_elements(_returns_per_dollar, return_dtype=pl.Float64).alias("rpd"),
        pl.struct(pl.all()).map_elements(_result_to_y_from_row, return_dtype=pl.Float64).alias("y"),
        pl.struct(pl.all()).map_elements(_close_side_prob, return_dtype=pl.Float64).alias("p_close"),
    ).filter(pl.col("rpd").is_not_null())

    historical_bets = core.filter(
        pl.col("passes_floor").cast(pl.Boolean).fill_null(False)
        & (pl.col("stake").cast(pl.Float64).fill_null(0.0) > 0)
    )
    current_policy = core.filter(pl.col("passes_current_policy"))

    scenarios = [
        _score_scenario(
            historical_bets,
            pl.col("stake").cast(pl.Float64),
            "historical_actual_stake",
        ),
        _score_scenario(
            current_policy,
            pl.lit(50.0),
            "current_policy_flat_1u",
        ),
        _score_scenario(
            current_policy,
            pl.when(pl.col("edge").cast(pl.Float64) >= 0.15)
            .then(pl.lit(75.0))
            .otherwise(pl.lit(50.0)),
            "current_policy_1p5u_over_15pct",
        ),
        _score_scenario(
            current_policy,
            pl.when(pl.col("edge").cast(pl.Float64) >= 0.18)
            .then(pl.lit(100.0))
            .otherwise(pl.lit(50.0)),
            "current_policy_2u_over_18pct",
        ),
    ]
    sc_df = pl.DataFrame(scenarios).with_columns(
        pl.lit(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")).alias("snapshot_utc")
    )
    sc_df.write_csv(REPLAY_CSV)

    calibration = _calibration_metrics(current_policy)
    kelly_diag = {}
    if not historical_bets.is_empty() and "kelly_frac" in historical_bets.columns:
        scoped = historical_bets.filter(pl.col("kelly_frac").is_not_null()).with_columns(
            pl.col("kelly_frac").cast(pl.Float64).alias("kelly_f")
        )
        if not scoped.is_empty():
            corr = scoped.select(pl.corr("kelly_f", "rpd")).item()
            kelly_diag = {
                "n": int(scoped.height),
                "corr_kelly_to_return_per_dollar": float(corr) if corr is not None and not math.isnan(float(corr)) else None,
                "mean_kelly_frac": float(scoped.select(pl.col("kelly_f").mean()).item()),
            }

    replay = {
        "snapshot_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "roi_mode": roi_mode,
        "dedupe_method": "keep_best_available_lines(game_date, player_name, side)",
        "base_counts": {
            "core_rows": int(core.height),
            "historical_bet_rows": int(historical_bets.height),
            "current_policy_rows": int(current_policy.height),
        },
        "scenarios": scenarios,
        "calibration_on_current_policy_rows": calibration,
        "kelly_diagnostic_on_historical_bets": kelly_diag,
    }
    REPLAY_JSON.write_text(json.dumps(replay, indent=2), encoding="utf-8")

    validation = {}
    if VALIDATION_PATH.exists():
        try:
            validation = json.loads(VALIDATION_PATH.read_text(encoding="utf-8"))
        except Exception:
            validation = {}
    recs = pl.read_parquet(RECS_PATH) if RECS_PATH.exists() else pl.DataFrame()
    checklist = _checklist(
        replay=replay,
        validation=validation,
        recs=recs,
        ledger=ledger,
        sparse_min_bets=int(ops.get("min_bets_today", 1)),
        max_unspecified_segments=int(ops.get("max_unspecified_segments", 4)),
    )
    checklist_payload = {
        "snapshot_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **checklist,
    }
    CHECKLIST_JSON.write_text(json.dumps(checklist_payload, indent=2), encoding="utf-8")
    checklist_row = {
        "snapshot_utc": checklist_payload["snapshot_utc"],
        "status": checklist_payload["status"],
        "n_failed_gates": checklist_payload["n_failed_gates"],
        "n_failed_critical_gates": checklist_payload.get("n_failed_critical_gates"),
        "n_failed_advisory_gates": checklist_payload.get("n_failed_advisory_gates"),
        "today": checklist_payload.get("today"),
    }
    for gate in checklist_payload.get("gates", []):
        checklist_row[f"gate_{gate.get('name')}"] = bool(gate.get("pass"))
    pl.DataFrame([checklist_row]).write_csv(CHECKLIST_CSV)

    print(f"wrote {REPLAY_JSON}")
    print(f"wrote {REPLAY_CSV}")
    print(f"wrote {CHECKLIST_JSON}")
    print(f"wrote {CHECKLIST_CSV}")


if __name__ == "__main__":
    main()
