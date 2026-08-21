"""Stability filter for production_sparse40 across folds/windows/holdout.

A feature is "stable" when permutation delta-MAE > 0 in every slice:
- outer_2024_h1, outer_2024_h2
- wf_2024_apr_may, wf_2024_jun_jul, wf_2024_aug_sep
- holdout_2025
"""

from __future__ import annotations

import json
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from Python import config
from Python.features import TARGET
from Python.registries import resolve_feature_names
from Python.training import build_model, fit_regressor, lightgbm_matrix, metrics, predict_clipped
from nested_cv import nested_research_folds

OUT_DIR = config.OUTPUT_DIR / "model_quality" / "deep_feature_review"


def _fit_model(train: pd.DataFrame, val: pd.DataFrame, features: list[str]):
    model = build_model("lightgbm", lightgbm_verbosity=-1)
    fit_regressor(
        model,
        "lightgbm",
        lightgbm_matrix(train, features),
        train[TARGET],
        validation_features=lightgbm_matrix(val, features),
        validation_target=val[TARGET],
        early_stopping_rounds=200,
        log_evaluation_period=0,
    )
    return model


def _perm_deltas(model, test: pd.DataFrame, features: list[str], *, seed: int) -> dict[str, float]:
    y = test[TARGET].to_numpy(dtype=float)
    base = predict_clipped(model, "lightgbm", test, features)
    base_mae = float(metrics(y, base)["mae"])
    rng = np.random.default_rng(seed)
    out: dict[str, float] = {}
    for feature in features:
        perm = test.copy()
        vals = perm[feature].to_numpy(copy=True)
        rng.shuffle(vals)
        perm[feature] = vals
        pred = predict_clipped(model, "lightgbm", perm, features)
        out[feature] = float(metrics(y, pred)["mae"] - base_mae)
    return out


def _load_wf():
    path = ROOT / "models" / "Strikeout-Model" / "research" / "walkforward_stack_backtest.py"
    spec = importlib.util.spec_from_file_location("walkforward_stack_backtest", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load walkforward module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = frame.dropna(subset=[TARGET, "game_date"]).sort_values(["game_date", "player_name"]).reset_index(drop=True)
    sparse = list(resolve_feature_names(frame, "production_sparse40"))

    deltas_by_slice: dict[str, dict[str, float]] = {}

    # Outer folds
    research = frame.loc[frame["season"].isin(config.FEATURE_RESEARCH_SEASONS)].copy().reset_index(drop=True)
    folds = nested_research_folds(research)
    for name, nested in folds.items():
        outer_train = nested.outer.train
        cut = int(len(outer_train) * 0.85)
        fit = outer_train.iloc[:cut]
        val = outer_train.iloc[cut:]
        model = _fit_model(fit, val, sparse)
        deltas_by_slice[name] = _perm_deltas(model, nested.outer.validation, sparse, seed=11)

    # WF windows
    wf = _load_wf()
    wf_frame = wf._load_frame()
    for idx, (name, start, end) in enumerate(wf.DEFAULT_WINDOWS):
        s = pd.Timestamp(start)
        e = pd.Timestamp(end)
        train = wf_frame[wf_frame["game_date"] < s]
        test = wf_frame[(wf_frame["game_date"] >= s) & (wf_frame["game_date"] < e)]
        cut = int(len(train) * 0.85)
        fit = train.iloc[:cut]
        val = train.iloc[cut:]
        model = _fit_model(fit, val, sparse)
        deltas_by_slice[name] = _perm_deltas(model, test, sparse, seed=23 + idx)

    # Holdout 2025
    train = frame[frame["season"].isin(config.FEATURE_RESEARCH_SEASONS)]
    hold = frame[frame["season"] == config.HOLDOUT_SEASON]
    cut = int(len(train) * 0.85)
    fit = train.iloc[:cut]
    val = train.iloc[cut:]
    model = _fit_model(fit, val, sparse)
    deltas_by_slice["holdout_2025"] = _perm_deltas(model, hold, sparse, seed=99)

    rows: list[dict[str, object]] = []
    for feature in sparse:
        vals = {slice_name: feature_map.get(feature, np.nan) for slice_name, feature_map in deltas_by_slice.items()}
        arr = np.array([v for v in vals.values() if np.isfinite(v)], dtype=float)
        rows.append(
            {
                "feature": feature,
                **vals,
                "min_delta": float(np.min(arr)) if arr.size else np.nan,
                "mean_delta": float(np.mean(arr)) if arr.size else np.nan,
                "n_positive_slices": int(np.sum(arr > 0)),
                "n_slices": int(arr.size),
                "stable_all_slices": bool(arr.size > 0 and np.all(arr > 0)),
            }
        )

    out = pd.DataFrame(rows).sort_values(["stable_all_slices", "mean_delta"], ascending=[False, False])
    out_path = OUT_DIR / "production_sparse40_stability.csv"
    out.to_csv(out_path, index=False)

    stable = out.loc[out["stable_all_slices"], "feature"].tolist()
    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_features_sparse40": len(sparse),
        "n_stable_all_slices": len(stable),
        "stable_features": stable,
        "slices": list(deltas_by_slice.keys()),
        "file": str(out_path),
    }
    (OUT_DIR / "production_sparse40_stability_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(out.to_string(index=False))
    print(json.dumps(summary, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

