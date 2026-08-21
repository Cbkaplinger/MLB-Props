"""Phase 11.A — nested LightGBM HPO on the frozen production 180 registry.

Search happens only on inner chronological folds. Outer folds confirm the
selected config and never enter the search loop. 2025 rows are excluded.

Examples:
    python models/Strikeout-Model/research/tune_lightgbm_production.py
    python models/Strikeout-Model/research/tune_lightgbm_production.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from Python import config
from Python.features import TARGET
from Python.registries import resolve_feature_names
from Python.training import (
    assert_pa_not_in_features,
    build_model,
    chronological_split,
    fit_regressor,
    lightgbm_matrix,
    metrics,
    predict_clipped,
)

EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from nested_cv import fold_metadata, nested_research_folds  # noqa: E402

# Defaults matching production train.py / freeze artifact.
BASELINE_PARAMS = {
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_child_samples": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 0.1,
    "reg_lambda": 2.0,
}

# Small chrono-safe grid (Phase 11.A: not Optuna over features).
SEARCH_GRID = {
    "learning_rate": (0.02, 0.03, 0.05),
    "num_leaves": (15, 31, 63),
    "min_child_samples": (30, 50, 100),
    "subsample": (0.7, 0.8, 1.0),
    "colsample_bytree": (0.6, 0.7, 0.9),
    "reg_lambda": (1.0, 2.0, 5.0),
}

# Cap total configs so a laptop can finish overnight; baseline always included.
MAX_CANDIDATES = 24


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_grid(*, max_candidates: int = MAX_CANDIDATES) -> list[dict]:
    """Build a compact candidate list; always includes the freeze baseline."""
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


def _fit_lgbm(
    train: pd.DataFrame,
    features: list[str],
    params: dict,
    *,
    validation: pd.DataFrame | None = None,
    early_stopping_rounds: int | None = 200,
    n_estimators: int = 5_000,
) -> object:
    # subsample is inactive in LightGBM unless bagging_freq > 0.
    fit_params = dict(params)
    if fit_params.get("subsample", 1.0) < 1.0:
        fit_params.setdefault("bagging_freq", 1)
    model = build_model(
        "lightgbm",
        lightgbm_n_estimators=n_estimators,
        lightgbm_verbosity=-1,
        lightgbm_params=fit_params,
    )
    if validation is not None and early_stopping_rounds is not None:
        fit_regressor(
            model,
            "lightgbm",
            lightgbm_matrix(train, features),
            train[TARGET],
            validation_features=lightgbm_matrix(validation, features),
            validation_target=validation[TARGET],
            early_stopping_rounds=early_stopping_rounds,
            log_evaluation_period=0,
        )
    else:
        fit_regressor(
            model,
            "lightgbm",
            lightgbm_matrix(train, features),
            train[TARGET],
        )
    return model


def _mae(model, frame: pd.DataFrame, features: list[str]) -> float:
    pred = predict_clipped(model, "lightgbm", frame, features)
    return metrics(frame[TARGET], pred)["mae"]


def main(*, max_candidates: int, dry_run: bool, refit: bool) -> None:
    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.loc[frame["season"].isin(config.FEATURE_RESEARCH_SEASONS)]
        .dropna(subset=[TARGET, "game_date"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    observed = tuple(sorted(frame["season"].unique()))
    if observed != config.FEATURE_RESEARCH_SEASONS:
        raise ValueError(
            f"expected {config.FEATURE_RESEARCH_SEASONS}, got {observed}"
        )

    features = list(resolve_feature_names(frame, "production"))
    assert_pa_not_in_features(features)
    candidates = _candidate_grid(max_candidates=max_candidates)
    folds = nested_research_folds(frame)

    output_dir = config.OUTPUT_DIR / "model_quality" / "phase11a_lgbm_hpo"
    output_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        print(
            json.dumps(
                {
                    "n_candidates": len(candidates),
                    "n_features": len(features),
                    "n_rows": len(frame),
                    "candidates": candidates,
                    "fold_metadata": fold_metadata(folds),
                    "output_dir": str(output_dir),
                },
                indent=2,
            )
        )
        return

    inner_rows: list[dict[str, object]] = []
    outer_rows: list[dict[str, object]] = []
    selections: list[dict[str, object]] = []

    for outer_name, nested in folds.items():
        # --- inner selection ---
        config_scores: dict[int, list[float]] = {i: [] for i in range(len(candidates))}
        best_iterations: dict[int, list[int]] = {i: [] for i in range(len(candidates))}

        for inner_name, inner in nested.inner.items():
            for idx, params in enumerate(candidates):
                model = _fit_lgbm(
                    inner.train,
                    features,
                    params,
                    validation=inner.validation,
                    early_stopping_rounds=200,
                )
                mae = _mae(model, inner.validation, features)
                config_scores[idx].append(mae)
                best_iter = int(getattr(model, "best_iteration_", 800) or 800)
                best_iterations[idx].append(best_iter)
                inner_rows.append(
                    {
                        "outer_fold": outer_name,
                        "inner_fold": inner_name,
                        "config_id": idx,
                        "is_baseline": params == BASELINE_PARAMS,
                        "mae": mae,
                        "best_iteration": best_iter,
                        **{f"param_{k}": v for k, v in params.items()},
                    }
                )

        mean_inner = {
            idx: float(sum(vals) / len(vals)) for idx, vals in config_scores.items()
        }
        selected_id = min(mean_inner, key=mean_inner.get)
        selected_params = candidates[selected_id]
        mean_best_iter = int(
            round(sum(best_iterations[selected_id]) / len(best_iterations[selected_id]))
        )
        selections.append(
            {
                "outer_fold": outer_name,
                "selected_config_id": selected_id,
                "selected_params": selected_params,
                "mean_inner_mae": mean_inner[selected_id],
                "baseline_mean_inner_mae": mean_inner[0],
                "mean_best_iteration": mean_best_iter,
            }
        )

        # --- outer confirmation: fixed trees from inner, never early-stop on outer ---
        n_trees = max(mean_best_iter, 100)
        for label, params in (
            ("selected", selected_params),
            ("baseline", BASELINE_PARAMS),
        ):
            model = _fit_lgbm(
                nested.outer.train,
                features,
                params,
                validation=None,
                early_stopping_rounds=None,
                n_estimators=n_trees if label == "selected" else n_trees,
            )
            # Baseline uses same tree budget for a fair compare on this fold.
            outer_mae = _mae(model, nested.outer.validation, features)
            outer_rows.append(
                {
                    "outer_fold": outer_name,
                    "arm": label,
                    "mae": outer_mae,
                    "n_estimators": n_trees,
                    "config_id": selected_id if label == "selected" else 0,
                    **{
                        f"param_{k}": v
                        for k, v in (
                            selected_params if label == "selected" else BASELINE_PARAMS
                        ).items()
                    },
                }
            )

    inner_df = pd.DataFrame(inner_rows)
    outer_df = pd.DataFrame(outer_rows)
    inner_path = output_dir / "inner_results.csv"
    outer_path = output_dir / "outer_results.csv"
    selections_path = output_dir / "selections.json"
    inner_df.to_csv(inner_path, index=False)
    outer_df.to_csv(outer_path, index=False)
    selections_path.write_text(json.dumps(selections, indent=2), encoding="utf-8")

    # Consensus: mean outer MAE for selected vs baseline; pick params that won
    # most often (or lower mean inner MAE if tie).
    from collections import Counter

    win_counts = Counter(s["selected_config_id"] for s in selections)
    consensus_id = win_counts.most_common(1)[0][0]
    consensus_params = candidates[consensus_id]

    selected_outer = outer_df[outer_df["arm"] == "selected"]["mae"].mean()
    baseline_outer = outer_df[outer_df["arm"] == "baseline"]["mae"].mean()

    metadata = {
        "phase": "11.A",
        "feature_set": "production",
        "n_features": len(features),
        "n_candidates": len(candidates),
        "n_rows": len(frame),
        "train_seasons": list(config.FEATURE_RESEARCH_SEASONS),
        "baseline_params": BASELINE_PARAMS,
        "consensus_config_id": consensus_id,
        "consensus_params": consensus_params,
        "mean_outer_mae_selected": float(selected_outer),
        "mean_outer_mae_baseline": float(baseline_outer),
        "delta_mae_selected_minus_baseline": float(selected_outer - baseline_outer),
        "selections": selections,
        "fold_metadata": fold_metadata(folds),
        "training_artifact": str(config.PITCHER_TRAINING_PATH),
        "training_artifact_sha256": _sha256(config.PITCHER_TRAINING_PATH),
        "approved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "compare_freeze_artifact": "lightgbm_krate_20260728_033241",
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))

    if not refit:
        return

    # Production-style refit on chronological train/val with early stopping on val.
    train, validation, test = chronological_split(frame)
    mean_trees = int(
        round(
            sum(s["mean_best_iteration"] for s in selections) / max(len(selections), 1)
        )
    )
    model = _fit_lgbm(
        train,
        features,
        consensus_params,
        validation=validation,
        early_stopping_rounds=200,
        n_estimators=5_000,
    )
    val_pred = predict_clipped(model, "lightgbm", validation, features)
    test_pred = predict_clipped(model, "lightgbm", test, features)
    report = {
        "params": consensus_params,
        "best_iteration": int(getattr(model, "best_iteration_", mean_trees) or mean_trees),
        "validation": metrics(validation[TARGET], val_pred),
        "test": metrics(test[TARGET], test_pred),
        "rows": {
            "train": len(train),
            "validation": len(validation),
            "test": len(test),
        },
    }
    config.ensure_output_directories()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = config.MODEL_DIR / f"lightgbm_krate_tuned_{stamp}"
    model.booster_.save_model(stem.with_suffix(".txt"))
    payload = {
        "phase": "11.A",
        "features": features,
        "evaluation": report,
        "hpo_metadata": metadata,
        "registry_freeze": {
            "status": "frozen",
            "feature_set": "production",
            "n_features": len(features),
        },
    }
    stem.with_suffix(".json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (output_dir / "refit_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(f"Saved tuned model to {stem.with_suffix('.txt')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=MAX_CANDIDATES,
        help="Cap on HPO configs (baseline always included).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print candidate grid and fold metadata without fitting.",
    )
    parser.add_argument(
        "--refit",
        action="store_true",
        help="After nested search, refit consensus params and save under artifacts/models/.",
    )
    args = parser.parse_args()
    main(
        max_candidates=args.max_candidates,
        dry_run=args.dry_run,
        refit=args.refit,
    )
