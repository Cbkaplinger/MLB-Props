"""Synthetic tests for the market-benchmark seam
(market_benchmark_seam.py). SYNTHETIC ONLY: no private-lake imports
(join_coverage is never imported), no real odds/PMF/assessment/cohort
reads, no live-path change.

Requirement -> implementation -> test-evidence closure table:
  Book two-sided de-vig probabilities (hand values); one-sided
  ladders never produce book probabilities                  -> test 1
  LTBO consensus excludes the target book (exact hand
  medians; >= 2 other books; unavailable recorded, never
  filled from other lines)                                  -> test 2
  All-book consensus delegates to the registered
  construction unchanged                                    -> test 3
  Harness model frame: keyed PMFs + observed K + declared
  cohort + declared dates -> the registered market-eval
  model contract (block via the registered add_block rule)  -> test 4
  Cohort identity gates: wrong hash, forecast != cohort,
  restricted observations not covering the cohort           -> test 5
  Date-contract gates: missing declared date, duplicate,
  protected/unknown block                                   -> test 6
"""
from __future__ import annotations

import sys
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"))
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"
                       / "pregame_pa_ext"))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import binary_k_comparison as bk  # noqa: E402
from pregame_pa_ext import market_eval_k as mk  # noqa: E402
from pregame_pa_ext import market_benchmark_seam as ms  # noqa: E402

START_A = (900201, "Top", 700001)
START_B = (900201, "Bot", 700002)
STARTS = [START_A, START_B]
D_REQ = date(2025, 4, 10)


def _pmf_control() -> np.ndarray:
    pmf = np.zeros(ad.K_MAX)
    pmf[2] = 0.5
    pmf[3] = 0.5
    return pmf


def _pmf_challenger() -> np.ndarray:
    pmf = np.zeros(ad.K_MAX)
    pmf[5] = 0.25
    pmf[ad.K_MAX - 1] = 0.75
    return pmf


def _k_pmf_frame(arm_col="pmf_control") -> pl.DataFrame:
    rows = []
    for gk, side, p in STARTS:
        for b in range(ad.K_MAX):
            rows.append((gk, side, p, b, float(_pmf_control()[b]),
                         float(_pmf_challenger()[b])))
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "bucket": pl.Int64, "pmf_control": pl.Float64,
        "pmf_challenger": pl.Float64}, orient="row")


def _cohort_frame() -> pl.DataFrame:
    return pl.DataFrame(STARTS, schema={
        "game_pk": pl.Int64, "side": pl.Utf8,
        "pitcher": pl.Int64}, orient="row")


def _dates_frame() -> pl.DataFrame:
    return pl.DataFrame(
        [(gk, side, p, D_REQ) for gk, side, p in STARTS], schema={
            "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
            "game_date": pl.Date}, orient="row")


def _observed_frame(ks=(3, 30)) -> pl.DataFrame:
    rows = [(gk, side, p, k) for (gk, side, p), k in zip(STARTS, ks)]
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "realized_k": pl.Int64}, orient="row")


def _near_close(books=("B1", "B2", "B3"), lines=(4.5,),
                prices=None):
    """Two-sided near-close quotes: per (start, book, line) an over
    and an under price. Default prices give p_over_book = 0.5 for
    every book (-110/-110)."""
    prices = prices or {}
    rows = []
    for gi, (gk, side, p) in enumerate([START_A, START_B]):
        for book in books:
            for line in lines:
                o, u = prices.get((gi, book, line), (-110, -110))
                rows.append((gk, p, book, line, "over", o))
                rows.append((gk, p, book, line, "under", u))
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "pitcher": pl.Int64, "book": pl.Utf8,
        "line": pl.Float64, "side": pl.Utf8, "price": pl.Int64},
        orient="row")


