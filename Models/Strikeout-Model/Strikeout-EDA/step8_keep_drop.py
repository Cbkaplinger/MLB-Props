"""Step 8 — cumulative family prune + chrono bake-off vs frozen 185 production.

Reads leave-family-out outer results for ``production``, greedily drops families
that improve MAE on **both** outer folds, then compares pruned vs full LightGBM
on the production chronological split for rate MAE and expected_K MAE.

Examples:
    python Models/Strikeout-Model/Strikeout-EDA/step8_keep_drop.py
    python Models/Strikeout-Model/Strikeout-EDA/step8_keep_drop.py --skip-lfo
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from Python import config
from Python.count_layer import count_point_metrics, expected_strikeouts
from Python.features import TARGET
from Python.registries import resolve_feature_names, write_registry_csv
from Python.tbf import TBF_DEFAULT_FEATURE_SET, TBF_TARGET, tbf_feature_names
from Python.training import (
    build_model,
    chronological_split,
    fit_regressor,
    lightgbm_matrix,
    predict_clipped,
    predict_nonnegative,
)

EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from leave_family_out_ablation import (  # noqa: E402
    _family_map,
    _fit,
    _metrics,
    _models,
    main as run_leave_family_out,
)
from nested_cv import nested_research_folds  # noqa: E402

_FAMILY_DROP_RE = re.compile(r"^drop_(.+)$")
_STRUCTURAL = frozenset(
    {
        "full",
        "drop_rolling_keep_std_and_static",
        "drop_std_keep_rolling_and_static",
    }
)


def _classify_families(outer: pd.DataFrame, model: str = "lightgbm") -> pd.DataFrame:
    """KEEP / DROP / HOLD from leave-one-family-out outer folds."""
    rows = []
    sub = outer[outer["model"] == model]
    for configuration, group in sub.groupby("configuration"):
        if configuration in _STRUCTURAL:
            continue
        match = _FAMILY_DROP_RE.match(configuration)
        if not match:
            continue
        family = match.group(1)
        deltas = group["delta_mae_vs_full"].to_numpy(dtype=float)
        mean_d = float(deltas.mean())
        min_d = float(deltas.min())
        max_d = float(deltas.max())
        # Dropping the family helps when delta_mae < 0 (model without family is better).
        if max_d < 0:
            decision = "DROP"
        elif min_d > 0:
            decision = "KEEP"
        else:
            decision = "HOLD"
        rows.append(
            {
                "family": family,
                "decision": decision,
                "mean_delta_mae_vs_full": mean_d,
                "min_delta_mae_vs_full": min_d,
                "max_delta_mae_vs_full": max_d,
                "n_folds": int(len(deltas)),
                "interpretation": (
                    "dropping family improves MAE on all outer folds"
                    if decision == "DROP"
                    else (
                        "dropping family hurts MAE on all outer folds"
                        if decision == "KEEP"
                        else "mixed or near-zero across folds"
                    )
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["decision", "mean_delta_mae_vs_full"],
        ascending=[True, True],
    )


def _cumulative_prune(
    frame: pd.DataFrame,
    features: list[str],
    families: dict[str, list[str]],
    *,
    model_name: str = "lightgbm",
) -> tuple[list[str], list[dict[str, object]]]:
    """Greedy drop of families that improve MAE on both outer folds."""
    folds = nested_research_folds(frame)
    remaining = list(features)
    history: list[dict[str, object]] = []

    while True:
        # Score full (current remaining) on each outer fold.
        full_mae: dict[str, float] = {}
        for outer_name, nested in folds.items():
            model = _models()[model_name]
            _fit(model, model_name, nested.outer.train, remaining)
            pred = model.predict(nested.outer.validation[remaining])
            full_mae[outer_name] = _metrics(nested.outer.validation[TARGET], pred)["mae"]

        candidates: list[tuple[str, float, dict[str, float]]] = []
        active_families = {
            name: members
            for name, members in families.items()
            if any(feature in remaining for feature in members)
        }
        for family, members in sorted(active_families.items()):
            selected = [feature for feature in remaining if feature not in members]
            if len(selected) == len(remaining):
                continue
            fold_deltas: dict[str, float] = {}
            for outer_name, nested in folds.items():
                model = _models()[model_name]
                _fit(model, model_name, nested.outer.train, selected)
                pred = model.predict(nested.outer.validation[selected])
                mae = _metrics(nested.outer.validation[TARGET], pred)["mae"]
                fold_deltas[outer_name] = mae - full_mae[outer_name]
            # Require improvement on every outer fold.
            if all(delta < 0 for delta in fold_deltas.values()):
                mean_delta = float(np.mean(list(fold_deltas.values())))
                candidates.append((family, mean_delta, fold_deltas))

        if not candidates:
            break

        # Drop the family with the largest mean improvement (most negative delta).
        candidates.sort(key=lambda item: item[1])
        family, mean_delta, fold_deltas = candidates[0]
        drop_members = set(families[family])
        remaining = [feature for feature in remaining if feature not in drop_members]
        step = {
            "dropped_family": family,
            "mean_delta_mae": mean_delta,
            "fold_deltas": fold_deltas,
            "n_features_after": len(remaining),
        }
        history.append(step)
        print("cumulative drop", step)

    return remaining, history


def _fit_lgbm(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
):
    model = build_model("lightgbm", lightgbm_verbosity=-1)
    fit_regressor(
        model,
        "lightgbm",
        lightgbm_matrix(train, features),
        train[TARGET],
        validation_features=lightgbm_matrix(validation, features),
        validation_target=validation[TARGET],
        early_stopping_rounds=200,
        log_evaluation_period=None,
    )
    return model


def _rate_metrics(y_true: pd.Series, pred: np.ndarray) -> dict[str, float]:
    pred = np.clip(pred, 0, 1)
    return {
        "mae": float(mean_absolute_error(y_true, pred)),
        "rmse": float(mean_squared_error(y_true, pred) ** 0.5),
        "r2": float(r2_score(y_true, pred)),
    }


def _bakeoff(
    frame: pd.DataFrame,
    full_features: list[str],
    pruned_features: list[str],
) -> dict[str, object]:
    train, validation, test = chronological_split(frame)
    report: dict[str, object] = {
        "rows": {
            "train": len(train),
            "validation": len(validation),
            "test": len(test),
        },
        "cutoffs": {
            "train_end": str(train["game_date"].max().date()),
            "validation_start": str(validation["game_date"].min().date()),
            "validation_end": str(validation["game_date"].max().date()),
            "test_start": str(test["game_date"].min().date()),
        },
        "variants": {},
    }

    # Shared TBF Ridge (thin bullpen) for expected_K comparison.
    tbf_features = list(tbf_feature_names(train, TBF_DEFAULT_FEATURE_SET))
    tbf_model = build_model("ridge")
    fit_regressor(tbf_model, "ridge", train[tbf_features], train[TBF_TARGET])
    tbf_upper = float(train[TBF_TARGET].quantile(0.999))

    for name, features in (("production_185", full_features), ("pruned", pruned_features)):
        model = _fit_lgbm(train, validation, features)
        part_report = {}
        for part_name, part in (("validation", validation), ("test", test)):
            k_hat = predict_clipped(model, "lightgbm", part, features)
            tbf_hat = predict_nonnegative(
                tbf_model, "ridge", part, tbf_features, upper=tbf_upper
            )
            expected = expected_strikeouts(k_hat, tbf_hat)
            part_report[part_name] = {
                "k_rate": _rate_metrics(part[TARGET], k_hat),
                "expected_K": count_point_metrics(part["K"], expected),
                "n_features": len(features),
            }
        report["variants"][name] = part_report
        print(name, json.dumps(part_report["test"], indent=2))

    return report


def main(*, skip_lfo: bool = False) -> Path:
    output_dir = config.OUTPUT_DIR / "feature_research" / "step8_keep_drop"
    output_dir.mkdir(parents=True, exist_ok=True)
    lfo_dir = config.OUTPUT_DIR / "feature_research" / "leave_family_out_production"

    if not skip_lfo or not (lfo_dir / "outer_results.csv").exists():
        lfo_dir = run_leave_family_out(
            ("lightgbm",),
            feature_set="production",
            output_dir=lfo_dir,
        )

    outer = pd.read_csv(lfo_dir / "outer_results.csv")
    decisions = _classify_families(outer, model="lightgbm")
    decisions.to_csv(output_dir / "family_decisions.csv", index=False)

    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "K", "PA", "game_date"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    research = frame[frame["season"].isin(config.FEATURE_RESEARCH_SEASONS)].copy()
    full_features = list(resolve_feature_names(research, "production"))
    families = _family_map(full_features)

    pruned, history = _cumulative_prune(
        research, full_features, families, model_name="lightgbm"
    )
    write_registry_csv(
        output_dir / "pruned_features.csv",
        tuple(pruned),
        source="step8_cumulative_prune",
    )
    (output_dir / "prune_history.json").write_text(
        json.dumps(history, indent=2),
        encoding="utf-8",
    )

    # Chrono bake-off on TRAIN_SEASONS frame (same as production trainer).
    train_frame = frame[frame["season"].isin(config.TRAIN_SEASONS)].copy()
    bake = _bakeoff(train_frame, full_features, pruned)

    payload = {
        "approved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseline_feature_set": "production",
        "n_features_full": len(full_features),
        "n_features_pruned": len(pruned),
        "families_dropped": [step["dropped_family"] for step in history],
        "family_decisions_path": str(output_dir / "family_decisions.csv"),
        "lfo_dir": str(lfo_dir),
        "bakeoff": bake,
        "notes": (
            "Step 8 keep/drop on frozen 185 LightGBM production. "
            "Cumulative prune requires MAE improvement on both nested outer folds. "
            "Bake-off reports k_rate and expected_K (× Ridge thin-bullpen TBF)."
        ),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({k: payload[k] for k in (
        "n_features_full", "n_features_pruned", "families_dropped"
    )}, indent=2))
    print(f"Wrote Step 8 artifacts to {output_dir}")
    return output_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-lfo",
        action="store_true",
        help="Reuse existing leave_family_out_production artifacts if present.",
    )
    main(skip_lfo=parser.parse_args().skip_lfo)
