"""Synthetic tests for the pa_completed_v1 scaffold (pa-lgbm contract 2026-10-09).

Pure frames only; no file I/O, no real data, no fitting.
"""

from __future__ import annotations

import math
import sys
from datetime import date
from pathlib import Path

import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1] / "research" / "offseason_2026"
sys.path.insert(0, str(HERE))

import pa_lgbm_scaffold as sc  # noqa: E402


def pitch_rows(rows):
    return pl.DataFrame(
        rows,
        schema={
            "game_pk": pl.Int64, "game_date": pl.Date, "pitcher": pl.Int64,
            "batter": pl.Int64, "stand": pl.String, "p_throws": pl.String,
            "events": pl.String, "at_bat_number": pl.Int64,
            "pitch_number": pl.Int64,
        },
        orient="row",
    )


def label(rows):
    return sc.build_pa_label_table(pitch_rows(rows))


# --- Event mapping -----------------------------------------------------------


def test_event_mapping_classes():
    assert sc.classify_event("strikeout") == sc.CLASS_COMPLETED
    assert sc.classify_event("strikeout_double_play") == sc.CLASS_COMPLETED
    assert sc.classify_event("walk") == sc.CLASS_COMPLETED
    assert sc.classify_event("wild_pitch") == sc.CLASS_BASERUNNING
    assert sc.classify_event("caught_stealing_2b") == sc.CLASS_BASERUNNING
    assert sc.classify_event("truncated_pa") == sc.CLASS_INCOMPLETE
    assert sc.classify_event(None) == sc.CLASS_INCOMPLETE
    with pytest.raises(ValueError):
        sc.classify_event("not_a_real_event")


# --- Label table --------------------------------------------------------------


def test_label_table_completed_basics():
    t = label([
        (1, date(2023, 5, 1), 100, 200, "L", "R", None, 1, 1),
        (1, date(2023, 5, 1), 100, 200, "L", "R", "strikeout", 1, 2),
        (1, date(2023, 5, 1), 100, 201, "R", "R", None, 2, 1),
        (1, date(2023, 5, 1), 100, 201, "R", "R", "walk", 2, 2),
        (1, date(2023, 5, 1), 100, 202, "L", "R", "strikeout_double_play",
         3, 1),
    ])
    assert t.height == 3
    assert t.select(pl.struct(["game_pk", "at_bat_number"]).n_unique()
                    ).item() == 3
    by_pa = {r["at_bat_number"]: r for r in t.iter_rows(named=True)}
    assert by_pa[1]["y"] == 1 and by_pa[1]["pa_class"] == sc.CLASS_COMPLETED
    assert by_pa[2]["y"] == 0 and by_pa[2]["event"] == "walk"
    assert by_pa[3]["y"] == 1
    assert t["y"].sum() == 2


def test_completed_event_before_baserunning_terminal_row_wins():
    # terminal row is a wild_pitch, but the group completed with a strikeout
    t = label([
        (1, date(2023, 5, 1), 100, 200, "L", "R", None, 1, 1),
        (1, date(2023, 5, 1), 100, 200, "L", "R", "strikeout", 1, 2),
        (1, date(2023, 5, 1), 100, 200, "L", "R", "wild_pitch", 1, 3),
    ])
    assert t.height == 1
    r = t.row(0, named=True)
    assert r["pa_class"] == sc.CLASS_COMPLETED and r["y"] == 1
    assert r["event"] == "strikeout"


def test_baserunning_only_group_excluded_and_classified():
    t = label([
        (1, date(2023, 5, 1), 100, 200, "L", "R", "wild_pitch", 1, 1),
        (1, date(2023, 5, 1), 100, 200, "L", "R", "caught_stealing_2b", 1, 2),
    ])
    r = t.row(0, named=True)
    assert r["pa_class"] == sc.CLASS_BASERUNNING
    assert r["y"] is None


def test_incomplete_group_truncated_and_null_terminal():
    t = label([
        (1, date(2023, 5, 1), 100, 200, "L", "R", "truncated_pa", 1, 1),
        (2, date(2023, 5, 1), 100, 201, "R", "R", None, 2, 1),
        (2, date(2023, 5, 1), 100, 201, "R", "R", None, 2, 2),
    ])
    assert (t["pa_class"] == sc.CLASS_INCOMPLETE).all()
    assert t["y"].is_null().all()


