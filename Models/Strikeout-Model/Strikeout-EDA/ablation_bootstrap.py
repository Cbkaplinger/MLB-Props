"""Paired bootstrap CIs for leave-family-out ΔMAE (within each outer fold).

Fits full vs drop once per (fold, model, configuration), then bootstraps
validation games to get a 95% CI on MAE_drop − MAE_full. Addresses fold-mean
uncertainty without inventing a CI across n=2 outer folds.

Example:
    python Models/Strikeout-Model/Strikeout-EDA/ablation_bootstrap.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from Python import config
from Python.features import TARGET
from Python.training import fit_kwargs_for_weights, resolve_sample_weights

EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from leave_family_out_ablation import (  # noqa: E402
    _configurations,
    _family_map,
)
from nested_cv import fold_metadata, nested_research_folds  # noqa: E402

OUT_DIR = config.OUTPUT_DIR / "feature_research" / "leave_family_out_bootstrap"

# Configurations reported in manuscript Table 6.
_FOCUS = (
    "drop_lineup",
    "drop_rolling_keep_std_and_static",
    "drop_pitch_physics",
    "drop_park",
    "drop_context",
    "drop_pitch_usage",
)


def _models() -> dict[str, object]:
    return {
        "ridge": make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            Ridge(alpha=1.0),
        ),
        "lightgbm": lgb.LGBMRegressor(
            objective="regression",
            n_estimators=800,
            learning_rate=0.03,
            num_leaves=31,
            min_child_samples=50,
            subsample=0.8,
            colsample_bytree=0.7,
            reg_alpha=0.1,
            reg_lambda=2.0,
            random_state=42,
            verbosity=-1,
            n_jobs=-1,
        ),
    }


def _fit(model, model_name: str, frame: pd.DataFrame, features: list[str]) -> None:
    model.fit(
        frame[features],
        frame[TARGET],
        **fit_kwargs_for_weights(
            model_name, resolve_sample_weights(frame, "none")
        ),
    )


def _bootstrap_delta(
    y: np.ndarray,
    pred_full: np.ndarray,
    pred_drop: np.ndarray,
    *,
    n_boot: int,
    seed: int,
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    err_full = np.abs(y - pred_full)
    err_drop = np.abs(y - pred_drop)
    point = float(err_drop.mean() - err_full.mean())
    n = len(y)
    deltas = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        deltas[b] = float(err_drop[idx].mean() - err_full[idx].mean())
    lo, hi = np.quantile(deltas, [0.025, 0.975])
    return {
        "delta_mae": point,
        "ci95_lo": float(lo),
        "ci95_hi": float(hi),
        "ci_excludes_zero": bool(lo > 0 or hi < 0),
        "n": int(n),
    }


def main() -> Path:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=("ridge", "lightgbm"),
        default=["lightgbm", "ridge"],
    )
    args = parser.parse_args()

    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "game_date"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    frame = frame[frame["season"].isin(config.FEATURE_RESEARCH_SEASONS)].copy()

    registry = pd.read_csv(
        config.OUTPUT_DIR
        / "feature_research"
        / "step1_registries"
        / "pre_freeze_248_registry.csv"
    )
    features = [f for f in registry["feature"].tolist() if f in frame.columns]
    if len(features) != 248:
        raise ValueError(
            f"expected 248 pre_freeze features present in frame, got {len(features)}"
        )
    families = _family_map(features)
    configurations = _configurations(features, families)
    folds = nested_research_folds(frame)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    for outer_name, nested in folds.items():
        outer = nested.outer
        y = outer.validation[TARGET].to_numpy(dtype=float)
        for model_name in args.models:
            full_model = _models()[model_name]
            _fit(full_model, model_name, outer.train, configurations["full"])
            pred_full = np.clip(
                full_model.predict(outer.validation[configurations["full"]]), 0, 1
            )
            for configuration in _FOCUS:
                selected = configurations[configuration]
                model = _models()[model_name]
                _fit(model, model_name, outer.train, selected)
                pred_drop = np.clip(model.predict(outer.validation[selected]), 0, 1)
                boot = _bootstrap_delta(
                    y,
                    pred_full,
                    pred_drop,
                    n_boot=args.n_boot,
                    seed=args.seed
                    + abs(hash((outer_name, model_name, configuration))) % 10_000,
                )
                row = {
                    "outer_fold": outer_name,
                    "model": model_name,
                    "configuration": configuration,
                    **boot,
                }
                rows.append(row)
                print(row)

    results = pd.DataFrame(rows)
    results.to_csv(OUT_DIR / "bootstrap_by_fold.csv", index=False)

    # Pool both folds' point estimates for display; CI reported per fold.
    summary = {
        "n_boot": args.n_boot,
        "feature_set": "pre_freeze_248",
        "protocol": (
            "Paired bootstrap of validation games within each outer fold; "
            "ΔMAE = MAE(drop) − MAE(full); 95% percentile interval."
        ),
        "folds": fold_metadata(folds),
        "by_fold": results.to_dict(orient="records"),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_DIR}")
    return OUT_DIR


if __name__ == "__main__":
    main()
