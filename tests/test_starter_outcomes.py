"""Synthetic tests for the historical starter-outcome derivation
(starter_outcomes.py, baseline contract v2). SYNTHETIC ONLY: no real
artifacts, no outcome scoring. Covers: two starters in one game,
reliever exclusion, duplicate detection, incorrect-role failure,
opener/multiple-starter-role anomaly, missing rows, side derivation,
determinism, overlap validation, the v2 adapter, and the end-to-end
derive_start_outcomes -> build_arms_v2 integration chain."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import baseline_ladder as bl  # noqa: E402
from pregame_pa_ext import starter_outcomes as so  # noqa: E402

P1, P2, R1 = 700001, 700002, 700003
P3 = 700004
P9 = 700005


def _pa_source_frame():
    """Canonical fixture: two games x two sides (one starter each) +
    reliever rows + one out-of-window 2022 row."""
    rows = [
        # game 1: Top starter P1 (6 PA, 3 K), reliever R1 (2 PA, 0 K), Bot starter P2 (2 PA, 1 K)
        (900001, date(2023, 5, 2), P1, 1, "starter_pa", "Top", 2),
        (900001, date(2023, 5, 2), P1, 0, "starter_pa", "Top", 3),
        (900001, date(2023, 5, 2), P1, 1, "starter_pa", "Top", 4),
        (900001, date(2023, 5, 2), P1, 1, "starter_pa", "Top", 5),
        (900001, date(2023, 5, 2), P1, 0, "starter_pa", "Top", 6),
        (900001, date(2023, 5, 2), P1, 0, "starter_pa", "Top", 7),
        (900001, date(2023, 5, 2), R1, 0, "reliever_pa", "Top", 8),
        (900001, date(2023, 5, 2), R1, 0, "reliever_pa", "Top", 9),
        (900001, date(2023, 5, 2), P2, 1, "starter_pa", "Bot", 1),
        (900001, date(2023, 5, 2), P2, 0, "starter_pa", "Bot", 2),
        # game 2 (2024): Top starter P3 (4 PA, 4 K), Bot starter P1 again (4 PA, 1 K)
        (900002, date(2024, 8, 15), P3, 1, "starter_pa", "Top", 1),
        (900002, date(2024, 8, 15), P3, 1, "starter_pa", "Top", 2),
        (900002, date(2024, 8, 15), P3, 1, "starter_pa", "Top", 3),
        (900002, date(2024, 8, 15), P3, 1, "starter_pa", "Top", 4),
        (900002, date(2024, 8, 15), P1, 0, "starter_pa", "Bot", 1),
        (900002, date(2024, 8, 15), P1, 0, "starter_pa", "Bot", 2),
        (900002, date(2024, 8, 15), P1, 0, "starter_pa", "Bot", 3),
        (900002, date(2024, 8, 15), P1, 1, "starter_pa", "Bot", 4),
        # 2022 row (outside the declared 2023-2024 window)
        (900003, date(2022, 5, 1), P1, 1, "starter_pa", "Top", 1),
    ]
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "game_date": pl.Date, "pitcher": pl.Int64,
        "y": pl.Int64, "pitcher_role": pl.Utf8,
        "inning_topbot": pl.Utf8, "at_bat_number": pl.Int64,
    }, orient="row")


def _pa_source():
    """Canonical fixture: two games x two sides (one starter each) +
    reliever rows + one out-of-window 2022 row."""
    return _pa_source_frame()


def _derive(**kw):  # noqa: ANN003
    return so.derive_start_outcomes(_pa_source(), **kw)


def test_baseline_derivation_two_starters_one_game():
    """Two starters in one game (one per side) are BOTH derived, with
    the exact BF/K definitions (realized_bf = row count, realized_k =
    sum of y) and the first-pitcher prespec."""
    res = so.derive_start_outcomes(_pa_source())
    s = res["start_outcomes"]
    assert res["meta"]["n_starts"] == 4  # 2 games x 2 sides
    assert res["meta"]["n_reliever_games_excluded"] >= 1
    g1_top = s.filter((pl.col("game_pk") == 900001)
                      & (pl.col("side") == "Top")).row(0, named=True)
    assert g1_top["pitcher"] == P1
    assert g1_top["realized_bf"] == 6
    assert g1_top["realized_k"] == 3
    b1 = s.filter((pl.col("game_pk") == 900001)
                  & (pl.col("side") == "Bot")).row(0, named=True)
    assert b1["pitcher"] == P2 and b1["realized_bf"] == 2
    assert b1["realized_k"] == 1
    # window filter: the 2022 row is out of window
    assert s.filter(pl.col("game_pk") == 900003).height == 0
    assert s.filter(pl.col("pitcher") == P1).height == 2  # 2023 + 2024


def test_baseline_derivation_excludes_relievers():
    res = _derive()
    s = res["start_outcomes"]
    # reliever R1's pitcher-game must not appear as a start
    assert not s.filter(pl.col("pitcher") == R1).height
    assert res["meta"]["n_reliever_games_excluded"] >= 1


def test_baseline_derivation_deterministic():
    a = _derive()["start_outcomes"]
    b = _derive()["start_outcomes"]
    assert a.equals(b)


def test_baseline_derivation_deterministic_under_shuffled_storage_order():
    """The SAME rows in a different storage order derive identical
    starts: the derivation sorts its output and never depends on source
    row order (fixed permutation, no RNG)."""
    pa = _pa_source()
    assert pa.height == 19
    perm = [5, 0, 11, 3, 18, 1, 9, 14, 2, 16, 7, 4, 12, 6, 17, 10, 8,
            13, 15]
    shuffled = pa[perm]
    a = so.derive_start_outcomes(pa)["start_outcomes"]
    b = so.derive_start_outcomes(shuffled)["start_outcomes"]
    assert a.equals(b)


# ------------------------------------------------------------ failures
def test_baseline_derivation_incorrect_role_fails():
    """A derived start whose rows carry reliever roles fails loud
    (incorrect-role failure) instead of being silently included."""
    pa = _pa_source().with_columns(
        pl.when(pl.col("pitcher") == P1)
        .then(pl.lit("reliever_pa")).otherwise(pl.col("pitcher_role"))
        .alias("pitcher_role"))
    with pytest.raises(so.DerivationError, match="incorrect-role failure"):
        so.derive_start_outcomes(pa)


def test_baseline_opener_role_anomaly_fails():
    """Two pitchers carrying starter rows in one game-side (opener/bulk)
    is a role anomaly: fail loud, no opener rule registered."""
    extra = pl.DataFrame(
        [(900001, date(2023, 5, 2), P9, 1, "starter_pa", "Top", 1)],
        schema=_pa_source().schema, orient="row")
    # P9 has an EARLIER at_bat_number (1, before P1's 2) in the same
    # game-side -> two starter-role pitchers in one game-side; P9
    # becomes the first pitcher and P1 (also starter-labeled) is the
    # anomaly
    with pytest.raises(so.DerivationError, match="role anomaly"):
        so.derive_start_outcomes(pl.concat([_pa_source(), extra]))


def test_baseline_duplicate_input_detection():
    dup = pl.concat([_pa_source(), _pa_source().head(1)])
    with pytest.raises(so.DerivationError, match="duplicate PA rows"):
        so.derive_start_outcomes(dup)


def test_baseline_missing_rows_detected():
    """Null outcome fields are missing SOURCE COVERAGE (present rows
    with unrecorded outcomes), reported distinctly from missing
    FIELDS (absent columns)."""
    bad = _pa_source().with_columns(
        pl.when(pl.col("pitcher") == P1).then(None)
        .otherwise(pl.col("y")).alias("y"))
    with pytest.raises(so.DerivationError,
                       match="missing source coverage"):
        so.derive_start_outcomes(bad)


def test_baseline_side_and_keys_two_starters_one_game():
    """One game with two starters (one per side): both derived as
    distinct (game_pk, side, pitcher) starts; reliever rows excluded."""
    out = _derive()["start_outcomes"]
    g1 = out.filter(pl.col("game_pk") == 900001)
    assert g1.height == 2
    assert set(g1["side"].to_list()) == {"Top", "Bot"}
    assert set(g1["pitcher"].to_list()) == {P1, P2}
    assert g1.filter(pl.col("side") == "Top")["realized_bf"][0] == 6
    assert g1.filter(pl.col("side") == "Top")["realized_k"][0] == 3
    # window filter: the 2022 row is out of window, 2023+2024 rows in
    assert out.filter(pl.col("game_pk") == 900003).height == 0
    assert out.filter(pl.col("pitcher") == P1).height == 2  # 2023 + 2024


# ------------------------------------------------- overlap validation
def test_baseline_overlap_validation_identical_and_mismatch(tmp_path):
    reg = pl.DataFrame(
        [(900001, "Top", P1, 6, 3), (900001, "Bot", P2, 2, 0),
         (900002, "Top", P3, 4, 4)],
        schema={"game_pk": pl.Int64, "side": pl.Utf8,
                "pitcher": pl.Int64, "realized_bf": pl.Int64,
                "realized_k": pl.Int64}, orient="row")
    derived = pl.DataFrame(
        [(900001, "Top", P1, 6, 3), (900001, "Bot", P2, 2, 0)],
        schema=reg.schema, orient="row")
    rep = so.validate_against_registered(derived, reg)
    # only-in-registered keys are expected for a partial derived window:
    # the verdict explains rather than silently patches
    assert rep["verdict"] == "DISCREPANCIES_REQUIRE_EXPLANATION"
    assert rep["bf_mismatches"] == 0 and rep["k_mismatches"] == 0
    assert rep["keys_only_in_registered"] == 1
    derived2 = derived.with_columns(
        pl.when((pl.col("game_pk") == 900001) & (pl.col("side") == "Top"))
        .then(pl.lit(7)).otherwise(pl.col("realized_bf"))
        .alias("realized_bf"))
    rep2 = so.validate_against_registered(derived2, reg)
    assert rep2["bf_mismatches"] == 1
    assert rep2["examples_bf_mismatch"][0][3] == 7


# ------------------------------------------------------- v2 contract
def test_baseline_v2_contract_window_and_adapter():
    """The v2 contract lengthens ONLY the reference-estimation history:
    the adapter attaches the window block, reuses the v1 machinery
    unchanged, and records the v2 identity."""
    train = pl.DataFrame(
        [(9002001, date(2023, 5, 2), "Top", P1, 6, 22),
         (9002002, date(2024, 8, 15), "Bot", P2, 3, 19),
         (9002003, date(2023, 4, 12), "Top", P3, 8, 25)],
        schema={"game_pk": pl.Int64, "game_date": pl.Date,
                "side": pl.Utf8, "pitcher": pl.Int64,
                "realized_k": pl.Int64, "realized_bf": pl.Int64},
        orient="row")
    starts = pl.DataFrame(
        [(9003001, "Top", 700001), (9003002, "Bot", 999999)],
        schema={"game_pk": pl.Int64, "side": pl.Utf8,
                "pitcher": pl.Int64}, orient="row")
    bf = {(9003001, "Top", 700001): _bf(), (9003002, "Bot", 999999):
          _bf()}
    arms = so.build_arms_v2(train, starts, bf)
    assert arms["settings"]["contract"] == so.DERIVED_CONTRACT
    assert arms["settings"]["train_interval"] == ["2023-01-01",
                                                  "2024-12-31"]
    # cold-start fallback intact under v2
    pop = arms["settings"]["population_rate"]
    cold = arms["pitcher"][(9003002, "Bot", 999999)]
    ref = bl.pitcher_arm_pmf(pop, _bf())
    assert float(np.abs(cold - ref).max()) == pytest.approx(0.0, abs=1e-15)
    # v2 window guard: out-of-window rows refused
    with pytest.raises(so.DerivationError, match="v2 training window"):
        so.build_arms_v2(
            train.with_columns(pl.lit(date(2022, 9, 1))
                               .alias("game_date")),
            starts, bf)


def _bf():
    v = np.full(37, 0.0)
    v[:35] = 0.02
    v[35] = 0.20
    v[36] = 0.10
    return v


def test_baseline_contract_sha_stable():
    """The v2 contract identity is PINNED, not self-compared: any change
    to DERIVED_CONTRACT or the declared train interval changes this
    digest and requires an explicit superseding handoff."""
    assert so.contract_sha() == (
        "be39e14440ca3a9b150e87927f8ad29ad30f5273ce2ae4f9acc2cccac5523eeb")


# ------------------------------------------- architect-finding regressions
def test_baseline_missing_field_vs_null_field_distinct():
    """An absent column is a missing FIELD (schema gap); a null value in
    a present column is missing source coverage. Distinct failure
    classes, never conflated."""
    no_y = _pa_source().drop("y")
    with pytest.raises(so.DerivationError, match=r"missing field.*'y'"):
        so.derive_start_outcomes(no_y)
    null_y = _pa_source().with_columns(
        pl.when(pl.col("pitcher") == P1).then(None)
        .otherwise(pl.col("y")).alias("y"))
    with pytest.raises(so.DerivationError,
                       match="null values.*'y'.*missing source coverage"):
        so.derive_start_outcomes(null_y)


def test_baseline_derivation_retains_game_date():
    """Each derived start retains its game_date (required downstream by
    build_arms_v2 / add_block)."""
    s = _derive()["start_outcomes"]
    assert "game_date" in s.columns
    g1 = s.filter(pl.col("game_pk") == 900001)
    assert set(g1["game_date"].to_list()) == {date(2023, 5, 2)}
    g2 = s.filter(pl.col("game_pk") == 900002)
    assert set(g2["game_date"].to_list()) == {date(2024, 8, 15)}


def test_baseline_inconsistent_game_date_within_start_fails():
    """One corrupted game_date row inside a pitcher-game fails loud
    instead of silently picking a date for the start."""
    bad = _pa_source().with_columns(
        pl.when((pl.col("game_pk") == 900001) & (pl.col("pitcher") == P1)
                & (pl.col("at_bat_number") == 2))
        .then(pl.lit(date(2023, 5, 3))).otherwise(pl.col("game_date"))
        .alias("game_date"))
    with pytest.raises(so.DerivationError,
                       match="inconsistent game_date within start"):
        so.derive_start_outcomes(bad)


def test_baseline_pitcher_in_both_halves_fails():
    """Identity anomaly: a pitcher appearing in both halves of one game
    fails loud (a pitcher-game must map to exactly one side)."""
    extra = pl.DataFrame(
        [(900001, date(2023, 5, 2), P1, 0, "reliever_pa", "Bot", 50)],
        schema=_pa_source().schema, orient="row")
    with pytest.raises(so.DerivationError, match="identity anomaly"):
        so.derive_start_outcomes(pl.concat([_pa_source(), extra]))


def test_baseline_outcome_domain_violation_fails():
    """y must be 0/1: any other value fails loud as a domain violation."""
    bad = _pa_source().with_columns(
        pl.when((pl.col("game_pk") == 900002) & (pl.col("pitcher") == P3)
                & (pl.col("at_bat_number") == 2))
        .then(pl.lit(2)).otherwise(pl.col("y")).alias("y"))
    with pytest.raises(so.DerivationError,
                       match=r"domain violation in y"):
        so.derive_start_outcomes(bad)


def test_baseline_side_domain_violation_fails():
    """inning_topbot must be Top/Bot: anything else fails loud."""
    bad = _pa_source().with_columns(
        pl.when(pl.col("pitcher") == R1)
        .then(pl.lit("top")).otherwise(pl.col("inning_topbot"))
        .alias("inning_topbot"))
    with pytest.raises(so.DerivationError,
                       match=r"domain violation in inning_topbot"):
        so.derive_start_outcomes(bad)


def test_baseline_role_domain_violation_fails():
    """pitcher_role must be starter_pa/reliever_pa: unregistered roles
    fail loud as domain violations (distinct from the starter/reliever
    role-contract failure)."""
    bad = _pa_source().with_columns(
        pl.when(pl.col("pitcher") == R1)
        .then(pl.lit("opener_pa")).otherwise(pl.col("pitcher_role"))
        .alias("pitcher_role"))
    with pytest.raises(so.DerivationError,
                       match=r"domain violation in pitcher_role"):
        so.derive_start_outcomes(bad)


def test_baseline_overlap_validation_rejects_duplicate_keys():
    """Overlap validation asserts exactly one row per key on BOTH sides
    BEFORE any join: duplicate/conflicting keys fail loud, never
    silently deduplicated."""
    reg = pl.DataFrame(
        [(900001, "Top", P1, 6, 3), (900001, "Bot", P2, 2, 0)],
        schema={"game_pk": pl.Int64, "side": pl.Utf8,
                "pitcher": pl.Int64, "realized_bf": pl.Int64,
                "realized_k": pl.Int64}, orient="row")
    # conflicting derived rows for one key (6/3 vs 5/2)
    derived_bad = pl.DataFrame(
        [(900001, "Top", P1, 6, 3), (900001, "Top", P1, 5, 2),
         (900001, "Bot", P2, 2, 0)],
        schema=reg.schema, orient="row")
    with pytest.raises(so.DerivationError,
                       match=r"derived keys carry more than one row"):
        so.validate_against_registered(derived_bad, reg)
    # duplicate registered rows also fail loud
    reg_bad = pl.concat([reg, reg.head(1)])
    with pytest.raises(so.DerivationError,
                       match=r"registered keys carry more than one row"):
        so.validate_against_registered(
            derived_bad.filter(pl.col("pitcher") != P1), reg_bad)


# ------------------------------------------------- end-to-end integration
def test_baseline_integration_derive_to_arms_v2():
    """THE synthetic integration slice:
    derive_start_outcomes -> returned start_outcomes -> build_arms_v2
    -> valid keyed baseline PMFs. The derived output schema must be
    directly usable by the next stage with no manual reshaping."""
    derived = _derive()["start_outcomes"]
    keys = [(int(r[0]), str(r[1]), int(r[2]))
            for r in derived.select("game_pk", "side", "pitcher").rows()]
    bf_lookup = {k: _bf() for k in keys}
    arms = so.build_arms_v2(derived, derived, bf_lookup)
    # the derived artifact feeds the adapter directly: identical keyed
    # arms on the registered 24-bucket support
    assert set(arms["population"]) == set(arms["pitcher"]) == set(keys)
    assert arms["settings"]["contract"] == so.DERIVED_CONTRACT
    assert arms["settings"]["train_interval"] == ["2023-01-01",
                                                  "2024-12-31"]
    for pmf in arms["pitcher"].values():
        assert pmf.shape == (24,)
        assert pmf.sum() == pytest.approx(1.0, abs=1e-9)
        ad.check_pmf(pmf, "integration_pitcher_arm")
    for pmf in arms["population"].values():
        assert pmf.shape == (24,)
        assert pmf.sum() == pytest.approx(1.0, abs=1e-12)
        ad.check_pmf(pmf, "integration_population")
    # arm S uses each derived pitcher's realized K/BF from the SAME
    # artifact that fed it (no external reshaping)
    p1 = [r for r in derived.rows() if r[2] == P1 and r[1] == "Top"][0]
    assert (p1[3], p1[4], p1[5]) == (date(2023, 5, 2), 6, 3)
