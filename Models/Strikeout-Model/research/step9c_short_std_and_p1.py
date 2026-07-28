"""Step 9c — short+std for every rate; P1 for every physics/mean metric.

User-directed follow-ups after Step 9 / 9b:

1. For **every rate metric**, test ``short + _std`` (P5+std, P10+std) against
   single windows, std-only, drop, and production full multi-window.
2. For **every mean/physics/usage/mechanics/FIP metric**, add **P1** (last
   start only) so arsenal shape changes mid-season can register, and compare
   to P3/P5/P10/P15/P20 and production full.

Does not mutate production registries. Nested 2023→2024 folds only.
"""

from __future__ import annotations

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

OUTPUT_DIR = config.OUTPUT_DIR / "feature_research" / "step9c_short_std_p1"
_WINDOW_RE = re.compile(r"^(.*)_P(\d+)$")
_STD_RE = re.compile(r"^(.*)_std(?:_shrunk)?$")
_RATE_STEMS = frozenset(DEFAULT_RATE_STATS) | frozenset(
    {"xBA", "wOBA", "xwOBA"}  # expected_contact rates in production
)

# Rate grid: emphasize short+std; keep a few longer anchors from 9b.
RATE_WINDOWS = (5, 10, 15, 20, 30)
# Mean grid: P1 is the new ultra-short form signal.
MEAN_WINDOWS = (1, 3, 5, 10, 15, 20)


def _metrics(actual: pd.Series, prediction: np.ndarray) -> dict[str, float]:
    prediction = np.clip(prediction, 0, 1)
    return {
        "mae": float(mean_absolute_error(actual, prediction)),
        "rmse": float(mean_squared_error(actual, prediction) ** 0.5),
        "r2": float(r2_score(actual, prediction)),
    }


def _lgbm(n_estimators: int = 400) -> lgb.LGBMRegressor:
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


def _fit_inner(train, validation, features):
    model = _lgbm(400)
    try:
        model.fit(
            train[features],
            train[TARGET],
            eval_X=validation[features],
            eval_y=validation[TARGET],
            callbacks=[lgb.early_stopping(30, verbose=False)],
        )
    except TypeError:
        model.fit(
            train[features],
            train[TARGET],
            eval_set=[(validation[features], validation[TARGET])],
            callbacks=[lgb.early_stopping(30, verbose=False)],
        )
    return model.predict(validation[features])


def _fit_outer(train, features):
    model = _lgbm(800)
    model.fit(train[features], train[TARGET])
    return model


def _load_base() -> tuple[pd.DataFrame, list[str]]:
    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "game_date"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    frame = frame[frame["season"].isin(config.FEATURE_RESEARCH_SEASONS)].copy()
    production = list(production_features(frame))
    if len(production) != 185:
        raise ValueError(f"expected 185 production features, got {len(production)}")
    return frame, production


def _metric_stems(production: list[str]) -> tuple[list[str], list[str]]:
    rates: set[str] = set()
    means: set[str] = set()
    for feature in production:
        match = _WINDOW_RE.match(feature)
        if match:
            stem = match.group(1)
            if stem in _RATE_STEMS or f"{stem}_std" in production:
                rates.add(stem)
            else:
                means.add(stem)
            continue
        match = _STD_RE.match(feature)
        if match:
            rates.add(match.group(1))
    # FIP/xFIP are mean-rolled
    means |= {stem for stem in ("FIP", "xFIP") if any(f.startswith(f"{stem}_P") for f in production)}
    rates -= {"FIP", "xFIP"}
    return sorted(rates), sorted(means)


def _materialize(frame: pd.DataFrame, rate_stems: list[str], mean_stems: list[str]) -> pd.DataFrame:
    games = pl.read_parquet(config.PITCHER_GAMES_PATH)
    rate_stats = {
        name: pair
        for name, pair in DEFAULT_RATE_STATS.items()
        if name in rate_stems
    }
    # xBA/wOBA/xwOBA live in DEFAULT_RATE_STATS already.
    mean_cols = [col for col in DEFAULT_MEAN_COLS if col in mean_stems]
    # Need extra rate windows + mean P1/P15/P20 (P3/P5/P10 often exist).
    generated = add_rolling_pitcher_features(
        games,
        rate_stats=rate_stats,
        mean_cols=mean_cols,
        rate_windows=(15, 30),
        mean_windows=(1, 15, 20),
        workload_cols=(),
        workload_windows=(),
        season_to_date=False,
        add_rest=False,
    )
    # FIP/xFIP ride mean_windows inside add_rolling when mean_cols path runs FIP —
    # _add_rolling_fip uses whatever mean_windows were passed. Include them by
    # calling with empty mean_cols but mean_windows still triggers FIP? Looking
    # at code: _add_rolling_fip(df, mean_windows) always runs. Good — P1 FIP
    # will be created when mean_windows includes 1.
    want = [
        column
        for column in generated.columns
        if _WINDOW_RE.match(column) and column not in frame.columns
    ]
    if not want:
        print("no new columns to materialize")
        return frame
    values = generated.select("game_pk", "pitcher", *want).to_pandas()
    out = frame.merge(values, on=["game_pk", "pitcher"], how="left", validate="1:1")
    print(f"materialized {len(want)} columns (incl P1 / long rates)")
    return out