def test_mid_pa_pitcher_change_flag_and_attribution():
    t = label([
        (1, date(2023, 5, 1), 100, 200, "L", "R", None, 1, 1),
        (1, date(2023, 5, 1), 999, 200, "L", "R", "strikeout", 1, 2),
    ])
    r = t.row(0, named=True)
    assert r["mid_pa_pitcher_change"] is True
    assert r["pitcher"] == 999  # defining-row attribution
    t2 = label([
        (1, date(2023, 5, 1), 100, 200, "L", "R", "strikeout", 1, 1),
    ])
    assert t2.row(0, named=True)["mid_pa_pitcher_change"] is False


def test_mixed_batter_group_incomplete_with_flag():
    t = label([
        (1, date(2023, 5, 1), 100, 200, "L", "R", None, 1, 1),
        (1, date(2023, 5, 1), 100, 999, "R", "R", "strikeout", 1, 2),
    ])
    r = t.row(0, named=True)
    assert r["mixed_batter"] is True
    assert r["pa_class"] == sc.CLASS_INCOMPLETE
    assert r["y"] is None
    assert r["event"] == "strikeout"  # kept for reporting, excluded from y


def test_unmapped_event_fails_loud():
    with pytest.raises(ValueError, match="unmapped"):
        label([(1, date(2023, 5, 1), 100, 200, "L", "R", "mystery", 1, 1)])


def test_first_pitcher_filter():
    keys = pl.DataFrame({"game_pk": [1], "forecast_pitcher": [100]},
                        schema={"game_pk": pl.Int64,
                                "forecast_pitcher": pl.Int64})
    t = label([
        (1, date(2023, 5, 1), 100, 200, "L", "R", "strikeout", 1, 1),
        (1, date(2023, 5, 1), 555, 201, "R", "R", "single", 2, 1),
    ])
    kept = sc.first_pitcher_filter(t, keys)
    assert kept.height == 1 and kept["pitcher"].item() == 100


# --- Pooled velocity vs mean-of-game-means ------------------------------------


def test_pooled_velocity_beats_mean_of_game_means():
    keys = pl.DataFrame(
        {"key_game_pk": [100], "cutoff_date": [date(2023, 5, 1)],
         "pitcher": [100]},
        schema={"key_game_pk": pl.Int64, "cutoff_date": pl.Date,
                "pitcher": pl.Int64})
    speed_rows = ([(1, date(2023, 4, 1), 100, "FF", 96.0)] * 10
                  + [(2, date(2023, 4, 20), 100, "FF", 92.0)] * 50)
    pr = pl.DataFrame(
        speed_rows,
        schema={"game_pk": pl.Int64, "game_date": pl.Date,
                "pitcher": pl.Int64, "pitch_type": pl.String,
                "release_speed": pl.Float64},
        orient="row")
    stats = sc.pitcher_pitchtype_priors(pr, keys)
    totals = (stats.group_by(sc.PITCHER_SNAPSHOT_COLUMNS)
              .agg(pl.col("n_type").sum().alias("n_eligible")))
    fin = sc.finalize_type_stats(stats, totals).row(0, named=True)
    # pooled = (10*96 + 50*92)/60 = 92.667; equal-start mean would be 94
    assert abs(fin["mean_speed"] - (10 * 96 + 50 * 92) / 60) < 1e-9
    assert fin["n_valid"] == 60


def test_usage_denominator_independent_of_velocity_missingness():
    keys = pl.DataFrame(
        {"key_game_pk": [100], "cutoff_date": [date(2023, 5, 1)],
         "pitcher": [100]},
        schema={"key_game_pk": pl.Int64, "cutoff_date": pl.Date,
                "pitcher": pl.Int64})
    rows = [(1, date(2023, 4, 1), 100, "FF", 96.0),
            (1, date(2023, 4, 1), 100, "FF", None),
            (1, date(2023, 4, 1), 100, "SL", 85.0),
            (1, date(2023, 4, 1), 100, "SL", None),
            (1, date(2023, 4, 1), 100, "SL", None)]
    pr = pl.DataFrame(
        rows,
        schema={"game_pk": pl.Int64, "game_date": pl.Date,
                "pitcher": pl.Int64, "pitch_type": pl.String,
                "release_speed": pl.Float64},
        orient="row")
    stats = sc.pitcher_pitchtype_priors(pr, keys)
    totals = (stats.group_by(sc.PITCHER_SNAPSHOT_COLUMNS)
              .agg(pl.col("n_type").sum().alias("n_eligible")))
    fin = sc.finalize_type_stats(stats, totals)
    by_type = {r["pitch_type"]: r for r in fin.iter_rows(named=True)}
    assert by_type["FF"]["n_valid"] == 1
    assert by_type["FF"]["n_missing_velocity"] == 1
    assert abs(by_type["FF"]["usage_share"] - 2 / 5) < 1e-9
    assert abs(by_type["SL"]["usage_share"] - 3 / 5) < 1e-9
    assert by_type["SL"]["n_valid"] == 1


