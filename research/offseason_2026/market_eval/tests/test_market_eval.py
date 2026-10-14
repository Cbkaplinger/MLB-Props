"""Tests for market-eval-v1 prep (market_eval.py).

Synthetic fixtures only: line types, push handling, de-vig math,
dedup/priority rule, timestamp pairing, exclusion rules, write-once guard.
No real archive reads.
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import market_eval as me  # noqa: E402

PMF_H3_COLS = ["pmf_h3_raw_%d" % i for i in range(me.PMF_SUPPORT)]
PMF_L5_COLS = ["pmf_l5_raw_%d" % i for i in range(me.PMF_SUPPORT)]


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------


def test_to_decimal():
    assert me.to_decimal(-110) == pytest.approx(1.9090909090909092)
    assert me.to_decimal(120) == pytest.approx(2.2)
    assert me.to_decimal(100) == pytest.approx(2.0)
    assert me.to_decimal(-100) == pytest.approx(2.0)


def test_to_decimal_validity_bounds():
    with pytest.raises(ValueError):
        me.to_decimal(0)
    with pytest.raises(ValueError):
        me.to_decimal(-(me.VALID_PRICE_ABS_MAX + 1))


def test_pmf_contract_probs_half_line():
    pmf = {3: 0.2, 4: 0.3, 5: 0.1, 6: 0.4}
    p_over, p_under, p_push = me.pmf_contract_probs(pmf, 5.5)
    assert p_over == pytest.approx(0.4)   # P(K >= 6)
    assert p_under == pytest.approx(0.6)  # P(K <= 5)
    assert p_push == 0.0
    assert p_over + p_under + p_push == pytest.approx(1.0)


def test_pmf_contract_probs_integer_line_push():
    pmf = {3: 0.2, 4: 0.3, 5: 0.1, 6: 0.4}
    p_over, p_under, p_push = me.pmf_contract_probs(pmf, 5)
    assert p_push == pytest.approx(0.1)   # P(K = 5)
    assert p_over == pytest.approx(0.4)   # P(K >= 6)
    assert p_under == pytest.approx(0.5)  # P(K <= 4)
    assert p_over + p_under + p_push == pytest.approx(1.0)


def test_pmf_contract_probs_degenerate():
    pmf = {3: 1.0}
    assert me.pmf_contract_probs(pmf, 3.5) == (0.0, 1.0, 0.0)
    assert me.pmf_contract_probs(pmf, 3) == (0.0, 0.0, 1.0)
    assert me.pmf_contract_probs(pmf, 2.5) == (1.0, 0.0, 0.0)


def test_pmf_contract_probs_support_truncation():
    pmf = {23: 1.0}
    p_over, p_under, p_push = me.pmf_contract_probs(pmf, 22.5)
    assert (p_over, p_under, p_push) == (1.0, 0.0, 0.0)
    p_over, p_under, p_push = me.pmf_contract_probs(pmf, 23.5)
    assert (p_over, p_under, p_push) == (0.0, 1.0, 0.0)


def test_pmf_contract_probs_zero_line_integer():
    pmf = {0: 1.0}
    p_over, p_under, p_push = me.pmf_contract_probs(pmf, 0)
    assert (p_over, p_under, p_push) == (0.0, 0.0, 1.0)


def test_build_prob_table_zero_integer_line_push():
    """C3 regression: build_prob_table dropped the push mass at integer line
    0.0 (push and under were forced to 0.0); registered
    pmf_contract_probs semantics are push = P(K = L) for any integer line,
    including L = 0."""
    payload = _payload_frame([
        {"game_pk": 1, "pitcher": 1, "game_date": date(2025, 5, 1),
         "pmf_h3": {0: 0.3, 1: 0.7}, "pmf_l5": {0: 1.0}},
    ])
    probs = me.build_prob_table(payload, [0.0, 0.5])
    row0 = probs.filter(pl.col("line") == 0.0).row(0, named=True)
    assert row0["p_h3_push"] == pytest.approx(0.3)   # P(K = 0); was 0.0
    assert row0["p_h3_over"] == pytest.approx(0.7)
    assert row0["p_h3_under"] == pytest.approx(0.0)
    assert (row0["p_h3_push"] + row0["p_h3_over"]
            + row0["p_h3_under"]) == pytest.approx(1.0)
    # identical to the registered pure-helper semantics
    assert row0["p_h3_push"] == me.pmf_contract_probs({0: 0.3, 1: 0.7}, 0.0)[2]
    assert row0["p_l5_push"] == pytest.approx(1.0)   # degenerate at K = 0
    # half line is unchanged by the fix
    row05 = probs.filter(pl.col("line") == 0.5).row(0, named=True)
    assert row05["p_h3_push"] == 0.0
    assert row05["p_h3_over"] == pytest.approx(0.7)
    assert row05["p_h3_under"] == pytest.approx(0.3)


def test_paper_bet_ev_uses_p_h3_lose_not_one_minus_win():
    """C3 regression: paper-bet EV used (1 - p_h3_win) as the lose
    probability, wrongly charging the PUSH mass against EV. With refund
    semantics EV = p_win*(d-1) - p_h3_lose; at integer line 0.0 with
    push = P(K = 0) = 0.3 and under = 0.0, the over EV must be
    0.7*(2.0 - 1) - 0.0 = 0.7 (the old code returned 0.4)."""
    payload = _payload_frame([
        {"game_pk": 1, "pitcher": 1, "game_date": date(2025, 5, 1),
         "pmf_h3": {0: 0.3, 1: 0.7}, "pmf_l5": {0: 1.0}},
    ])
    probs = me.build_prob_table(payload, [0.0])
    eval_pairs = pl.DataFrame({
        "game_pk": [1], "pitcher": [1], "pitcher_key": ["a alice"],
        "game_date": [date(2025, 5, 1)], "block": ["b"], "tier": [me.TIER_A],
        "first_pitch_ts": [ts("2025-05-01T23:00:00Z")], "line": [0.0],
        "event_id": ["e1"], "book": ["draftkings"],
        "pair_ts": [ts("2025-05-01T18:00:00Z")],
        "price_over": [-100], "price_under": [100],
        "d_over": [2.0], "d_under": [2.0],
    })
    closing_empty = pl.DataFrame(schema={
        "game_pk": pl.Int64, "pitcher": pl.Int64, "line": pl.Float64,
        "book": pl.String, "side": pl.String,
        "quote_ts": pl.Datetime("us", "UTC"), "price": pl.Int64,
    })
    bets = me.build_paper_bets(eval_pairs, probs, closing_empty)
    assert bets.height == 1
    bet = bets.row(0, named=True)
    assert bet["side"] == "over"
    assert bet["p_h3_win"] == pytest.approx(0.7)
    assert bet["p_h3_lose"] == pytest.approx(0.0)   # push mass NOT in lose
    assert bet["ev_h3"] == pytest.approx(0.7 * (2.0 - 1.0) - 0.0)


def test_devig_proportional():
    p_o, p_u = me.devig_proportional(*[me.to_decimal(-110)] * 2)
    assert p_o == pytest.approx(0.5)
    assert p_u == pytest.approx(0.5)
    p_o, p_u = me.devig_proportional(me.to_decimal(-130), me.to_decimal(110))
    inv_o = 1.0 / me.to_decimal(-130)
    inv_u = 1.0 / me.to_decimal(110)
    assert p_o == pytest.approx(inv_o / (inv_o + inv_u))
    assert p_o + p_u == pytest.approx(1.0)
    with pytest.raises(ValueError):
        me.devig_proportional(1.0, 2.0)


def test_ev_per_unit_push_refund():
    # win -> +(d-1), lose -> -1, push -> 0
    ev = me.ev_per_unit(0.5, 0.3, 0.2, 2.2)
    assert ev == pytest.approx(0.5 * 1.2 - 0.3)
    assert me.ev_per_unit(0.0, 0.0, 1.0, 3.0) == pytest.approx(0.0)


def test_bet_qualifies_margin():
    assert me.bet_qualifies(0.55, 2.0) is True          # 0.55 > 0.52
    assert me.bet_qualifies(0.51, 2.0) is False
    assert me.bet_qualifies(0.52, 2.0) is False          # strict >
    assert me.bet_qualifies(0.521, 2.0) is True


def test_book_priority_index():
    assert me.book_priority_index("draftkings") == 0
    assert me.book_priority_index("fanduel") == 1
    assert me.book_priority_index("unknown_book") == len(me.BOOK_PRIORITY)


def test_choose_observation_pair_best_total_then_priority_then_ts():
    rows = [
        {"book": "draftkings", "pair_ts": "t1", "d_over": 1.9, "d_under": 2.0},
        {"book": "fanduel", "pair_ts": "t1", "d_over": 2.0, "d_under": 2.0},
        {"book": "betmgm", "pair_ts": "t2", "d_over": 2.0, "d_under": 2.0},
    ]
    # fanduel and betmgm tie on total (4.0) > draftkings (3.9); fanduel wins priority
    assert me.choose_observation_pair(rows)["book"] == "fanduel"
    rows2 = [
        {"book": "fanduel", "pair_ts": "t1", "d_over": 2.0, "d_under": 2.0},
        {"book": "betmgm", "pair_ts": "t2", "d_over": 2.0, "d_under": 2.0},
    ]
    # same priority impossible; equal totals + equal priority -> latest ts
    rows3 = [
        {"book": "draftkings", "pair_ts": "t1", "d_over": 2.0, "d_under": 2.0},
        {"book": "draftkings", "pair_ts": "t2", "d_over": 2.0, "d_under": 2.0},
    ]
    assert me.choose_observation_pair(rows3)["pair_ts"] == "t2"
    assert me.choose_observation_pair(rows2)["book"] == "fanduel"


# ---------------------------------------------------------------------------
# frame-level filters
# ---------------------------------------------------------------------------


def _joined_frame(rows):
    schema = {
        "game_pk": pl.Int64, "pitcher": pl.Int64, "line": pl.Float64,
        "book": pl.String, "side": pl.String, "snapshot": pl.String,
        "quote_ts": pl.Datetime("us", "UTC"), "price": pl.Int64,
        "tier": pl.String, "first_pitch_ts": pl.Datetime("us", "UTC"),
        "predictor_available_ts": pl.Datetime("us", "UTC"),
        "event_id": pl.String, "pitcher_key": pl.String,
        "game_date": pl.Date, "block": pl.String, "pitch_half": pl.String,
        "vendor_game_date": pl.Date, "market": pl.String,
    }
    return pl.DataFrame(rows, schema=schema)


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


PA = ts("2025-05-01T04:00:00Z")   # predictor available 00:00 ET game day
PB = ts("2025-05-02T04:00:00Z")


def test_actionable_vs_closing_split_tiers():
    fp = ts("2025-05-01T23:00:00Z")
    rows = [
        {"game_pk": 1, "pitcher": 10, "line": 5.5, "book": "dk", "side": "over",
         "snapshot": "close", "quote_ts": ts("2025-05-01T22:55:00Z"), "price": -110,
         "tier": me.TIER_A, "first_pitch_ts": fp, "predictor_available_ts": PA, "event_id": "e1",
         "pitcher_key": "a alice", "game_date": date(2025, 5, 1), "block": "b",
         "pitch_half": "Top", "vendor_game_date": date(2025, 5, 1),
         "market": "pitcher_strikeouts"},
        {"game_pk": 1, "pitcher": 10, "line": 5.5, "book": "dk", "side": "over",
         "snapshot": "morning", "quote_ts": ts("2025-05-01T23:05:00Z"), "price": -105,
         "tier": me.TIER_A, "first_pitch_ts": fp, "predictor_available_ts": PA, "event_id": "e1",
         "pitcher_key": "a alice", "game_date": date(2025, 5, 1), "block": "b",
         "pitch_half": "Top", "vendor_game_date": date(2025, 5, 1),
         "market": "pitcher_strikeouts"},
        {"game_pk": 2, "pitcher": 10, "line": 5.5, "book": "dk", "side": "over",
         "snapshot": "close", "quote_ts": ts("2025-05-02T22:55:00Z"), "price": -110,
         "tier": me.TIER_B, "first_pitch_ts": None, "predictor_available_ts": PB, "event_id": "e2",
         "pitcher_key": "a alice", "game_date": date(2025, 5, 2), "block": "b",
         "pitch_half": "Top", "vendor_game_date": date(2025, 5, 2),
         "market": "pitcher_strikeouts"},
        {"game_pk": 2, "pitcher": 10, "line": 5.5, "book": "dk", "side": "over",
         "snapshot": "morning", "quote_ts": ts("2025-05-02T18:00:00Z"), "price": -105,
         "tier": me.TIER_B, "first_pitch_ts": None, "predictor_available_ts": PB, "event_id": "e2",
         "pitcher_key": "a alice", "game_date": date(2025, 5, 2), "block": "b",
         "pitch_half": "Top", "vendor_game_date": date(2025, 5, 2),
         "market": "pitcher_strikeouts"},
    ]
    jf = _joined_frame(rows)
    act, closing_side, pre = me.split_actionable_closing(jf)
    # tier A: post-first-pitch quote is out entirely; the latest pre-cutoff
    # quote (close 22:55) is the closing ref and is NOT actionable
    # tier B: close clock is closing-only; morning is actionable
    assert act.height == 1
    assert act["game_pk"].item() == 2
    assert act["snapshot"].item() == "morning"
    # closing refs: tier A latest pre-cutoff (close clock) + tier B close clock
    assert closing_side.height == 2
    assert (closing_side["quote_ts"] == ts("2025-05-01T22:55:00Z")).sum() == 1
    assert (closing_side["quote_ts"] == ts("2025-05-02T22:55:00Z")).sum() == 1
    assert pre.height == 2


def test_pairing_requires_both_sides_and_excludes_closing():
    fp = ts("2025-05-01T23:00:00Z")
    base = {
        "game_pk": 1, "pitcher": 10, "line": 5.5, "book": "dk",
        "tier": me.TIER_A, "first_pitch_ts": fp, "predictor_available_ts": PA, "event_id": "e1",
        "pitcher_key": "a alice", "game_date": date(2025, 5, 1), "block": "b",
        "pitch_half": "Top", "vendor_game_date": date(2025, 5, 1),
        "market": "pitcher_strikeouts",
    }
    rows = [
        dict(base, side="over", snapshot="morning",
             quote_ts=ts("2025-05-01T18:00:00Z"), price=-105),
        dict(base, side="under", snapshot="morning",
             quote_ts=ts("2025-05-01T18:00:00Z"), price=-115),
        dict(base, side="over", snapshot="close",
             quote_ts=ts("2025-05-01T22:55:00Z"), price=-110),
        # under side missing at the close clock
    ]
    jf = _joined_frame(rows)
    act, closing_side, pre = me.split_actionable_closing(jf)
    # closing refs: over -> close 22:55 (latest), under -> morning 18:00
    assert closing_side.height == 2
    # under's only quote became its closing ref -> no actionable under;
    # over's actionable row is the morning quote only
    assert act.height == 1
    assert act["side"].item() == "over"
    # no both-sides actionable clock -> no paired observation for this book
    paired = me.pair_sides(act)
    assert paired.height == 0
    # but the closing-eligible set pairs at the latest both-sides clock (18:00)
    closing_pair = me.pair_sides(pre)
    assert closing_pair.height == 1
    assert closing_pair["pair_ts"].item() == ts("2025-05-01T18:00:00Z")
    assert closing_pair["price_over"].item() == -105
    assert closing_pair["p_over_mkt"].item() == pytest.approx(
        (1.0 / me.to_decimal(-105))
        / (1.0 / me.to_decimal(-105) + 1.0 / me.to_decimal(-115))
    )


def test_pairing_latest_both_sides_clock():
    fp = ts("2025-05-01T23:00:00Z")
    base = {
        "game_pk": 1, "pitcher": 10, "line": 5.5, "book": "dk",
        "tier": me.TIER_A, "first_pitch_ts": fp, "predictor_available_ts": PA, "event_id": "e1",
        "pitcher_key": "a alice", "game_date": date(2025, 5, 1), "block": "b",
        "pitch_half": "Top", "vendor_game_date": date(2025, 5, 1),
        "market": "pitcher_strikeouts",
    }
    rows = [
        dict(base, side="over", snapshot="morning",
             quote_ts=ts("2025-05-01T18:00:00Z"), price=-105),
        dict(base, side="under", snapshot="morning",
             quote_ts=ts("2025-05-01T18:00:00Z"), price=-115),
        dict(base, side="over", snapshot="close",
             quote_ts=ts("2025-05-01T22:55:00Z"), price=-110),
        dict(base, side="under", snapshot="close",
             quote_ts=ts("2025-05-01T22:55:00Z"), price=-110),
    ]
    jf = _joined_frame(rows)
    act, closing_side, pre = me.split_actionable_closing(jf)
    paired = me.pair_sides(act)
    # actionable pairing uses the morning clock (close rows are closing-only)
    assert paired.height == 1
    assert paired["pair_ts"].item() == ts("2025-05-01T18:00:00Z")
    assert paired["price_over"].item() == -105
    assert paired["price_under"].item() == -115
    closing_pair = me.pair_sides(pre)
    assert closing_pair["pair_ts"].item() == ts("2025-05-01T22:55:00Z")
    assert closing_pair["price_over"].item() == -110


def test_latest_per_side_no_fanout_same_ts_distinct_labels():
    """C3 regression: two closing-eligible rows can share ONE quote_ts for
    the same (start, line, book, side) under distinct snapshot labels;
    latest_per_side must collapse them to ONE row per key so the
    closing-ref join cannot fan out actionable rows or paper bets."""
    fp = ts("2025-05-01T23:00:00Z")
    base = {
        "game_pk": 1, "pitcher": 10, "line": 5.5, "book": "dk",
        "tier": me.TIER_A, "first_pitch_ts": fp, "predictor_available_ts": PA,
        "event_id": "e1", "pitcher_key": "a alice",
        "game_date": date(2025, 5, 1), "block": "b", "pitch_half": "Top",
        "vendor_game_date": date(2025, 5, 1), "market": "pitcher_strikeouts",
    }
    rows = [
        dict(base, side="over", snapshot="morning",
             quote_ts=ts("2025-05-01T18:00:00Z"), price=-105),
        dict(base, side="under", snapshot="morning",
             quote_ts=ts("2025-05-01T18:00:00Z"), price=-115),
        # two distinct snapshot labels at the SAME closing ts
        dict(base, side="over", snapshot="close",
             quote_ts=ts("2025-05-01T22:55:00Z"), price=-110),
        dict(base, side="over", snapshot="late_close",
             quote_ts=ts("2025-05-01T22:55:00Z"), price=-112),
        dict(base, side="under", snapshot="close",
             quote_ts=ts("2025-05-01T22:55:00Z"), price=-110),
    ]
    jf = _joined_frame(rows)
    latest = me.latest_per_side(me.closing_eligible(jf))
    assert latest.height == 2  # one per side, not 3
    assert latest.filter(pl.col("side") == "over").height == 1
    act, closing_side, pre = me.split_actionable_closing(jf)
    # the actionable morning pair must not be duplicated by the fan-out
    assert act.height == 2
    assert act.select("game_pk", "pitcher", "line", "book", "side").n_unique() == 2
    assert closing_side.height == 2
    assert closing_side.select(
        "game_pk", "pitcher", "line", "book", "side"
    ).n_unique() == 2


def test_choose_eval_pairs_book_name_tiebreak_deterministic():
    """C3 regression: two books outside BOOK_PRIORITY tie on priority index,
    total decimal, and pair_ts; the book-name tiebreak must make the
    one-pair-per-(start, line) choice deterministic (lexicographically
    first book wins)."""
    base = {"game_pk": 1, "pitcher": 10, "line": 5.5,
            "pair_ts": ts("2025-05-01T18:00:00Z"),
            "d_over": 2.0, "d_under": 2.0}
    paired = pl.DataFrame([
        dict(base, book="zeta_book"),
        dict(base, book="alpha_book"),
    ])
    for _ in range(5):
        chosen = me.choose_eval_pairs(paired)
        assert chosen.height == 1
        assert chosen["book"].item() == "alpha_book"


# ---------------------------------------------------------------------------
# end-to-end prep on synthetic parquet fixtures
# ---------------------------------------------------------------------------


def _payload_frame(rows):
    cols = (["game_pk", "pitcher", "game_date", "block", "side", "forecast_cutoff"]
            + PMF_H3_COLS + PMF_L5_COLS)
    data = {c: [] for c in cols}
    for r in rows:
        data["game_pk"].append(int(r["game_pk"]))
        data["pitcher"].append(int(r["pitcher"]))
        data["game_date"].append(r["game_date"])
        data["block"].append(r.get("block", "block_test"))
        data["side"].append(r.get("side", "Top"))
        data["forecast_cutoff"].append(r.get("forecast_cutoff", r["game_date"]))
        h3 = r.get("pmf_h3", {})
        l5 = r.get("pmf_l5", {})
        for i in range(me.PMF_SUPPORT):
            data["pmf_h3_raw_%d" % i].append(float(h3.get(i, 0.0)))
            data["pmf_l5_raw_%d" % i].append(float(l5.get(i, 0.0)))
    return pl.DataFrame(data).with_columns(
        pl.col("game_pk").cast(pl.Int64), pl.col("pitcher").cast(pl.Int64),
        pl.col("game_date").cast(pl.Date),
    )


def _quotes_frame(rows):
    cols = ["event_id", "snapshot", "snapshot_ts", "game_date", "season_type",
            "book", "market", "player", "player_norm", "line", "side", "price"]
    data = {c: [] for c in cols}
    for r in rows:
        for c in cols:
            data[c].append(r[c])
    return pl.DataFrame(data).with_columns(
        pl.col("line").cast(pl.Float64), pl.col("price").cast(pl.Int64)
    )


def _envelope_frame(rows):
    return pl.DataFrame(
        {"event_id": [r["event_id"] for r in rows],
         "commence_time": [r["commence_time"] for r in rows]}
    )


def _id_map_frame(rows):
    return pl.DataFrame(
        {"mlb_id": [r["mlb_id"] for r in rows],
         "player_name": [r["player_name"] for r in rows]}
    ).with_columns(pl.col("mlb_id").cast(pl.Int64))


def _q(event_id, snapshot, snapshot_ts, game_date, book, line, side, price,
       player_norm="alice a", market="pitcher_strikeouts", season="regular"):
    return {
        "event_id": event_id, "snapshot": snapshot, "snapshot_ts": snapshot_ts,
        "game_date": game_date, "season_type": season, "book": book,
        "market": market, "player": "Alice A", "player_norm": player_norm,
        "line": line, "side": side, "price": price,
    }


def _write_fixtures(tmp_path, payload_rows, quote_rows, envelope_rows, id_rows):
    d = tmp_path / "in"
    d.mkdir(parents=True, exist_ok=True)
    _payload_frame(payload_rows).write_parquet(d / "payload.parquet")
    _quotes_frame(quote_rows).write_parquet(d / "book_lines.parquet")
    _envelope_frame(envelope_rows).write_parquet(d / "envelope.parquet")
    _id_map_frame(id_rows).write_parquet(d / "id_map.parquet")
    return d


H3_A = {3: 0.25, 4: 0.5, 5: 0.25}
L5_A = {3: 1.0}


def _standard_fixtures(tmp_path):
    payload_rows = [
        {"game_pk": 100, "pitcher": 1, "game_date": date(2025, 5, 1),
         "pmf_h3": H3_A, "pmf_l5": L5_A},                     # eligible, tier A
        {"game_pk": 101, "pitcher": 2, "game_date": date(2025, 5, 1),
         "pmf_h3": H3_A, "pmf_l5": L5_A},                     # unresolved id
        {"game_pk": 102, "pitcher": 1, "game_date": date(2025, 5, 2),
         "pmf_h3": H3_A, "pmf_l5": L5_A},                     # doubleheader ambiguous
        {"game_pk": 103, "pitcher": 1, "game_date": date(2025, 5, 3),
         "pmf_h3": H3_A, "pmf_l5": L5_A},                     # eligible, tier B
    ]
    quote_rows = [
        # E1: start A's event (tier A via envelope commence)
        _q("e1", "morning", "2025-05-01T18:00:00Z", "2025-05-01", "draftkings", 5.5, "over", -105),
        _q("e1", "morning", "2025-05-01T18:00:00Z", "2025-05-01", "draftkings", 5.5, "under", -115),
        _q("e1", "close", "2025-05-01T22:55:00Z", "2025-05-01", "draftkings", 5.5, "over", -110),
        _q("e1", "close", "2025-05-01T22:55:00Z", "2025-05-01", "draftkings", 5.5, "under", -110),
        _q("e1", "morning", "2025-05-01T18:00:00Z", "2025-05-01", "draftkings", 4.0, "over", -105),
        _q("e1", "morning", "2025-05-01T18:00:00Z", "2025-05-01", "draftkings", 4.0, "under", -105),
        _q("e1", "close", "2025-05-01T22:55:00Z", "2025-05-01", "draftkings", 4.0, "over", -105),
        _q("e1", "close", "2025-05-01T22:55:00Z", "2025-05-01", "draftkings", 4.0, "under", -105),
        # E2/E3: duplicate (game_date, player) key -> start 102 ambiguous
        _q("e2", "morning", "2025-05-02T18:00:00Z", "2025-05-02", "draftkings", 5.5, "over", -110),
        _q("e3", "morning", "2025-05-02T18:00:00Z", "2025-05-02", "draftkings", 5.5, "over", -110),
        # E4: start D's event, NO envelope row -> tier B clock proxy
        _q("e4", "morning", "2025-05-03T15:00:00Z", "2025-05-03", "fanduel", 5.5, "over", -120),
        _q("e4", "morning", "2025-05-03T15:00:00Z", "2025-05-03", "fanduel", 5.5, "under", 100),
        _q("e4", "close", "2025-05-03T15:40:00Z", "2025-05-03", "fanduel", 5.5, "over", -130),
        _q("e4", "close", "2025-05-03T15:40:00Z", "2025-05-03", "fanduel", 5.5, "under", -110),
    ]
    envelope_rows = [
        {"event_id": "e1", "commence_time": "2025-05-01T23:00:00Z"},
    ]
    id_rows = [
        {"mlb_id": 1, "player_name": "Alice A"},
        # mlb_id 2 deliberately absent -> unresolved-id exclusion
    ]
    return _write_fixtures(tmp_path, payload_rows, quote_rows, envelope_rows, id_rows)


def _run_prep(d, out_name="out"):
    return me.run_prep(
        d / "book_lines.parquet", d / "envelope.parquet",
        d / "payload.parquet", d / "id_map.parquet", d / out_name,
    )


def test_prep_identity_exclusions_and_tiers(tmp_path):
    d = _standard_fixtures(tmp_path)
    summary = _run_prep(d)
    ident = summary["identity"]
    assert ident["starts_total"] == 4
    assert ident["unresolved_ids_excluded"] == 1        # pitcher 2
    assert ident["doubleheader_ambiguous_excluded"] == 1  # start 102
    assert ident["eligible_starts"] == 2                # starts 100 (A), 103 (B)
    assert ident["eligible_by_tier"] == {
        me.TIER_A: 1, me.TIER_B: 1,
    }


def test_prep_contracts_push_and_probs(tmp_path):
    d = _standard_fixtures(tmp_path)
    summary = _run_prep(d)
    c = summary["contracts"]
    # start A: lines 5.5 (morning pair) + 4.0 (close pair) -> 4 side rows
    # start D: line 5.5 only -> 2 side rows
    assert c["contract_side_rows"] == 6
    assert c["half_line_rows"] == 4
    assert c["integer_line_rows"] == 2
    assert c["integer_push_expected_nonzero"] == 2  # line 4.0 both sides (H3 push .5)
    assert c["eval_pairs_one_per_start_line"] == 3  # 3 (start, line) pairs

    m = pl.read_parquet(d / "out" / "matched_contracts.parquet")
    a4 = m.filter((pl.col("game_pk") == 100) & (pl.col("line") == 4.0))
    assert a4.height == 2
    over4 = a4.filter(pl.col("side") == "over").row(0, named=True)
    assert over4["p_h3_push"] == pytest.approx(0.5)
    assert over4["p_h3_win"] == pytest.approx(0.25)      # P(K >= 5)
    assert over4["p_h3_lose"] == pytest.approx(0.25)     # P(K <= 3)
    assert over4["p_l5_push"] == 0.0                      # LOG5 degenerate at 3
    # de-vig from -105/-105 is 0.5/0.5 and break-even = 1/d
    assert over4["p_market"] == pytest.approx(0.5)
    assert over4["break_even"] == pytest.approx(1.0 / me.to_decimal(-105))

    # half-line 5.5 has zero push by construction
    a55 = m.filter((pl.col("game_pk") == 100) & (pl.col("line") == 5.5))
    assert (a55["p_h3_push"] == 0.0).all()


def test_prep_observation_selection_and_closing_separation(tmp_path):
    d = _standard_fixtures(tmp_path)
    _run_prep(d)
    pairs = pl.read_parquet(d / "out" / "actionable_pairs.parquet")
    a55 = pairs.filter((pl.col("game_pk") == 100) & (pl.col("line") == 5.5))
    # actionable set excludes the closing-ref rows -> only the morning clock
    assert a55.height == 1
    assert bool(a55["chosen_for_eval"].item()) is True
    assert a55["pair_ts"].item() == ts("2025-05-01T18:00:00Z")
    assert a55["price_over"].item() == -105
    assert a55["price_under"].item() == -115

    closing = pl.read_parquet(d / "out" / "closing_refs.parquet")
    c55 = closing.filter((pl.col("game_pk") == 100) & (pl.col("line") == 5.5))
    # tier A closing ref = LAST pre-commence pair = the close clock
    assert c55["pair_ts"].item() == ts("2025-05-01T22:55:00Z")
    assert c55["price_over"].item() == -110
    assert c55["price_under"].item() == -110


def test_prep_paper_bets_and_clv(tmp_path):
    d = _standard_fixtures(tmp_path)
    summary = _run_prep(d)
    bets = pl.read_parquet(d / "out" / "paper_bets.parquet")
    # under side at line 5.5 for both eligible starts: p_under = 1.0 (H3)
    # bet rule picks the FIRST qualifying book by priority (draftkings for
    # start A; fanduel is the only book covering start D)
    assert summary["paper_bets"]["bets"] == 2
    assert set(bets["side"].to_list()) == {"under"}
    assert set(bets["book"].to_list()) == {"draftkings", "fanduel"}
    assert summary["paper_bets"]["missing_closing_ref"] == 0

    bet_a = bets.filter(pl.col("game_pk") == 100).row(0, named=True)
    # p_under = 1.0 > 1/1.8696 + 0.02 -> bet at dk's paired morning price -115
    assert bet_a["price"] == -115
    assert bet_a["stake_units"] == 1.0
    assert bet_a["close_price"] == -110
    expected_clv = (me.to_decimal(-115) - me.to_decimal(-110)) / me.to_decimal(-110)
    assert bet_a["clv_pct"] == pytest.approx(expected_clv)

    bet_d = bets.filter(pl.col("game_pk") == 103).row(0, named=True)
    # tier B: actionable = morning clock (+100 under); close clock is
    # closing-only and must NOT be bet
    assert bet_d["tier"] == me.TIER_B
    assert bet_d["price"] == 100
    assert bet_d["close_price"] == -110


def test_prep_coverage_after_exclusions(tmp_path):
    d = _standard_fixtures(tmp_path)
    summary = _run_prep(d)
    cov = summary["coverage"]
    assert cov["after_exclusions_all"]["eligible_starts"] == 2
    assert cov["after_exclusions_all"]["with_precutoff_quote"] == 2
    assert cov["after_exclusions_all"]["with_closing_ref"] == 2
    assert cov["after_exclusions_tier_A"]["eligible_starts"] == 1
    assert cov["after_exclusions_tier_B"]["eligible_starts"] == 1


def test_prep_write_once_guard(tmp_path):
    d = _standard_fixtures(tmp_path)
    _run_prep(d)
    with pytest.raises(me.WriteOnceError):
        _run_prep(d, out_name="out")


def test_score_implemented_but_requires_inputs(capsys, tmp_path):
    """--score is IMPLEMENTED (correction C2) but fails loud without a valid
    prep dir; it has NOT been executed against the real frozen prep. The
    score-dir is always inside tmp_path so tests can never write to the
    default scoring directory."""
    with pytest.raises(me.ScoreReadError):
        me.main([
            "--score", "--prep-dir", str(tmp_path / "nope"),
            "--score-dir", str(tmp_path / "score"),
        ])


def test_load_quotes_pooled_market_two_pitcher_collision(tmp_path):
    """C3 regression (independent check of the registered v1 defect): v1
    pooled the two K markets on (event, snapshot, book, line, side) WITHOUT
    player_norm, so whenever two pitchers shared such a key one pitcher's
    quotes were arbitrarily deleted and the pipeline ran nondeterministically
    (750k+ such shared keys in the archive). v2 pools WITHIN a pitcher:
    both pitchers must survive each snapshot with their own bettor-best
    price, and repeated loads must be identical (file-row-index
    tie-breaks + maintain_order unique)."""
    rows = []
    for snap, snap_ts in (("morning", "2025-05-01T18:00:00Z"),
                          ("close", "2025-05-01T22:55:00Z")):
        for price in (-120, -110):  # duplicate key rows; -110 is bettor-best
            rows.append(_q("e1", snap, snap_ts, "2025-05-01", "draftkings",
                           5.5, "over", price, player_norm="alice a"))
        rows.append(_q("e1", snap, snap_ts, "2025-05-01", "draftkings",
                       5.5, "over", 105, player_norm="bob b"))
    qpath = tmp_path / "book_lines.parquet"
    _quotes_frame(rows).write_parquet(qpath)
    q1, meta1 = me.load_quotes(qpath)
    q2, meta2 = me.load_quotes(qpath)
    assert q1.height == 4  # 2 pitchers x 2 snapshots, per-side pooled
    snap1 = q1.filter(pl.col("snapshot") == "morning")
    assert snap1.height == 2
    alice = snap1.filter(pl.col("player_norm") == "alice a")
    bob = snap1.filter(pl.col("player_norm") == "bob b")
    assert alice.height == 1 and bob.height == 1
    assert alice["price"].item() == -110   # max-price dedup within alice
    assert bob["price"].item() == 105      # bob's quote NOT deleted by the key collision
    assert q1.equals(q2)                   # deterministic across loads
    assert meta1 == meta2
