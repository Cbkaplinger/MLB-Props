"""Step 9b — widen rolling windows for priority metrics only.

Probes longer starts windows than Step 9 defaults for metrics that already
pulled toward the long end of the grid or split short vs long across folds.

Rate candidates: {5,10,15,20,25,30,35,40} + season-to-date ``_std``.
Mean candidates (edge P20 winners): {15,20,25,30}.

Does not mutate production registries.
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
from Python.features import TARGET
from Python.pitcher_rolling import (
    DEFAULT_MEAN_COLS,
    DEFAULT_RATE_STATS,
    add_rolling_pitcher_features,
)
from Python.registries import production_features

EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from nested_cv import fold_metadata, nested_research_folds  # noqa: E402

OUTPUT_DIR = config.OUTPUT_DIR / "feature_research" / "step9_widen"
RATE_WINDOWS = (5, 10, 15, 20, 25, 30, 35, 40)
MEAN_WINDOWS = (15, 20, 25, 30)
EXTRA_RATE = (25, 35, 40)  # 15/30 already from Step 9 materialize path; rebuild all extras
EXTRA_MEAN = (25, 30)

# Metrics that need a longer / denser grid from Step 9 votes.
PRIORITY_RATES = (
    "xBA",
    "hr_rate",
    "xwOBA",
    "whiff_rate",
    "swstr_rate",
    "chase_rate",
    "bb_rate",
    "cs_rate",
    "k_rate",
)
# Means that locked or split onto P20 (edge of prior grid).
PRIORITY_MEANS = (
    "sl_hb",
    "sl_usage_vL",
    "st_vaa",
    "cu_velo",
    "rel_x_sd",
    "ch_ivb",
)

_WINDOW_RE = re.compile(r"^(.*)_P(\d+)$")


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


def _load() -> tuple[pd.DataFrame, list[str]]:
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
        raise ValueError(f"expected 185 features before materialize, got {len(production)}")
    return frame, production


def _materialize(frame: pd.DataFrame) -> pd.DataFrame:
    games = pl.read_parquet(config.PITCHER_GAMES_PATH)
    rate_stats = {k: v for k, v in DEFAULT_RATE_STATS.items() if k in PRIORITY_RATES}
    mean_cols = [c for c in DEFAULT_MEAN_COLS if c in PRIORITY_MEANS]
    # Also need FIP-style not in DEFAULT_MEAN for priority means - none of PRIORITY_MEANS are FIP.
    generated = add_rolling_pitcher_features(
        games,
        rate_stats=rate_stats,
        mean_cols=mean_cols,
        rate_windows=tuple(sorted(set(RATE_WINDOWS) - {5, 10, 20})),  # extras + 15,30,25,35,40
        mean_windows=tuple(sorted(set(MEAN_WINDOWS) - {3, 5, 10})),
        workload_cols=(),
        workload_windows=(),
        season_to_date=False,
        add_rest=False,
    )
    # Generate any missing windows from full candidate sets.
    want = []
    for stem in PRIORITY_RATES:
        for w in RATE_WINDOWS:
            col = f"{stem}_P{w}"
            if col in generated.columns and col not in frame.columns:
                want.append(col)
    for stem in PRIORITY_MEANS:
        for w in MEAN_WINDOWS:
            col = f"{stem}_P{w}"
            if col in generated.columns and col not in frame.columns:
                want.append(col)
    # Second pass: ensure 25/35/40 exist even if first call skipped defaults.
    generated2 = add_rolling_pitcher_features(
        games,
        rate_stats=rate_stats,
        mean_cols=mean_cols,
        rate_windows=EXTRA_RATE + (15, 30),
        mean_windows=EXTRA_MEAN,
        workload_cols=(),
        workload_windows=(),
        season_to_date=False,
        add_rest=False,
    )
    for col in generated2.columns:
        if _WINDOW_RE.match(col) and col not in frame.columns:
            want.append(col)
    want = sorted(set(want))
    if not want:
        print("no new columns")
        return frame
    values = generated2.select("game_pk", "pitcher", *[c for c in want if c in generated2.columns])
    # Merge any from first gen too
    missing = [c for c in want if c not in values.columns and c in generated.columns]
    if missing:
        values = values.join(
            generated.select("game_pk", "pitcher", *missing),
            on=["game_pk", "pitcher"],
            how="left",
        )
    out = frame.merge(values.to_pandas(), on=["game_pk", "pitcher"], how="left", validate="1:1")
    print(f"materialized {len(want)} widen columns")
    return out


def _members(production: list[str], stem: str) -> list[str]:
    return [
        f
        for f in production
        if f == f"{stem}_std" or f.startswith(f"{stem}_P")
    ]


def _configs(stem: str, kind: str, frame: pd.DataFrame, full: list[str]) -> dict[str, list[str]]:
    windows = RATE_WINDOWS if kind == "rate" else MEAN_WINDOWS
    std = f"{stem}_std" if f"{stem}_std" in frame.columns and kind == "rate" else None
    configs: dict[str, list[str]] = {"drop": [], "full": list(full)}
    if std:
        configs["std_only"] = [std]
    for w in windows:
        col = f"{stem}_P{w}"
        if col not in frame.columns:
            continue
        configs[f"P{w}"] = [col]
        if std:
            configs[f"P{w}+std"] = [col, std]
    # Dual-scale for short/long split rates: P5+P30, P10+P30, P5+P25, etc.
    if kind == "rate":
        for short, long in ((5, 30), (10, 30), (5, 40), (10, 40), (5, 25), (10, 25)):
            a, b = f"{stem}_P{short}", f"{stem}_P{long}"
            if a in frame.columns and b in frame.columns:
                name = f"P{short}+P{long}"
                configs[name] = [a, b]
                if std:
                    configs[f"{name}+std"] = [a, b, std]
    return {
        n: cols
        for n, cols in configs.items()
        if all(c in frame.columns for c in cols) or n in {"drop", "full"}
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base, production = _load()
    frame = _materialize(base)
    folds = nested_research_folds(frame)

    inner_rows = []
    outer_rows = []
    selections_rows = []

    jobs = [(s, "rate") for s in PRIORITY_RATES] + [(s, "mean") for s in PRIORITY_MEANS]
    for stem, kind in jobs:
        full = _members(production, stem)
        if not full and kind == "mean":
            # production may only have P3/P5
            full = [f for f in production if f.startswith(f"{stem}_P")]
        members = set(full)
        configs = _configs(stem, kind, frame, full)
        print(f"{stem}: {len(configs)} configs, full={full}", flush=True)

        for outer_name, nested in folds.items():
            for inner_name, inner in nested.inner.items():
                for conf, chosen in configs.items():
                    feats = [f for f in production if f not in members] + list(chosen)
                    if not feats:
                        continue
                    pred = _fit_inner(inner.train, inner.validation, feats)
                    m = _metrics(inner.validation[TARGET], pred)
                    inner_rows.append(
                        {
                            "metric": stem,
                            "kind": kind,
                            "outer_fold": outer_name,
                            "inner_fold": inner_name,
                            "configuration": conf,
                            "n_metric_cols": len(chosen),
                            "metric_cols": "|".join(chosen),
                            **m,
                        }
                    )
            print(f"inner done {stem}/{outer_name}", flush=True)

        inner_df = pd.DataFrame(inner_rows)
        metric_inner = inner_df[inner_df.metric == stem]
        agg = (
            metric_inner.groupby(["outer_fold", "configuration"], as_index=False)
            .agg(
                inner_mean_mae=("mae", "mean"),
                n_metric_cols=("n_metric_cols", "first"),
                metric_cols=("metric_cols", "first"),
            )
            .sort_values(["outer_fold", "inner_mean_mae", "n_metric_cols"])
        )
        picks = agg.drop_duplicates("outer_fold", keep="first")
        for row in picks.itertuples(index=False):
            selections_rows.append(
                {
                    "metric": stem,
                    "kind": kind,
                    "outer_fold": row.outer_fold,
                    "selected_configuration": row.configuration,
                    "metric_cols": row.metric_cols,
                    "inner_mean_mae": row.inner_mean_mae,
                }
            )
            outer = folds[row.outer_fold].outer
            chosen = configs[row.configuration]
            feats = [f for f in production if f not in members] + list(chosen)
            full_feats = [f for f in production if f not in members] + list(full)
            sel = _fit_outer(outer.train, feats)
            ful = _fit_outer(outer.train, full_feats)
            sel_m = _metrics(outer.validation[TARGET], sel.predict(outer.validation[feats]))
            ful_m = _metrics(outer.validation[TARGET], ful.predict(outer.validation[full_feats]))
            outer_rows.append(
                {
                    "metric": stem,
                    "kind": kind,
                    "outer_fold": row.outer_fold,
                    "selected_configuration": row.configuration,
                    "metric_cols": "|".join(chosen),
                    "inner_mean_mae": row.inner_mean_mae,
                    "mae": sel_m["mae"],
                    "full_mae": ful_m["mae"],
                    "delta_mae_vs_full": sel_m["mae"] - ful_m["mae"],
                }
            )
            print(
                f"outer {stem}/{row.outer_fold} -> {row.configuration} "
                f"dMAE={sel_m['mae']-ful_m['mae']:+.6f}",
                flush=True,
            )

        pd.DataFrame(inner_rows).to_csv(OUTPUT_DIR / "inner_results.csv", index=False)

    outer_df = pd.DataFrame(outer_rows)
    outer_df.to_csv(OUTPUT_DIR / "outer_results.csv", index=False)
    pd.DataFrame(selections_rows).to_csv(OUTPUT_DIR / "selections.csv", index=False)

    # Verdicts: both folds same config, or same primary window.
    verdicts = []
    for metric, g in outer_df.groupby("metric"):
        configs = sorted(g.selected_configuration.unique())
        if len(configs) == 1:
            decision = "AGREE"
            chosen = configs[0]
        else:
            # window agree?
            def primary(c: str) -> str:
                if c.startswith("P") and "+" in c and c[1:c.index("+")].isdigit():
                    return "P" + c[1 : c.index("+")]
                if c.startswith("P") and c[1:].isdigit():
                    return c
                return c

            primaries = {primary(c) for c in configs}
            if len(primaries) == 1 and not any(c in {"drop", "full"} for c in configs):
                decision = "WINDOW_AGREE"
                chosen = next(iter(primaries))
            else:
                decision = "DISAGREE"
                chosen = "|".join(configs)
        verdicts.append(
            {
                "metric": metric,
                "kind": g.kind.iloc[0],
                "decision": decision,
                "chosen": chosen,
                "fold_configs": "|".join(configs),
                "mean_delta_mae_vs_full": float(g.delta_mae_vs_full.mean()),
                "explore_further": decision == "DISAGREE"
                or (
                    decision in {"AGREE", "WINDOW_AGREE"}
                    and any(
                        tok in chosen
                        for tok in ("P25", "P30", "P35", "P40", "P5+P", "P10+P")
                    )
                ),
            }
        )
    verd = pd.DataFrame(verdicts).sort_values(["decision", "metric"])
    verd.to_csv(OUTPUT_DIR / "verdicts.csv", index=False)

    meta = {
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "rate_windows": list(RATE_WINDOWS),
        "mean_windows": list(MEAN_WINDOWS),
        "priority_rates": list(PRIORITY_RATES),
        "priority_means": list(PRIORITY_MEANS),
        "fold_metadata": fold_metadata(folds),
        "verdicts": verd.to_dict(orient="records"),
    }
    (OUTPUT_DIR / "metadata.json").write_text(json.dumps(meta, indent=2))
    print(verd.to_string(index=False))
    print(f"wrote {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
