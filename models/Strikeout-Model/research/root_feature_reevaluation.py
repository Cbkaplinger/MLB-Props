"""Comprehensive feature-set reevaluation + compact retune on leaders.

This runner does three things:
1) Sweep every registered feature set through the Phase 11.B walk-forward stack.
2) Rank by expected_K MAE and identify top candidates.
3) Run compact nested LightGBM tuning on top candidates to test if retuning
   adds lift beyond feature selection.
"""

from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from Python import config
from Python.features import TARGET
from Python.registries import FEATURE_SETS, resolve_feature_names
from Python.training import (
    assert_pa_not_in_features,
    build_model,
    fit_regressor,
    lightgbm_matrix,
    metrics,
    predict_clipped,
)

EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))
from nested_cv import nested_research_folds  # noqa: E402

OUT_DIR = config.OUTPUT_DIR / "model_quality" / "root_feature_reevaluation"

BASELINE_PARAMS = {
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_child_samples": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 0.1,
    "reg_lambda": 2.0,
}
SEARCH_GRID = {
    "learning_rate": (0.02, 0.03, 0.05),
    "num_leaves": (15, 31, 63),
    "min_child_samples": (30, 50, 100),
    "subsample": (0.7, 0.8, 1.0),
    "colsample_bytree": (0.6, 0.7, 0.9),
    "reg_lambda": (1.0, 2.0, 5.0),
}


