"""Persist and compare daily calibration readiness snapshots.

Usage:
  python production/ops/calibration_snapshot.py
  python production/ops/calibration_snapshot.py --compare
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.kpi_policy import DEFAULT_POLICY_PATH  # noqa: E402

HISTORY_PATH = ROOT / "artifacts" / "odds_log" / "calibration_snapshot_history.parquet"
LATEST_JSON = ROOT / "artifacts" / "odds_log" / "calibration_snapshot_latest.json"


def _run_kpi_json(policy_path: str) -> dict[str, object]:
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    cmd = [
        str(python),
        "production/ops/kpi_daily_action.py",
        "--json",
        "--kpi-policy",
        str(policy_path),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"kpi_daily_action failed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout)


def _as_row(payload: dict[str, object]) -> pl.DataFrame:
    row = {
        "snapshot_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": payload.get("status"),
        "action": payload.get("action"),
        "n_warn": payload.get("n_warn"),
        "mae_err_k_rate": payload.get("mae_err_k_rate"),
        "under_bias_tbf": payload.get("under_bias_tbf"),
        "n_joined": payload.get("n_joined"),
        "n_dates": payload.get("n_dates"),
        "chrono_min_dates": payload.get("chrono_min_dates"),
        "recalibration_promote_ready": payload.get("recalibration_promote_ready"),
        "recalibration_promote_blockers": json.dumps(payload.get("recalibration_promote_blockers", [])),
        "promotion_over_clv_n": payload.get("promotion_over_clv_n"),
        "promotion_over_mean_clv_pp": payload.get("promotion_over_mean_clv_pp"),
    }
    return pl.DataFrame([row])


def _compare_latest(hist: pl.DataFrame) -> dict[str, object] | None:
    if hist.height < 2:
        return None
    a = hist.tail(2).to_dicts()
    prev, curr = a[0], a[1]
    out = {
        "prev_snapshot_utc": prev.get("snapshot_utc"),
        "curr_snapshot_utc": curr.get("snapshot_utc"),
        "delta_mae_err_k_rate": (
            float(curr["mae_err_k_rate"]) - float(prev["mae_err_k_rate"])
            if curr.get("mae_err_k_rate") is not None and prev.get("mae_err_k_rate") is not None
            else None
        ),
        "delta_under_bias_tbf": (
            float(curr["under_bias_tbf"]) - float(prev["under_bias_tbf"])
            if curr.get("under_bias_tbf") is not None and prev.get("under_bias_tbf") is not None
            else None
        ),
        "delta_n_warn": (
            int(curr["n_warn"]) - int(prev["n_warn"])
            if curr.get("n_warn") is not None and prev.get("n_warn") is not None
            else None
        ),
        "delta_n_dates": (
            int(curr["n_dates"]) - int(prev["n_dates"])
            if curr.get("n_dates") is not None and prev.get("n_dates") is not None
            else None
        ),
        "promote_ready_prev": bool(prev.get("recalibration_promote_ready")),
        "promote_ready_curr": bool(curr.get("recalibration_promote_ready")),
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kpi-policy", type=str, default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--compare", action="store_true", help="Print latest-vs-previous delta summary.")
    args = parser.parse_args()

    payload = _run_kpi_json(args.kpi_policy)
    row = _as_row(payload)
    if HISTORY_PATH.exists():
        hist = pl.read_parquet(HISTORY_PATH)
        hist = pl.concat([hist, row], how="diagonal_relaxed")
    else:
        hist = row
    hist = hist.sort("snapshot_utc")
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    hist.write_parquet(HISTORY_PATH)

    latest_out = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kpi_action": payload,
    }
    if args.compare:
        latest_out["compare"] = _compare_latest(hist)
    LATEST_JSON.write_text(json.dumps(latest_out, indent=2), encoding="utf-8")
    print(json.dumps({"history": str(HISTORY_PATH), "latest": str(LATEST_JSON), "action": payload.get("action")}, indent=2))


if __name__ == "__main__":
    main()