def test_swing_identity_whiffs_plus_contacts():
    keys = pl.DataFrame(
        {"key_game_pk": [100], "cutoff_date": [date(2023, 5, 1)],
         "pitcher": [100]},
        schema={"key_game_pk": pl.Int64, "cutoff_date": pl.Date,
                "pitcher": pl.Int64})
    descs = ["swinging_strike", "foul_tip", "foul", "hit_into_play",
             "called_strike", "ball"]
    rows = [(1, date(2023, 4, 1), 100, d) for d in descs]
    pr = pl.DataFrame(
        rows,
        schema={"game_pk": pl.Int64, "game_date": pl.Date,
                "pitcher": pl.Int64, "description": pl.String},
        orient="row")
    s = sc.pitcher_swing_priors(pr, keys).row(0, named=True)
    assert s["n_swings"] == 4
    assert s["n_whiffs"] == 2
    assert s["n_contacts"] == 2
    assert s["n_swings"] == s["n_whiffs"] + s["n_contacts"]


# --- Pregame availability ------------------------------------------------------


def _full_prior_world():
    label_rows = label([
        # prior game 2023-04-01: 2 PA, 1 K
        (1, date(2023, 4, 1), 100, 200, "L", "R", "strikeout", 1, 1),
        (1, date(2023, 4, 1), 100, 201, "R", "R", "single", 2, 1),
        # current game 2023-05-01 rows (must NOT enter snapshots)
        (2, date(2023, 5, 1), 100, 202, "L", "R", "strikeout", 1, 1),
    ])
    keys = pl.DataFrame(
        {"key_game_pk": [2], "cutoff_date": [date(2023, 5, 1)],
         "pitcher": [100]},
        schema={"key_game_pk": pl.Int64, "cutoff_date": pl.Date,
                "pitcher": pl.Int64})
    pr = pl.DataFrame(
        [(1, date(2023, 4, 1), 100, "FF", 95.0, "swinging_strike"),
         (2, date(2023, 5, 1), 100, "FF", 99.0, "called_strike")],
        schema={"game_pk": pl.Int64, "game_date": pl.Date,
                "pitcher": pl.Int64, "pitch_type": pl.String,
                "release_speed": pl.Float64, "description": pl.String},
        orient="row")
    return label_rows, keys, pr


def test_pregame_cutoff_excludes_current_game():
    label_rows, keys, pr = _full_prior_world()
    snap = sc.assemble_pitcher_snapshots(label_rows, pr, keys, lg=0.22)
    r = snap.row(0, named=True)
    assert r["n_prior"] == 2 and r["k_prior"] == 1
    stats = sc.pitcher_pitchtype_priors(pr, keys).row(0, named=True)
    assert stats["n_valid"] == 1 and abs(stats["sum_speed"] - 95.0) < 1e-9


def test_future_append_and_outcome_mutation_invariance():
    label_rows, keys, pr = _full_prior_world()
    base = sc.assemble_pitcher_snapshots(label_rows, pr, keys, lg=0.22)

    # future-append: a brand-new later game leaves the snapshot unchanged
    extra = pl.DataFrame(
        {"game_pk": [3], "game_date": [date(2023, 6, 1)], "pitcher": [100],
         "batter": [203], "stand": ["L"], "p_throws": ["R"],
         "event": ["home_run"], "pa_class": [sc.CLASS_COMPLETED],
         "y": [0], "mid_pa_pitcher_change": [False], "n_pitches": [4]},
        schema={"game_pk": pl.Int64, "game_date": pl.Date,
                "pitcher": pl.Int64, "batter": pl.Int64, "stand": pl.String,
                "p_throws": pl.String, "event": pl.String,
                "pa_class": pl.String, "y": pl.Int8,
                "mid_pa_pitcher_change": pl.Boolean, "n_pitches": pl.UInt32})
    appended = pl.concat([label_rows, extra], how="diagonal")
    assert sc.assemble_pitcher_snapshots(
        appended, pr, keys, lg=0.22).equals(base)

    # outcome-mutation: flipping the CURRENT game's outcome changes nothing
    mutated = label_rows.with_columns(
        pl.when(pl.col("game_pk") == 2).then(pl.lit(0, dtype=pl.Int8))
        .otherwise(pl.col("y")).alias("y"))
    assert sc.assemble_pitcher_snapshots(
        mutated, pr, keys, lg=0.22).equals(base)


