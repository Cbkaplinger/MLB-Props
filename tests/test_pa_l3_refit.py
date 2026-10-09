"""Synthetic tests for the PA L3-style refit machinery (no real data)."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1] / "research" / "offseason_2026"
sys.path.insert(0, str(HERE))

import pa_lgbm_scaffold as sc  # noqa: E402
import run_pa_l3_refit as rf  # noqa: E402
import run_pa_lgbm_comparison as base  # noqa: E402

RAW_SCHEMA = {"game_pk": pl.Int64, "game_date": pl.Date, "pitcher": pl.Int64,
              "batter": pl.Int64, "stand": pl.String, "p_throws": pl.String,
              "events": pl.String, "at_bat_number": pl.Int64,
              "pitch_number": pl.Int64, "description": pl.String,
              "pitch_type": pl.String, "release_speed": pl.Float64,
              "zone": pl.Int64, "home_team": pl.String}


def raw(rows):
    return pl.DataFrame([tuple(r) + ("HOME",) for r in rows],
                        schema=RAW_SCHEMA, orient="row")


def label(rows):
    return sc.build_pa_label_table(raw(rows))


# --- Discipline accumulators ---------------------------------------------------


def test_pitcher_per_start_discipline_trailing5():
    # 6 starts; start N's P5 window = prior <=5 starts (career cum - shift5)
    rows = []
    speeds = {"swinging_strike": ("FF", 95.0, 12), "called_strike":
              ("FF", 95.0, 12)}
    d0 = date(2023, 4, 1)
    for g in range(6):
        gd = d0 + timedelta(days=7 * g)
        rows.append((g + 1, gd, 100, 200, "L", "R", "strikeout", 1, 1,
                     "called_strike", "FF", 95.0, 3))
        rows.append((g + 1, gd, 100, 200, "L", "R", "single", 2, 2,
                     "swinging_strike", "FF", 95.0, 13))
        rows.append((g + 1, gd, 100, 200, "L", "R", "field_out", 3, 3,
                     "foul", "SL", 85.0, 5))
    ps = rf.pitcher_per_start_discipline(raw(rows))
    assert ps.height == 6
    last = ps.row(5, named=True)
    # start 6: career cum wh = 6 (one swinging_strike per start)
    assert last["c_wh"] == 6
    # trailing-5 window = starts 2..6 -> wh = 5 (cum 6 - cum@start1 = 1)
    assert last["w5_wh"] == 5
    assert last["w5_sw"] == 10  # 2 swings per start
    assert last["w5_np"] == 15
    first = ps.row(0, named=True)
    assert first["w5_wh"] == 1  # shift(5) null -> 0
    second = ps.row(1, named=True)
    assert second["w5_wh"] == 2


def test_attach_pitcher_discipline_strictly_prior_and_season_boundary():
    rows = [
        (1, date(2022, 9, 1), 100, 200, "L", "R", "strikeout", 1, 1,
         "called_strike", "FF", 95.0, 3),
        (2, date(2023, 4, 1), 100, 200, "L", "R", "single", 1, 1,
         "swinging_strike", "FF", 95.0, 13),
    ]
    ps = rf.pitcher_per_start_discipline(raw(rows))
    keys = pl.DataFrame(
        {"key_game_pk": [3], "cutoff_date": [date(2023, 4, 2)],
         "pitcher": [100]},
        schema={"key_game_pk": pl.Int64, "cutoff_date": pl.Date,
                "pitcher": pl.Int64})
    att = rf.attach_pitcher_discipline(ps, keys).row(0, named=True)
    # last prior start = the 2023 start (a swinging strike); career wh = 1,
    # trailing-5 window = both starts -> wh = 1 (2022 start was called)
    assert att["w5_wh"] == 1
    assert att["w5_sw"] == 1  # called_strike is not a swing
    # season-std restricted to the cutoff season (2023): only the 2023 start
    assert att["std_wh"] == 1
    keys2 = pl.DataFrame(
        {"key_game_pk": [3], "cutoff_date": [date(2023, 1, 1)],
         "pitcher": [100]},
        schema={"key_game_pk": pl.Int64, "cutoff_date": pl.Date,
                "pitcher": pl.Int64})
    att2 = rf.attach_pitcher_discipline(ps, keys2).row(0, named=True)
    # last prior start is 2022 -> season-std null (no same-season start)
    assert att2["std_wh"] is None
    assert att2["w5_wh"] == 0


def test_batter_discipline_asof_cumulative():
    rows = [
        (1, date(2023, 4, 1), 100, 200, "L", "R", None, 1, 1, "ball", "FF",
         95.0, 1),
        (1, date(2023, 4, 1), 100, 200, "L", "R", "strikeout", 1, 2,
         "swinging_strike", "FF", 95.0, 13),
        (2, date(2023, 4, 10), 100, 200, "L", "R", None, 3, 1, "foul", "SL",
         85.0, 5),
    ]
    cutoffs = pl.DataFrame(
        {"batter": [200, 200], "cutoff_date": [date(2023, 4, 1),
                                               date(2023, 4, 11)]},
        schema={"batter": pl.Int64, "cutoff_date": pl.Date})
    out = rf.batter_discipline_asof(raw(rows), cutoffs)
    d = {r["cutoff_date"]: r for r in out.iter_rows(named=True)}
    assert d[date(2023, 4, 1)]["b_sw"] == 0  # same-day excluded
    assert d[date(2023, 4, 11)]["b_sw"] == 2
    assert d[date(2023, 4, 11)]["b_wh"] == 1
    assert d[date(2023, 4, 11)]["b_np"] == 3


def test_park_factors_prior_eb():
    lab_rows = [
        (1, date(2022, 5, 1), 100, 200, "L", "R", "strikeout", 1, 1,
         "called_strike", "FF", 95.0, 3),
        (1, date(2022, 5, 1), 100, 201, "R", "R", "single", 2, 1,
         "hit_into_play", "SL", 85.0, 5),
        (2, date(2022, 5, 2), 100, 202, "L", "R", "strikeout", 1, 1,
         "called_strike", "FF", 95.0, 3),
        (2, date(2022, 5, 2), 100, 203, "R", "R", "strikeout", 2, 1,
         "swinging_strike", "FF", 95.0, 13),
    ]
    lab = label(lab_rows)
    pf = rf.park_factors_prior(lab, raw(lab_rows))
    # league rate = 3/4; the single park saw 3 K in 4 PA -> factor 1.0
    r = pf.row(0, named=True)
    assert r["park_k"] == pytest.approx(1.0)


# --- Frozen matrix ---------------------------------------------------------------


def _base_frame():
    return pl.DataFrame({
        "game_pk": [1], "game_date": [date(2023, 5, 1)],
        "at_bat_number": [1], "pitcher": [100], "batter": [200], "y": [1],
        "stand": ["L"], "p_throws": ["L"],
        "k_prior": [30], "n_prior": [120], "n_prior_season": [40],
        "n_prior_starts": [6], "n_prior_pa": [110],
        "days_since_prev_start": [4], "n_prior_short_starts": [0],
        "b_k_vs_lhp": [0], "b_n_vs_lhp": [0],
        "b_k_vs_rhp": [50], "b_n_vs_rhp": [200],
        "b_sw": [30], "b_wh": [8], "b_cs": [15], "b_ch": [5], "b_np": [90],
        "park_k": [None], "spi": [10],
        "w5_sw": [10], "w5_wh": [3], "w5_cs": [4], "w5_ch": [1],
        "w5_iz": [8], "w5_ct": [6], "w5_np": [20],
        "std_sw": [40], "std_wh": [10], "std_cs": [20], "std_ch": [4],
        "std_iz": [30], "std_ct": [24], "std_np": [100],
    })


def test_l3_matrix_fills_and_hand_rate():
    lg = 0.22
    X = rf.l3_matrix(_base_frame(), lg)
    assert X.shape == (1, 24)
    idx = {c: i for i, c in enumerate(rf.L3_FEATURES)}
    assert X[0, idx["same_hand"]] == 1.0
    # pitcher throws L -> b_hand_rate uses the vs-LHP split, which is empty
    # in this fixture -> league fallback
    assert X[0, idx["b_hand_rate"]] == pytest.approx(lg)
    # whiff = 3/10; swstr = (4+3)/20; zone = 8/20; contact = 6/10
    assert X[0, idx["p_whiff_P5"]] == pytest.approx(0.3)
    assert X[0, idx["p_swstr_P5"]] == pytest.approx(0.35)
    assert X[0, idx["p_zone_P5"]] == pytest.approx(0.4)
    assert X[0, idx["p_contact_P5"]] == pytest.approx(0.6)
    assert X[0, idx["log_pa_curr"]] == pytest.approx(np.log(41))
    assert X[0, idx["log_pa_prior"]] == pytest.approx(np.log(121))
    assert X[0, idx["park_k"]] == 1.0  # filled
    assert X[0, idx["rest"]] == 4.0
    assert X[0, idx["debut"]] == 0.0
    assert X[0, idx["trip_ge_4"]] == 1.0  # spi 10
    assert X[0, idx["trip_eq_2"]] == 0.0
    assert X[0, idx["spi_over_9"]] == pytest.approx(10 / 9)


def test_l3_matrix_cold_start_fills_zero():
    f = _base_frame()
    cold = f.with_columns(
        pl.lit(0, dtype=pl.Int64).alias("w5_sw"),
        pl.lit(0, dtype=pl.Int64).alias("w5_wh"),
        pl.lit(0, dtype=pl.Int64).alias("w5_np"),
        pl.lit(None, dtype=pl.Int64).alias("std_sw"),
        pl.lit(None, dtype=pl.Int64).alias("std_wh"),
        pl.lit(None, dtype=pl.Int64).alias("std_np"),
        pl.lit(None, dtype=pl.Int64).alias("days_since_prev_start"),
    )
    X = rf.l3_matrix(cold, 0.22)
    idx = {c: i for i, c in enumerate(rf.L3_FEATURES)}
    assert X[0, idx["p_whiff_P5"]] == 0.0  # nan_to_num fill
    assert X[0, idx["p_whiff_std"]] == 0.0
    assert X[0, idx["rest"]] == 15.0
    assert np.isfinite(X).all()


# --- Preflight guards ---------------------------------------------------------------


def test_preflight_ledger_catches_duplication():
    rows = [
        (1, date(2023, 4, 1), 100, 200, "L", "R", "strikeout", 1, 1,
         "called_strike", "FF", 95.0, 3),
    ]
    lab = label(rows)
    fp = lab.clone()
    feat = lab.filter(pl.col("pa_class") == sc.CLASS_COMPLETED)
    ok = rf.preflight_ledger(lab, fp, feat)
    assert ok["n_duplicate_pa"] == 0 and ok["join_expansion"] == 0
    doubled = pl.concat([feat, feat], how="vertical")
    with pytest.raises(rf.RunFailure, match="join_expansion"):
        rf.preflight_ledger(lab, fp, doubled)


def test_holm_single_family_passthrough():
    res = base.holm({"D3-A": 0.03})
    assert res["D3-A"]["p_adj"] == 0.03
