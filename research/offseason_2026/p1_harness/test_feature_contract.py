"""Executable checks for FEATURE_CONTRACT.md (P1 harness, frozen logistic).

(a) mutating current-game outcomes of a PA's own game cannot change that PA's
    pregame features;
(b) appending a future game cannot change earlier rows' features;
(c) on the executed artifact data/features.parquet, every feature source date
    strictly precedes its game_date;
(d) all three model candidates (reference A, log5, logistic B) predict the
    identical EVAL key set in data/eval_predictions.parquet.

(a) and (b) rebuild features from synthetic PA tables using the executed
builder primitives imported from scripts/build_features.py, mirroring the
assembly in its main() (lines 156-242) exactly.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import polars as pl

HARNESS = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS / "scripts"))

import build_features as bf  # noqa: E402

FEATURE_COLS = [
    "p_pitcher_prior_w150",
    "p_batter_prior_w150",
    "p_pitcher_prior_w500",
    "p_batter_prior_w500",
    "lg_rate",
    "n_prior_pitcher",
    "n_prior_batter",
    "cold_start",
]
KEYS = ["game_pk", "at_bat_number", "batter"]


def assemble_features(pa: pl.DataFrame) -> pl.DataFrame:
    """Mirror build_features.main() feature assembly (lines 156-242)."""
    lg = bf.league_daily(pa)
    lg = lg.with_columns(
        pl.when(pl.col("lg_n_prior") > 0)
        .then(pl.col("lg_k_prior") / pl.col("lg_n_prior"))
        .otherwise(None)
        .alias("lg_rate")
    ).with_columns(pl.col("lg_rate").backward_fill())

    p_daily = bf.daily_cumulative(pa, "pitcher").rename(
        {"prior_k": "pk", "prior_n": "pn", "src_date": "src_date_pitcher"}
    )
    b_daily = bf.daily_cumulative(pa, "batter").rename(
        {"prior_k": "bk", "prior_n": "bn", "src_date": "src_date_batter"}
    )

    feat = (
        pa.select(*KEYS, "game_date", "pitcher")
        .sort("game_date")
        .join_asof(
            p_daily,
            left_on="game_date",
            right_on="game_date",
            by="pitcher",
            strategy="backward",
        )
        .sort("game_date")
        .join_asof(
            b_daily.select(
                pl.col("game_date"), pl.col("batter").alias("batter_key"),
                "bk", "bn", "src_date_batter",
            ),
            left_on="game_date",
            right_on="game_date",
            by_left="batter",
            by_right="batter_key",
            strategy="backward",
        )
        .sort("game_date")
        .join_asof(
            lg.select("game_date", "lg_rate", "lg_k_prior", "lg_n_prior", "lg_src_date"),
            left_on="game_date",
            right_on="game_date",
            strategy="backward",
        )
    )

    feat = (
        feat.with_columns(
            *[bf.shrunk(pl.col("pk"), pl.col("pn"), pl.col("lg_rate"), w) for w in bf.W_LEVELS]
        )
        .rename({"p_w150": "p_pitcher_prior_w150", "p_w500": "p_pitcher_prior_w500"})
        .with_columns(
            *[bf.shrunk(pl.col("bk"), pl.col("bn"), pl.col("lg_rate"), w) for w in bf.W_LEVELS]
        )
        .rename({"p_w150": "p_batter_prior_w150", "p_w500": "p_batter_prior_w500"})
        .with_columns(
            (pl.col("pn") == 0).fill_null(True).alias("cold_start_pitcher"),
            (pl.col("bn") == 0).fill_null(True).alias("cold_start_batter"),
        )
        .with_columns(
            (pl.col("cold_start_pitcher") | pl.col("cold_start_batter"))
            .cast(pl.Int8)
            .alias("cold_start")
        )
        .rename({"pn": "n_prior_pitcher", "bn": "n_prior_batter"})
        .select(*KEYS, "game_date", *FEATURE_COLS,
                "src_date_pitcher", "src_date_batter", "lg_src_date")
    )
    bf.validate_no_future_leakage(feat)
    return feat


def synthetic_pa() -> pl.DataFrame:
    """Four dates, two pitchers, two batters; a PA of interest on date 2."""
    rows = []
    pk = 100
    for d in [date(2024, 4, 1), date(2024, 4, 2), date(2024, 4, 3), date(2024, 4, 4)]:
        ab = 0
        for pitcher in [101, 102]:
            for batter in [201, 202]:
                for _ in range(3):
                    ab += 1
                    rows.append(
                        {
                            "game_pk": pk,
                            "at_bat_number": ab,
                            "batter": batter,
                            "pitcher": pitcher,
                            "game_date": d,
                            "y": (ab + pk) % 2,
                        }
                    )
        pk += 1
    return pl.DataFrame(rows)


def pa_of_interest(pa: pl.DataFrame) -> dict:
    """First PA of pitcher 101 vs batter 201 on the table's second date."""
    row = (
        pa.filter(pl.col("game_date") == date(2024, 4, 2))
        .filter((pl.col("pitcher") == 101) & (pl.col("batter") == 201))
        .sort("at_bat_number")
        .head(1)
    )
    return row.to_dicts()[0]


