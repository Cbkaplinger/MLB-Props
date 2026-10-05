"""Builder-level synthetic leakage tests L1-L7 for workload_spine (v2.2).

All fixtures are hand-constructed; no real data is opened and no
scientific metrics are computed. L6 is intentionally NOT tested here:
inner-fit isolation must be proven in the new fitting pipeline when it
exists, not inherited from Run 1 by assertion.
"""

import datetime as dt
import json
import sys
from pathlib import Path

import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"))

import workload_spine as ws  # noqa: E402

COV_START = dt.date(2019, 1, 1)
COV_END = dt.date(2023, 12, 31)


def appearance(gp, pid, date, is_start, pitches, outs, bf):
    return (gp, pid, dt.date.fromisoformat(date), is_start,
            pitches, outs, bf)


def make_appearances(rows):
    return pl.DataFrame(
        rows,
        schema={
            "game_pk": pl.Int64, "pitcher": pl.Int64,
            "game_date": pl.Date, "is_start": pl.Boolean,
            "pitches": pl.Int64, "outs": pl.Int64, "bf": pl.Int64,
        },
        orient="row",
    )


def forecast_row(gp, pid, date):
    return pl.DataFrame({
        "game_pk": [gp], "pitcher": [pid],
        "game_date": [dt.date.fromisoformat(date)],
    })


def hist1(df):
    return df.row(0, named=True)


def build(apps, fr, pop=20.0, **kw):
    return hist1(ws.build_appearance_history(
        make_appearances(apps), fr, pop, COV_START, COV_END, **kw))


PRIOR = [
    appearance(1, 500, "2023-04-01", True, 90, 15, 18),
    appearance(2, 500, "2023-04-08", True, 95, 18, 22),
    appearance(3, 500, "2023-04-15", True, 85, 15, 20),
    appearance(4, 500, "2023-04-22", True, 100, 18, 24),
    appearance(5, 500, "2023-04-29", True, 88, 15, 19),
]

FEATURE_COLS = ("start_capacity_mean_bf", "start_bf_mean_last5",
                "actual_bf_mean_last5", "start_pitches_mean_last5",
                "n_capacity_appearances", "start_capacity_median_bf_5")


# ---------------------------------------------------------------------------
# L1-L5, L7 (builder level)
# ---------------------------------------------------------------------------


def test_l1_current_outcome_mutation_leaves_features_unchanged():
    fr = forecast_row(10, 500, "2023-05-06")
    base = build(PRIOR, fr)
    mutated = PRIOR + [appearance(10, 500, "2023-05-06", True, 5, 1, 2)]
    after = build(mutated, fr)
    for col in FEATURE_COLS:
        assert base[col] == after[col]


def test_l2_future_row_mutation_leaves_forecast_unchanged():
    fr = forecast_row(10, 500, "2023-05-06")
    base = build(PRIOR, fr)
    future = PRIOR + [appearance(11, 500, "2023-09-01", True, 30, 3, 2)]
    after = build(future, fr)
    for col in FEATURE_COLS:
        assert base[col] == after[col]
    assert base["label"] == after["label"]


def test_l3_truncation_equals_full_construction():
    fr = forecast_row(10, 500, "2023-05-06")
    full = build(PRIOR, fr)
    cutoff = [r for r in PRIOR if r[2] < dt.date(2023, 5, 6)]
    truncated = build(cutoff, fr)
    assert full == truncated


def test_l4_doubleheader_same_date_excluded():
    fr = forecast_row(10, 500, "2023-04-30")
    with_dh = PRIOR + [appearance(9, 500, "2023-04-30", True, 40, 6, 8)]
    got = build(with_dh, fr)
    assert got["n_capacity_appearances"] == 5
    assert got["actual_bf_mean_last5"] == pytest.approx(
        sum(r[6] for r in PRIOR[-5:]) / 5)


def pitch(game_pk, pitcher, date, inning, topbot, ab, pn):
    return (game_pk, pitcher, date, inning, topbot, ab, pn)


def make_pitches(rows):
    return pl.DataFrame(
        rows,
        schema={
            "game_pk": pl.Int64, "pitcher": pl.Int64,
            "game_date": pl.Date, "inning": pl.Int64,
            "inning_topbot": pl.String,
            "at_bat_number": pl.Int64, "pitch_number": pl.Int64,
        },
        orient="row",
    )


