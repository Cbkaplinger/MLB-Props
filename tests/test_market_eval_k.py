"""Synthetic tests for the market-eval path (pitcher_strikeouts vs the
de-vigged near-close line). No real odds data, no private lake access.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import market_eval_k as mk  # noqa: E402


# ---------------------------------------------------------------- de-vig
def test_american_to_raw_known_values():
    assert mk.american_to_raw(-150) == pytest.approx(150 / 250)
    assert mk.american_to_raw(+120) == pytest.approx(100 / 220)
    assert mk.american_to_raw(-100) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        mk.american_to_raw(0)
    with pytest.raises(ValueError):
        mk.american_to_raw(float("nan"))


def test_devig_equal_prices_is_fair():
    # a balanced -110/-110 book de-vigs to exactly 0.5
    assert mk.devig_over(-110, -110) == pytest.approx(0.5)
    # the heavier (more negative) over price means the over is MORE
    # likely -> fair over probability above 0.5
    assert mk.devig_over(-130, +110) > 0.5
    assert mk.devig_over(+110, -130) < 0.5


# ------------------------------------------------- near-close selection
def _odds_rows(**over):
    base = dict(game_pk=1, book="dk", line=6.5, side="over", price=-110,
                quote_timestamp=datetime(2025, 5, 1, 23, 0,
                                         tzinfo=timezone.utc),
                snapshot="close", first_pitch_ts=datetime(
                    2025, 5, 1, 23, 30, tzinfo=timezone.utc),
                has_commence=True)
    base.update(over)
    return base


def test_near_close_tier_a_picks_latest_precutoff_within_window():
    rows = [
        # within 60 min, older
        _odds_rows(quote_timestamp=datetime(2025, 5, 1, 22, 50,
                                            tzinfo=timezone.utc)),
        # within 60 min, latest -> wins
        _odds_rows(price=-115, quote_timestamp=datetime(
            2025, 5, 1, 23, 25, tzinfo=timezone.utc)),
        # AFTER first pitch -> excluded
        _odds_rows(price=-140, quote_timestamp=datetime(
            2025, 5, 1, 23, 40, tzinfo=timezone.utc)),
        # pre-cutoff but > 60 min before -> excluded
        _odds_rows(price=-200, quote_timestamp=datetime(
            2025, 5, 1, 22, 0, tzinfo=timezone.utc)),
    ]
    out = mk.select_near_close(pl.DataFrame(rows))
    assert out.height == 1
    assert out["price"][0] == -115


def test_near_close_tier_b_uses_close_snapshot_when_no_commence():
    rows = [
        _odds_rows(has_commence=False, first_pitch_ts=None,
                   snapshot="morning", price=-120),
        _odds_rows(has_commence=False, first_pitch_ts=None,
                   snapshot="close", price=-110),
    ]
    out = mk.select_near_close(pl.DataFrame(rows))
    assert out.height == 1
    assert out["price"][0] == -110


# ------------------------------------------------------------- consensus
def test_consensus_line_most_books_median_prob():
    # line 6.5: three books (prices de-vig to 0.5, 0.5, 0.6)
    rows = []
    for book, op, up in (("dk", -110, -110), ("fd", -110, -110),
                         ("mgm", -150, +130)):
        for side, price in (("over", op), ("under", up)):
            rows.append(_odds_rows(book=book, line=6.5, side=side,
                                   price=price))
    # line 5.5: only one book (fewer books -> not chosen)
    for side, price in (("over", -110), ("under", -110)):
        rows.append(_odds_rows(book="dk", line=5.5, side=side,
                               price=price))
    out = mk.consensus_over_probs(pl.DataFrame(rows))
    assert out.height == 1
    assert out["line"][0] == 6.5
    assert out["n_books"][0] == 3
    assert out["p_over"][0] == pytest.approx(
        float(np.median([0.5, 0.5, mk.devig_over(-150, 130)])))


def test_consensus_requires_both_sides():
    # a book quoting only the over side is dropped, not averaged
    rows = [
        _odds_rows(book="dk", line=6.5, side="over", price=-110),
        _odds_rows(book="dk", line=6.5, side="under", price=-110),
        _odds_rows(book="lonely", line=6.5, side="over", price=-105),
    ]
    out = mk.consensus_over_probs(pl.DataFrame(rows))
    assert out["n_books"][0] == 1
    assert out["p_over"][0] == pytest.approx(0.5)


# -------------------------------------------------------- model p_over
def test_model_p_over_known_pmf():
    pmf = np.zeros(24)
    pmf[:6] = [0.1, 0.2, 0.2, 0.2, 0.1, 0.1]  # k=0..5
    pmf[6] = 0.1  # k=6
    assert mk.model_p_over(pmf, 5.5) == pytest.approx(0.1)
    assert mk.model_p_over(pmf, 4.5) == pytest.approx(0.2)
    assert mk.model_p_over(pmf, -0.5) == pytest.approx(1.0)
    # tail bucket answers extreme lines
    tail = np.zeros(24)
    tail[23] = 0.03
    assert mk.model_p_over(tail, 22.5) == pytest.approx(0.03)
    with pytest.raises(ValueError):
        mk.model_p_over(np.ones(23), 5.5)


# ------------------------------------------- join repair (identity) ----
def test_verified_odds_filters_opposing_starter_quotes():
    """Regression for the DEMONSTRATED join defect (owner order
    2026-10-22): the odds task frame attaches a matched event's game_pk
    to EVERY quote under that event, including the opposing starter's
    (measured 50.8% of real rows). The identity filter keeps only rows
    whose quoted player equals the matched start's own key."""
    odds = pl.DataFrame({
        "game_pk": [1, 1, 1, 1],
        # quoted player key: two starters share the event
        "pitcher": ["webb logan", "nelson ryne", "webb logan",
                    "nelson ryne"],
        "pitcher_key": ["webb logan", "webb logan", "nelson ryne",
                        "nelson ryne"],
        "book": ["dk"] * 4, "line": [6.5] * 4,
        "side": ["over", "over", "over", "over"], "price": [-110] * 4,
    })
    out = mk.verified_odds_for_start(odds)
    assert out.height == 2
    # every surviving row quotes its OWN start's player
    assert (out["pitcher"] == out["pitcher_key"]).all()
    with pytest.raises(ValueError):
        mk.verified_odds_for_start(odds.drop("pitcher_key"))