def _members(production: list[str], stem: str) -> list[str]:
    return [
        feature
        for feature in production
        if feature == f"{stem}_std" or feature.startswith(f"{stem}_P")
    ]


def _rate_configs(stem: str, frame: pd.DataFrame, full: list[str]) -> dict[str, list[str]]:
    std = f"{stem}_std" if f"{stem}_std" in frame.columns else None
    configs: dict[str, list[str]] = {"drop": [], "full": list(full)}
    if std:
        configs["std_only"] = [std]
    for window in RATE_WINDOWS:
        column = f"{stem}_P{window}"
        if column not in frame.columns:
            continue
        configs[f"P{window}"] = [column]
        if std:
            # Primary user test: short form + season talent.
            configs[f"P{window}+std"] = [column, std]
    return {
        name: cols
        for name, cols in configs.items()
        if name in {"drop", "full"} or all(column in frame.columns for column in cols)
    }


def _mean_configs(stem: str, frame: pd.DataFrame, full: list[str]) -> dict[str, list[str]]:
    configs: dict[str, list[str]] = {"drop": [], "full": list(full)}
    for window in MEAN_WINDOWS:
        column = f"{stem}_P{window}"
        if column in frame.columns:
            configs[f"P{window}"] = [column]
    # Ultra-short + mid: catch pitch redesign without discarding medium memory.
    for short, mid in ((1, 5), (1, 10), (1, 3)):
        a, b = f"{stem}_P{short}", f"{stem}_P{mid}"
        if a in frame.columns and b in frame.columns:
            configs[f"P{short}+P{mid}"] = [a, b]
    return {
        name: cols
        for name, cols in configs.items()
        if name in {"drop", "full"} or all(column in frame.columns for column in cols)
    }


def _select_inner(metric_inner: pd.DataFrame) -> pd.DataFrame:
    agg = (
        metric_inner.groupby(["outer_fold", "configuration"], as_index=False)
        .agg(
            inner_mean_mae=("mae", "mean"),
            n_metric_cols=("n_metric_cols", "first"),
            metric_cols=("metric_cols", "first"),
        )
        .sort_values(["outer_fold", "inner_mean_mae", "n_metric_cols", "configuration"])
    )
    return agg.drop_duplicates("outer_fold", keep="first")


