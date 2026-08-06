"""Fit / evaluate chrono-safe post-hoc calibrators for ``p_over_*``.

Uses Phase 11.B walk-forward OOS predictions (k-rate/TBF already OOS).
Calibrator selection: expanding windows — fit on earlier WF windows, score on
later. Production artifact: refit selected method on all WF windows through
cutoff (documented), never claim that refit as a test metric.

Does not retrain LightGBM or Ridge. Does not use paper-ticket ROI.

Examples:
    python Models/Strikeout-Model/research/fit_prob_calibration.py
    python Models/Strikeout-Model/research/fit_prob_calibration.py --method isotonic --set-production
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402
from Python.env_load import load_project_dotenv  # noqa: E402
from Python.prob_calibration import (  # noqa: E402
    DEFAULT_CALIBRATION_LINES,
    ProbCalibrationBundle,
    band_metrics,
    expected_calibration_error,
    fit_bundle_from_arrays,
    outcome_over,
    p_over_col,
    save_bundle,
    scoring_metrics,
    set_production_pointer,
    transform_line,
)

load_project_dotenv(override=True)

WF_DEFAULT = (
    config.OUTPUT_DIR
    / "model_quality"
    / "phase11b_walkforward"
    / "walkforward_predictions.parquet"
)
OUT_DIR = config.OUTPUT_DIR / "model_quality" / "prob_calibration"

# Chronological WF window order (expanding).
WINDOW_ORDER = ("wf_2024_apr_may", "wf_2024_jun_jul", "wf_2024_aug_sep")


def _load_wf(path: Path) -> pl.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run walkforward_stack_backtest.py first."
        )
    df = pl.read_parquet(path)
    if "game_date" not in df.columns or "K" not in df.columns:
        raise ValueError("walkforward predictions need game_date and K")
    # Normalize date
    if df["game_date"].dtype != pl.Date:
        df = df.with_columns(pl.col("game_date").cast(pl.Date))
    return df


def _line_arrays(
    frame: pl.DataFrame,
    lines: tuple[float, ...],
) -> dict[float, tuple[np.ndarray, np.ndarray]]:
    out: dict[float, tuple[np.ndarray, np.ndarray]] = {}
    k = frame["K"].to_numpy().astype(np.float64)
    for line in lines:
        col = p_over_col(line, calibrated=False)
        if col not in frame.columns:
            continue
        p = frame[col].to_numpy().astype(np.float64)
        y = outcome_over(k, line)
        mask = np.isfinite(p) & np.isfinite(y)
        out[float(line)] = (p[mask], y[mask])
    return out


def _eval_frame(
    frame: pl.DataFrame,
    bundle: ProbCalibrationBundle,
    lines: tuple[float, ...],
) -> dict[str, Any]:
    k = frame["K"].to_numpy().astype(np.float64)
    raw_all_p: list[np.ndarray] = []
    raw_all_y: list[np.ndarray] = []
    cal_all_p: list[np.ndarray] = []
    by_line: list[dict[str, Any]] = []
    for line in lines:
        col = p_over_col(line, calibrated=False)
        if col not in frame.columns:
            continue
        p_raw = frame[col].to_numpy().astype(np.float64)
        y = outcome_over(k, line)
        mask = np.isfinite(p_raw)
        p_raw, y = p_raw[mask], y[mask]
        p_cal, scope = transform_line(bundle, line, p_raw)
        raw_m = scoring_metrics(y, p_raw)
        cal_m = scoring_metrics(y, p_cal)
        _, raw_bins = expected_calibration_error(y, p_raw)
        _, cal_bins = expected_calibration_error(y, p_cal)
        by_line.append(
            {
                "line": line,
                "scope": scope,
                "raw": raw_m,
                "calibrated": cal_m,
                "bands_raw": band_metrics(y, p_raw),
                "bands_cal": band_metrics(y, p_cal),
                "delta_brier": (
                    None
                    if raw_m["brier"] is None or cal_m["brier"] is None
                    else float(cal_m["brier"] - raw_m["brier"])
                ),
                "delta_ece": (
                    None
                    if raw_m["ece"] is None or cal_m["ece"] is None
                    else float(cal_m["ece"] - raw_m["ece"])
                ),
            }
        )
        raw_all_p.append(p_raw)
        raw_all_y.append(y)
        cal_all_p.append(p_cal)
    pooled_raw = scoring_metrics(np.concatenate(raw_all_y), np.concatenate(raw_all_p))
    pooled_cal = scoring_metrics(np.concatenate(raw_all_y), np.concatenate(cal_all_p))
    return {
        "n_rows": frame.height,
        "pooled_raw": pooled_raw,
        "pooled_calibrated": pooled_cal,
        "by_line": by_line,
        "bands_pooled_raw": band_metrics(
            np.concatenate(raw_all_y), np.concatenate(raw_all_p)
        ),
        "bands_pooled_cal": band_metrics(
            np.concatenate(raw_all_y), np.concatenate(cal_all_p)
        ),
    }


def walkforward_select(
    df: pl.DataFrame,
    *,
    method: str,
    lines: tuple[float, ...],
) -> dict[str, Any]:
    """Expanding-window CV: fit on windows[:i], test on windows[i]."""
    folds = []
    for i in range(1, len(WINDOW_ORDER)):
        train_windows = WINDOW_ORDER[:i]
        test_window = WINDOW_ORDER[i]
        train = df.filter(pl.col("window").is_in(list(train_windows)))
        test = df.filter(pl.col("window") == test_window)
        if train.is_empty() or test.is_empty():
            continue
        cutoff = train["game_date"].max()
        bundle = fit_bundle_from_arrays(
            method=method,  # type: ignore[arg-type]
            line_data=_line_arrays(train, lines),
            fit_cutoff=str(cutoff),
            fit_source=f"wf_train:{','.join(train_windows)}",
            version=f"cv_{method}_{test_window}",
        )
        ev = _eval_frame(test, bundle, lines)
        folds.append(
            {
                "train_windows": list(train_windows),
                "test_window": test_window,
                "fit_cutoff": str(cutoff),
                "n_train": train.height,
                "n_test": test.height,
                "eval": ev,
            }
        )
    # Aggregate mean delta Brier / ECE across folds
    d_brier = []
    d_ece = []
    for f in folds:
        pr = f["eval"]["pooled_raw"]
        pc = f["eval"]["pooled_calibrated"]
        if pr.get("brier") is not None and pc.get("brier") is not None:
            d_brier.append(pc["brier"] - pr["brier"])
        if pr.get("ece") is not None and pc.get("ece") is not None:
            d_ece.append(pc["ece"] - pr["ece"])
    return {
        "method": method,
        "folds": folds,
        "mean_delta_brier": float(np.mean(d_brier)) if d_brier else None,
        "mean_delta_ece": float(np.mean(d_ece)) if d_ece else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=WF_DEFAULT)
    parser.add_argument(
        "--method",
        choices=("isotonic", "platt", "both"),
        default="both",
        help="Calibrator family to evaluate / ship",
    )
    parser.add_argument(
        "--set-production",
        action="store_true",
        help="Point production at the chosen refit artifact",
    )
    parser.add_argument(
        "--prefer",
        choices=("isotonic", "platt", "auto"),
        default="auto",
        help="Which method to refit for production when --method both",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = _load_wf(args.predictions)
    lines = tuple(DEFAULT_CALIBRATION_LINES)

    methods = ("isotonic", "platt") if args.method == "both" else (args.method,)
    cv_results = {
        m: walkforward_select(df, method=m, lines=lines) for m in methods
    }

    # Choose production method
    if args.prefer != "auto":
        chosen = args.prefer
    elif "isotonic" in cv_results and "platt" in cv_results:
        # Prefer lower (more negative) mean_delta_ece, then brier
        iso = cv_results["isotonic"]
        pla = cv_results["platt"]
        iso_key = (
            iso["mean_delta_ece"] if iso["mean_delta_ece"] is not None else 0.0,
            iso["mean_delta_brier"] if iso["mean_delta_brier"] is not None else 0.0,
        )
        pla_key = (
            pla["mean_delta_ece"] if pla["mean_delta_ece"] is not None else 0.0,
            pla["mean_delta_brier"] if pla["mean_delta_brier"] is not None else 0.0,
        )
        chosen = "isotonic" if iso_key <= pla_key else "platt"
    else:
        chosen = methods[0]

    # Production refit on all WF OOS rows (after method selection via CV)
    cutoff = df["game_date"].max()
    prod = fit_bundle_from_arrays(
        method=chosen,  # type: ignore[arg-type]
        line_data=_line_arrays(df, lines),
        fit_cutoff=str(cutoff),
        fit_source=str(args.predictions),
        version=None,
        metrics={
            "selection": "walkforward_cv",
            "cv": {
                m: {
                    "mean_delta_brier": cv_results[m]["mean_delta_brier"],
                    "mean_delta_ece": cv_results[m]["mean_delta_ece"],
                    "n_folds": len(cv_results[m]["folds"]),
                }
                for m in cv_results
            },
            "chosen_method": chosen,
            "n_fit_rows": df.height,
            "date_min": str(df["game_date"].min()),
            "date_max": str(cutoff),
            "note": (
                "Production map refit on all WF OOS predictions after CV method "
                "selection. CV fold metrics are the leakage-safe claim; refit "
                "metrics below are descriptive only."
            ),
        },
        notes=[
            "Does not change expected_K / k_rate / TBF.",
            "Lines 2.5/8.5/9.5 use nearest-line or global fallback at apply time.",
            f"WF windows: {list(WINDOW_ORDER)}",
        ],
    )
    # Descriptive metrics on full WF (NOT a test claim)
    prod.metrics["refit_descriptive_full_wf"] = _eval_frame(df, prod, lines)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = config.MODEL_DIR / f"prob_calibration_{chosen}_{stamp}"
    joblib_path, json_path = save_bundle(prod, stem)

    report = {
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "predictions": str(args.predictions),
        "chosen_method": chosen,
        "artifact_joblib": str(joblib_path),
        "artifact_json": str(json_path),
        "cv": cv_results,
        "production_bundle": {
            "version": prod.version,
            "fit_cutoff": prod.fit_cutoff,
            "lines": prod.lines,
            "notes": prod.notes,
            "metrics": prod.metrics,
        },
    }
    report_path = OUT_DIR / f"fit_report_{chosen}_{stamp}.json"
    # Make JSON-serializable (numpy types)
    report_path.write_text(
        json.dumps(report, indent=2, default=lambda o: float(o) if hasattr(o, "item") else str(o)),
        encoding="utf-8",
    )

    if args.set_production:
        set_production_pointer(
            joblib_path,
            meta={
                "version": prod.version,
                "method": chosen,
                "fit_cutoff": prod.fit_cutoff,
                "report": str(report_path),
            },
        )

    print(json.dumps(
        {
            "chosen_method": chosen,
            "joblib": str(joblib_path),
            "report": str(report_path),
            "cv_summary": {
                m: {
                    "mean_delta_brier": cv_results[m]["mean_delta_brier"],
                    "mean_delta_ece": cv_results[m]["mean_delta_ece"],
                }
                for m in cv_results
            },
            "production_pointer": bool(args.set_production),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