# ------------------- 1. book probabilities: hand de-vig, one-sided
def test_book_probabilities_hand_devig():
    prices = {(0, "B1", 4.5): (-150, 130),   # raw o 0.6, u 100/230
              (1, "B2", 4.5): (-200, 150)}   # raw o 2/3, u 0.4
    nc = _near_close(books=("B1", "B2", "B3"), prices=prices)
    probs = ms.book_over_probabilities(nc)
    got = {(r["pitcher"], r["book"]): r["p_over_book"]
           for r in probs.iter_rows(named=True)}
    hand_b1 = mk.devig_over(-150, 130)
    assert hand_b1 == pytest.approx(
        0.6 / (0.6 + 100.0 / 230.0))
    assert got[(700001, "B1")] == pytest.approx(hand_b1)
    hand_b2 = (200.0 / 300.0) / ((200.0 / 300.0) + 0.4)
    assert got[(700002, "B2")] == pytest.approx(hand_b2)
    assert got[(700001, "B3")] == pytest.approx(0.5)
    assert got[(700002, "B3")] == pytest.approx(0.5)
    # a one-sided ladder never produces a book probability
    one_sided = _near_close(books=("B1",)).filter(
        pl.col("side") == "over")
    with pytest.raises(ValueError, match="over/under bet sides"):
        ms.book_over_probabilities(one_sided)


# ------------------- 2. LTBO consensus excludes the target book
def test_ltbo_excludes_target_book():
    nc = _near_close(books=("B1", "B2", "B3"))
    probs = ms.book_over_probabilities(nc)
    ltbo, n_unavailable = ms.ltbo_consensus(probs)
    assert n_unavailable == 0
    assert ltbo.height == 6  # 2 starts x 3 books
    for r in ltbo.iter_rows(named=True):
        assert r["n_other_books"] == 2
        assert r["p_over_book"] == pytest.approx(0.5)
        assert r["p_over_ltbo"] == pytest.approx(0.5)  # median of 2
    # asymmetric books at START_A only: B1 de-vigs to 0.5798,
    # B2/B3 stay 0.5; the LTBO median for every book excludes itself
    prices = {(0, "B1", 4.5): (-150, 130)}
    nc = _near_close(books=("B1", "B2", "B3"), prices=prices)
    probs = ms.book_over_probabilities(nc)
    ltbo, _ = ms.ltbo_consensus(probs)
    rows = {r["book"]: r for r in ltbo.iter_rows(named=True)
            if r["pitcher"] == 700001}
    assert rows["B1"]["p_over_book"] == pytest.approx(
        mk.devig_over(-150, 130))
    assert rows["B1"]["p_over_ltbo"] == pytest.approx(0.5)
    assert rows["B2"]["p_over_ltbo"] == pytest.approx(
        (mk.devig_over(-150, 130) + 0.5) / 2)
    assert rows["B3"]["p_over_ltbo"] == pytest.approx(
        (mk.devig_over(-150, 130) + 0.5) / 2)


def test_ltbo_unavailable_recorded_never_filled():
    nc = _near_close(books=("B1", "B2"))  # only one OTHER book
    probs = ms.book_over_probabilities(nc)
    ltbo, n_unavailable = ms.ltbo_consensus(probs)
    assert n_unavailable == 4  # 2 starts x 2 books
    assert ltbo.height == 0


# ------------------- 3. all-book consensus reuses the registered
def test_all_book_consensus_delegates():
    nc = _near_close(books=("B1", "B2", "B3"))
    out = ms.all_book_consensus(nc).sort(["game_pk", "pitcher"])
    expected = mk.consensus_over_probs(nc).sort(["game_pk", "pitcher"])
    assert out.equals(expected)
    assert out.height == 2  # one consensus per start
    assert set(out.columns) >= {"game_pk", "pitcher", "line",
                                "p_over", "n_books"}