def _parse_primary(name: str) -> str:
    if name in {"drop", "full", "std_only"}:
        return name
    if name.startswith("P") and "+std" in name and name[1 : name.index("+")].isdigit():
        return "P" + name[1 : name.index("+")]
    if name.startswith("P") and name[1:].isdigit():
        return name
    if "+P" in name:
        return name  # dual kept as-is for agreement
    return name


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    base, production = _load_base()
    rate_stems, mean_stems = _metric_stems(production)
    frame = _materialize(base, rate_stems, mean_stems)
    folds = nested_research_folds(frame)

    inner_rows: list[dict] = []
    outer_rows: list[dict] = []
    jobs = [(stem, "rate") for stem in rate_stems] + [
        (stem, "mean") for stem in mean_stems
    ]

    for stem, kind in jobs:
        full = _members(production, stem)
        members = set(full)
        configs = (
            _rate_configs(stem, frame, full)
            if kind == "rate"
            else _mean_configs(stem, frame, full)
        )
        print(f"{stem} ({kind}): {len(configs)} configs full={full}", flush=True)

        for outer_name, nested in folds.items():
            for inner_name, inner in nested.inner.items():
                for conf, chosen in configs.items():
                    feats = [f for f in production if f not in members] + list(chosen)
                    if not feats:
                        continue
                    pred = _fit_inner(inner.train, inner.validation, feats)
                    result = _metrics(inner.validation[TARGET], pred)
                    inner_rows.append(
                        {
                            "metric": stem,
                            "kind": kind,
                            "outer_fold": outer_name,
                            "inner_fold": inner_name,
                            "configuration": conf,
                            "n_metric_cols": len(chosen),
                            "metric_cols": "|".join(chosen),
                            **result,
                        }
                    )
            print(f"  inner done {stem}/{outer_name}", flush=True)

        picks = _select_inner(pd.DataFrame(inner_rows).query("metric == @stem"))
        for row in picks.itertuples(index=False):
            outer = folds[row.outer_fold].outer
            chosen = configs[row.configuration]
            feats = [f for f in production if f not in members] + list(chosen)
            full_feats = [f for f in production if f not in members] + list(full)
            sel = _fit_outer(outer.train, feats)
            ful = _fit_outer(outer.train, full_feats)
            sel_m = _metrics(outer.validation[TARGET], sel.predict(outer.validation[feats]))
            ful_m = _metrics(
                outer.validation[TARGET], ful.predict(outer.validation[full_feats])
            )
            outer_rows.append(
                {
                    "metric": stem,
                    "kind": kind,
                    "outer_fold": row.outer_fold,
                    "selected_configuration": row.configuration,
                    "metric_cols": "|".join(chosen),
                    "n_metric_cols": len(chosen),
                    "inner_mean_mae": row.inner_mean_mae,
                    "mae": sel_m["mae"],
                    "full_mae": ful_m["mae"],
                    "delta_mae_vs_full": sel_m["mae"] - ful_m["mae"],
                }
            )
            print(
                f"  outer {stem}/{row.outer_fold} -> {row.configuration} "
                f"dMAE={sel_m['mae'] - ful_m['mae']:+.6f}",
                flush=True,
            )
        pd.DataFrame(inner_rows).to_csv(OUTPUT_DIR / "inner_results.csv", index=False)

    outer_df = pd.DataFrame(outer_rows)
    outer_df.to_csv(OUTPUT_DIR / "outer_results.csv", index=False)

    # Verdicts + thin assembly
    decisions = []
    drop_members: set[str] = set()
    replace: dict[str, list[str]] = {}
    for metric, group in outer_df.groupby("metric"):
        configs = sorted(group["selected_configuration"].astype(str).unique())
        full = _members(production, str(metric))
        members = set(full)
        if len(configs) == 1:
            chosen_name = configs[0]
            chosen_cols = [
                part
                for part in str(
                    group.loc[
                        group["selected_configuration"] == chosen_name, "metric_cols"
                    ].iloc[0]
                ).split("|")
                if part
            ]
            if chosen_name == "full":
                decision = "HOLD_FULL"
                chosen_cols = full
            elif chosen_name == "drop":
                decision = "DROP"
                drop_members |= members
                chosen_cols = []
            else:
                decision = "THIN"
                replace[str(metric)] = chosen_cols
                drop_members |= members - set(chosen_cols)
        else:
            primaries = {_parse_primary(name) for name in configs}
            # short+std agree on same Pw
            if all("+std" in name or name.endswith("+std") for name in configs if name not in {"drop", "full"}):
                windows = set()
                for name in configs:
                    if name.startswith("P") and "+std" in name:
                        windows.add("P" + name[1 : name.index("+")])
                if len(windows) == 1:
                    w = next(iter(windows))  # e.g. "P5"
                    chosen_name = f"{w}+std"
                    chosen_cols = [f"{metric}_{w}", f"{metric}_std"]
                    decision = "THIN_SHORT_STD_AGREE"
                    replace[str(metric)] = chosen_cols
                    drop_members |= members - set(chosen_cols)
                else:
                    decision = "HOLD_DISAGREE"
                    chosen_name = "|".join(configs)
                    chosen_cols = full
            elif len(primaries) == 1 and "full" not in primaries and "drop" not in primaries:
                primary = next(iter(primaries))
                # Prefer +std if either fold had it
                want_std = any("+std" in name for name in configs)
                if primary.startswith("P") and primary[1:].isdigit():
                    chosen_cols = [f"{metric}_{primary}"]
                    if want_std and all("+std" in name for name in configs):
                        chosen_cols.append(f"{metric}_std")
                        chosen_name = f"{primary}+std"
                        decision = "THIN_WINDOW_AGREE"
                    elif not any("+std" in name for name in configs):
                        chosen_name = primary
                        decision = "THIN_WINDOW_AGREE"
                    else:
                        # mixed std — keep window without forcing std
                        chosen_name = primary
                        decision = "THIN_WINDOW_AGREE"
                    replace[str(metric)] = chosen_cols
                    drop_members |= members - set(chosen_cols)
                elif primary.startswith("P") and "+P" in primary:
                    # dual agree exact
                    decision = "HOLD_DISAGREE"
                    chosen_name = "|".join(configs)
                    chosen_cols = full
                else:
                    decision = "HOLD_DISAGREE"
                    chosen_name = "|".join(configs)
                    chosen_cols = full
            else:
                decision = "HOLD_DISAGREE"
                chosen_name = "|".join(configs)
                chosen_cols = full

        decisions.append(
            {
                "metric": metric,
                "kind": group["kind"].iloc[0],
                "decision": decision,
                "selected_configurations": chosen_name,
                "chosen_cols": "|".join(chosen_cols),
                "n_full": len(full),
                "n_chosen": len(chosen_cols),
                "mean_delta_mae_vs_full": float(group["delta_mae_vs_full"].mean()),
                "p1_selected": any(
                    "P1" in str(c) for c in group["selected_configuration"]
                ),
                "short_std_selected": any(
                    re.match(r"^P(5|10)\+std$", str(c))
                    for c in group["selected_configuration"]
                ),
            }
        )

    decisions_df = pd.DataFrame(decisions).sort_values(["kind", "decision", "metric"])
    decisions_df.to_csv(OUTPUT_DIR / "decisions.csv", index=False)

    thin: list[str] = []
    seen: set[str] = set()
    for feature in production:
        if feature in drop_members or feature in seen:
            continue
        thin.append(feature)
        seen.add(feature)
    for cols in replace.values():
        for column in cols:
            if column not in seen and column in frame.columns:
                thin.append(column)
                seen.add(column)
    write_registry_csv(OUTPUT_DIR / "thin_registry.csv", tuple(thin))

    # Bake-off
    full = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    full["game_date"] = pd.to_datetime(full["game_date"])
    full = (
        full.dropna(subset=[TARGET, "game_date", TBF_TARGET])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    extra = [c for c in thin if c not in full.columns]
    if extra:
        add = frame[["game_pk", "pitcher", *extra]].drop_duplicates(["game_pk", "pitcher"])
        full = full.merge(add, on=["game_pk", "pitcher"], how="left", validate="1:1")

    train, validation, test = chronological_split(full)
    tbf_features = list(tbf_feature_names(train, TBF_DEFAULT_FEATURE_SET))
    tbf_model = build_model("ridge")
    fit_regressor(tbf_model, "ridge", train[tbf_features], train[TBF_TARGET])
    tbf_upper = float(train[TBF_TARGET].quantile(0.999))

    bake_rows = []
    for name, features in (("production_185", production), ("step9c_thin", thin)):
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
        k_hat = predict_clipped(model, "lightgbm", test, features)
        tbf_hat = predict_nonnegative(
            tbf_model, "ridge", test, tbf_features, upper=tbf_upper
        )
        expected = expected_strikeouts(k_hat, tbf_hat)
        count = count_point_metrics(test["K"], expected)
        bake_rows.append(
            {
                "variant": name,
                "n_features": len(features),
                "k_rate_mae": float(
                    mean_absolute_error(test[TARGET], np.clip(k_hat, 0, 1))
                ),
                "expected_K_mae": count["mae"],
            }
        )
        print(bake_rows[-1], flush=True)

    pd.DataFrame(bake_rows).to_csv(OUTPUT_DIR / "bakeoff.csv", index=False)

    # Highlight tables
    short_std = decisions_df[
        decisions_df["selected_configurations"].astype(str).str.contains(
            r"P(5|10)\+std", regex=True, na=False
        )
        | (decisions_df["decision"] == "THIN_SHORT_STD_AGREE")
    ]
    p1_hits = decisions_df[
        decisions_df["selected_configurations"].astype(str).str.contains("P1", na=False)
        | decisions_df["chosen_cols"].astype(str).str.contains("_P1", na=False)
    ]

    meta = {
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "n_production": len(production),
        "n_thin": len(thin),
        "n_rate_stems": len(rate_stems),
        "n_mean_stems": len(mean_stems),
        "decision_counts": decisions_df["decision"].value_counts().to_dict(),
        "bakeoff": bake_rows,
        "short_std_agree_metrics": short_std["metric"].tolist(),
        "p1_involved_metrics": p1_hits["metric"].tolist(),
        "fold_metadata": fold_metadata(folds),
    }
    (OUTPUT_DIR / "metadata.json").write_text(json.dumps(meta, indent=2))
    print(decisions_df.to_string(index=False))
    print("short+std highlights:", short_std["metric"].tolist())
    print("P1 highlights:", p1_hits["metric"].tolist())
    print(json.dumps(meta["decision_counts"], indent=2))
    print(f"wrote {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