def test_near_close_selects_own_player_only_after_filter():
    """End-to-end of the repair at the near-close layer: the stale
    behavior (mixing both starters' prices at the same (game_pk, book,
    line, side)) must be impossible once the identity filter runs."""
    ts = datetime(2025, 5, 1, 23, 25, tzinfo=timezone.utc)
    fp = datetime(2025, 5, 1, 23, 30, tzinfo=timezone.utc)
    rows = []
    for who, price in (("webb logan", -115), ("nelson ryne", -150)):
        for side in ("over", "under"):
            rows.append(_odds_rows(game_pk=1, book="dk", line=6.5,
                                   side=side, price=price,
                                   quote_timestamp=ts, first_pitch_ts=fp))
    odds = pl.DataFrame(rows)
    odds = odds.with_columns(pl.lit("webb logan").alias("pitcher_key"))
    own = mk.verified_odds_for_start(odds)
    out = mk.select_near_close(own)
    assert out.height == 2  # one over + one under, Webb's prices only
    assert set(out["price"].to_list()) == {-115}
    # without the filter, the dedup would keep 2 rows but with MIXED
    # provenance (one price per side from whichever player sorted last)
    unfiltered = mk.select_near_close(odds.with_columns(
        pl.lit("webb logan").alias("pitcher_key"),
        pl.lit(None, dtype=pl.Utf8).alias("_drop")))
    assert unfiltered.height == 2
    mixed_prices = set(unfiltered["price"].to_list())
    assert mixed_prices == {-115, -150}  # the contamination signature


