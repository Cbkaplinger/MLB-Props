"""Leave-family-out screen on a named feature registry (Step 3 / Step 8).

For each outer nested fold, fit the full model and each leave-one-family-out
variant on outer-train only, then score outer validation. Also tests dropping
all rolling windows vs all season-to-date columns. Does not use 2025.

Examples:
    python models/Strikeout-Model/research/leave_family_out_ablation.py
    python models/Strikeout-Model/research/leave_family_out_ablation.py --feature-set production --models lightgbm
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from Python import config
from Python.features import TARGET
from Python.registries import FEATURE_SETS, resolve_feature_names
from Python.training import fit_kwargs_for_weights, resolve_sample_weights

EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from nested_cv import fold_metadata, nested_research_folds  # noqa: E402

_ROLLING_RE = re.compile(r"_P\d+$")
_STD_RE = re.compile(r"_std(?:_shrunk)?$")


def _metrics(actual: pd.Series, prediction: np.ndarray) -> dict[str, float]:
    prediction = np.clip(prediction, 0, 1)
    return {
        "mae": float(mean_absolute_error(actual, prediction)),
        "rmse": float(mean_squared_error(actual, prediction) ** 0.5),
        "r2": float(r2_score(actual, prediction)),
    }


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


def _family_map(features: list[str]) -> dict[str, list[str]]:
    dictionary = pd.read_csv(
        config.OUTPUT_DIR / "feature_research" / "feature_dictionary.csv"
    )
    mapping = dictionary.set_index("feature")["family"].to_dict()
    missing = [feature for feature in features if feature not in mapping]
    if missing:
        raise ValueError(f"features missing from dictionary: {missing[:10]}")
    families: dict[str, list[str]] = {}
    for feature in features:
        families.setdefault(mapping[feature], []).append(feature)
    return families


def _structural_drops(features: list[str]) -> dict[str, list[str]]:
    """Return feature lists after removing rolling-only or STD-only columns."""
    rolling = [feature for feature in features if _ROLLING_RE.search(feature)]
    season_to_date = [feature for feature in features if _STD_RE.search(feature)]
    return {
        "drop_rolling_keep_std_and_static": [
            feature for feature in features if feature not in rolling
        ],
        "drop_std_keep_rolling_and_static": [
            feature for feature in features if feature not in season_to_date
        ],
    }


def _configurations(
    features: list[str], families: dict[str, list[str]]
) -> dict[str, list[str]]:
    configs = {"full": list(features)}
    for family, members in sorted(families.items()):
        configs[f"drop_{family}"] = [
            feature for feature in features if feature not in members
        ]
    configs.update(_structural_drops(features))
    return configs


def main(
    models: tuple[str, ...],
    *,
    feature_set: str = "pre_freeze_248",
    output_dir: Path | None = None,
) -> Path:
    if feature_set not in FEATURE_SETS:
        raise ValueError(f"unsupported feature set {feature_set!r}")

    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "game_date"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    frame = frame[frame["season"].isin(config.FEATURE_RESEARCH_SEASONS)].copy()
    observed = tuple(sorted(frame["season"].unique()))
    if observed != config.FEATURE_RESEARCH_SEASONS:
        raise ValueError(
            f"expected {config.FEATURE_RESEARCH_SEASONS}, got {observed}"
        )

    features = list(resolve_feature_names(frame, feature_set))
    families = _family_map(features)
    configurations = _configurations(features, families)
    folds = nested_research_folds(frame)

    if output_dir is None:
        suffix = "leave_family_out" if feature_set == "pre_freeze_248" else f"leave_family_out_{feature_set}"
        output_dir = config.OUTPUT_DIR / "feature_research" / suffix
    output_dir.mkdir(parents=True, exist_ok=True)

    outer_rows: list[dict[str, object]] = []
    for outer_name, nested in folds.items():
        outer = nested.outer
        for model_name in models:
            full_model = _models()[model_name]
            _fit(full_model, model_name, outer.train, configurations["full"])
            full_metrics = _metrics(
                outer.validation[TARGET],
                full_model.predict(outer.validation[configurations["full"]]),
            )
            for configuration, selected in configurations.items():
                model = _models()[model_name]
                _fit(model, model_name, outer.train, selected)
                scored = _metrics(
                    outer.validation[TARGET],
                    model.predict(outer.validation[selected]),
                )
                dropped = len(configurations["full"]) - len(selected)
                outer_rows.append(
                    {
                        "outer_fold": outer_name,
                        "model": model_name,
                        "configuration": configuration,
                        "n_features": len(selected),
                        "n_dropped": dropped,
                        "train_rows": len(outer.train),
                        "validation_rows": len(outer.validation),
                        **scored,
                        "delta_mae_vs_full": scored["mae"] - full_metrics["mae"],
                        "delta_rmse_vs_full": scored["rmse"] - full_metrics["rmse"],
                        "delta_r2_vs_full": scored["r2"] - full_metrics["r2"],
                    }
                )
                print(
                    outer_name,
                    model_name,
                    configuration,
                    {
                        "mae": scored["mae"],
                        "delta_mae": scored["mae"] - full_metrics["mae"],
                    },
                )

    results = pd.DataFrame(outer_rows)
    results.to_csv(output_dir / "outer_results.csv", index=False)

    aggregate = (
        results.groupby(["model", "configuration"], as_index=False)
        .agg(
            outer_folds=("outer_fold", "nunique"),
            mean_mae=("mae", "mean"),
            mean_rmse=("rmse", "mean"),
            mean_r2=("r2", "mean"),
            mean_delta_mae_vs_full=("delta_mae_vs_full", "mean"),
            mean_delta_rmse_vs_full=("delta_rmse_vs_full", "mean"),
            mean_n_features=("n_features", "mean"),
            mean_n_dropped=("n_dropped", "mean"),
            # Both-fold consistency: min delta (must be <0 for a drop candidate)
            min_delta_mae_vs_full=("delta_mae_vs_full", "min"),
            max_delta_mae_vs_full=("delta_mae_vs_full", "max"),
        )
        .sort_values(["model", "mean_delta_mae_vs_full", "configuration"])
    )
    aggregate.to_csv(output_dir / "aggregate.csv", index=False)

    metadata = {
        "feature_set": feature_set,
        "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
        "holdout_season_not_read": config.HOLDOUT_SEASON,
        "n_features_full": len(features),
        "families": {name: len(members) for name, members in families.items()},
        "configurations": {
            name: len(selected) for name, selected in configurations.items()
        },
        "selection_note": (
            "Outer-only leave-family-out / structural drops; positive delta_mae "
            "means the drop hurt vs full. Drop candidates need mean_delta<0 and "
            "max_delta<0 (helps both outer folds)."
        ),
        "folds": fold_metadata(folds),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    # Persist full feature list for Step 8 cumulative prune.
    pd.DataFrame({"feature": features}).to_csv(
        output_dir / "full_features.csv", index=False
    )
    print(aggregate.to_string(index=False))
    print(f"Wrote leave-family-out results to {output_dir}")
    return output_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        nargs="+",
        choices=("ridge", "lightgbm"),
        default=["ridge", "lightgbm"],
    )
    parser.add_argument(
        "--feature-set",
        choices=FEATURE_SETS,
        default="pre_freeze_248",
        help="Registry to screen (default: pre_freeze_248 for Step 3 back-compat).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional artifact directory override.",
    )
    args = parser.parse_args()
    main(
        tuple(args.models),
        feature_set=args.feature_set,
        output_dir=args.output_dir,
    )
