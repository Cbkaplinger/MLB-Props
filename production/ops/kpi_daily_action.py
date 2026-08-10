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
    ):
        if key in out:
            print(f"{key}: {out[key]}")


if __name__ == "__main__":
    main()

