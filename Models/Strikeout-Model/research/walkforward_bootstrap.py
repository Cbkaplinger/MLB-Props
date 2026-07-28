"""Paired (game-resampled) bootstrap CIs for walk-forward expected-K MAE.

Reads existing Phase 11.B window predictions and reports a 95% percentile
interval per expanding window (B = 2000), matching the ablation bootstrap
protocol in ``ablation_bootstrap.py``.

Example:
    python models/Strikeout-Model/research/walkforward_bootstrap.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from Python import config

PRED_PATH = (
    config.OUTPUT_DIR
    / "model_quality"
    / "phase11b_walkforward"
    / "walkforward_predictions.parquet"
)
OUTER_PATH = (
    config.OUTPUT_DIR / "model_quality" / "phase11b_walkforward" / "outer_results.csv"
)
OUT_DIR = config.OUTPUT_DIR / "model_quality" / "phase11b_walkforward_bootstrap"

# Stable display order matching DEFAULT_WINDOWS in walkforward_stack_backtest.py.
_WINDOW_ORDER = (
    "wf_2024_apr_may",
    "wf_2024_jun_jul",
    "wf_2024_aug_sep",
)


def _bootstrap_mae(
    y: np.ndarray,
    pred: np.ndarray,
    *,
    n_boot: int,
    seed: int,
) -> dict[str, float]:
    abs_err = np.abs(y - pred)
    point = float(abs_err.mean())
    rng = np.random.default_rng(seed)
    n = len(abs_err)
    boots = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[b] = float(abs_err[idx].mean())
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {
        "mae": point,
        "ci95_lo": float(lo),
        "ci95_hi": float(hi),
        "n": int(n),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not PRED_PATH.exists():
        raise FileNotFoundError(
            f"Missing {PRED_PATH}; run walkforward_stack_backtest.py first."
        )

    pred = pd.read_parquet(PRED_PATH)
    if "window" not in pred.columns or "expected_K" not in pred.columns:
        raise ValueError("predictions must include window and expected_K columns")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for i, name in enumerate(_WINDOW_ORDER):
        sub = pred.loc[pred["window"] == name]
        if sub.empty:
            raise ValueError(f"no rows for window {name}")
        stats = _bootstrap_mae(
            sub["K"].to_numpy(dtype=float),
            sub["expected_K"].to_numpy(dtype=float),
            n_boot=args.n_boot,
            seed=args.seed + i,
        )
        rows.append({"window": name, **stats})

    # Published mean/σ from Phase 11.B (do not overwrite).
    published_mean = 1.778
    published_std = 0.036
    intervals = [(r["ci95_lo"], r["ci95_hi"]) for r in rows]
    # Pairwise overlap of 95% intervals.
    overlaps = []
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            lo_i, hi_i = intervals[i]
            lo_j, hi_j = intervals[j]
            overlaps.append(not (hi_i < lo_j or hi_j < lo_i))

    summary = {
        "n_boot": args.n_boot,
        "seed": args.seed,
        "published_mean_mae": published_mean,
        "published_std_across_windows": published_std,
        "windows": rows,
        "all_pairwise_intervals_overlap": bool(all(overlaps)),
        "predictions_path": str(PRED_PATH),
    }
    if OUTER_PATH.exists():
        outer = pd.read_csv(OUTER_PATH)
        summary["outer_results_mae"] = {
            str(r["window"]): float(r["expected_K_mae"])
            for _, r in outer.iterrows()
        }

    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    pd.DataFrame(rows).to_csv(OUT_DIR / "window_mae_bootstrap.csv", index=False)
    print(json.dumps(summary, indent=2))
    print(f"Wrote {OUT_DIR}")


if __name__ == "__main__":
    main()