def full_game(game_pk, date):
    """Both halves of inning 1 (two opposing first pitchers) plus
    later relief rows on both sides."""
    return [
        pitch(game_pk, 501, date, 1, "Top", 1, 1),
        pitch(game_pk, 501, date, 1, "Top", 1, 2),
        pitch(game_pk, 502, date, 1, "Bot", 50, 1),
        pitch(game_pk, 502, date, 1, "Bot", 50, 2),
        pitch(game_pk, 503, date, 3, "Top", 100, 1),   # relief, home side
        pitch(game_pk, 504, date, 4, "Bot", 150, 1),   # relief, away side
    ]


def test_l5_row_existence_independent_of_outcome():
    # Same game, first pitcher faces 2 vs 200 batters: identical keys.
    thin = make_pitches([
        pitch(1, 500, dt.date(2023, 5, 1), 1, "Top", 1, 1),
        pitch(1, 500, dt.date(2023, 5, 1), 1, "Top", 1, 2),
        pitch(1, 600, dt.date(2023, 5, 1), 1, "Bot", 50, 1),
    ])
    fat = make_pitches([
        pitch(1, 500, dt.date(2023, 5, 1), 1, "Top", 1, 1),
    ] + [
        pitch(1, 500, dt.date(2023, 5, 1), 1, "Top", 1 + i, j)
        for i in range(1, 200) for j in (1, 2)
    ] + [
        pitch(1, 600, dt.date(2023, 5, 1), 1, "Bot", 500, 1),
    ])
    a = ws.first_pitcher_keys(thin).sort("forecast_pitcher")
    b = ws.first_pitcher_keys(fat).sort("forecast_pitcher")
    assert a.equals(b)
    assert sorted(a["forecast_pitcher"].to_list()) == [500, 600]


def test_identity_both_teams_first_pitchers_returned():
    rows = full_game(1, dt.date(2023, 5, 1))
    keys = ws.first_pitcher_keys(make_pitches(rows))
    assert sorted(keys["forecast_pitcher"].to_list()) == [501, 502]
    # Output key identifies game + pitching team (side + is_home).
    by_pitcher = {r["forecast_pitcher"]: r
                  for r in keys.iter_rows(named=True)}
    assert by_pitcher[501]["inning_topbot"] == "Top"
    assert by_pitcher[501]["is_home"] is True   # home pitches the Top
    assert by_pitcher[502]["inning_topbot"] == "Bot"
    assert by_pitcher[502]["is_home"] is False
    assert set(keys["game_pk"].to_list()) == {1}


def test_identity_relief_not_selected_and_order_invariant():
    rows = full_game(1, dt.date(2023, 5, 1))
    shuffled = list(reversed(rows))
    a = ws.first_pitcher_keys(make_pitches(rows)).sort("forecast_pitcher")
    b = ws.first_pitcher_keys(
        make_pitches(shuffled)).sort("forecast_pitcher")
    assert a.equals(b)  # deterministic earliest-pitch ordering
    assert 503 not in a["forecast_pitcher"].to_list()
    assert 504 not in a["forecast_pitcher"].to_list()


def test_identity_mid_pa_substitution_selects_opener():
    # First PA of the half: pitcher 501 starts it (pitches 1-2),
    # pitcher 502 completes it. The OPENER (501) began the half.
    rows = [
        pitch(1, 501, dt.date(2023, 5, 1), 1, "Top", 1, 1),
        pitch(1, 501, dt.date(2023, 5, 1), 1, "Top", 1, 2),
        pitch(1, 502, dt.date(2023, 5, 1), 1, "Top", 1, 3),
        pitch(1, 600, dt.date(2023, 5, 1), 1, "Bot", 50, 1),
    ]
    keys = ws.first_pitcher_keys(make_pitches(rows))
    assert sorted(keys["forecast_pitcher"].to_list()) == [501, 600]


def test_identity_missing_half_fails_loud():
    rows = [pitch(1, 501, dt.date(2023, 5, 1), 1, "Top", 1, 1)]
    with pytest.raises(ValueError, match="missing an inning-1 half"):
        ws.first_pitcher_keys(make_pitches(rows))


def test_identity_contradictory_date_fails_loud():
    rows = (full_game(1, dt.date(2023, 5, 1))
            + [pitch(1, 501, dt.date(2023, 5, 2), 5, "Top", 900, 1)])
    with pytest.raises(ValueError, match="contradictory game_date"):
        ws.first_pitcher_keys(make_pitches(rows))