# ------------------- 4. harness -> registered model frame
def test_harness_model_frame():
    observed = _observed_frame()
    out = ms.harness_model_frame(
        _k_pmf_frame(), observed, _dates_frame(), _cohort_frame(),
        bk._cohort_hash(list(STARTS)), arm="pmf_control")
    assert out.height == 2
    assert list(out.columns) == ["game_pk", "side", "pitcher",
                                 "game_date", "block", "realized_k",
                                 "pmf_baseline"]
    assert set(out["block"].to_list()) == {"block_2025H1"}
    for r in out.iter_rows(named=True):
        assert r["pmf_baseline"] == pytest.approx(
            _pmf_control().tolist())
    exp_ks = dict(zip(STARTS, (3, 30)))
    assert out["realized_k"].to_list() == [
        exp_ks[s] for s in sorted(STARTS)]
    # the output plugs straight into the registered runner's contract
    assert all(isinstance(v, list) and len(v) == ad.K_MAX
               for v in out["pmf_baseline"].to_list())


# ------------------- 5. cohort identity gates
def test_cohort_gates():
    with pytest.raises(ValueError, match="cohort identity mismatch"):
        ms.harness_model_frame(
            _k_pmf_frame(), _observed_frame(), _dates_frame(),
            _cohort_frame(), "0" * 64, arm="pmf_control")
    # forecast has an extra start outside the cohort
    extra_rows = []
    for b in range(ad.K_MAX):
        extra_rows.append((900301, "Top", 700003, b,
                           float(_pmf_control()[b]),
                           float(_pmf_challenger()[b])))
    bad = pl.concat([_k_pmf_frame(), pl.DataFrame(extra_rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "bucket": pl.Int64, "pmf_control": pl.Float64,
        "pmf_challenger": pl.Float64}, orient="row")])
    with pytest.raises(ValueError,
                       match="forecast/declared-cohort key mismatch"):
        ms.harness_model_frame(
            bad, _observed_frame(), _dates_frame(), _cohort_frame(),
            bk._cohort_hash(list(STARTS)), arm="pmf_control")


# ------------------- 6. date-contract gates
def test_date_contract_gates():
    # a declared cohort start missing its date refuses (no invention)
    partial_dates = _dates_frame().head(1)
    with pytest.raises(ValueError, match="dates do not cover"):
        ms.harness_model_frame(
            _k_pmf_frame(), _observed_frame(), partial_dates,
            _cohort_frame(), bk._cohort_hash(list(STARTS)),
            arm="pmf_control")
    # duplicate date rows refuse
    dup_dates = pl.concat([_dates_frame(), _dates_frame().head(1)])
    with pytest.raises(ValueError, match="duplicate identity"):
        ms.harness_model_frame(
            _k_pmf_frame(), _observed_frame(), dup_dates,
            _cohort_frame(),
            bk._cohort_hash(list(STARTS)), arm="pmf_control")
    # a date mapping into the protected partition refuses
    late = _dates_frame().with_columns(
        pl.when(pl.col("pitcher") == 700001)
        .then(pl.date(2025, 7, 5)).otherwise(pl.col("game_date"))
        .alias("game_date"))
    with pytest.raises(ValueError, match="protected/unknown block"):
        ms.harness_model_frame(
            _k_pmf_frame(), _observed_frame(), late, _cohort_frame(),
            bk._cohort_hash(list(STARTS)), arm="pmf_control")


# ------------------- 8. end-to-end benchmark contract assembly


def _quotes_frame(books=("B1", "B2", "B3"),
                  include_start_b_b2=False,
                  include_after_first_pitch=False):
    """Two-sided near-close quotes with VENDOR pitcher keys (the
    reduced market key). Decision timestamp = each start's
    first_pitch_ts; quotes are stamped at T-30min (inside the
    registered 60-minute tier-A window). An optional after-first-pitch
    quote exercises the tier-A exclusion."""
    import datetime as dt
    fp = dt.datetime(2025, 5, 1, 19, 0, tzinfo=dt.timezone.utc)
    t_in = fp - dt.timedelta(minutes=30)
    t_after = fp + dt.timedelta(minutes=5)
    key_of = {700001: "P700001", 700002: "P700002"}
    rows = []
    for gk, side, p in STARTS:
        for book in books:
            if book == "B2" and p == 700002 and not include_start_b_b2:
                continue
            o, u = (-150, 130) if (book == "B1" and p == 700001) \
                else (-110, -110)
            for bet, price in (("over", o), ("under", u)):
                rows.append((gk, key_of[p], book, 4.5, bet, price,
                             t_in, "live", fp, True))
        if include_after_first_pitch and p == 700001:
            rows.append((gk, key_of[p], "B1", 4.5, "over", -110,
                         t_after, "live", fp, True))
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "pitcher": pl.Utf8, "book": pl.Utf8,
        "line": pl.Float64, "side": pl.Utf8, "price": pl.Int64,
        "quote_timestamp": pl.Datetime("us", "UTC"),
        "snapshot": pl.Utf8, "first_pitch_ts": pl.Datetime("us", "UTC"),
        "has_commence": pl.Boolean}, orient="row")


