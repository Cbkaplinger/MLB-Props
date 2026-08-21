"""Marcel-lite season K% baseline vs chronological game-level k_rate.

Builds a Tangotiger-style three-prior-season weighted K/PA projection
(weights 3/2/1, empirical-Bayes regression to the league mean, **no age
adjustment** — birthdates are not in the project identity map) and scores it
as a constant pregame prediction on the same 2023–2024 chronological test used
for the rate model.

This is an external talent baseline, not a matchup model. It answers whether
the frozen stack beats a simple public-style projection floor on game k_rate.

Example:
    python models/Strikeout-Model/research/marcel_baseline.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from Python import config
from Python.features import TARGET
from Python.statcast import load_statcast_years, plate_appearances
from Python.training import chronological_split

OUTPUT_DIR = config.OUTPUT_DIR / "feature_research" / "marcel_baseline"

# Prior-season weights for seasons Y-1, Y-2, Y-3 (most recent first).
_WEIGHTS = (3.0, 2.0, 1.0)
# PA of league-average rate mixed in (Marcel-style regression).
_REGRESS_PA = 100.0
# History years needed for projections into 2023–2024 games.
_HISTORY_YEARS = (2020, 2021, 2022, 2023)


def _pitcher_season_rates(years: tuple[int, ...]) -> pl.DataFrame:
    """Aggregate pitcher-season K and PA from Statcast (all appearances)."""
    raw = load_statcast_years(
        years,
        columns=(
            "game_pk",
            "game_date",
            "game_year",
            "at_bat_number",
            "pitch_number",
            "pitcher",
            "events",
        ),
    )
    pa = plate_appearances(raw)
    return (
        pa.group_by(["pitcher", "game_year"])
        .agg(
            pl.len().alias("PA"),
            pl.col("is_k").sum().cast(pl.Int64).alias("K"),
        )
        .rename({"game_year": "season"})
        .with_columns((pl.col("K") / pl.col("PA")).alias("k_rate"))
        .sort(["pitcher", "season"])
    )


def _league_rate_by_season(season_rates: pl.DataFrame) -> dict[int, float]:
    rows = (
        season_rates.group_by("season")
        .agg(pl.col("K").sum(), pl.col("PA").sum())
        .with_columns((pl.col("K") / pl.col("PA")).alias("lg_k_rate"))
        .sort("season")
    )
    return {int(s): float(r) for s, r in rows.select("season", "lg_k_rate").iter_rows()}


def marcel_k_rate(
    pitcher: int,
    target_season: int,
    by_pitcher: dict[int, dict[int, tuple[float, float]]],
    league_rate: dict[int, float],
) -> float:
    """Preseason Marcel-lite K/PA for ``target_season`` (prior seasons only)."""
    hist = by_pitcher.get(int(pitcher), {})
    k_w = 0.0
    pa_w = 0.0
    lg_num = 0.0
    lg_den = 0.0
    for weight, lag in zip(_WEIGHTS, (1, 2, 3)):
        season = target_season - lag
        if season not in hist:
            continue
        k, pa = hist[season]
        k_w += weight * k
        pa_w += weight * pa
        if season in league_rate:
            lg_num += weight * league_rate[season] * pa
            lg_den += weight * pa
    if pa_w <= 0:
        # Rookie / no prior: league mean of the most recent available prior year.
        for lag in (1, 2, 3):
            season = target_season - lag
            if season in league_rate:
                return league_rate[season]
        return float(np.mean(list(league_rate.values())))
    lg = lg_num / lg_den if lg_den > 0 else float(np.mean(list(league_rate.values())))
    return (k_w + _REGRESS_PA * lg) / (pa_w + _REGRESS_PA)


def _metrics(actual: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    pred = np.clip(pred, 0.0, 1.0)
    return {
        "mae": float(mean_absolute_error(actual, pred)),
        "rmse": float(mean_squared_error(actual, pred) ** 0.5),
        "r2": float(r2_score(actual, pred)),
        "n": int(len(actual)),
    }


def main() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Aggregating pitcher-season K/PA from Statcast", _HISTORY_YEARS)
    season_rates = _pitcher_season_rates(_HISTORY_YEARS)
    season_rates.write_parquet(OUTPUT_DIR / "pitcher_season_kpa.parquet")
    league_rate = _league_rate_by_season(season_rates)

    by_pitcher: dict[int, dict[int, tuple[float, float]]] = {}
    for pitcher, season, k, pa in season_rates.select(
        "pitcher", "season", "K", "PA"
    ).iter_rows():
        by_pitcher.setdefault(int(pitcher), {})[int(season)] = (float(k), float(pa))

    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "game_date", "pitcher", "season"])
        .loc[lambda d: d["season"].isin(config.FEATURE_RESEARCH_SEASONS)]
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    train, validation, test = chronological_split(frame)

    def score_partition(part: pd.DataFrame, name: str) -> dict[str, object]:
        actual = part[TARGET].to_numpy(dtype=float)
        marcel = np.array(
            [
                marcel_k_rate(int(p), int(s), by_pitcher, league_rate)
                for p, s in zip(part["pitcher"], part["season"])
            ],
            dtype=float,
        )
        mean_pred = np.full_like(actual, fill_value=float(train[TARGET].mean()))
        # Prior-season only (weight on Y-1 alone, same regression).
        prior_only = []
        for p, s in zip(part["pitcher"], part["season"]):
            hist = by_pitcher.get(int(p), {})
            y1 = int(s) - 1
            if y1 in hist:
                k, pa = hist[y1]
                lg = league_rate.get(y1, float(np.mean(list(league_rate.values()))))
                prior_only.append((k + _REGRESS_PA * lg) / (pa + _REGRESS_PA))
            else:
                prior_only.append(
                    league_rate.get(y1, float(np.mean(list(league_rate.values()))))
                )
        prior_only_arr = np.asarray(prior_only, dtype=float)
        out = {
            "partition": name,
            "marcel": _metrics(actual, marcel),
            "prior_season_only": _metrics(actual, prior_only_arr),
            "train_mean": _metrics(actual, mean_pred),
            "coverage": {
                "rows": int(len(part)),
                "pitchers_with_any_prior": int(
                    sum(
                        1
                        for p, s in zip(part["pitcher"], part["season"])
                        if any(
                            (int(s) - lag) in by_pitcher.get(int(p), {})
                            for lag in (1, 2, 3)
                        )
                    )
                ),
            },
        }
        return out

    results = {
        "train": score_partition(train, "train"),
        "validation": score_partition(validation, "validation"),
        "test": score_partition(test, "test"),
    }
    # Published frozen LightGBM gate (same chronological test dates) for the paper table.
    results["frozen_lightgbm_test_reference"] = {
        "mae": 0.0787,
        "rmse": 0.0987,
        "r2": 0.147,
        "source": "docs/research/step10_p1_registry_freeze.md / manuscript Table 3",
        "note": "Not re-fit in this script; same test start 2024-08-06.",
    }
    results["protocol"] = {
        "weights": list(_WEIGHTS),
        "regress_pa": _REGRESS_PA,
        "age_adjustment": False,
        "history_years": list(_HISTORY_YEARS),
        "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
        "test_start": str(test["game_date"].min().date()),
        "test_end": str(test["game_date"].max().date()),
        "definition": (
            "Preseason Marcel-lite: weighted K/PA over seasons Y-1..Y-3 only; "
            "no same-season games; no age curve; league-mean fill for no-history pitchers."
        ),
    }

    (OUTPUT_DIR / "metrics.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    summary = pd.DataFrame(
        [
            {
                "partition": part,
                "model": model,
                **results[part][model],
            }
            for part in ("validation", "test")
            for model in ("train_mean", "prior_season_only", "marcel")
        ]
    )
    summary.to_csv(OUTPUT_DIR / "summary.csv", index=False)
    print(summary.to_string(index=False))
    print("Frozen LightGBM test reference:", results["frozen_lightgbm_test_reference"])
    print(f"Wrote {OUTPUT_DIR}")
    return OUTPUT_DIR


if __name__ == "__main__":
    # Ensure src/Python is importable when launched from repo root.
    src = Path(__file__).resolve().parents[3] / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    main()