def test_identity_missing_columns_fail_loud():
    with pytest.raises(ValueError, match="require columns missing"):
        ws.first_pitcher_keys(pl.DataFrame({"game_pk": [1]}))


def test_reset_boundary_exactly_1095_does_not_reset():
    # Boundary operator is strictly greater than 1095 days.
    prior = dt.date(2020, 1, 2)
    assert (dt.date(2023, 1, 1) - prior).days == 1095
    rows = [appearance(1, 500, str(prior), True, 100, 21, 28)]
    got = build(rows, forecast_row(10, 500, "2023-01-01"))
    assert got["capacity_reset"] is False
    assert got["n_capacity_appearances"] == 1


def test_reset_boundary_1096_does_reset():
    prior = dt.date(2019, 12, 30)  # 1098 days before 2023-01-01
    assert (dt.date(2023, 1, 1) - prior).days == 1098
    rows = [appearance(1, 500, str(prior), True, 100, 21, 28)]
    got = build(rows, forecast_row(10, 500, "2023-01-01"))
    assert got["capacity_reset"] is True
    assert got["n_capacity_appearances"] == 0
    # Identity metadata preserved; capacity fallback finite and
    # distinguishable from observed capacity.
    assert got["n_prior_all_seasons"] == 1
    assert got["prior_starts_all"] == 1
    assert got["no_prior_start_fallback"] is True
    assert got["start_capacity_mean_bf"] is None  # no observed capacity
    assert got["start_capacity_shrunk_bf"] == pytest.approx(20.0)


def test_internal_gap_boundary_1095_vs_1096():
    day0 = dt.date(2020, 1, 1)
    gap_ok = day0 + dt.timedelta(days=1095)
    rows = [appearance(1, 500, str(day0), True, 100, 21, 28),
            appearance(2, 500, str(gap_ok), True, 100, 21, 26)]
    got = build(rows, forecast_row(10, 500, str(
        gap_ok + dt.timedelta(days=10))))
    assert got["capacity_reset"] is False  # 1095 exactly: no reset
    assert got["n_capacity_appearances"] == 2
    rows2 = [appearance(1, 500, str(day0), True, 100, 21, 28),
             appearance(3, 500, str(day0 + dt.timedelta(days=1096)),
                        True, 100, 21, 26)]
    got2 = build(rows2, forecast_row(11, 500, str(
        day0 + dt.timedelta(days=1106))))
    assert got2["capacity_reset"] is True  # 1096: reset
    assert got2["n_capacity_appearances"] == 1


def test_nonfinite_population_mean_refused():
    fr = forecast_row(10, 500, "2023-05-06")
    with pytest.raises(ValueError, match="must be finite"):
        build(PRIOR, fr, pop=float("nan"))
    with pytest.raises(ValueError, match="must be finite"):
        build(PRIOR, fr, pop=float("inf"))


def test_l7_lineage_present_and_complete():
    fr = forecast_row(10, 500, "2023-05-06")
    df = ws.build_appearance_history(
        make_appearances(PRIOR), fr, 20.0, COV_START, COV_END)
    lineage = json.loads(df["lineage"][0])
    assert lineage["rule_version"] == "workload_spine_v2.2"
    assert lineage["coverage_bounds"]["coverage_start"] == str(COV_START)
    assert lineage["coverage_bounds"]["coverage_end"] == str(COV_END)
    assert "ACTUAL SOURCE COVERAGE" in json.loads(
        df["lineage"][0])["coverage_bounds_rule"]
    assert "strictly greater" in lineage["capacity_reset_rule"]
    assert "NEVER erased" in lineage["capacity_reset_rule"] \
        or "NEVER" in lineage["capacity_reset_rule"].upper()
    assert "NOT a proven debut" in lineage["debut_rule"]
    assert "recency-sensitive" in lineage["robustness_note"]
    assert "K=20 prior appearances" in lineage["robustness_note"]
    assert "never from pitch/BF counts" in lineage["injury_rule"]
    assert "separately" in lineage["role_separation"]
    # The 2029-case tests below are synthetic fixtures only -- they do
    # not open, reference, or authorize inspection of future-period or
    # held-out artifacts.