def _bridge_frame() -> pl.DataFrame:
    import datetime as dt
    fp = dt.datetime(2025, 5, 1, 19, 0, tzinfo=dt.timezone.utc)
    return pl.DataFrame(
        [(900201, "P700001", 700001, fp, True),
         (900201, "P700002", 700002, fp, True)],
        schema={"game_pk": pl.Int64, "pitcher_key": pl.Utf8,
                "pitcher": pl.Int64,
                "first_pitch_ts": pl.Datetime("us", "UTC"),
                "has_commence": pl.Boolean}, orient="row")


# ------------------- 8. end-to-end benchmark contract assembly
def test_end_to_end_benchmark_contract():
    """Hand-computed end-to-end case: 2-start declared cohort,
    3 books (B1 de-vigs to 0.5798 at start A, B2/B3 to 0.5), start B
    missing B2 (LTBO unavailable there), one after-first-pitch quote
    (excluded by the tier-A decision timestamp)."""
    observed = _observed_frame()
    quotes = _quotes_frame(include_after_first_pitch=True)
    out = ms.benchmark_contract_rows(
        _k_pmf_frame(), observed, _dates_frame(), _cohort_frame(),
        bk._cohort_hash(list(STARTS)), "pmf_control", quotes,
        _bridge_frame())

    # ---- observable coverage accounting (exact)
    cov = out["coverage"]
    assert cov["cohort"] == {"n_keys": 2,
                             "content_hash": bk._cohort_hash(list(STARTS)),
                             "match": True}
    assert cov["n_forecast_starts"] == 2
    assert cov["observed_only_outside_cohort"]["n"] == 0
    assert cov["n_matched_model_starts"] == 2
    assert cov["consensus_starts_total"] == 2
    assert cov["n_consensus_unmatched_to_model"] == 0
    assert cov["ltbo_unavailable_rows"] == 2  # start B: B1/B3 rows
    assert cov["book_rows"] == 5  # A: B1+B2+B3; B: B1+B3 (B2 absent)
    assert cov["quotes_funnel"]["quotes_total"] == 11
    # the game_pk timing join fans out per (game_pk, pitcher_key); the
    # own-player filter then drops the opposing-starter duplicates
    assert cov["quotes_funnel"]["quotes_attached_to_starts"] == 22
    assert cov["quotes_funnel"]["quotes_other_player_dropped"] == 11
    assert cov["quotes_funnel"][
        "quotes_near_close_selected"] == 10
    assert "first_pitch_ts" in cov["quotes_funnel"]["decision_timestamp"]

    # ---- model-vs-consensus: existing scorer on identical rows
    sc = out["model_vs_consensus"]
    assert sc["n"] == 2
    # control PMF mass at K=2/3 only -> p_over_4.5 = 0.0 both starts;
    # realized over: A (K=3) -> 0 (ll 0), B (K=30 overflow) -> 1
    # (ll = -ln(1e-12)); mean = 13.8155...
    assert sc["log_loss_model"] == pytest.approx(
        (0.0 + -math.log(1e-12)) / 2)
    assert sc["log_loss_close"] == pytest.approx(-math.log(0.5))
    assert sc["brier_model"] == pytest.approx(0.5)
    assert sc["brier_close"] == pytest.approx(0.25)
    assert sc["count_rps_model_mean"] == pytest.approx(
        (0.25 + 20.25) / 2)
    assert "log_loss_delta_p" in sc["slate_date_bootstrap"]

    # ---- book-vs-LTBO: target-book exclusion + exact hand values.
    # LTBO rows exist only at start A (start B's B1/B3 rows are
    # single-other -> unavailable); every book scores n_starts = 1.
    bs = out["book_scores"]
    assert set(bs) == {"B1", "B2", "B3"}
    assert bs["B1"]["n_starts"] == 1
    assert bs["B2"]["n_starts"] == 1
    assert bs["B3"]["n_starts"] == 1
    # B1 at start A: p_book = devig(-150, 130) = 0.5798, realized under
    # (K=3) -> ll_a = -ln(1 - 0.5798); LTBO = median(B2, B3) = 0.5,
    # realized under -> ll_b = -ln(0.5)
    assert bs["B1"]["log_loss_a"] == pytest.approx(
        -math.log(1 - mk.devig_over(-150, 130)))
    assert bs["B1"]["log_loss_b"] == pytest.approx(-math.log(0.5))
    assert bs["B1"]["brier_a"] == pytest.approx(
        (mk.devig_over(-150, 130)) ** 2)
    assert bs["B1"]["brier_b"] == pytest.approx(0.25)
    # B3 at start A: p_book = 0.5 vs its LTBO = median(B1, B2) =
    # (0.5798 + 0.5) / 2; realized under (K=3, single row) ->
    # ll_a = -ln(1 - 0.5), ll_b = -ln(1 - 0.5399)
    assert bs["B3"]["log_loss_a"] == pytest.approx(
        -math.log(1 - 0.5 + 1e-12))
    assert bs["B3"]["log_loss_b"] == pytest.approx(
        -math.log(1 - (mk.devig_over(-150, 130) + 0.5) / 2 + 1e-12))