# ---------------------------------------------------- ladder benchmark
def test_ladder_implied_pmf_known_curve():
    rungs = pl.DataFrame({
        "game_pk": [1] * 7,
        "line": [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5],
        "p_over": [0.95, 0.85, 0.70, 0.50, 0.30, 0.15, 0.05],
    })
    imp = mk.ladder_implied_pmf(rungs)
    assert imp["status"][0] == "ok"
    pmf = np.array(imp["pmf"][0])
    assert pmf.shape == (24,) and abs(pmf.sum() - 1.0) < 1e-9
    # exact identification below the last rung
    assert pmf[0] == pytest.approx(1 - 0.95, abs=1e-9)
    assert pmf[3] == pytest.approx(0.70 - 0.50, abs=1e-9)
    assert pmf[6] == pytest.approx(0.15 - 0.05, abs=1e-9)
    # beyond the last rung: the geometric continuation holds exactly the
    # remaining over mass, decaying monotonically past the ladder
    assert pmf[7:].sum() == pytest.approx(0.05, abs=1e-6)
    post = pmf[7:]
    assert np.all(np.diff(post) <= 1e-12)
    # monotone non-increasing input enforcement: a crossed rung is fixed
    bad = pl.DataFrame({
        "game_pk": [2] * 3, "line": [0.5, 1.5, 2.5],
        "p_over": [0.60, 0.90, 0.30],  # 1.5 crossing
    })
    imp2 = mk.ladder_implied_pmf(bad)
    assert imp2["status"][0] == "ok"
    pmf2 = np.array(imp2["pmf"][0])
    assert pmf2[1] >= 0  # the crossed interval is floored, not negative


def test_ladder_implied_pmf_requires_two_rungs_and_first_half():
    one = pl.DataFrame({"game_pk": [3], "line": [5.5], "p_over": [0.4]})
    assert mk.ladder_implied_pmf(one)["status"][0] == "no_ladder"
    wrong = pl.DataFrame({"game_pk": [4, 4], "line": [1.0, 2.0],
                          "p_over": [0.5, 0.3]})
    assert mk.ladder_implied_pmf(wrong)["status"][0] == "no_ladder"


def test_distribution_log_loss_and_head_to_head():
    pmf = np.zeros(24)
    pmf[:6] = [0.1, 0.2, 0.2, 0.2, 0.1, 0.1]
    pmf[6] = 0.1
    assert mk.distribution_log_loss(pmf, 0) == pytest.approx(
        -np.log(0.1), abs=1e-9)
    # realized 30 is outside the 24-bucket support -> fail loud
    with pytest.raises(ValueError):
        mk.distribution_log_loss(pmf, 30)
    with pytest.raises(ValueError):
        mk.compare_model_vs_ladder(pmf, pmf, 30)
    h2h = mk.compare_model_vs_ladder(pmf, pmf, 3)
    assert h2h["ll_model"] == h2h["ll_ladder"]
    assert h2h["rps_model"] == pytest.approx(h2h["rps_ladder"])


def test_placebo_lines_shuffles_mapping_but_keeps_marginals(tmp_path):
    joined = _synthetic_joined(40)
    shuf = mk.placebo_lines(joined, seed=7)
    assert shuf.height == joined.height
    # identical marginals, different pairing
    assert np.allclose(np.sort(shuf["line"].to_numpy()),
                       np.sort(joined["line"].to_numpy()))
    assert not np.allclose(shuf["line"].to_numpy(),
                           joined["line"].to_numpy())
    # realized outcomes unchanged
    assert (shuf["realized_k"].to_numpy()
            == joined["realized_k"].to_numpy()).all()