def test_a_own_game_outcome_mutation_cannot_change_pregame_features() -> None:
    """(a) flipping y inside the PA's own game leaves that PA's features fixed."""
    pa = synthetic_pa()
    target = pa_of_interest(pa)
    base = assemble_features(pa).filter(
        (pl.col("game_pk") == target["game_pk"])
        & (pl.col("at_bat_number") == target["at_bat_number"])
        & (pl.col("batter") == target["batter"])
    )

    mutated = pa.with_columns(
        pl.when(pl.col("game_pk") == target["game_pk"])
        .then(1 - pl.col("y"))
        .otherwise(pl.col("y"))
        .alias("y")
    )
    after = assemble_features(mutated).filter(
        (pl.col("game_pk") == target["game_pk"])
        & (pl.col("at_bat_number") == target["at_bat_number"])
        & (pl.col("batter") == target["batter"])
    )

    assert base.height == 1 and after.height == 1
    diff = base.select(*FEATURE_COLS).transpose().to_series() - after.select(
        *FEATURE_COLS
    ).transpose().to_series()
    assert diff.abs().sum() == 0.0, f"own-game mutation changed features: {diff}"


def test_b_future_game_append_cannot_change_earlier_rows() -> None:
    """(b) appending a later-dated game leaves every earlier feature row fixed."""
    pa = synthetic_pa()
    base = assemble_features(pa).sort(*KEYS)

    future_game = pa.head(3).to_dicts()
    for r in future_game:
        r["game_pk"] = 999
        r["game_date"] = date(2024, 5, 1)
        r["y"] = 1
    appended = pl.concat([pa, pl.DataFrame(future_game)])
    after = assemble_features(appended).sort(*KEYS)

    joined = base.join(after, on=KEYS, suffix="_new")
    assert joined.height == base.height
    for col in FEATURE_COLS:
        delta = (joined[col] - joined[col + "_new"]).abs().sum()
        assert delta == 0.0, f"append changed earlier rows' {col} (delta={delta})"


def test_c_executed_artifact_source_dates_strictly_precede_game_date() -> None:
    """(c) full-frame strict-prior check on the executed features.parquet."""
    feat = pl.read_parquet(HARNESS / "data" / "features.parquet")
    for src_col in ["src_date_pitcher", "src_date_batter", "lg_src_date"]:
        with_src = feat.filter(pl.col(src_col).is_not_null())
        assert with_src.height > 0, f"{src_col}: no rows with support"
        bad = with_src.filter(pl.col(src_col) >= pl.col("game_date"))
        assert bad.height == 0, f"{src_col}: {bad.height} rows with src >= game_date"


def test_d_eval_prediction_key_sets_identical_across_candidates() -> None:
    """(d) reference A, log5, and logistic B share one EVAL key set."""
    ev = pl.read_parquet(HARNESS / "data" / "eval_predictions.parquet")
    assert ev.height > 0
    pred_cols = {
        "A_reference": "pred_A_reference",
        "LOG5_reference": "pred_LOG5_reference",
        "B_logreg": "pred_B_logreg",
    }
    for name, col in pred_cols.items():
        assert col in ev.columns, f"missing {col} for {name}"
        assert ev[col].null_count() == 0, f"{name}: {ev[col].null_count()} null keys"
    # identical key set == every key carries all three predictions
    assert ev.select(*KEYS).n_unique() == ev.height, "duplicate EVAL keys"
