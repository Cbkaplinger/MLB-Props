"""Nested chronological beta-binomial challenger for Step 5.

Two-stage beta-binomial (binomial-GLM mean + MLE concentration) on the same
``nested_research_folds`` / production allow-list used by earlier Step 5 arms.
Also scores LightGBM/Ridge means under binomial and beta-binomial NLL so
dispersion gains are comparable across mean models.

Examples:
    python Models/Strikeout-Model/Strikeout-EDA/beta_binomial_nested_compare.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from Python import config
from Python.features import TARGET, model_feature_names
from Python.likelihoods import (
    BetaBinomialModel,
    BinomialGLM,
    fit_beta_binomial_kappa,
    rate_and_likelihood_metrics,
)
from Python.training import (
    assert_pa_not_in_features,
    build_model,
    fit_regressor,
    lightgbm_matrix,
    predict_clipped,
    resolve_sample_weights,
)

EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from nested_cv import fold_metadata, nested_research_folds  # noqa: E402


def _fit_reference(
    model_name: str,
    train: pd.DataFrame,
    features: list[str],
    sample_weight_mode: str,
):
    model = build_model(
        model_name,
        lightgbm_n_estimators=800,
        lightgbm_verbosity=-1,
    )
    train_weight = resolve_sample_weights(train, sample_weight_mode)
    if model_name == "lightgbm":
        fit_regressor(
            model,
            model_name,
            lightgbm_matrix(train, features),
            train[TARGET],
            train_weight=train_weight,
        )
    else:
        fit_regressor(
            model,
            model_name,
            train[features],
            train[TARGET],
            train_weight=train_weight,
        )
    return model


def _score(
    frame: pd.DataFrame,
    prediction,
    *,
    train_for_kappa: pd.DataFrame | None = None,
    train_prediction: object | None = None,
) -> dict[str, float]:
    """Score rates + binomial NLL; attach BB NLL when train predictions given."""
    kappa = None
    if train_for_kappa is not None and train_prediction is not None:
        kappa = fit_beta_binomial_kappa(
            train_for_kappa["K"],
            train_for_kappa["PA"],
            train_prediction,
        )
    return rate_and_likelihood_metrics(frame, prediction, kappa=kappa)


def main(*, alpha: float, include_references: bool) -> None:
    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "game_date", "PA", "K"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    frame = frame[frame["season"].isin(config.FEATURE_RESEARCH_SEASONS)].copy()
    observed = tuple(sorted(frame["season"].unique()))
    if observed != config.FEATURE_RESEARCH_SEASONS:
        raise ValueError(
            f"expected {config.FEATURE_RESEARCH_SEASONS}, got {observed}"
        )

    features = list(model_feature_names(frame))
    assert_pa_not_in_features(features)
    folds = nested_research_folds(frame)

    output_dir = config.OUTPUT_DIR / "feature_research" / "step5_beta_binomial"
    output_dir.mkdir(parents=True, exist_ok=True)

    arms: list[tuple[str, str]] = [
        ("beta_binomial", "binomial_glm_mean"),
        ("binomial_glm", "binomial_trials"),
    ]
    if include_references:
        arms.extend(
            [
                ("lightgbm", "none"),
                ("lightgbm", "pa"),
                ("ridge", "none"),
            ]
        )

    outer_rows: list[dict[str, object]] = []
    inner_rows: list[dict[str, object]] = []

    for outer_name, nested in folds.items():
        for arm_name, weight_mode in arms:
            for split_name, split in [
                *((f"inner/{name}", fold) for name, fold in nested.inner.items()),
                ("outer", nested.outer),
            ]:
                if arm_name == "beta_binomial":
                    model = BetaBinomialModel(alpha=alpha).fit(
                        split.train, features
                    )
                    prediction = model.predict_proba(split.validation, features)
                    scored = rate_and_likelihood_metrics(
                        split.validation,
                        prediction,
                        kappa=model.kappa,
                    )
                    kappa = model.kappa
                elif arm_name == "binomial_glm":
                    model = BinomialGLM(alpha=alpha).fit(split.train, features)
                    train_mu = model.predict_proba(split.train, features)
                    prediction = model.predict_proba(split.validation, features)
                    scored = _score(
                        split.validation,
                        prediction,
                        train_for_kappa=split.train,
                        train_prediction=train_mu,
                    )
                    kappa = scored.get("kappa")
                else:
                    model = _fit_reference(
                        arm_name, split.train, features, weight_mode
                    )
                    train_mu = predict_clipped(
                        model, arm_name, split.train, features
                    )
                    prediction = predict_clipped(
                        model, arm_name, split.validation, features
                    )
                    scored = _score(
                        split.validation,
                        prediction,
                        train_for_kappa=split.train,
                        train_prediction=train_mu,
                    )
                    kappa = scored.get("kappa")

                row = {
                    "outer_fold": outer_name,
                    "split": split_name,
                    "arm": arm_name,
                    "sample_weight": weight_mode,
                    "n_features": len(features),
                    "train_rows": len(split.train),
                    "validation_rows": len(split.validation),
                    "binomial_alpha": alpha,
                    "fitted_kappa": kappa,
                    **scored,
                }
                if split_name == "outer":
                    outer_rows.append(row)
                else:
                    inner_rows.append(
                        {
                            **row,
                            "inner_fold": split_name.removeprefix("inner/"),
                        }
                    )
                print(
                    split_name,
                    outer_name,
                    arm_name,
                    weight_mode,
                    {
                        "mae": scored["unweighted_mae"],
                        "bin_nll_pa": scored["binomial_nll_per_pa"],
                        "bb_nll_pa": scored.get("beta_binomial_nll_per_pa"),
                        "kappa": kappa,
                    },
                )

    inner_results = pd.DataFrame(inner_rows)
    outer_results = pd.DataFrame(outer_rows)
    inner_results.to_csv(output_dir / "inner_results.csv", index=False)
    outer_results.to_csv(output_dir / "outer_results.csv", index=False)

    aggregate = (
        outer_results.groupby(["arm", "sample_weight"], as_index=False)
        .agg(
            outer_folds=("outer_fold", "nunique"),
            mean_unweighted_mae=("unweighted_mae", "mean"),
            mean_unweighted_rmse=("unweighted_rmse", "mean"),
            mean_binomial_nll_per_pa=("binomial_nll_per_pa", "mean"),
            mean_beta_binomial_nll_per_pa=("beta_binomial_nll_per_pa", "mean"),
            mean_fitted_kappa=("fitted_kappa", "mean"),
        )
        .sort_values(
            [
                "mean_beta_binomial_nll_per_pa",
                "mean_binomial_nll_per_pa",
                "mean_unweighted_mae",
            ]
        )
    )
    aggregate.to_csv(output_dir / "aggregate.csv", index=False)

    metadata = {
        "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
        "holdout_season_not_read": config.HOLDOUT_SEASON,
        "arms": [{"arm": arm, "sample_weight": weight} for arm, weight in arms],
        "n_features": len(features),
        "feature_gate": "model_feature_names(include_experimental=False)",
        "binomial_alpha": alpha,
        "beta_binomial": (
            "two-stage: mean from BinomialGLM (or reference regressor), "
            "global kappa MLE on training rows only"
        ),
        "related_findings": [
            "docs/step5_pa_weight_findings.md",
            "docs/step5_binomial_findings.md",
        ],
        "folds": fold_metadata(folds),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    print(aggregate.to_string(index=False))
    print(f"Wrote Step 5 beta-binomial nested comparison to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument(
        "--skip-references",
        action="store_true",
        help="Fit only binomial/beta-binomial GLM arms.",
    )
    args = parser.parse_args()
    main(alpha=args.alpha, include_references=not args.skip_references)
