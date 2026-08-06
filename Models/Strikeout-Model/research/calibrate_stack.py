"""Phase 11.C — calibration / ECE / residual slices on walk-forward preds.

Reads ``artifacts/model_quality/phase11b_walkforward/walkforward_predictions.parquet``
(or a path you pass) and reports:
- reliability bins + ECE for each K-line over probability
- k_rate residual bias by predicted-rate bin
- binomial vs poisson note (kappa already at binomial limit in 11.B)

Diagnose-only. To **fit/apply** post-hoc Platt/isotonic maps, use
``Models/Strikeout-Model/research/fit_prob_calibration.py`` and
``src/Python/prob_calibration.py`` (see ``docs/research/prob_calibration_findings.md``).

Examples:
    python Models/Strikeout-Model/research/calibrate_stack.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from Python import config
from Python.count_layer import DEFAULT_K_LINES, over_threshold


def expected_calibration_error(
    y: np.ndarray,
    p: np.ndarray,
    *,
    n_bins: int = 10,
) -> tuple[float, list[dict[str, float]]]:
    """Equal-width probability bins; ECE = sum (|acc - conf| * weight)."""
    y = np.asarray(y, dtype=np.float64)
    p = np.clip(np.asarray(p, dtype=np.float64), 1e-12, 1.0 - 1e-12)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[dict[str, float]] = []
    ece = 0.0
    n = len(y)
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        if i == n_bins - 1:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)
        count = int(mask.sum())
        if count == 0:
            bins.append(
                {
                    "bin": i,
                    "lo": float(lo),
                    "hi": float(hi),
                    "n": 0,
                    "mean_prob": float("nan"),
                    "empirical": float("nan"),
                    "gap": float("nan"),
                }
            )
            continue
        mean_p = float(p[mask].mean())
        emp = float(y[mask].mean())
        gap = abs(emp - mean_p)
        ece += gap * (count / n)
        bins.append(
            {
                "bin": i,
                "lo": float(lo),
                "hi": float(hi),
                "n": count,
                "mean_prob": mean_p,
                "empirical": emp,
                "gap": gap,
            }
        )
    return float(ece), bins


def rate_residual_bins(
    actual: np.ndarray,
    pred: np.ndarray,
    *,
    n_bins: int = 10,
) -> list[dict[str, float]]:
    """Bias / MAE of k_rate residuals by predicted-rate quantile bins."""
    actual = np.asarray(actual, dtype=np.float64)
    pred = np.asarray(pred, dtype=np.float64)
    resid = actual - pred
    try:
        qs = pd.qcut(pred, n_bins, labels=False, duplicates="drop")
    except ValueError:
        return []
    rows: list[dict[str, float]] = []
    for qi in sorted(pd.Series(qs).dropna().unique()):
        mask = qs == qi
        rows.append(
            {
                "bin": int(qi),
                "n": int(mask.sum()),
                "pred_mean": float(pred[mask].mean()),
                "actual_mean": float(actual[mask].mean()),
                "bias": float(resid[mask].mean()),
                "mae": float(np.abs(resid[mask]).mean()),
            }
        )
    return rows


def main(*, predictions: Path, n_bins: int) -> None:
    if not predictions.exists():
        raise FileNotFoundError(
            f"Missing {predictions}. Run walkforward_stack_backtest.py first."
        )
    frame = pd.read_parquet(predictions)
    required = {"K", "k_rate", "k_rate_pred", "expected_K", "window"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"predictions missing columns: {sorted(missing)}")

    output_dir = config.OUTPUT_DIR / "model_quality" / "phase11c_calibration"
    output_dir.mkdir(parents=True, exist_ok=True)

    line_report: dict[str, object] = {}
    reliability_rows: list[dict[str, object]] = []
    for line in DEFAULT_K_LINES:
        col = f"p_over_{str(line).replace('.', '_')}"
        if col not in frame.columns:
            raise ValueError(f"missing probability column {col}")
        y = (frame["K"].to_numpy(dtype=float) >= over_threshold(line)).astype(int)
        p = frame[col].to_numpy(dtype=float)
        ece, bins = expected_calibration_error(y, p, n_bins=n_bins)
        # Simple sharpness / bias checks
        line_report[str(line)] = {
            "n": int(len(y)),
            "base_rate": float(y.mean()),
            "mean_prob": float(p.mean()),
            "prob_minus_base": float(p.mean() - y.mean()),
            "ece": ece,
            "bins": bins,
        }
        for b in bins:
            reliability_rows.append({"line": float(line), **b})

        # Per-window ECE (fold variance)
        per_window = {}
        for window, grp in frame.groupby("window"):
            yw = (grp["K"].to_numpy(dtype=float) >= over_threshold(line)).astype(int)
            pw = grp[col].to_numpy(dtype=float)
            ece_w, _ = expected_calibration_error(yw, pw, n_bins=n_bins)
            per_window[str(window)] = {
                "ece": ece_w,
                "base_rate": float(yw.mean()),
                "mean_prob": float(pw.mean()),
                "n": int(len(yw)),
            }
        line_report[str(line)]["per_window"] = per_window

    rate_bins = rate_residual_bins(
        frame["k_rate"].to_numpy(dtype=float),
        frame["k_rate_pred"].to_numpy(dtype=float),
        n_bins=n_bins,
    )
    rate_bias = float(
        (frame["k_rate"] - frame["k_rate_pred"]).mean()
    )

    # Heuristic pass: mean |prob - base| small and ECE not extreme.
    eces = [float(line_report[str(L)]["ece"]) for L in DEFAULT_K_LINES]
    mean_ece = float(np.mean(eces))
    max_ece = float(np.max(eces))
    # Soft research bar: ECE < 0.05 mean and < 0.08 max is "ok enough" to proceed;
    # recalibration only if clearly worse.
    needs_recalibration = bool(mean_ece >= 0.05 or max_ece >= 0.08)

    summary = {
        "phase": "11.C",
        "source_predictions": str(predictions),
        "n_rows": int(len(frame)),
        "n_windows": int(frame["window"].nunique()),
        "n_bins": n_bins,
        "k_rate_residual_bias": rate_bias,
        "k_rate_residual_bins": rate_bins,
        "line_calibration": line_report,
        "ece_mean": mean_ece,
        "ece_max": max_ece,
        "needs_recalibration": needs_recalibration,
        "recalibration_policy": (
            "Do not fit isotonic/temperature on the pooled walk-forward test. "
            "If needs_recalibration, fit inside each expanding train window and "
            "apply only to that window's test block."
        ),
        "binomial_vs_poisson": (
            "11.B kappa ~1e6 (binomial limit); poisson Brier essentially tied. "
            "Keep binomial as default count family."
        ),
        "approved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    pd.DataFrame(reliability_rows).to_csv(
        output_dir / "reliability_bins.csv", index=False
    )
    pd.DataFrame(rate_bins).to_csv(
        output_dir / "k_rate_residual_bins.csv", index=False
    )
    (output_dir / "metadata.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    # Compact console view
    compact = {
        "ece_mean": mean_ece,
        "ece_max": max_ece,
        "needs_recalibration": needs_recalibration,
        "k_rate_residual_bias": rate_bias,
        "per_line": {
            str(L): {
                "ece": line_report[str(L)]["ece"],
                "base_rate": line_report[str(L)]["base_rate"],
                "mean_prob": line_report[str(L)]["mean_prob"],
                "prob_minus_base": line_report[str(L)]["prob_minus_base"],
            }
            for L in DEFAULT_K_LINES
        },
    }
    print(json.dumps(compact, indent=2))
    print(f"Wrote {output_dir / 'metadata.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--predictions",
        type=Path,
        default=(
            config.OUTPUT_DIR
            / "model_quality"
            / "phase11b_walkforward"
            / "walkforward_predictions.parquet"
        ),
    )
    parser.add_argument("--n-bins", type=int, default=10)
    args = parser.parse_args()
    main(predictions=args.predictions, n_bins=args.n_bins)