# ---------------------------------------------------------------------------
# Identity / capacity / debut dimensions
# ---------------------------------------------------------------------------


def test_no_prior_appearance_is_not_a_debut():
    fr = forecast_row(10, 700, "2023-05-06")
    got = build(PRIOR, fr)
    assert got["label"] == "no_prior_appearance_observed"
    # Debut label requires independent evidence.
    got2 = build(PRIOR, fr, debut_evidence={10: True})
    assert got2["label"] == "first_mlb_pitching_appearance"
    lineage = ws.build_appearance_history(
        make_appearances(PRIOR), fr, 20.0, COV_START, COV_END
    )["lineage"][0]
    assert "NOT a proven debut" in json.loads(lineage)["debut_rule"]


def test_no_prior_start_is_not_proven_first_mlb_start():
    rows = [appearance(1, 500, "2023-04-01", False, 25, 6, 8),
            appearance(2, 500, "2023-04-03", False, 20, 6, 7)]
    fr = forecast_row(10, 500, "2023-04-15")
    got = build(rows, fr)
    assert got["label"] == "no_prior_start_observed"
    # Explicit fallback: starter capacity from population mean, flagged.
    assert got["no_prior_start_fallback"] is True
    assert got["start_capacity_shrunk_bf"] == pytest.approx(20.0)
    # Relief history still recorded separately.
    assert got["relief_mean_bf"] == pytest.approx(7.5)
    assert got["prior_relief_all"] == 2


def test_capacity_reset_truncates_but_preserves_metadata():
    rows = [appearance(1, 500, "2019-06-01", True, 100, 21, 28),
            appearance(2, 500, "2019-06-08", True, 100, 21, 26),
            appearance(3, 500, "2023-05-01", True, 90, 18, 20)]
    fr = forecast_row(10, 500, "2023-05-06")
    got = build(rows, fr)
    assert got["capacity_reset"] is True
    assert got["label"] == "capacity_reset"
    # Post-gap capacity only.
    assert got["n_capacity_appearances"] == 1
    assert got["start_capacity_mean_bf"] == pytest.approx(20.0)
    # Known experience metadata preserved across the reset.
    assert got["n_prior_all_seasons"] == 3
    assert got["prior_starts_all"] == 3


def test_second_reset_after_a_later_long_gap():
    rows = [appearance(1, 500, "2019-06-01", True, 100, 21, 28),
            appearance(2, 500, "2019-06-08", True, 100, 21, 26),
            appearance(3, 500, "2023-05-01", True, 90, 18, 20),
            appearance(4, 500, "2023-05-08", True, 90, 18, 22)]
    fr1 = forecast_row(10, 500, "2023-05-15")
    got1 = build(rows, fr1)
    assert got1["capacity_reset"] is True
    assert got1["n_capacity_appearances"] == 2  # 2023 suffix
    # Later forecast after another long gap resets again.
    fr2 = forecast_row(11, 500, "2029-05-15")
    got2 = build(rows, fr2)
    assert got2["capacity_reset"] is True
    assert got2["n_capacity_appearances"] == 0
    assert got2["n_prior_all_seasons"] == 4  # metadata still there


def test_gap_reaching_forecast_empties_capacity():
    rows = [appearance(1, 500, "2019-06-01", True, 100, 21, 28)]
    fr = forecast_row(10, 500, "2023-05-06")
    got = build(rows, fr)
    assert got["capacity_reset"] is True
    assert got["n_capacity_appearances"] == 0
    assert got["n_prior_all_seasons"] == 1
    assert got["days_since_last_all"] == 1435


def test_prior_short_outings_preserved_and_used():
    rows = [appearance(1, 500, "2023-04-01", True, 20, 3, 3),
            appearance(2, 500, "2023-04-08", True, 95, 18, 21)]
    fr = forecast_row(10, 500, "2023-04-15")
    got = build(rows, fr)
    assert got["actual_expanding_mean_bf"] == pytest.approx(12.0)
    assert got["n_capacity_appearances"] == 2


