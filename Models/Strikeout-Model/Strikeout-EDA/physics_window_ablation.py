"""Step 4 mean-window thinning screen (physics / usage / mechanics / FIP).

Compares predeclared P3/P5/P10 subsets of the production mean-window families
on outer nested folds. LightGBM is the decision backbone; Ridge is optional
diagnostics only. Does not use 2025.

Examples:
    python Models/Strikeout-Model/Strikeout-EDA/physics_window_ablation.py
    python Models/Strikeout-Model/Strikeout-EDA/physics_window_ablation.py --models lightgbm
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
from Python.features import TARGET, model_feature_names
from Python.training import fit_kwargs_for_weights, resolve_sample_weights

EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from nested_cv import fold_metadata, nested_research_folds  # noqa: E402

MEAN_FAMILIES = ("pitch_physics", "pitch_usage", "mechanics", "fip_xfip")
_WINDOW_RE = re.compile(r"_P(\d+)$")


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


def _window_of(feature: str) -> int | None:
    match = _WINDOW_RE.search(feature)
    return int(match.group(1)) if match else None


def _mean_family_members(families: dict[str, list[str]]) -> list[str]:
    members: list[str] = []
    for family in MEAN_FAMILIES:
        members.extend(families.get(family, []))
    return members


def _configurations(
    features: list[str], families: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Thin only mean-window families; leave rates / lineup / park untouched."""
    mean_members = set(_mean_family_members(families))
    if not mean_members:
        raise ValueError("no mean-window family members found in production list")
    observed = {_window_of(feature) for feature in mean_members}
    if observed != {3, 5, 10}:
        raise ValueError(
            f"expected mean-window members to use P3/P5/P10 only; got {sorted(observed)}"
        )

    keep_windows = {
        "full_P3_P5_P10": {3, 5, 10},
        "mean_P3_only": {3},
        "mean_P5_only": {5},
        "mean_P10_only": {10},
        "mean_P3_P5": {3, 5},
        "mean_P3_P10": {3, 10},
        "mean_P5_P10": {5, 10},
        "drop_mean_families": set(),
    }
    configs: dict[str, list[str]] = {}
    for name, windows in keep_windows.items():
        selected = []
        for feature in features:
            if feature not in mean_members:
                selected.append(feature)
                continue
            window = _window_of(feature)
            if window in windows:
                selected.append(feature)
        configs[name] = selected
    return configs


def main(models: tuple[str, ...]) -> None:
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

    features = list(model_feature_names(frame))
    families = _family_map(features)
    configurations = _configurations(features, families)
    folds = nested_research_folds(frame)

    output_dir = config.OUTPUT_DIR / "feature_research" / "step4_physics_windows"
    output_dir.mkdir(parents=True, exist_ok=True)

    outer_rows: list[dict[str, object]] = []
    for outer_name, nested in folds.items():
        outer = nested.outer
        for model_name in models:
            full_features = configurations["full_P3_P5_P10"]
            full_model = _models()[model_name]
            _fit(full_model, model_name, outer.train, full_features)
            full_metrics = _metrics(
                outer.validation[TARGET],
                full_model.predict(outer.validation[full_features]),
            )
            for configuration, selected in configurations.items():
                model = _models()[model_name]
                _fit(model, model_name, outer.train, selected)
                scored = _metrics(
                    outer.validation[TARGET],
                    model.predict(outer.validation[selected]),
                )
                outer_rows.append(
                    {
                        "outer_fold": outer_name,
                        "model": model_name,
                        "configuration": configuration,
                        "n_features": len(selected),
                        "n_dropped": len(full_features) - len(selected),
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
                        "mae": round(scored["mae"], 6),
                        "delta_mae": round(scored["mae"] - full_metrics["mae"], 6),
                        "n_features": len(selected),
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
            positive_hurt_folds=(
                "delta_mae_vs_full",
                lambda values: int((values > 0).sum()),
            ),
        )
        .sort_values(["model", "mean_delta_mae_vs_full", "configuration"])
    )
    aggregate.to_csv(output_dir / "aggregate.csv", index=False)

    metadata = {
        "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
        "holdout_season_not_read": config.HOLDOUT_SEASON,
        "decision_backbone": "lightgbm",
        "n_features_full": len(features),
        "mean_families": list(MEAN_FAMILIES),
        "mean_family_counts": {
            family: len(families.get(family, [])) for family in MEAN_FAMILIES
        },
        "configurations": {
            name: len(selected) for name, selected in configurations.items()
        },
        "selection_note": (
            "Outer-only mean-window thinning on production allow-list. "
            "Positive delta_mae means the thinned config hurt vs full P3/P5/P10."
        ),
        "folds": fold_metadata(folds),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    print(aggregate.to_string(index=False))
    print(f"Wrote Step 4 physics-window results to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        nargs="+",
        choices=("ridge", "lightgbm"),
        default=["lightgbm"],
    )
    main(tuple(parser.parse_args().models))
