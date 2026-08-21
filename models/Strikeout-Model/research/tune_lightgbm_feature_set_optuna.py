"""Nested-CV Optuna tuning for a configurable feature set.

Primary objective:
- Minimize expected_K MAE

Soft constraints:
- k_rate MAE guardrail
- TBF perturbation sensitivity guardrail (+/- 3%)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

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
from Python.tbf import TBF_DEFAULT_FEATURE_SET, TBF_TARGET, tbf_feature_names
from Python.training import (
    build_model,
    fit_regressor,
    lightgbm_matrix,
    metrics,
    predict_clipped,
    predict_nonnegative,
)
from nested_cv import nested_research_folds


def _fit_tbf(train: pd.DataFrame, features: list[str]):
    model = build_model("ridge", ridge_alpha=123.28467394420659)
    fit_regressor(model, "ridge", train[features], train[TBF_TARGET])
    upper = float(train[TBF_TARGET].quantile(0.999))
    return model, upper


def _fit_lgbm(train: pd.DataFrame, val: pd.DataFrame, features: list[str], params: dict) -> object:
    model = build_model(
        "lightgbm",
        lightgbm_n_estimators=5_000,
        lightgbm_verbosity=-1,
        lightgbm_params=params,
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


def _trial_params(trial, monotone_constraints: list[int] | None) -> dict:
    p = {
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.08, log=True),
        "num_leaves": trial.suggest_int("num_leaves", 15, 127),
        "min_child_samples": trial.suggest_int("min_child_samples", 20, 140),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        "bagging_freq": 1,
        "objective": "regression",
        "seed": 42,
        "feature_fraction_seed": 42,
        "bagging_seed": 42,
        "data_random_seed": 42,
    }
    if monotone_constraints is not None:
        p["monotone_constraints"] = monotone_constraints
        p["monotone_constraints_method"] = "advanced"
    return p


def _expected_k_mae(actual_k: pd.Series, k_rate_pred: np.ndarray, tbf_pred: np.ndarray) -> float:
    ek = expected_strikeouts(k_rate_pred, tbf_pred)
    return float(metrics(actual_k, ek, clip_to_unit_interval=False)["mae"])


def _feature_constraints(features: list[str]) -> list[int]:
    pos = ("k_rate_", "opp_lineup_k", "opp_lineup_whiff", "opp_lineup_swstr", "opp_lineup_chase", "park_k_factor")
    neg = ("opp_lineup_zcontact", "opp_lineup_bb")
    out: list[int] = []
    for f in features:
        if any(f == s or f.startswith(s) for s in pos):
            out.append(1)
        elif any(f == s or f.startswith(s) for s in neg):
            out.append(-1)
        else:
            out.append(0)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-set", required=True)
    parser.add_argument("--trials", type=int, default=80)
    parser.add_argument("--k-rate-mae-max", type=float, default=0.0745)
    parser.add_argument("--tbf-sens-max", type=float, default=0.012)
    parser.add_argument("--output-tag", default="")
    args = parser.parse_args()

    try:
        import optuna
    except ImportError as exc:
        raise SystemExit("optuna is required. Install with `pip install optuna`.") from exc

    feature_set = str(args.feature_set)
    monotone = feature_set.endswith("_monotone")
    source_set = feature_set.removesuffix("_monotone")

    frame = (
        pl.read_parquet(config.PITCHER_TRAINING_PATH)
        .with_columns(pl.col("game_date").cast(pl.Datetime, strict=False))
        .filter(
            pl.col("season").is_in(list(config.FEATURE_RESEARCH_SEASONS))
            & pl.col(TARGET).is_not_null()
            & pl.col("K").is_not_null()
            & pl.col("PA").is_not_null()
            & pl.col("game_date").is_not_null()
        )
        .sort(["game_date", "player_name"])
        .to_pandas()
        .reset_index(drop=True)
    )
    features = list(resolve_feature_names(frame, source_set))
    tbf_features = list(tbf_feature_names(frame, TBF_DEFAULT_FEATURE_SET))
    mono_constraints = _feature_constraints(features) if monotone else None
    folds = nested_research_folds(frame)

    tag = args.output_tag.strip() or feature_set
    output_dir = config.OUTPUT_DIR / "model_quality" / "feature_set_optuna_nested" / tag
    output_dir.mkdir(parents=True, exist_ok=True)

    fold_results: list[dict[str, object]] = []
    outer_summary: list[dict[str, object]] = []

    for outer_name, nested in folds.items():
        inner_items = list(nested.inner.items())

        def objective(trial):
            params = _trial_params(trial, mono_constraints)
            expected_maes = []
            k_rate_maes = []
            tbf_sens = []
            for _, inner in inner_items:
                tbf_model, tbf_upper = _fit_tbf(inner.train, tbf_features)
                tbf_hat = predict_nonnegative(
                    tbf_model, "ridge", inner.validation, tbf_features, upper=tbf_upper
                )
                model = _fit_lgbm(inner.train, inner.validation, features, params)
                k_hat = predict_clipped(model, "lightgbm", inner.validation, features)
                mae_k = float(metrics(inner.validation[TARGET], k_hat)["mae"])
                mae_ek = _expected_k_mae(inner.validation["K"], k_hat, tbf_hat)
                mae_ek_minus = _expected_k_mae(inner.validation["K"], k_hat, tbf_hat * 0.97)
                mae_ek_plus = _expected_k_mae(inner.validation["K"], k_hat, tbf_hat * 1.03)
                sens = float(max(abs(mae_ek_minus - mae_ek), abs(mae_ek_plus - mae_ek)))
                expected_maes.append(mae_ek)
                k_rate_maes.append(mae_k)
                tbf_sens.append(sens)

            mean_expected = float(np.mean(expected_maes))
            mean_k = float(np.mean(k_rate_maes))
            mean_sens = float(np.mean(tbf_sens))
            penalty = 0.0
            if mean_k > args.k_rate_mae_max:
                penalty += 10.0 * (mean_k - args.k_rate_mae_max)
            if mean_sens > args.tbf_sens_max:
                penalty += 10.0 * (mean_sens - args.tbf_sens_max)
            trial.set_user_attr("mean_k_rate_mae", mean_k)
            trial.set_user_attr("mean_tbf_sensitivity", mean_sens)
            return mean_expected + penalty

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=max(1, int(args.trials)))
        best_params = _trial_params(study.best_trial, mono_constraints)

        tbf_model, tbf_upper = _fit_tbf(nested.outer.train, tbf_features)
        tbf_hat_outer = predict_nonnegative(
            tbf_model, "ridge", nested.outer.validation, tbf_features, upper=tbf_upper
        )
        model_outer = _fit_lgbm(
            nested.outer.train,
            nested.outer.validation,
            features,
            best_params,
        )
        k_hat_outer = predict_clipped(model_outer, "lightgbm", nested.outer.validation, features)
        mae_k_outer = float(metrics(nested.outer.validation[TARGET], k_hat_outer)["mae"])
        mae_ek_outer = _expected_k_mae(nested.outer.validation["K"], k_hat_outer, tbf_hat_outer)
        mae_ek_minus = _expected_k_mae(nested.outer.validation["K"], k_hat_outer, tbf_hat_outer * 0.97)
        mae_ek_plus = _expected_k_mae(nested.outer.validation["K"], k_hat_outer, tbf_hat_outer * 1.03)
        sens_outer = float(max(abs(mae_ek_minus - mae_ek_outer), abs(mae_ek_plus - mae_ek_outer)))

        outer_summary.append(
            {
                "outer_fold": outer_name,
                "best_value": float(study.best_value),
                "expected_k_mae_outer": mae_ek_outer,
                "k_rate_mae_outer": mae_k_outer,
                "tbf_sensitivity_outer": sens_outer,
                **{f"param_{k}": v for k, v in best_params.items()},
            }
        )
        for t in study.trials:
            fold_results.append(
                {
                    "outer_fold": outer_name,
                    "trial_number": int(t.number),
                    "value": float(t.value) if t.value is not None else None,
                    "mean_k_rate_mae": t.user_attrs.get("mean_k_rate_mae"),
                    "mean_tbf_sensitivity": t.user_attrs.get("mean_tbf_sensitivity"),
                    **{f"param_{k}": v for k, v in t.params.items()},
                }
            )

    trials_df = pd.DataFrame(fold_results)
    outer_df = pd.DataFrame(outer_summary)
    trials_df.to_csv(output_dir / "inner_optuna_trials.csv", index=False)
    outer_df.to_csv(output_dir / "outer_fold_summary.csv", index=False)

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feature_set": feature_set,
        "source_feature_set": source_set,
        "monotone_constraints": bool(monotone),
        "n_features": len(features),
        "trials_per_outer_fold": int(args.trials),
        "constraints": {
            "k_rate_mae_max": float(args.k_rate_mae_max),
            "tbf_sensitivity_max": float(args.tbf_sens_max),
        },
        "mean_expected_k_mae_outer": float(outer_df["expected_k_mae_outer"].mean()),
        "mean_k_rate_mae_outer": float(outer_df["k_rate_mae_outer"].mean()),
        "mean_tbf_sensitivity_outer": float(outer_df["tbf_sensitivity_outer"].mean()),
        "files": {
            "inner_optuna_trials_csv": str(output_dir / "inner_optuna_trials.csv"),
            "outer_fold_summary_csv": str(output_dir / "outer_fold_summary.csv"),
        },
    }
    (output_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