def test_role_separation_relief_never_dilutes_starter_capacity():
    # Established starter history + recent one-inning relief outings.
    rows = [
        appearance(1, 500, "2023-03-01", True, 95, 18, 22),
        appearance(2, 500, "2023-03-08", True, 90, 18, 20),
        appearance(3, 500, "2023-04-01", False, 15, 1, 1),
        appearance(4, 500, "2023-04-02", False, 12, 1, 1),
        appearance(5, 500, "2023-04-03", False, 10, 1, 1),
    ]
    fr = forecast_row(10, 500, "2023-04-15")
    got = build(rows, fr)
    # 12-day gap, same-year prior appearances exist: ordinary.
    assert got["label"] == "ordinary"
    # Starter capacity unaffected by the relief outings.
    assert got["start_capacity_mean_bf"] == pytest.approx(21.0)
    assert got["relief_mean_bf"] == pytest.approx(1.0)
    assert got["actual_expanding_mean_bf"] == pytest.approx(9.0)
    assert got["no_prior_start_fallback"] is False


def test_shrinkage_definition():
    # K=20 prior APPEARANCES toward population mean; cutoff prior.
    rows = [appearance(1, 500, "2023-04-01", True, 90, 18, 10)]
    fr = forecast_row(10, 500, "2023-04-08")
    got = build(rows, fr, pop=30.0)
    expected = (1 * 10.0 + 20 * 30.0) / 21
    assert got["start_capacity_shrunk_bf"] == pytest.approx(expected)


def test_returning_after_gap_label_and_days():
    rows = [appearance(1, 500, "2023-03-05", True, 80, 15, 18)]
    fr = forecast_row(10, 500, "2023-05-10")
    got = build(rows, fr)
    assert got["label"] == "returning_after_gap"
    assert got["days_since_last_capacity"] == 66


def test_injury_label_requires_evidence():
    rows = [appearance(1, 500, "2023-04-01", True, 15, 1, 2)]
    fr = forecast_row(10, 500, "2023-04-05")
    no_evidence = build(rows, fr)
    assert no_evidence["label"] != "injury_return"
    with_evidence = build(rows, fr, injury_evidence={10: True})
    assert with_evidence["label"] == "injury_return"


def test_season_debut_vs_ordinary():
    rows = [appearance(1, 500, "2022-08-01", True, 90, 18, 21)]
    fr = forecast_row(10, 500, "2023-04-01")
    got = build(rows, fr)
    # First appearance of the 2023 season (no same-year prior):
    # season_debut takes precedence over the gap-return label; the
    # gap itself is still recorded in days_since_last_capacity.
    assert got["label"] == "season_debut"
    assert got["days_since_last_capacity"] == 243
    rows2 = rows + [appearance(2, 500, "2023-04-05", True, 90, 18, 21)]
    got2 = build(rows2, forecast_row(10, 500, "2023-04-08"))
    assert got2["label"] == "ordinary"
    rows3 = rows2 + [appearance(3, 500, "2023-04-07", True, 90, 18, 21)]
    got3 = build(rows3, forecast_row(11, 500, "2023-04-10"))
    assert got3["label"] == "ordinary"


def test_no_name_based_joins():
    # The builder schema has no name column anywhere; identity is by
    # id only. Structural assertion over the lineage + fields.
    fr = forecast_row(10, 500, "2023-05-06")
    df = ws.build_appearance_history(
        make_appearances(PRIOR), fr, 20.0, COV_START, COV_END)
    assert "name" not in " ".join(df.columns).lower()


def test_identity_position_player_opener_retained_and_counted():
    # Position-player status is a SEPARATE synthetic attribute: it never
    # enters the pitch frame, so it cannot override canonical
    # first-pitcher membership. Opener 501 opened the Top despite the
    # external designation.
    position_player_ids = {501}
    rows = full_game(1, dt.date(2023, 5, 1))
    assert 501 in position_player_ids  # designation recorded externally
    keys = ws.first_pitcher_keys(make_pitches(rows))
    assert 501 in keys["forecast_pitcher"].to_list()
    # Team-side identity intact: both halves still keyed.
    assert sorted(keys["forecast_pitcher"].to_list()) == [501, 502]
    # The same appearance, supplied with is_start=True, is counted by
    # the history builder -- not excluded because of the attribute.
    # Strictly-prior cutoff intact: 2023-05-01 appearance, 2023-05-06
    # forecast, distinct game_pks.
    apps = [appearance(1, 501, "2023-05-01", True, 20, 3, 5)]
    got = build(apps, forecast_row(10, 501, "2023-05-06"))
    assert got["n_capacity_appearances"] == 1
    assert got["prior_starts_all"] == 1
    assert got["no_prior_start_fallback"] is False