def _load_walkforward_module():
    path = ROOT / "models" / "Strikeout-Model" / "research" / "walkforward_stack_backtest.py"
    spec = importlib.util.spec_from_file_location("walkforward_stack_backtest", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load walkforward module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate_grid(max_candidates: int) -> list[dict]:
    keys = list(SEARCH_GRID.keys())
    raw = [
        {**BASELINE_PARAMS, **dict(zip(keys, values, strict=True))}
        for values in itertools.product(*(SEARCH_GRID[k] for k in keys))
    ]

    def _distance(params: dict) -> float:
        score = 0.0
        for key, base in BASELINE_PARAMS.items():
            val = params[key]
            if key in {"learning_rate", "num_leaves", "min_child_samples"}:
                score += abs(float(val) - float(base)) / float(base)
            else:
                score += abs(float(val) - float(base))
        return score

    ranked = sorted(raw, key=_distance)
    selected: list[dict] = [dict(BASELINE_PARAMS)]
    seen = {tuple(sorted(BASELINE_PARAMS.items()))}
    for params in ranked:
        key = tuple(sorted(params.items()))
        if key in seen:
            continue
        selected.append(params)
        seen.add(key)
        if len(selected) >= max_candidates:
            break
    return selected


def _fit_lgbm(train: pd.DataFrame, validation: pd.DataFrame, features: list[str], params: dict):
    fit_params = dict(params)
    if fit_params.get("subsample", 1.0) < 1.0:
        fit_params.setdefault("bagging_freq", 1)
    model = build_model(
        "lightgbm",
        lightgbm_n_estimators=5000,
        lightgbm_verbosity=-1,
        lightgbm_params=fit_params,
    )
    fit_regressor(
        model,
        "lightgbm",
        lightgbm_matrix(train, features),
        train[TARGET],
        validation_features=lightgbm_matrix(validation, features),
        validation_target=validation[TARGET],
        early_stopping_rounds=200,
        log_evaluation_period=0,
    )
    return model


def _nested_tune_feature_set(frame: pd.DataFrame, feature_set: str, max_candidates: int) -> dict[str, object]:
    features = list(resolve_feature_names(frame, feature_set))
    assert_pa_not_in_features(features)
    candidates = _candidate_grid(max_candidates=max_candidates)
    folds = nested_research_folds(frame)
    selected_outer: list[float] = []
    baseline_outer: list[float] = []
    selected_ids: list[int] = []

    for nested in folds.values():
        inner_scores: dict[int, list[float]] = {i: [] for i in range(len(candidates))}
        for inner in nested.inner.values():
            for idx, params in enumerate(candidates):
                model = _fit_lgbm(inner.train, inner.validation, features, params)
                pred = predict_clipped(model, "lightgbm", inner.validation, features)
                mae = metrics(inner.validation[TARGET], pred)["mae"]
                inner_scores[idx].append(float(mae))
        mean_inner = {idx: float(np.mean(vals)) for idx, vals in inner_scores.items()}
        best_id = min(mean_inner, key=mean_inner.get)
        selected_ids.append(int(best_id))

        # Fair outer compare with early-stopped train/val inside outer train split.
        outer_train = nested.outer.train
        cut = int(len(outer_train) * 0.85)
        fit = outer_train.iloc[:cut]
        val = outer_train.iloc[cut:]
        selected_model = _fit_lgbm(fit, val, features, candidates[best_id])
        baseline_model = _fit_lgbm(fit, val, features, BASELINE_PARAMS)

        pred_sel = predict_clipped(selected_model, "lightgbm", nested.outer.validation, features)
        pred_base = predict_clipped(baseline_model, "lightgbm", nested.outer.validation, features)
        selected_outer.append(float(metrics(nested.outer.validation[TARGET], pred_sel)["mae"]))
        baseline_outer.append(float(metrics(nested.outer.validation[TARGET], pred_base)["mae"]))

    return {
        "feature_set": feature_set,
        "n_features": len(features),
        "n_candidates": len(candidates),
        "selected_outer_mae_mean": float(np.mean(selected_outer)),
        "baseline_outer_mae_mean": float(np.mean(baseline_outer)),
        "delta_selected_minus_baseline": float(np.mean(selected_outer) - np.mean(baseline_outer)),
        "selected_config_ids": selected_ids,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k-retune", type=int, default=3)
    parser.add_argument("--max-candidates", type=int, default=12)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wf = _load_walkforward_module()
    frame = wf._load_frame()

    sweep_rows: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for feature_set in FEATURE_SETS:
        try:
            _ = resolve_feature_names(frame, feature_set)
        except Exception as exc:
            failures.append({"feature_set": feature_set, "stage": "resolve", "error": str(exc)})
            continue
        try:
            out_dir = config.OUTPUT_DIR / "model_quality" / f"phase11b_walkforward_{feature_set}"
            wf.main(
                dry_run=False,
                tune_alpha=True,
                feature_set=feature_set,
                output_dir=out_dir,
            )
            md = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
            sweep_rows.append(
                {
                    "feature_set": feature_set,
                    "n_features_k_rate": int(md.get("n_features_k_rate", 0)),
                    "expected_K_mae_mean": float(md.get("expected_K_mae_mean", np.nan)),
                    "expected_K_mae_std": float(md.get("expected_K_mae_std", np.nan)),
                    "pass_expected_K_vs_baseline": bool(md.get("pass_expected_K_vs_baseline", False)),
                    "output_dir": str(out_dir),
                }
            )
        except Exception as exc:
            failures.append({"feature_set": feature_set, "stage": "walkforward", "error": str(exc)})

    sweep = pd.DataFrame(sweep_rows).sort_values("expected_K_mae_mean")
    if not sweep.empty:
        base = float(
            sweep.loc[sweep["feature_set"] == "production", "expected_K_mae_mean"].iloc[0]
        )
        sweep["delta_vs_production_mae"] = sweep["expected_K_mae_mean"] - base
    sweep.to_csv(OUT_DIR / "feature_set_sweep.csv", index=False)

    retune_rows: list[dict[str, object]] = []
    if not sweep.empty:
        top_sets = sweep["feature_set"].head(max(1, int(args.top_k_retune))).tolist()
        for feature_set in top_sets:
            try:
                retune_rows.append(
                    _nested_tune_feature_set(frame, feature_set, max_candidates=max(4, int(args.max_candidates)))
                )
            except Exception as exc:
                failures.append({"feature_set": feature_set, "stage": "retune", "error": str(exc)})
    retune = pd.DataFrame(retune_rows).sort_values("selected_outer_mae_mean")
    retune.to_csv(OUT_DIR / "top_feature_set_retune.csv", index=False)

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_feature_sets_total": len(FEATURE_SETS),
        "n_feature_sets_scored": int(len(sweep_rows)),
        "top_k_retuned": int(len(retune_rows)),
        "files": {
            "feature_set_sweep_csv": str(OUT_DIR / "feature_set_sweep.csv"),
            "top_feature_set_retune_csv": str(OUT_DIR / "top_feature_set_retune.csv"),
        },
        "failures": failures,
        "best_feature_set_by_walkforward": (
            sweep.iloc[0].to_dict() if not sweep.empty else None
        ),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(sweep.to_string(index=False) if not sweep.empty else "No feature sets scored.")
    if not retune.empty:
        print("\nRetune summary:")
        print(retune.to_string(index=False))
    if failures:
        print("\nFailures:")
        print(json.dumps(failures, indent=2))
    print(f"Wrote {OUT_DIR}")


if __name__ == "__main__":
    main()