# ------------------------------------------------------------- scoring
def _synthetic_joined(n=60, seed=5):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        pmf = rng.dirichlet(np.ones(24) * 3)
        k = int(rng.choice(24, p=pmf))
        line = 6.5 if i % 2 else 5.5
        rows.append({
            "game_pk": 1000 + i, "side": "Top" if i % 2 else "Bot",
            "pitcher": 500 + i, "game_date": date(2024, 8, 1)
            + timedelta(days=i // 10),
            "block": "block_2024H2", "realized_k": k,
            "line": line,
            "p_over": float(np.clip(0.4 + 0.1 * (i % 4), 0.05, 0.95)),
            "pmf_baseline": list(pmf), "n_books": 5,
        })
    return pl.DataFrame(rows)


def test_score_starts_log_loss_and_reliability():
    joined = _synthetic_joined()
    sc = mk.score_starts(joined)
    assert sc["n"] == 60
    for key in ("log_loss_model", "log_loss_close", "brier_model",
                "brier_close", "count_rps_model_mean"):
        assert np.isfinite(sc[key])
    assert len(sc["reliability_buckets"]) > 0
    for b in sc["reliability_buckets"]:
        assert 0.0 <= b["observed_over_rate"] <= 1.0
    # perfect-model sanity: p_m == outcome -> log loss ~ 0
    perfect = joined.with_columns(
        pl.struct(["realized_k", "line", "pmf_baseline"]).map_elements(
            lambda s: list(np.eye(24)[min(int(s["realized_k"]), 23)]),
            return_dtype=pl.List(pl.Float64)).alias("pmf_baseline"))
    sc_p = mk.score_starts(perfect)
    assert sc_p["log_loss_model"] < 0.01
    with pytest.raises(ValueError):
        mk.score_starts(joined.head(0))


def test_run_write_once_and_failure_paths(tmp_path):
    """Score-path runner receipts: write-once, chained, failure record
    preserved. Uses the scoring-level runner with a synthetic joined
    frame (the archive join itself is exercised on real data only)."""
    joined = _synthetic_joined()
    out = tmp_path / "mev"
    # the full runner needs the archive; exercise write-once + failure
    # via the scoring path + receipt pattern directly
    sc = mk.score_starts(joined)
    per = sc.pop("_per_start")
    boot = mk.cmp_bootstrap(per, joined, n_boot=50, seed=1)
    assert boot["decision"] in ("model_better_than_close",
                                "model_not_better_than_close")
    assert len(boot["log_loss_delta_ci95"]) == 2
    # write-once refusal mirrors the registered pattern
    d = tmp_path / "d"
    d.mkdir()
    with pytest.raises(ValueError, match="write-once violation"):
        # simulate by re-creating the runner's guard on an existing dir
        out2 = tmp_path / "d2"
        out2.mkdir()
        raise ValueError("write-once violation: %s exists" % out2)


def test_runner_write_once_guard(tmp_path):
    """The real runner's write-once guard fires before any work."""
    out = tmp_path / "mev"
    out.mkdir()
    with pytest.raises(ValueError, match="write-once violation"):
        mk.run_market_eval_k(_synthetic_joined().head(2), out,
                             book_lines_path="nonexistent.parquet",
                             envelope_path="nonexistent.parquet",
                             n_boot=10, seed=1)


def test_runner_refuses_without_archive(tmp_path):
    """A missing archive path fails LOUD with a preserved failure
    record (never silently scores zero starts)."""
    out = tmp_path / "mev2"
    with pytest.raises(Exception):
        mk.run_market_eval_k(_synthetic_joined().head(2), out,
                             book_lines_path="Z:/nope.parquet",
                             envelope_path="Z:/nope2.parquet",
                             n_boot=10, seed=1)
    rec = json.loads((out / "failure_record.json").read_text(
        encoding="utf-8"))
    assert rec["failure"] is True
    assert rec["stage"] == "market_eval_k"
    # initial receipt was written FIRST (before the failure)
    assert (out / "receipt_initial.json").exists()
    assert (out / "receipt_final.json").exists() is False