def test_decision_timestamp_and_selector_precondition():
    import datetime as dt
    fp = dt.datetime(2025, 5, 1, 19, 0, tzinfo=dt.timezone.utc)
    bridge = _bridge_frame()
    # quotes AFTER first pitch are excluded by the tier-A rule
    out = ms.benchmark_contract_rows(
        _k_pmf_frame(), _observed_frame(), _dates_frame(),
        _cohort_frame(), bk._cohort_hash(list(STARTS)), "pmf_control",
        _quotes_frame(include_after_first_pitch=True),
        bridge)
    assert out["coverage"]["quotes_funnel"][
        "quotes_near_close_selected"] == 10
    # the after-first-pitch quote (start A, B1, over) is excluded: the
    # tier-A decision timestamp keeps only pre-first-pitch quotes
    assert out["coverage"]["quotes_funnel"][
        "quotes_attached_to_starts"] == 22
    assert out["coverage"]["quotes_funnel"][
        "quotes_other_player_dropped"] == 11
    assert out["coverage"]["quotes_funnel"][
        "quotes_total"] == 11
    # every selected quote is at or before the decision timestamp
    # duplicate quote-side rows refuse at the seam boundary (the
    # registered selector would silently keep the last via pivot)
    dup = pl.concat([_quotes_frame(), _quotes_frame().head(1)])
    with pytest.raises(ValueError, match="duplicate identity"):
        ms.validate_selected_quotes(dup)


def test_ambiguous_identity_mapping_refused():
    import datetime as dt
    fp = dt.datetime(2025, 5, 1, 19, 0, tzinfo=dt.timezone.utc)
    bad_bridge = pl.DataFrame(
        [(900201, "P700001", 700001, fp, True),
         (900201, "P700001", 700099, fp, True)],
        schema={"game_pk": pl.Int64, "pitcher_key": pl.Utf8,
                "pitcher": pl.Int64,
                "first_pitch_ts": pl.Datetime("us", "UTC"),
                "has_commence": pl.Boolean}, orient="row")
    with pytest.raises(ValueError, match="ambiguous market/start"):
        ms.benchmark_contract_rows(
            _k_pmf_frame(), _observed_frame(), _dates_frame(),
            _cohort_frame(), bk._cohort_hash(list(STARTS)),
            "pmf_control", _quotes_frame(), bad_bridge)