# --- Shrinkage, league rate, cold starts ---------------------------------------


def test_league_rate_and_shrunk_rate():
    label_rows, _, _ = _full_prior_world()
    lg = sc.league_rate(label_rows, date(2023, 5, 1))
    assert abs(lg - 0.5) < 1e-12  # 1 K of 2 prior completed PAs
    assert math.isnan(sc.league_rate(label_rows, date(2023, 4, 1)))
    # shrunk toward league: (1 + 150*0.5)/(2 + 150)
    assert abs(sc.shrunk_rate(1, 2, 0.5) - (1 + 75.0) / 152.0) < 1e-12


def test_cold_start_taxonomy_and_fallback():
    assert sc.classify_cold_start(0, 0) == "career_debut"
    assert sc.classify_cold_start(300, 0) == "season_debut"
    assert sc.classify_cold_start(40, 40) == "insufficient_history"
    assert sc.classify_cold_start(300, 100) == "established"
    label_rows, keys, pr = _full_prior_world()
    empty_keys = pl.DataFrame(
        {"key_game_pk": [7], "cutoff_date": [date(2023, 3, 30)],
         "pitcher": [100]},
        schema={"key_game_pk": pl.Int64, "cutoff_date": pl.Date,
                "pitcher": pl.Int64})
    snap = sc.assemble_pitcher_snapshots(label_rows, pr, empty_keys, lg=0.22)
    r = snap.row(0, named=True)
    assert r["cold_start_class"] == "career_debut"
    assert r["k_rate_shrunk"] == 0.22  # league fallback at n_prior = 0


def test_batter_hand_split_priors():
    label_rows = label([
        (1, date(2023, 4, 1), 100, 200, "L", "R", "strikeout", 1, 1),
        (1, date(2023, 4, 1), 555, 200, "L", "L", "single", 2, 1),
        (1, date(2023, 4, 1), 100, 200, "L", "R", "strikeout", 3, 1),
    ])
    keys = pl.DataFrame(
        {"key_game_pk": [2], "cutoff_date": [date(2023, 5, 1)],
         "batter": [200]},
        schema={"key_game_pk": pl.Int64, "cutoff_date": pl.Date,
                "batter": pl.Int64})
    b = sc.batter_rate_priors(label_rows, keys).row(0, named=True)
    assert b["n_prior"] == 3 and b["k_prior"] == 2
    assert b["n_prior_vs_rhp"] == 2 and b["k_prior_vs_rhp"] == 2
    assert b["n_prior_vs_lhp"] == 1 and b["k_prior_vs_lhp"] == 0


# --- Workload priors ------------------------------------------------------------


def test_workload_priors_short_start_history():
    label_rows = label([
        # prior start 1: 3 PAs (short), 1 K
        (1, date(2023, 4, 1), 100, 200, "L", "R", "strikeout", 1, 1),
        (1, date(2023, 4, 1), 100, 201, "R", "R", "single", 2, 1),
        (1, date(2023, 4, 1), 100, 202, "L", "R", "walk", 3, 1),
        # prior start 2: 10 PAs (not short)
        (2, date(2023, 4, 12), 100, 200, "L", "R", "field_out", 1, 1),
    ] + [(2, date(2023, 4, 12), 100, 200 + (i % 5), "L", "R", "single",
          2 + i, 1) for i in range(9)])
    keys = pl.DataFrame(
        {"key_game_pk": [3], "cutoff_date": [date(2023, 5, 1)],
         "pitcher": [100]},
        schema={"key_game_pk": pl.Int64, "cutoff_date": pl.Date,
                "pitcher": pl.Int64})
    w = sc.pitcher_workload_priors(label_rows, keys).row(0, named=True)
    assert w["n_prior_starts"] == 2
    assert w["n_prior_pa"] == 13
    assert w["n_prior_short_starts"] == 1
    assert w["days_since_prev_start"] == 19  # 5/1 - 4/12


# --- Feature dictionary ----------------------------------------------------------


def test_feature_dictionary_completeness():
    fd = sc.feature_dictionary()
    required = {"name", "estimand", "construction", "numerator",
                "denominator", "history_unit", "cutoff", "evidence_columns"}
    for f in fd:
        assert required <= set(f), f["name"]
        assert f["denominator"], f["name"]
        assert f["cutoff"].startswith("game_date <"), f["name"]
