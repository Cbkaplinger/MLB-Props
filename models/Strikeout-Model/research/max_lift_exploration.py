"""Broader max-lift exploration on sparse frontier.

Explores:
1) In-between SHAP-ranked K values (feature-count frontier).
2) Alternative LightGBM objectives (regression, huber, regression_l1).
3) Monotone constraints on directional features.
4) Compact nested retune on top K candidates.
"""

from __future__ import annotations

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
EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from Python import config
from Python.count_layer import expected_strikeouts
from Python.features import TARGET
from Python.registries import resolve_feature_names
from Python.tbf import TBF_DEFAULT_FEATURE_SET, tbf_feature_names
from Python.training import (
    build_model,
    fit_regressor,
    lightgbm_matrix,
    metrics,
    predict_clipped,
    predict_nonnegative,
)
from nested_cv import nested_research_folds

OUT_DIR = config.OUTPUT_DIR / "model_quality" / "max_lift_exploration"
ATTR_PATH = config.OUTPUT_DIR / "model_quality" / "deep_feature_review" / "legacy_feature_attribution.csv"

K_GRID = (16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64, 68, 72, 80, 96, 112)
OBJECTIVES = ("regression", "huber", "regression_l1")

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


def _load_wf():
    path = ROOT / "models" / "Strikeout-Model" / "research" / "walkforward_stack_backtest.py"
    spec = importlib.util.spec_from_file_location("walkforward_stack_backtest", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load walkforward module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _monotone_constraints(features: list[str]) -> list[int]:
    positive_stems = {
        "k_rate_",
        "opp_lineup_k",
        "opp_lineup_whiff",
        "opp_lineup_swstr",
        "opp_lineup_chase",
        "park_k_factor",
    }
    out: list[int] = []
    for feature in features:
        if any(feature == stem or feature.startswith(stem) for stem in positive_stems):
            out.append(1)
        else:
            out.append(0)
    return out


def _fit_k_model(
    train: pd.DataFrame,
    val: pd.DataFrame,
    features: list[str],
    *,
    objective: str,
    monotone: bool,
    params: dict[str, object],
):
    fit_params = dict(params)
    fit_params["objective"] = objective
    if monotone:
        fit_params["monotone_constraints"] = _monotone_constraints(features)
        fit_params["monotone_constraints_method"] = "advanced"
    if float(fit_params.get("subsample", 1.0)) < 1.0:
        fit_params.setdefault("bagging_freq", 1)
    model = build_model(
        "lightgbm",
        lightgbm_verbosity=-1,
        lightgbm_params=fit_params,
    )
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


def _fit_tbf(train: pd.DataFrame, tbf_features: list[str]):
    model = build_model("ridge", ridge_alpha=123.28467394420659)
    fit_regressor(model, "ridge", train[tbf_features], train["PA"])
    upper = float(train["PA"].quantile(0.999))
    return model, upper


def _eval_wf(
    wf,
    frame: pd.DataFrame,
    features: list[str],
    *,
    objective: str = "regression",
    monotone: bool = False,
    params: dict[str, object] | None = None,
) -> tuple[float, float, float]:
    p = params if params is not None else BASELINE_PARAMS
    tbf_features = list(tbf_feature_names(frame, TBF_DEFAULT_FEATURE_SET))
    ek_maes: list[float] = []
    kr_maes: list[float] = []
    for _, start, end in wf.DEFAULT_WINDOWS:
        s = pd.Timestamp(start)
        e = pd.Timestamp(end)
        train = frame[frame["game_date"] < s]
        test = frame[(frame["game_date"] >= s) & (frame["game_date"] < e)]
        cut = int(len(train) * 0.85)
        fit = train.iloc[:cut]
        val = train.iloc[cut:]
        k_model = _fit_k_model(
            fit,
            val,
            features,
            objective=objective,
            monotone=monotone,
            params=p,
        )
        tbf_model, tbf_upper = _fit_tbf(train, tbf_features)
        k_hat = predict_clipped(k_model, "lightgbm", test, features)
        tbf_hat = predict_nonnegative(tbf_model, "ridge", test, tbf_features, upper=tbf_upper)
        expected = expected_strikeouts(k_hat, tbf_hat)
        ek_maes.append(float(metrics(test["K"], expected, clip_to_unit_interval=False)["mae"]))
        kr_maes.append(float(metrics(test[TARGET], k_hat)["mae"]))
    return float(np.mean(ek_maes)), float(np.std(ek_maes, ddof=0)), float(np.mean(kr_maes))


def _candidate_grid(max_candidates: int) -> list[dict[str, object]]:
    keys = list(SEARCH_GRID.keys())
    raw = [
        {**BASELINE_PARAMS, **dict(zip(keys, values, strict=True))}
        for values in itertools.product(*(SEARCH_GRID[k] for k in keys))
    ]

    def _distance(params: dict[str, object]) -> float:
        score = 0.0
        for key, base in BASELINE_PARAMS.items():
            val = params[key]
            if key in {"learning_rate", "num_leaves", "min_child_samples"}:
                score += abs(float(val) - float(base)) / float(base)
            else:
                score += abs(float(val) - float(base))
        return score

    ranked = sorted(raw, key=_distance)
    selected: list[dict[str, object]] = [dict(BASELINE_PARAMS)]
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


def _retune_nested(
    frame: pd.DataFrame,
    features: list[str],
    *,
    objective: str,
    monotone: bool,
    max_candidates: int,
) -> dict[str, object]:
    folds = nested_research_folds(frame)
    candidates = _candidate_grid(max_candidates=max_candidates)
    selected_outer: list[float] = []
    baseline_outer: list[float] = []
    selected_ids: list[int] = []
    for nested in folds.values():
        inner_scores: dict[int, list[float]] = {i: [] for i in range(len(candidates))}
        for inner in nested.inner.values():
            for idx, params in enumerate(candidates):
                model = _fit_k_model(
                    inner.train,
                    inner.validation,
                    features,
                    objective=objective,
                    monotone=monotone,
                    params=params,
                )
                pred = predict_clipped(model, "lightgbm", inner.validation, features)
                inner_scores[idx].append(float(metrics(inner.validation[TARGET], pred)["mae"]))
        means = {idx: float(np.mean(vals)) for idx, vals in inner_scores.items()}
        best_idx = min(means, key=means.get)
        selected_ids.append(int(best_idx))

        outer_train = nested.outer.train
        cut = int(len(outer_train) * 0.85)
        fit = outer_train.iloc[:cut]
        val = outer_train.iloc[cut:]
        model_sel = _fit_k_model(
            fit,
            val,
            features,
            objective=objective,
            monotone=monotone,
            params=candidates[best_idx],
        )
        model_base = _fit_k_model(
            fit,
            val,
            features,
            objective=objective,
            monotone=monotone,
            params=BASELINE_PARAMS,
        )
        pred_sel = predict_clipped(model_sel, "lightgbm", nested.outer.validation, features)
        pred_base = predict_clipped(model_base, "lightgbm", nested.outer.validation, features)
        selected_outer.append(float(metrics(nested.outer.validation[TARGET], pred_sel)["mae"]))
        baseline_outer.append(float(metrics(nested.outer.validation[TARGET], pred_base)["mae"]))
    return {
        "objective": objective,
        "monotone": monotone,
        "selected_outer_mae_mean": float(np.mean(selected_outer)),
        "baseline_outer_mae_mean": float(np.mean(baseline_outer)),
        "delta_selected_minus_baseline": float(np.mean(selected_outer) - np.mean(baseline_outer)),
        "selected_config_ids": selected_ids,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not ATTR_PATH.exists():
        raise FileNotFoundError(f"Missing {ATTR_PATH}")
    wf = _load_wf()
    frame = wf._load_frame()
    prod = set(resolve_feature_names(frame, "production"))
    ranked = pd.read_csv(ATTR_PATH)["feature"].astype(str).tolist()
    ranked = [f for f in ranked if f in prod]

    frontier_rows: list[dict[str, object]] = []
    for k in K_GRID:
        features = ranked[:k]
        ek_mean, ek_std, kr_mean = _eval_wf(wf, frame, features, objective="regression", monotone=False)
        frontier_rows.append(
            {
                "k_features": k,
                "objective": "regression",
                "monotone": False,
                "wf_expected_k_mae_mean": ek_mean,
                "wf_expected_k_mae_std": ek_std,
                "wf_k_rate_mae_mean": kr_mean,
            }
        )
    frontier = pd.DataFrame(frontier_rows).sort_values("wf_expected_k_mae_mean")
    frontier_path = OUT_DIR / "sparse_k_frontier.csv"
    frontier.to_csv(frontier_path, index=False)

    best_k = int(frontier.iloc[0]["k_features"])
    best_features = ranked[:best_k]

    variants_rows: list[dict[str, object]] = []
    for objective in OBJECTIVES:
        for monotone in (False, True):
            if objective != "regression" and monotone:
                continue
            ek_mean, ek_std, kr_mean = _eval_wf(
                wf,
                frame,
                best_features,
                objective=objective,
                monotone=monotone,
            )
            variants_rows.append(
                {
                    "k_features": best_k,
                    "objective": objective,
                    "monotone": monotone,
                    "wf_expected_k_mae_mean": ek_mean,
                    "wf_expected_k_mae_std": ek_std,
                    "wf_k_rate_mae_mean": kr_mean,
                }
            )
    variants = pd.DataFrame(variants_rows).sort_values("wf_expected_k_mae_mean")
    variants_path = OUT_DIR / "sparse_bestk_objective_scan.csv"
    variants.to_csv(variants_path, index=False)

    top_configs = variants.head(2).to_dict(orient="records")
    retune_rows: list[dict[str, object]] = []
    for cfg in top_configs:
        ret = _retune_nested(
            frame,
            best_features,
            objective=str(cfg["objective"]),
            monotone=bool(cfg["monotone"]),
            max_candidates=24,
        )
        ret["k_features"] = best_k
        retune_rows.append(ret)
    retune = pd.DataFrame(retune_rows).sort_values("selected_outer_mae_mean")
    retune_path = OUT_DIR / "sparse_bestk_retune.csv"
    retune.to_csv(retune_path, index=False)

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "best_k": best_k,
        "files": {
            "frontier_csv": str(frontier_path),
            "objective_scan_csv": str(variants_path),
            "retune_csv": str(retune_path),
        },
        "best_frontier_row": frontier.iloc[0].to_dict() if not frontier.empty else None,
        "best_variant_row": variants.iloc[0].to_dict() if not variants.empty else None,
        "best_retune_row": retune.iloc[0].to_dict() if not retune.empty else None,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(frontier.to_string(index=False))
    print("\nObjective/monotone scan:")
    print(variants.to_string(index=False))
    print("\nRetune scan:")
    print(retune.to_string(index=False))
    print(f"Wrote {OUT_DIR}")


if __name__ == "__main__":
    main()

