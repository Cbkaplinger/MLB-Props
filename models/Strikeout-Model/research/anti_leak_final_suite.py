"""Anti-leak final suite: inner-fold OOF permutation ranking + sparse candidate eval."""

from __future__ import annotations

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
from Python.features import TARGET
from Python.registries import resolve_feature_names
from Python.training import build_model, fit_regressor, lightgbm_matrix, metrics, predict_clipped
from nested_cv import nested_research_folds

OUT_DIR = config.OUTPUT_DIR / "model_quality" / "anti_leak_final_suite"
SEED = 11
K_GRID = (40, 48, 56, 64, 72, 80)
_MONO_POS = (
    "k_rate_",
    "opp_lineup_k",
    "opp_lineup_whiff",
    "opp_lineup_swstr",
    "opp_lineup_chase",
    "park_k_factor",
)
_MONO_NEG = ("opp_lineup_zcontact", "opp_lineup_bb")
BASE_PARAMS = {
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_child_samples": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 0.1,
    "reg_lambda": 2.0,
}


def _constraints(features: list[str], mode: str) -> list[int]:
    if mode == "none":
        return [0] * len(features)
    out: list[int] = []
    for feature in features:
        if any(feature == stem or feature.startswith(stem) for stem in _MONO_POS):
            out.append(1)
        elif mode == "refined_signed" and any(
            feature == stem or feature.startswith(stem) for stem in _MONO_NEG
        ):
            out.append(-1)
        else:
            out.append(0)
    return out


def _fit(
    train: pd.DataFrame,
    val: pd.DataFrame,
    features: list[str],
    *,
    mode: str = "none",
) -> object:
    params = dict(BASE_PARAMS)
    params.update(
        {
            "seed": SEED,
            "feature_fraction_seed": SEED,
            "bagging_seed": SEED,
            "data_random_seed": SEED,
            "objective": "regression",
        }
    )
    if float(params.get("subsample", 1.0)) < 1.0:
        params["bagging_freq"] = 1
    cons = _constraints(features, mode)
    if any(v != 0 for v in cons):
        params["monotone_constraints"] = cons
        params["monotone_constraints_method"] = "advanced"
    model = build_model("lightgbm", lightgbm_verbosity=-1, lightgbm_params=params)
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


def _inner_oof_permutation_ranking(frame: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    folds = nested_research_folds(frame)
    rng = np.random.default_rng(SEED)
    stats: dict[str, list[float]] = {f: [] for f in features}
    base_rows: list[dict[str, object]] = []
    for outer_name, nested in folds.items():
        for inner_name, inner in nested.inner.items():
            train = inner.train
            val = inner.validation
            model = _fit(train, val, features, mode="none")
            base_pred = predict_clipped(model, "lightgbm", val, features)
            base_mae = float(metrics(val[TARGET], base_pred)["mae"])
            base_rows.append(
                {
                    "outer_fold": outer_name,
                    "inner_fold": inner_name,
                    "base_mae": base_mae,
                    "validation_rows": len(val),
                }
            )
            for feature in features:
                perm = val[features].copy()
                perm[feature] = rng.permutation(perm[feature].to_numpy())
                pred = predict_clipped(model, "lightgbm", perm, features)
                mae = float(metrics(val[TARGET], pred)["mae"])
                stats[feature].append(mae - base_mae)
    base_df = pd.DataFrame(base_rows)
    base_df.to_csv(OUT_DIR / "inner_oof_base_mae.csv", index=False)
    rows = []
    for feature in features:
        deltas = np.array(stats[feature], dtype=float)
        rows.append(
            {
                "feature": feature,
                "perm_delta_mae_mean": float(np.mean(deltas)),
                "perm_delta_mae_std": float(np.std(deltas, ddof=0)),
                "perm_positive_share": float(np.mean(deltas > 0.0)),
                "n_inner_folds": int(deltas.size),
            }
        )
    rank = pd.DataFrame(rows).sort_values(
        ["perm_delta_mae_mean", "perm_positive_share"],
        ascending=[False, False],
    )
    return rank


def _nested_k_mode_select(
    frame: pd.DataFrame, ranked: list[str]
) -> pd.DataFrame:
    folds = nested_research_folds(frame)
    rows: list[dict[str, object]] = []
    for outer_name, nested in folds.items():
        choices: list[dict[str, object]] = []
        for k in K_GRID:
            feats = ranked[:k]
            for mode in ("none", "coarse_positive", "refined_signed"):
                inner_maes: list[float] = []
                for inner in nested.inner.values():
                    model = _fit(inner.train, inner.validation, feats, mode=mode)
                    pred = predict_clipped(model, "lightgbm", inner.validation, feats)
                    inner_maes.append(float(metrics(inner.validation[TARGET], pred)["mae"]))
                choices.append(
                    {
                        "k_features": k,
                        "constraint_mode": mode,
                        "inner_mean_mae": float(np.mean(inner_maes)),
                    }
                )
        best = sorted(choices, key=lambda x: x["inner_mean_mae"])[0]
        feats = ranked[: int(best["k_features"])]
        model = _fit(nested.outer.train, nested.outer.validation, feats, mode=str(best["constraint_mode"]))
        pred = predict_clipped(model, "lightgbm", nested.outer.validation, feats)
        outer_mae = float(metrics(nested.outer.validation[TARGET], pred)["mae"])
        rows.append(
            {
                "outer_fold": outer_name,
                **best,
                "outer_mae": outer_mae,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "game_date"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    frame = frame[frame["season"].isin(config.FEATURE_RESEARCH_SEASONS)].copy()
    prod_features = list(resolve_feature_names(frame, "production"))

    rank = _inner_oof_permutation_ranking(frame, prod_features)
    rank_path = OUT_DIR / "oof_permutation_ranking.csv"
    rank.to_csv(rank_path, index=False)

    top72 = rank["feature"].head(72).astype(str).tolist()
    pd.DataFrame({"feature": top72}).to_csv(OUT_DIR / "oof_top72_features.csv", index=False)

    nested = _nested_k_mode_select(frame, rank["feature"].astype(str).tolist())
    nested.to_csv(OUT_DIR / "nested_k_mode_selection.csv", index=False)

    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
        "n_production_features": len(prod_features),
        "top72_file": str(OUT_DIR / "oof_top72_features.csv"),
        "best_nested_choice_mean_outer_mae": float(nested["outer_mae"].mean()),
        "most_common_k": int(nested["k_features"].mode().iloc[0]),
        "most_common_constraint_mode": str(nested["constraint_mode"].mode().iloc[0]),
        "files": {
            "oof_permutation_ranking_csv": str(rank_path),
            "nested_k_mode_selection_csv": str(OUT_DIR / "nested_k_mode_selection.csv"),
            "inner_oof_base_mae_csv": str(OUT_DIR / "inner_oof_base_mae.csv"),
        },
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(rank.head(20).to_string(index=False))
    print("\nNested selection:")
    print(nested.to_string(index=False))
    print(f"\nWrote {OUT_DIR}")


if __name__ == "__main__":
    main()

