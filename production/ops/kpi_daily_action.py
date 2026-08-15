"""Print daily KPI-driven recommended action from latest scorecard snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.kpi_policy import DEFAULT_POLICY_PATH, load_kpi_policy  # noqa: E402

SCORECARD_PATH = ROOT / "artifacts" / "odds_log" / "model_health_scorecard_daily.parquet"
DECOMP_PATH = ROOT / "artifacts" / "odds_log" / "k_error_decomposition.parquet"
LEDGER_PATH = ROOT / "artifacts" / "odds_log" / "ledger.parquet"


def _action_for_latest(latest: dict, *, policy: dict) -> tuple[str, list[str]]:
    kpi = policy.get("kpi", {})
    states = policy.get("state_actions", {})
    reasons: list[str] = []

    n_warn = int(latest.get("n_warn") or 0)
    mae = float(latest.get("mae_err_k_rate") or 0.0)
    under_bias = float(latest.get("under_bias_tbf") or 0.0)
    n_joined = int(latest.get("n_joined") or 0)

    if n_joined < int(kpi.get("min_joined", 100)):
        return "ACCUMULATE", [f"n_joined<{int(kpi.get('min_joined', 100))}"]

    if mae > float(kpi.get("mae_k_rate_warn", 0.075)):
        reasons.append("k_rate_calibration_warn")
    if abs(under_bias) > float(kpi.get("abs_under_tbf_bias_warn", 1.5)):
        reasons.append("under_tbf_bias_warn")

    healthy_max = int(states.get("healthy_max_warn", 1))
    caution_max = int(states.get("caution_max_warn", 3))
    if n_warn <= healthy_max and not reasons:
        return "ACCUMULATE", ["scorecard_healthy"]
    if "k_rate_calibration_warn" in reasons:
        return "RECALIBRATE", reasons
    if "under_tbf_bias_warn" in reasons:
        return "TBF_FIX", reasons
    if n_warn <= caution_max:
        return "GATE_CAUTION", ["multi_warn_state"]
    return "GATE_STRICT", ["risk_state"]


def _over_clv_health() -> tuple[float | None, int]:
    if not LEDGER_PATH.exists():
        return None, 0
    led = pl.read_parquet(LEDGER_PATH)
    if led.is_empty():
        return None, 0
    over = led.filter(
        (pl.col("status") == "settled")
        & (pl.col("side") == "over")
        & pl.col("clv_pp").is_not_null()
        & (pl.col("stake").cast(pl.Float64).fill_null(0.0) > 0.0)
    )
    if over.is_empty():
        return None, 0
    return float(over["clv_pp"].cast(pl.Float64).mean()), int(over.height)


def _promotion_gate_status(
    latest: dict,
    *,
    policy: dict,
    n_dates: int,
) -> tuple[bool, list[str], dict[str, object]]:
    cfg = policy.get("recalibration_promotion", {})
    kpi = policy.get("kpi", {})
    min_dates = int(cfg.get("min_dates", kpi.get("chrono_min_dates", 15)))
    max_warn = int(cfg.get("max_warn_for_promotion", 1))
    require_k_rate_below_warn = bool(cfg.get("require_k_rate_below_warn", True))
    require_non_negative_over_clv = bool(cfg.get("require_non_negative_over_clv_pp", True))
    min_over_clv_samples = int(cfg.get("min_over_clv_samples", 20))
    k_rate_warn = float(kpi.get("mae_k_rate_warn", 0.075))

    over_clv_pp, over_clv_n = _over_clv_health()
    blockers: list[str] = []

    n_warn = int(latest.get("n_warn") or 0)
    mae = float(latest.get("mae_err_k_rate") or 0.0)
    if n_dates < min_dates:
        blockers.append(f"n_dates<{min_dates}")
    if n_warn > max_warn:
        blockers.append(f"n_warn>{max_warn}")
    if require_k_rate_below_warn and mae > k_rate_warn:
        blockers.append(f"mae_err_k_rate>{k_rate_warn:.3f}")
    if require_non_negative_over_clv:
        if over_clv_n < min_over_clv_samples:
            blockers.append(f"over_clv_n<{min_over_clv_samples}")
        elif over_clv_pp is not None and over_clv_pp < 0.0:
            blockers.append("over_mean_clv_pp<0")

    detail: dict[str, object] = {
        "promotion_min_dates": min_dates,
        "promotion_max_warn": max_warn,
        "promotion_k_rate_warn_threshold": k_rate_warn,
        "promotion_over_clv_n": over_clv_n,
        "promotion_over_mean_clv_pp": over_clv_pp,
        "promotion_min_over_clv_samples": min_over_clv_samples,
    }
    return len(blockers) == 0, blockers, detail


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kpi-policy", type=str, default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    policy = load_kpi_policy(args.kpi_policy)
    out: dict[str, object] = {
        "scorecard_path": str(SCORECARD_PATH),
        "policy_path": str(Path(args.kpi_policy)),
    }

    if not SCORECARD_PATH.exists():
        out.update({"status": "missing_scorecard", "action": "RUN_DASHBOARD"})
    else:
        score = pl.read_parquet(SCORECARD_PATH).sort("snapshot_utc")
        if score.is_empty():
            out.update({"status": "empty_scorecard", "action": "RUN_DASHBOARD"})
        else:
            latest = score.tail(1).to_dicts()[0]
            action, reasons = _action_for_latest(latest, policy=policy)
            n_dates = 0
            if DECOMP_PATH.exists():
                d = pl.read_parquet(DECOMP_PATH)
                if "game_date" in d.columns:
                    n_dates = int(
                        d.select(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).n_unique()).item()
                    )
            chrono_min = int(policy.get("kpi", {}).get("chrono_min_dates", 24))
            out.update(
                {
                    "status": "ok",
                    "action": action,
                    "reasons": reasons,
                    "n_warn": int(latest.get("n_warn") or 0),
                    "mae_err_k_rate": float(latest.get("mae_err_k_rate") or 0.0),
                    "under_bias_tbf": float(latest.get("under_bias_tbf") or 0.0),
                    "n_joined": int(latest.get("n_joined") or 0),
                    "n_dates": n_dates,
                    "chrono_min_dates": chrono_min,
                    "chrono_days_remaining": max(0, chrono_min - n_dates),
                }
            )
            promote_ready, blockers, detail = _promotion_gate_status(
                latest, policy=policy, n_dates=n_dates
            )
            out["recalibration_promote_ready"] = promote_ready
            out["recalibration_promote_blockers"] = blockers
            out.update(detail)

    if args.json:
        print(json.dumps(out, indent=2))
        return

    print("--- daily KPI action ---")
    for key in (
        "status",
        "action",
        "reasons",
        "n_warn",
        "mae_err_k_rate",
        "under_bias_tbf",
        "n_joined",
        "n_dates",
        "chrono_days_remaining",
        "recalibration_promote_ready",
        "recalibration_promote_blockers",
    ):
        if key in out:
            print(f"{key}: {out[key]}")


if __name__ == "__main__":
    main()

