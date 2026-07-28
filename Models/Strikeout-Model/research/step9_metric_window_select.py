"""Step 9 — per-metric nested window selection (fine tooth comb).

Family-level screens (Steps 3/8) do not answer ``swstr_P5`` vs ``swstr_P20``
or whether ``opp_lineup_chase`` is dead weight. This script does:

1. Freeze production-185 **before** joining research windows.
2. Materialize longer windows (rate P15/P30, mean P15/P20) from Level 1 games.
3. For each multi-window metric, nested-inner-select among:
   - drop the metric entirely
   - at most one ``P{w}`` (candidates include longer windows)
   - optional season-to-date ``_std`` (rates only; expanding within-season)
   - ``P{w}+std``
4. Leave-one-column-out for static production columns (lineup / park / is_home).
5. Assemble a thin registry (fold agreement rules below).
6. Chrono bake-off thin vs production 185 on k-rate MAE and expected_K MAE.

Does not use 2025 rows. Does not mutate production registries.

Examples:
    python models/Strikeout-Model/research/step9_metric_window_select.py --skip-means
    python models/Strikeout-Model/research/step9_metric_window_select.py --finalize-only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import polars as pl
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="lightgbm")

from Python import config
from Python.count_layer import count_point_metrics, expected_strikeouts
from Python.features import TARGET
from Python.pitcher_rolling import (
    DEFAULT_MEAN_COLS,
    DEFAULT_RATE_STATS,
    add_rolling_pitcher_features,
)
from Python.registries import production_features, write_registry_csv
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

from nested_cv import fold_metadata, nested_research_folds  # noqa: E402

OUTPUT_DIR = config.OUTPUT_DIR / "feature_research" / "step9_metric_windows"
RATE_CANDIDATE_WINDOWS = (5, 10, 15, 20, 30)
MEAN_CANDIDATE_WINDOWS = (3, 5, 10, 15, 20)
EXTRA_RATE_WINDOWS = (15, 30)
EXTRA_MEAN_WINDOWS = (15, 20)

_WINDOW_RE = re.compile(r"^(.*)_P(\d+)$")
_STD_RE = re.compile(r"^(.*)_std(?:_shrunk)?$")
_RATE_STEMS = frozenset(DEFAULT_RATE_STATS)


def _metrics(actual: pd.Series, prediction: np.ndarray) -> dict[str, float]:
    prediction = np.clip(prediction, 0, 1)
    return {
        "mae": float(mean_absolute_error(actual, prediction)),
        "rmse": float(mean_squared_error(actual, prediction) ** 0.5),
        "r2": float(r2_score(actual, prediction)),
    }


def _lgbm(*, n_estimators: int = 400) -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(
        objective="regression",
        n_estimators=n_estimators,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=50,
        subsample=0.8,
        colsample_bytree=0.7,
        reg_alpha=0.1,
        reg_lambda=2.0,
        random_state=42,
        verbosity=-1,
        n_jobs=-1,
    )


def _fit_inner(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
) -> np.ndarray:
    model = _lgbm(n_estimators=400)
    fit_kwargs: dict[str, object] = {
        "callbacks": [lgb.early_stopping(30, verbose=False)],
    }
    try:
        model.fit(
            train[features],
            train[TARGET],
            eval_X=validation[features],
            eval_y=validation[TARGET],
            **fit_kwargs,
        )
    except TypeError:
        model.fit(
            train[features],
            train[TARGET],
            eval_set=[(validation[features], validation[TARGET])],
            **fit_kwargs,
        )
    return model.predict(validation[features])


def _fit_outer(train: pd.DataFrame, features: list[str]) -> lgb.LGBMRegressor:
    model = _lgbm(n_estimators=800)
    model.fit(train[features], train[TARGET])
    return model


def _load_research_frame() -> pd.DataFrame:
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
    return frame


def _freeze_production(frame: pd.DataFrame) -> list[str]:
    """Resolve production 185 before research windows are joined."""
    features = list(production_features(frame))
    if any(feature.endswith(("_P15", "_P30")) for feature in features):
        raise ValueError(
            "production list already contains P15/P30 — refuse to freeze"
        )
    if len(features) != 185:
        raise ValueError(f"expected 185 production features, got {len(features)}")
    path = OUTPUT_DIR / "production_185_frozen.csv"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"feature": features}).to_csv(path, index=False)
    pd.DataFrame({"feature": features}).to_csv(
        OUTPUT_DIR / "production_185.csv", index=False
    )
    return features


def _materialize_extra_windows(frame: pd.DataFrame) -> pd.DataFrame:
    games = pl.read_parquet(config.PITCHER_GAMES_PATH)
    generated = add_rolling_pitcher_features(
        games,
        rate_stats=DEFAULT_RATE_STATS,
        mean_cols=DEFAULT_MEAN_COLS,
        rate_windows=EXTRA_RATE_WINDOWS,
        mean_windows=EXTRA_MEAN_WINDOWS,
        workload_cols=(),
        workload_windows=(),
        season_to_date=False,
        add_rest=False,
    )
    want = [
        column
        for column in generated.columns
        if _WINDOW_RE.match(column)
        and int(_WINDOW_RE.match(column).group(2)) in {15, 20, 30}
        and column not in frame.columns
    ]
    if not want:
        print("no extra window columns to materialize")
        return frame
    values = generated.select("game_pk", "pitcher", *want).to_pandas()
    out = frame.merge(
        values,
        on=["game_pk", "pitcher"],
        how="left",
        validate="1:1",
    )
    print(f"materialized {len(want)} extra window columns")
    return out


def _metric_groups(features: list[str]) -> dict[str, dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    static: list[str] = []
    for feature in features:
        match = _WINDOW_RE.match(feature)
        if match:
            stem, window = match.group(1), int(match.group(2))
            bucket = groups.setdefault(
                stem, {"windows": {}, "std": None, "kind": "mean"}
            )
            bucket["windows"][window] = feature
            continue
        match = _STD_RE.match(feature)
        if match:
            stem = match.group(1)
            bucket = groups.setdefault(
                stem, {"windows": {}, "std": None, "kind": "rate"}
            )
            bucket["std"] = feature
            continue
        static.append(feature)
    for stem, bucket in groups.items():
        if bucket.get("std") is not None or stem in _RATE_STEMS:
            bucket["kind"] = "rate"
        else:
            bucket["kind"] = "mean"
    groups["__static__"] = {
        "windows": {},
        "std": None,
        "kind": "static",
        "members": static,
    }
    return groups


def _available_windows(
    stem: str,
    kind: str,
    frame: pd.DataFrame,
) -> dict[int, str]:
    candidates = RATE_CANDIDATE_WINDOWS if kind == "rate" else MEAN_CANDIDATE_WINDOWS
    available: dict[int, str] = {}
    for window in candidates:
        column = f"{stem}_P{window}"
        if column in frame.columns:
            available[window] = column
    return available


def _metric_configs(
    available: dict[int, str],
    std_col: str | None,
    full_cols: list[str],
) -> dict[str, list[str]]:
    configs: dict[str, list[str]] = {"drop": [], "full": list(full_cols)}
    if std_col is not None:
        configs["std_only"] = [std_col]
    for window, column in sorted(available.items()):
        configs[f"P{window}"] = [column]
        if std_col is not None:
            configs[f"P{window}+std"] = [column, std_col]
    return {
        name: cols
        for name, cols in configs.items()
        if all(column in available.values() or column == std_col or column in full_cols
               or name == "drop"
               for column in cols)
        or name in {"drop", "full"}
    }


def _background(
    production: list[str],
    metric_members: set[str],
    chosen: list[str],
) -> list[str]:
    return [feature for feature in production if feature not in metric_members] + list(
        chosen
    )


def _select_inner(results: pd.DataFrame) -> pd.DataFrame:
    aggregate = (
        results.groupby(
            ["metric", "outer_fold", "configuration"],
            as_index=False,
        )
        .agg(
            n_features=("n_features", "first"),
            n_metric_cols=("n_metric_cols", "first"),
            inner_folds=("inner_fold", "nunique"),
            inner_mean_mae=("mae", "mean"),
            inner_mean_rmse=("rmse", "mean"),
            inner_mean_r2=("r2", "mean"),
        )
        .sort_values(
            [
                "metric",
                "outer_fold",
                "inner_mean_mae",
                "n_metric_cols",
                "n_features",
                "configuration",
            ]
        )
    )
    return aggregate.drop_duplicates(["metric", "outer_fold"], keep="first")


def _run_metric_screen(
    frame: pd.DataFrame,
    production: list[str],
    groups: dict[str, dict[str, object]],
    *,
    skip_means: bool,
    means_only: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    folds = nested_research_folds(frame)
    inner_rows: list[dict[str, object]] = []
    config_lookup: dict[str, dict[str, list[str]]] = {}

    stems = sorted(
        stem
        for stem, meta in groups.items()
        if stem != "__static__"
        and len(meta["windows"]) >= 1
        and not (skip_means and meta["kind"] == "mean")
        and not (means_only and meta["kind"] != "mean")
    )

    for stem in stems:
        meta = groups[stem]
        kind = str(meta["kind"])
        prod_windows: dict[int, str] = {
            window: column
            for window, column in dict(meta["windows"]).items()  # type: ignore[arg-type]
            if column in production
        }
        available = _available_windows(stem, kind, frame)
        std_col = meta["std"] if isinstance(meta["std"], str) else None
        if std_col is not None and std_col not in production:
            std_col = None

        members = set(prod_windows.values())
        if std_col is not None:
            members.add(std_col)
        full_cols = [feature for feature in production if feature in members]
        configs = _metric_configs(available, std_col, full_cols)
        # Ensure every config column exists on the frame.
        configs = {
            name: cols
            for name, cols in configs.items()
            if all(column in frame.columns for column in cols)
        }
        config_lookup[stem] = configs

        for outer_name, nested in folds.items():
            for inner_name, inner in nested.inner.items():
                for configuration, chosen in configs.items():
                    features = _background(production, members, chosen)
                    if not features:
                        continue
                    pred = _fit_inner(inner.train, inner.validation, features)
                    result = _metrics(inner.validation[TARGET], pred)
                    inner_rows.append(
                        {
                            "metric": stem,
                            "kind": kind,
                            "outer_fold": outer_name,
                            "inner_fold": inner_name,
                            "configuration": configuration,
                            "n_features": len(features),
                            "n_metric_cols": len(chosen),
                            "metric_cols": "|".join(chosen),
                            "train_rows": len(inner.train),
                            "validation_rows": len(inner.validation),
                            **result,
                        }
                    )
            print(f"inner done: {stem} / {outer_name}", flush=True)
        pd.DataFrame(inner_rows).to_csv(OUTPUT_DIR / "inner_results.csv", index=False)

    inner_results = pd.DataFrame(inner_rows)
    selections = _select_inner(inner_results)

    outer_rows: list[dict[str, object]] = []
    for selection in selections.itertuples(index=False):
        outer = folds[selection.outer_fold].outer
        configs = config_lookup[selection.metric]
        meta = groups[selection.metric]
        prod_windows = {
            window: column
            for window, column in dict(meta["windows"]).items()  # type: ignore[arg-type]
            if column in production
        }
        members = set(prod_windows.values())
        if isinstance(meta["std"], str) and meta["std"] in production:
            members.add(meta["std"])

        chosen = configs[selection.configuration]
        features = _background(production, members, chosen)
        full_features = _background(production, members, configs["full"])

        selected_model = _fit_outer(outer.train, features)
        selected_metrics = _metrics(
            outer.validation[TARGET],
            selected_model.predict(outer.validation[features]),
        )
        full_model = _fit_outer(outer.train, full_features)
        full_metrics = _metrics(
            outer.validation[TARGET],
            full_model.predict(outer.validation[full_features]),
        )
        outer_rows.append(
            {
                "metric": selection.metric,
                "kind": groups[selection.metric]["kind"],
                "outer_fold": selection.outer_fold,
                "selected_configuration": selection.configuration,
                "metric_cols": "|".join(chosen),
                "n_metric_cols": len(chosen),
                "n_features": len(features),
                "inner_mean_mae": selection.inner_mean_mae,
                "mae": selected_metrics["mae"],
                "rmse": selected_metrics["rmse"],
                "r2": selected_metrics["r2"],
                "full_mae": full_metrics["mae"],
                "delta_mae_vs_full": selected_metrics["mae"] - full_metrics["mae"],
            }
        )
        print(
            f"outer done: {selection.metric} / {selection.outer_fold} -> "
            f"{selection.configuration}",
            flush=True,
        )

    return inner_results, selections, pd.DataFrame(outer_rows)


def _run_static_loco(
    frame: pd.DataFrame,
    production: list[str],
    static_cols: list[str],
) -> pd.DataFrame:
    folds = nested_research_folds(frame)
    rows: list[dict[str, object]] = []
    for column in static_cols:
        for outer_name, nested in folds.items():
            inner_keep = []
            inner_drop = []
            for _inner_name, inner in nested.inner.items():
                keep_pred = _fit_inner(inner.train, inner.validation, production)
                drop_features = [feature for feature in production if feature != column]
                drop_pred = _fit_inner(inner.train, inner.validation, drop_features)
                inner_keep.append(_metrics(inner.validation[TARGET], keep_pred)["mae"])
                inner_drop.append(_metrics(inner.validation[TARGET], drop_pred)["mae"])
            prefer_drop = float(np.mean(inner_drop)) < float(np.mean(inner_keep))
            selected = "drop" if prefer_drop else "keep"

            outer = nested.outer
            keep_model = _fit_outer(outer.train, production)
            keep_mae = _metrics(
                outer.validation[TARGET],
                keep_model.predict(outer.validation[production]),
            )["mae"]
            drop_features = [feature for feature in production if feature != column]
            drop_model = _fit_outer(outer.train, drop_features)
            drop_mae = _metrics(
                outer.validation[TARGET],
                drop_model.predict(outer.validation[drop_features]),
            )["mae"]
            rows.append(
                {
                    "column": column,
                    "outer_fold": outer_name,
                    "selected_configuration": selected,
                    "inner_mean_mae_keep": float(np.mean(inner_keep)),
                    "inner_mean_mae_drop": float(np.mean(inner_drop)),
                    "keep_mae": keep_mae,
                    "drop_mae": drop_mae,
                    "delta_mae_drop_vs_keep": drop_mae - keep_mae,
                }
            )
            print(f"static LOCO: {column} / {outer_name} -> {selected}", flush=True)
    return pd.DataFrame(rows)


def _parse_config(name: str) -> tuple[int | None, bool, bool]:
    """Return (window, include_std, is_special)."""
    if name in {"drop", "full"}:
        return None, False, True
    if name == "std_only":
        return None, True, False
    if name.endswith("+std") and name.startswith("P"):
        return int(name[1:-4]), True, False
    if name.startswith("P") and name[1:].isdigit():
        return int(name[1:]), False, False
    return None, False, True


def _assemble_thin(
    production: list[str],
    groups: dict[str, dict[str, object]],
    outer_results: pd.DataFrame,
    static_loco: pd.DataFrame,
) -> tuple[list[str], pd.DataFrame]:
    decisions: list[dict[str, object]] = []
    drop_members: set[str] = set()
    replace: dict[str, list[str]] = {}

    for metric, group in outer_results.groupby("metric"):
        meta = groups[str(metric)]
        members = {
            column
            for column in dict(meta["windows"]).values()  # type: ignore[arg-type]
            if column in production
        }
        if isinstance(meta["std"], str) and meta["std"] in production:
            members.add(meta["std"])
        full_cols = [feature for feature in production if feature in members]
        configs = sorted(group["selected_configuration"].astype(str).unique())

        if len(configs) == 1:
            chosen_name = configs[0]
            chosen_cols = str(
                group.loc[
                    group["selected_configuration"] == chosen_name, "metric_cols"
                ].iloc[0]
            )
            chosen_list = [part for part in chosen_cols.split("|") if part]
            if chosen_name == "full":
                decision = "HOLD_FULL"
                chosen_list = full_cols
            elif chosen_name == "drop":
                decision = "DROP"
                drop_members |= members
                chosen_list = []
            else:
                decision = "THIN"
                replace[str(metric)] = chosen_list
                drop_members |= members - set(chosen_list)
        else:
            parsed = [_parse_config(name) for name in configs]
            windows = {window for window, _std, special in parsed if not special and window is not None}
            specials = {name for name in configs if _parse_config(name)[2]}
            if not specials and len(windows) == 1:
                window = next(iter(windows))
                std_votes = [
                    include_std
                    for win, include_std, special in parsed
                    if not special and win == window
                ]
                keep_std = bool(std_votes) and all(std_votes) and isinstance(
                    meta["std"], str
                )
                column = f"{metric}_P{window}"
                chosen_list = [column]
                if keep_std:
                    chosen_list.append(str(meta["std"]))
                decision = "THIN_WINDOW_AGREE"
                chosen_name = f"P{window}" + ("+std" if keep_std else "")
                replace[str(metric)] = chosen_list
                drop_members |= members - set(chosen_list)
            else:
                decision = "HOLD_DISAGREE"
                chosen_name = "|".join(configs)
                chosen_list = full_cols

        decisions.append(
            {
                "metric": metric,
                "kind": meta["kind"],
                "decision": decision,
                "selected_configurations": chosen_name,
                "chosen_cols": "|".join(chosen_list),
                "n_full": len(full_cols),
                "n_chosen": len(chosen_list),
                "mean_delta_mae_vs_full": float(group["delta_mae_vs_full"].mean()),
            }
        )

    if not static_loco.empty:
        for column, group in static_loco.groupby("column"):
            picks = set(group["selected_configuration"].astype(str))
            both_inner = picks == {"drop"}
            both_outer = bool((group["delta_mae_drop_vs_keep"] < 0).all())
            if both_inner and both_outer:
                drop_members.add(str(column))
                decisions.append(
                    {
                        "metric": column,
                        "kind": "static",
                        "decision": "DROP",
                        "selected_configurations": "drop",
                        "chosen_cols": "",
                        "n_full": 1,
                        "n_chosen": 0,
                        "mean_delta_mae_vs_full": float(
                            group["delta_mae_drop_vs_keep"].mean()
                        ),
                    }
                )
            else:
                decisions.append(
                    {
                        "metric": column,
                        "kind": "static",
                        "decision": "KEEP",
                        "selected_configurations": "|".join(sorted(picks)),
                        "chosen_cols": str(column),
                        "n_full": 1,
                        "n_chosen": 1,
                        "mean_delta_mae_vs_full": float(
                            group["delta_mae_drop_vs_keep"].mean()
                        ),
                    }
                )

    thin: list[str] = []
    seen: set[str] = set()
    for feature in production:
        if feature in drop_members or feature in seen:
            continue
        thin.append(feature)
        seen.add(feature)
    for cols in replace.values():
        for column in cols:
            if column not in seen:
                thin.append(column)
                seen.add(column)

    production_order = {feature: index for index, feature in enumerate(production)}
    thin.sort(key=lambda name: production_order.get(name, 10_000 + hash(name) % 1000))
    return thin, pd.DataFrame(decisions)


def _fit_lgbm_bakeoff(
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


def _bakeoff(
    frame_full: pd.DataFrame,
    production: list[str],
    thin: list[str],
) -> dict[str, object]:
    full = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    full["game_date"] = pd.to_datetime(full["game_date"])
    full = (
        full.dropna(subset=[TARGET, "game_date", TBF_TARGET])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    extra = [column for column in thin if column not in full.columns]
    if extra:
        add = frame_full[["game_pk", "pitcher", *extra]].drop_duplicates(
            ["game_pk", "pitcher"]
        )
        full = full.merge(add, on=["game_pk", "pitcher"], how="left", validate="1:1")

    train, validation, test = chronological_split(full)
    report: dict[str, object] = {
        "rows": {
            "train": len(train),
            "validation": len(validation),
            "test": len(test),
        },
        "cutoffs": {
            "train_end": str(train["game_date"].max().date()),
            "test_start": str(test["game_date"].min().date()),
        },
        "variants": {},
    }

    tbf_features = list(tbf_feature_names(train, TBF_DEFAULT_FEATURE_SET))
    tbf_model = build_model("ridge")
    fit_regressor(tbf_model, "ridge", train[tbf_features], train[TBF_TARGET])
    tbf_upper = float(train[TBF_TARGET].quantile(0.999))

    for name, features in (("production_185", production), ("step9_thin", thin)):
        missing = [feature for feature in features if feature not in full.columns]
        if missing:
            raise KeyError(f"{name} missing columns: {missing[:10]}")
        model = _fit_lgbm_bakeoff(train, validation, features)
        part_report: dict[str, object] = {}
        for part_name, part in (("validation", validation), ("test", test)):
            k_hat = predict_clipped(model, "lightgbm", part, features)
            tbf_hat = predict_nonnegative(
                tbf_model, "ridge", part, tbf_features, upper=tbf_upper
            )
            expected = expected_strikeouts(k_hat, tbf_hat)
            part_report[part_name] = {
                "k_rate_mae": float(
                    mean_absolute_error(part[TARGET], np.clip(k_hat, 0, 1))
                ),
                "k_rate_rmse": float(
                    mean_squared_error(part[TARGET], np.clip(k_hat, 0, 1)) ** 0.5
                ),
                "expected_K": count_point_metrics(part["K"], expected),
                "n_features": len(features),
            }
        report["variants"][name] = part_report
        print(name, json.dumps(part_report["test"], indent=2), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-means",
        action="store_true",
        help="Only screen rate metrics + static LOCO (faster).",
    )
    parser.add_argument(
        "--means-only",
        action="store_true",
        help="Screen mean/physics metrics only; merge with existing rate outer CSV.",
    )
    parser.add_argument(
        "--finalize-only",
        action="store_true",
        help="Assemble thin registry + bake-off from saved outer/static CSVs.",
    )
    parser.add_argument(
        "--skip-static",
        action="store_true",
        help="Skip leave-one-column-out on lineup/park/is_home.",
    )
    args = parser.parse_args()
    if args.skip_means and args.means_only:
        raise SystemExit("choose at most one of --skip-means / --means-only")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()

    base = _load_research_frame()
    production = _freeze_production(base)
    frame = _materialize_extra_windows(base)
    groups = _metric_groups(production)
    static_cols = list(groups["__static__"]["members"])  # type: ignore[index]

    if args.finalize_only:
        outer_results = pd.read_csv(OUTPUT_DIR / "outer_results.csv")
        static_path = OUTPUT_DIR / "static_loco.csv"
        static_loco = (
            pd.read_csv(static_path) if static_path.exists() else pd.DataFrame()
        )
    elif args.means_only:
        prior = pd.read_csv(OUTPUT_DIR / "outer_results.csv")
        prior = prior[prior["kind"] != "mean"].copy()
        _inner, _sel, mean_outer = _run_metric_screen(
            frame,
            production,
            groups,
            skip_means=False,
            means_only=True,
        )
        outer_results = pd.concat([prior, mean_outer], ignore_index=True)
        outer_results.to_csv(OUTPUT_DIR / "outer_results.csv", index=False)
        static_path = OUTPUT_DIR / "static_loco.csv"
        static_loco = (
            pd.read_csv(static_path) if static_path.exists() else pd.DataFrame()
        )
    else:
        inner_results, selections, outer_results = _run_metric_screen(
            frame,
            production,
            groups,
            skip_means=args.skip_means,
            means_only=False,
        )
        inner_results.to_csv(OUTPUT_DIR / "inner_results.csv", index=False)
        selections.to_csv(OUTPUT_DIR / "inner_selections.csv", index=False)
        outer_results.to_csv(OUTPUT_DIR / "outer_results.csv", index=False)

        if args.skip_static:
            static_loco = pd.DataFrame()
        else:
            static_loco = _run_static_loco(frame, production, static_cols)
            static_loco.to_csv(OUTPUT_DIR / "static_loco.csv", index=False)

    thin, decisions = _assemble_thin(production, groups, outer_results, static_loco)
    decisions.to_csv(OUTPUT_DIR / "decisions.csv", index=False)
    write_registry_csv(OUTPUT_DIR / "thin_registry.csv", tuple(thin))

    bake = _bakeoff(frame, production, thin)
    (OUTPUT_DIR / "bakeoff.json").write_text(json.dumps(bake, indent=2))
    bake_rows = []
    for variant, parts in bake["variants"].items():
        test = parts["test"]
        bake_rows.append(
            {
                "variant": variant,
                "n_features": test["n_features"],
                "k_rate_mae": test["k_rate_mae"],
                "k_rate_rmse": test["k_rate_rmse"],
                "expected_K_mae": test["expected_K"]["mae"],
                "expected_K_rmse": test["expected_K"]["rmse"],
            }
        )
    pd.DataFrame(bake_rows).to_csv(OUTPUT_DIR / "bakeoff.csv", index=False)

    metadata = {
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "n_production": len(production),
        "n_thin": len(thin),
        "skip_means": args.skip_means,
        "means_only": args.means_only,
        "skip_static": args.skip_static,
        "finalize_only": args.finalize_only,
        "rate_candidate_windows": list(RATE_CANDIDATE_WINDOWS),
        "mean_candidate_windows": list(MEAN_CANDIDATE_WINDOWS),
        "fold_metadata": fold_metadata(nested_research_folds(frame)),
        "bakeoff_test": bake_rows,
        "decision_counts": decisions["decision"].value_counts().to_dict()
        if not decisions.empty
        else {},
    }
    (OUTPUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))
    print(f"wrote {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
