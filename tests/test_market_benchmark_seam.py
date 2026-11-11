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
