"""Synthetic end-to-end tests for the market-eval-v1 scoring run.

test_score_end_to_end.py builds a tiny synthetic prep directory (matched
contracts, paper bets, prep manifest with correct hashes) plus a synthetic
start_metrics parquet with KNOWN realized K, then runs market_eval.run_score
and asserts:

  - known payouts (over win, under win, push refund)
  - no-bet cases (edge below margin never enter the ledger)
  - missing closing reference (bet kept, excluded from CLV stats, count
    disclosed)
  - all six score outputs are written
  - skill metrics match hand-computed values
  - bootstrap is deterministic under the registered seed
  - write-once guard + prep-hash verification fire loudly

No real archive reads. ASCII only.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import market_eval as me  # noqa: E402

# ---------------------------------------------------------------------------
# pure settlement helpers
# ---------------------------------------------------------------------------


def test_settle_half_line():
    assert me.settle_result(5.5, "over", 6) == "win"
    assert me.settle_result(5.5, "over", 5) == "lose"
    assert me.settle_result(5.5, "under", 5) == "win"
    assert me.settle_result(5.5, "under", 6) == "lose"
    assert me.settle_result(5.5, "over", 15) == "win"


def test_settle_integer_line_push_refund():
    assert me.settle_result(5.0, "over", 5) == "push"
    assert me.settle_result(5.0, "under", 5) == "push"
    assert me.settle_result(5.0, "over", 6) == "win"
    assert me.settle_result(5.0, "under", 4) == "win"
    assert me.settle_result(5.0, "over", 4) == "lose"
    assert me.settle_result(5.0, "under", 6) == "lose"


def test_payout_units_known_values():
    assert me.payout_units("win", 2.0) == pytest.approx(1.0)
    assert me.payout_units("win", 1.9090909090909092) == pytest.approx(0.9090909090909092)
    assert me.payout_units("lose", 2.5) == pytest.approx(-1.0)
    assert me.payout_units("push", 3.0) == 0.0
    with pytest.raises(ValueError):
        me.payout_units("nonsense", 2.0)


def test_settlement_half_line_never_pushes_and_integer_push_refunds():
    """F-3: pinned settlement semantics across a full K sweep.
    Half line: over wins at K >= ceil(L), under wins at K <= floor(L);
    NO K value may settle to push (there is no integer at a half line).
    Integer line: K == L settles to push for BOTH sides and refunds the
    full stake exactly (payout 0.0); over wins at K >= L+1, under at
    K <= L-1."""
    L = 5.5
    for k in range(0, 21):
        assert me.settle_result(L, "over", k) == ("win" if k >= 6 else "lose")
        assert me.settle_result(L, "under", k) == ("win" if k <= 5 else "lose")
        assert me.settle_result(L, "over", k) != "push"
        assert me.settle_result(L, "under", k) != "push"
    for k in range(0, 21):
        if k == 5:
            assert me.settle_result(5.0, "over", k) == "push"
            assert me.settle_result(5.0, "under", k) == "push"
            assert me.payout_units("push", 2.2) == 0.0  # stake refunded
        elif k >= 6:
            assert me.settle_result(5.0, "over", k) == "win"
            assert me.settle_result(5.0, "under", k) == "lose"
        else:
            assert me.settle_result(5.0, "over", k) == "lose"
            assert me.settle_result(5.0, "under", k) == "win"
    # invalid side / negative K fail loud
    with pytest.raises(ValueError):
        me.settle_result(5.5, "middle", 6)
    with pytest.raises(ValueError):
        me.settle_result(5.5, "over", -1)


def test_mc_brier_row_hand_values():
    # perfect one-hot prediction -> 0; uniform thirds on one-hot -> 2/3
    assert me.mc_brier_row(1.0, 0.0, 0.0, 1, 0, 0) == pytest.approx(0.0)
    assert me.mc_brier_row(1.0, 0.0, 0.0, 0, 0, 1) == pytest.approx(2.0)
    assert me.mc_brier_row(1 / 3, 1 / 3, 1 / 3, 1, 0, 0) == pytest.approx(2.0 / 3.0)


# ---------------------------------------------------------------------------
# synthetic end-to-end fixture
# ---------------------------------------------------------------------------

PMF_H3 = ["pmf_h3_raw_%d" % i for i in range(me.PMF_SUPPORT)]
PMF_L5 = ["pmf_l5_raw_%d" % i for i in range(me.PMF_SUPPORT)]
MC_COLS = [
    "game_pk", "pitcher", "pitcher_key", "game_date", "block", "pitch_half",
    "tier", "first_pitch_ts", "line", "book", "pair_ts",
    "p_over_mkt", "p_under_mkt", "event_id", "side", "price", "decimal_odds",
    "p_h3_win", "p_h3_lose", "p_h3_push", "p_l5_win", "p_l5_lose",
    "p_l5_push", "p_market", "break_even", "ev_h3", "ev_l5",
]
BET_COLS = [
    "game_pk", "pitcher", "pitcher_key", "game_date", "block", "tier",
    "first_pitch_ts", "line", "event_id", "side", "book", "quote_ts",
    "price", "decimal_odds", "p_h3_win", "break_even", "stake_units",
    "ev_h3", "close_quote_ts", "close_price", "clv_pct",
]


def _ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _contract(game_pk, pitcher, half, line, side, price, d, p_over_mkt,
              p_h3_over, p_h3_under, p_l5_over, p_l5_under, game_date,
              push_h3=0.0, push_l5=0.0):
    p_h3_win = p_h3_over if side == "over" else p_h3_under
    p_h3_lose = p_h3_under if side == "over" else p_h3_over
    p_l5_win = p_l5_over if side == "over" else p_l5_under
    p_l5_lose = p_l5_under if side == "over" else p_l5_over
    return {
        "game_pk": game_pk, "pitcher": pitcher, "pitcher_key": "a alice",
        "game_date": game_date, "block": "block_test", "pitch_half": "Top",
        "tier": me.TIER_A, "first_pitch_ts": _ts("2025-05-01T23:00:00Z"),
        "line": line, "book": "draftkings",
        "pair_ts": _ts("2025-05-01T18:00:00Z"),
        "p_over_mkt": p_over_mkt, "p_under_mkt": 1.0 - p_over_mkt,
        "event_id": "e%d" % game_pk, "side": side, "price": price,
        "decimal_odds": d,
        "p_h3_win": p_h3_win, "p_h3_lose": p_h3_lose, "p_h3_push": push_h3,
        "p_l5_win": p_l5_win, "p_l5_lose": p_l5_lose, "p_l5_push": push_l5,
        "p_market": p_over_mkt if side == "over" else 1.0 - p_over_mkt,
        "break_even": 1.0 / d,
        "ev_h3": p_h3_win * (d - 1.0) - p_h3_lose,
        "ev_l5": p_l5_win * (d - 1.0) - p_l5_lose,
    }


def _write_synth(tmp_path):
    """Four settled cases + one no-bet + one missing-close, all with hand-
    computable outcomes:

    S1 line 5.5 over  @ +150 (d=2.5), realized K=7 -> WIN  (payout +1.5)
       H3: P(over)=0.6 -> edge over break-even 0.4: 0.6 > 0.42 -> bet
    S2 line 5.5 under @ -200 (d=1.5), realized K=7 -> LOSE (payout -1.0)
       H3: P(under)=0.2 -> 0.2 vs break-even 0.6667: no edge -> but forced
       into the bets file for settlement coverage of the lose case.
    S3 line 5.0 over  @ +100 (d=2.0), realized K=5 -> PUSH (payout 0)
       H3: P(over)=0.3, push=0.4.
    S4 line 6.5 over  @ +120 (d=2.2), realized K=4 -> LOSE; close MISSING.
    S5 line 4.5 under @ -110, realized K=4 -> WIN; H3 P(under)=0.5,
       break-even 0.5238 -> NO BET (must not appear in the ledger).
    """
    gd = date(2025, 5, 1)
    contracts = [
        _contract(1, 100, True, 5.5, "over", 150, 2.5, 0.4, 0.6, 0.4, 0.3, 0.7, gd),
        _contract(2, 200, True, 5.5, "under", -200, 1.5, 0.4, 0.6, 0.4, 0.3, 0.7, gd),
        _contract(3, 300, True, 5.0, "over", 100, 2.0, 0.5, 0.3, 0.7, 0.2, 0.8,
                  gd, push_h3=0.4, push_l5=0.0),
        _contract(4, 400, True, 6.5, "over", 120, 2.2, 0.45, 0.55, 0.45, 0.5, 0.5,
                  date(2025, 5, 2)),
        _contract(5, 500, True, 4.5, "under", -110, 1.9090909090909092,
                  0.5180722891566265, 0.5, 0.5, 0.4, 0.6, gd),
    ]
    matched = pl.DataFrame(contracts, schema=MC_COLS)

    bets = matched.filter(
        pl.col("game_pk").is_in([1, 2, 3, 4])
    ).with_columns(
        pl.col("pair_ts").alias("quote_ts"),
        pl.lit(1.0).alias("stake_units"),
        pl.lit(None, dtype=pl.Datetime("us", "UTC")).alias("close_quote_ts"),
        pl.lit(None, dtype=pl.Int64).alias("close_price"),
        pl.lit(None, dtype=pl.Float64).alias("clv_pct"),
    ).select(BET_COLS)
    # S4 has no closing reference; S1-S3 get closes
    bets = bets.with_columns(
        pl.when(pl.col("game_pk") == 1).then(_ts("2025-05-01T22:55:00Z"))
        .when(pl.col("game_pk") == 2).then(_ts("2025-05-01T22:55:00Z"))
        .when(pl.col("game_pk") == 3).then(_ts("2025-05-01T22:55:00Z"))
        .otherwise(None).alias("close_quote_ts"),
        pl.when(pl.col("game_pk") == 1).then(130)
        .when(pl.col("game_pk") == 2).then(-150)
        .when(pl.col("game_pk") == 3).then(110)
        .otherwise(None).alias("close_price"),
    ).with_columns(
        pl.when(pl.col("close_price").is_not_null()).then(
            (pl.col("decimal_odds") - me.decimal_expr("close_price"))
            / me.decimal_expr("close_price")
        ).otherwise(None).alias("clv_pct")
    ).select(BET_COLS)

    sm_rows = [
        {"game_pk": 1, "side": "Top", "pitcher": 100, "game_date": gd,
         "realized_k": 7, "prior_n": 20, "cold_start": 0},
        {"game_pk": 2, "side": "Top", "pitcher": 200, "game_date": gd,
         "realized_k": 7, "prior_n": 20, "cold_start": 0},
        {"game_pk": 3, "side": "Top", "pitcher": 300, "game_date": gd,
         "realized_k": 5, "prior_n": 20, "cold_start": 0},
        {"game_pk": 4, "side": "Top", "pitcher": 400, "game_date": date(2025, 5, 2),
         "realized_k": 4, "prior_n": 20, "cold_start": 0},
        {"game_pk": 5, "side": "Top", "pitcher": 500, "game_date": gd,
         "realized_k": 4, "prior_n": 20, "cold_start": 0},
    ]
    sm_cols = (["game_pk", "side", "pitcher", "game_date", "realized_k",
                "prior_n", "cold_start"]
               + ["base_h3_" + c for c in me.PERSISTED_COUNT_COLS]
               + ["base_l5_" + c for c in me.PERSISTED_COUNT_COLS])
    sm = pl.DataFrame(
        {c: ([0.5] * len(sm_rows) if c.startswith("base_") else
             [r.get(c, None) for r in sm_rows]) for c in sm_cols}
    )

    prep = tmp_path / "prep"
    prep.mkdir()
    matched.write_parquet(prep / "matched_contracts.parquet")
    bets.write_parquet(prep / "paper_bets.parquet")
    manifest = {
        "outputs_sha256_16": {
            f: me.sha256_16(prep / f) for f in
            ["matched_contracts.parquet", "paper_bets.parquet"]
        }
    }
    (prep / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    sm.write_parquet(tmp_path / "start_metrics.parquet")
    return prep, tmp_path / "start_metrics.parquet"


def test_score_end_to_end(tmp_path):
    prep, sm_path = _write_synth(tmp_path)
    out = tmp_path / "score"
    summary = me.run_score(prep, sm_path, out, seed=20261001, n_boot=200)

    # ---- all outputs written ----
    for f in me.SCORE_FILES:
        assert (out / f).exists(), f

    # ---- known payouts ----
    ledger = pl.read_parquet(out / "bets_ledger.parquet").sort("game_pk")
    assert ledger.height == 4  # S5 (no-bet) excluded
    res = dict(zip(ledger["game_pk"].to_list(), ledger["result"].to_list()))
    pnl = dict(zip(ledger["game_pk"].to_list(), ledger["pnl_units"].to_list()))
    assert res[1] == "win" and pnl[1] == pytest.approx(1.5)   # +150 -> d=2.5
    assert res[2] == "lose" and pnl[2] == pytest.approx(-1.0)
    assert res[3] == "push" and pnl[3] == 0.0                 # refund
    assert res[4] == "lose" and pnl[4] == pytest.approx(-1.0)
    assert summary["bets"]["wins"] == 1
    assert summary["bets"]["losses"] == 2
    assert summary["bets"]["pushes"] == 1
    assert summary["bets"]["pnl_units"] == pytest.approx(-0.5)
    assert summary["bets"]["roi_per_bet"] == pytest.approx(-0.125)

    # ---- no-bet case ----
    assert 5 not in res

    # ---- missing close: bet kept, excluded from CLV stats, count disclosed --
    clv = pl.read_parquet(out / "clv_table.parquet")
    assert clv.height == 3
    assert 4 not in clv["game_pk"].to_list()
    assert summary["bets"]["missing_close"] == 1
    b1 = clv.filter(pl.col("game_pk") == 1).row(0, named=True)
    d_close = me.to_decimal(130)
    assert b1["clv_pct"] == pytest.approx((2.5 - d_close) / d_close)

    # ---- skill metrics: hand-computed multi-class Brier ----
    sk = json.loads((out / "skill_metrics.json").read_text(encoding="utf-8"))
    # H3 rows: (p_win, p_push, p_lose) vs outcome one-hot
    # S1 over:  (.6, 0, .4) vs (1,0,0) -> .16+.16            = .32
    # S2 under: (.4, 0, .6) vs (0,0,1) -> .16+.16            = .32
    # S3 over:  (.3, .4, .7) vs (0,1,0) -> .09+.36+.49       = .94
    # S4 over:  (.55,0,.45) vs (0,0,1) -> .3025+.3025        = .605
    # S5 under: (.5, 0, .5) vs (1,0,0) -> .25+.25            = .50
    assert sk["brier"]["h3"] == pytest.approx((0.32 + 0.32 + 0.94 + 0.605 + 0.50) / 5)
    # LOG5 rows (zero push mass):
    # S1 over win:  (.3,0,.7) vs (1,0,0) = .49+.49           = .98
    # S2 under lose:(.7,0,.3) vs (0,0,1) = .49+.49           = .98
    # S3 over push: (.2,0,.8) vs (0,1,0) = .04+1+.64         = 1.68
    # S4 over lose: (.5,0,.5) vs (0,0,1) = .25+.25           = .50
    # S5 under win: (.6,0,.4) vs (1,0,0) = .16+.16           = .32
    assert sk["brier"]["l5"] == pytest.approx((0.98 + 0.98 + 1.68 + 0.50 + 0.32) / 5)
    # market: p_market is the de-vig win prob at the row's own side; compute
    # the expected Brier from the fixture frame under the same definition
    m = pl.read_parquet(prep / "matched_contracts.parquet")
    m = m.join(
        pl.read_parquet(sm_path).select(["game_pk", "realized_k"]),
        on="game_pk", how="left",
    )
    exp_market = []
    for r in m.iter_rows(named=True):
        K, L = r["realized_k"], float(r["line"])
        if L.is_integer():
            y_push = int(K == L)
            over_win = int(K >= L + 1)
        else:
            import math
            y_push = 0
            over_win = int(K >= math.ceil(L))
        if r["side"] == "over":
            y_win, y_lose = over_win, 1 - over_win - y_push
        else:
            y_win, y_lose = 1 - over_win - y_push, over_win
        exp_market.append(
            (r["p_market"] - y_win) ** 2 + (0.0 - y_push) ** 2
            + ((1.0 - r["p_market"]) - y_lose) ** 2
        )
    assert sk["brier"]["market"] == pytest.approx(sum(exp_market) / len(exp_market))
    assert sk["effective_counts"]["push_rows"] == 1
    assert sk["effective_counts"]["contract_side_rows"] == 5
    assert sk["effective_counts"]["distinct_starts"] == 5
    # count layer reused, not recomputed
    assert sk["count_layer_persisted_reused"]["n_starts"] == 5
    assert sk["count_layer_persisted_reused"]["h3"]["rps"] == pytest.approx(0.5)

    # ---- bootstrap deterministic under the registered seed ----
    b1 = json.loads((out / "bootstrap.json").read_text(encoding="utf-8"))
    assert b1["params"]["seed"] == 20261001
    assert b1["params"]["n_boot"] == 200
    assert "h3_minus_market" in b1["brier"]
    me.run_score(prep, sm_path, tmp_path / "score2", seed=20261001, n_boot=200)
    b2 = json.loads((tmp_path / "score2" / "bootstrap.json").read_text(encoding="utf-8"))
    assert b1 == b2

    # ---- write-once guard ----
    with pytest.raises(me.WriteOnceError):
        me.run_score(prep, sm_path, out)

    # ---- prep hash verification fires loudly ----
    bad = tmp_path / "bad"
    bad.mkdir()
    tampered = pl.read_parquet(prep / "matched_contracts.parquet").head(1)
    tampered.write_parquet(bad / "matched_contracts.parquet")
    (bad / "paper_bets.parquet").write_bytes(
        (prep / "paper_bets.parquet").read_bytes())
    (bad / "manifest.json").write_bytes((prep / "manifest.json").read_bytes())
    with pytest.raises(me.ScoreReadError):
        me.run_score(bad, sm_path, tmp_path / "score3")

    # ---- missing realized K refuses to score ----
    sm_bad = pl.read_parquet(sm_path).filter(pl.col("game_pk") != 3)
    sm_bad.write_parquet(tmp_path / "sm_bad.parquet")
    with pytest.raises(me.ScoreReadError):
        me.run_score(prep, tmp_path / "sm_bad.parquet", tmp_path / "score4")


def test_score_flag_runs_end_to_end(tmp_path, capsys):
    """The literal --score command path works on the synthetic fixture
    (with the F-4 explicit opt-in flag present)."""
    prep, sm_path = _write_synth(tmp_path)
    out = tmp_path / "score_cli"
    rc = me.main([
        "--score", "--i-accept-outcome-scoring",
        "--prep-dir", str(prep), "--start-metrics", str(sm_path),
        "--score-dir", str(out), "--n-boot", "50",
    ])
    assert rc == 0
    assert (out / "score_summary.json").exists()
    assert "wrote score outputs" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# C3 regression: block-stratified, row-weighted slate-date bootstrap
# ---------------------------------------------------------------------------


def test_slate_bootstrap_block_stratified_row_weighted():
    """Regression for the unstratified-pool bootstrap scale bug (C3).

    Fixture: block b1 has one 100-row date (value 1.0) and one 1-row date
    (value 1.0); block b2 has one 1-row date (value 0.0). The repair requires
    every replicate to draw b1's 2 dates from b1 and b2's 1 date from b2 and
    to combine row-weighted, so the pooled resample mean can only take the
    values {2/3, 101/102, 200/201}. The old unstratified pooled multinomial
    (a) divided per-date sums by the date count (per-date scale, not per-row
    scale -> values up to 100.0 with unequal date row counts) and (b) let a
    replicate drop an entire block.
    """
    from datetime import date as _date
    d1, d2, d3 = _date(2025, 5, 1), _date(2025, 5, 2), _date(2025, 5, 3)
    dates = [d1] * 100 + [d2] + [d3]
    blocks = ["b1"] * 101 + ["b2"]
    values = {
        "h3": [1.0] * 101 + [0.0],
        "market": [0.0] * 102,
    }
    boot = me._slate_bootstrap(values, dates, blocks, n_boot=2000, seed=20261001)
    assert boot["h3"]["point"] == pytest.approx(101.0 / 102.0)
    assert boot["market"]["point"] == pytest.approx(0.0)
    # every replicate stays on the per-row scale (old code could reach 100.0)
    assert boot["h3"]["p97.5"] == pytest.approx(200.0 / 201.0)
    assert boot["h3"]["p2.5"] == pytest.approx(2.0 / 3.0)
    # block b2 can never be dropped by a replicate (stratification)
    assert boot["h3"]["p2.5"] > 0.0
    assert boot["h3_minus_market"]["p97.5"] == pytest.approx(200.0 / 201.0)
    assert boot["h3_minus_market"]["p2.5"] == pytest.approx(2.0 / 3.0)
    # determinism under the same seed
    boot2 = me._slate_bootstrap(values, dates, blocks, n_boot=2000, seed=20261001)
    assert boot == boot2


def test_slate_bootstrap_hand_calculated_unequal_slate_sizes():
    """F-1 regression: hand-calculated expected results on UNEQUAL slate
    sizes (2 dates with 3 and 30 rows), independently derived without
    running the estimator.

    Case A (one block, two dates d1=3 rows @ 2.0, d2=30 rows @ 0.0):
    every replicate draws exactly n_dates_b = 2 dates (multinomial over the
    block's dates, p = 1/2 each) and combines ROW-WEIGHTED, so the resample
    mean is (3*2*k1) / (3*k1 + 30*(2-k1)) for k1 = #times d1 drawn:
        k1=0 -> 0.0    (P = 1/4)
        k1=1 -> 6/33   (P = 1/2)
        k1=2 -> 2.0    (P = 1/4)
    With 2000 resamples the 2.5/97.5 percentiles land strictly inside the
    k1=0 and k1=2 regions (each holds ~25% of replicates >> 2.5%), so they
    are EXACTLY 0.0 and 2.0. The point estimate 6/33 is a flat row mean and
    the interval endpoint 2.0 is on the same per-row scale; we do NOT assert
    that every interval brackets the point estimate in general.

    Case B (pooled = combined row-weighted across two blocks):
    b1 = d1 (3 rows @ 2.0) + d2 (30 rows @ 0.0); b2 = d3 (6 rows @ 1.0).
    b1 draws exactly 2 of ITS dates, b2 exactly 1 of ITS dates, so the only
    free draw is again k1:
        res = (3*2*k1 + 6*1) / (3*k1 + 30*(2-k1) + 6)
            = (6*k1 + 6) / (66 - 27*k1)
        k1=0 -> 6/66 = 1/11  (P = 1/4)
        k1=1 -> 12/39 = 4/13 (P = 1/2)
        k1=2 -> 18/12 = 1.5  (P = 1/4)
    The pooled point estimate is the combined row-weighted mean
    (3*2 + 30*0 + 6*1)/39 = 12/39 = 4/13 - NOT the mean of date means
    ((2+0+1)/3 = 1.0) and NOT the mean of block means. An estimator that
    averaged per-date means would return 0.5 at k1=1, not 4/13.
    """
    from datetime import date as _date
    d1, d2, d3 = _date(2025, 5, 1), _date(2025, 5, 2), _date(2025, 5, 3)

    # ---- case A: single block, 2 dates, 3 and 30 rows ----
    dates = [d1] * 3 + [d2] * 30
    blocks = ["b"] * 33
    boot = me._slate_bootstrap(
        {"h3": [2.0] * 3 + [0.0] * 30, "market": [0.0] * 33},
        dates, blocks, n_boot=2000, seed=20261001,
    )
    assert boot["h3"]["point"] == pytest.approx(6.0 / 33.0)
    assert boot["h3"]["p2.5"] == pytest.approx(0.0)
    assert boot["h3"]["p97.5"] == pytest.approx(2.0)
    # paired diff vs an all-zero competitor has the same exact endpoints
    assert boot["h3_minus_market"]["point"] == pytest.approx(6.0 / 33.0)
    assert boot["h3_minus_market"]["p2.5"] == pytest.approx(0.0)
    assert boot["h3_minus_market"]["p97.5"] == pytest.approx(2.0)
    boot_a2 = me._slate_bootstrap(
        {"h3": [2.0] * 3 + [0.0] * 30, "market": [0.0] * 33},
        dates, blocks, n_boot=2000, seed=20261001,
    )
    assert boot == boot_a2  # deterministic under the same seed

    # ---- case B: pooled = combined row-weighted across two blocks ----
    dates = [d1] * 3 + [d2] * 30 + [d3] * 6
    blocks = ["b1"] * 33 + ["b2"] * 6
    boot = me._slate_bootstrap(
        {"h3": [2.0] * 3 + [0.0] * 30 + [1.0] * 6, "market": [0.0] * 39},
        dates, blocks, n_boot=2000, seed=20261001,
    )
    assert boot["h3"]["point"] == pytest.approx(12.0 / 39.0)
    assert boot["h3"]["p2.5"] == pytest.approx(1.0 / 11.0)
    assert boot["h3"]["p97.5"] == pytest.approx(1.5)
    assert boot["h3_minus_market"]["p2.5"] == pytest.approx(1.0 / 11.0)
    assert boot["h3_minus_market"]["p97.5"] == pytest.approx(1.5)
    boot_b2 = me._slate_bootstrap(
        {"h3": [2.0] * 3 + [0.0] * 30 + [1.0] * 6, "market": [0.0] * 39},
        dates, blocks, n_boot=2000, seed=20261001,
    )
    assert boot == boot_b2


def test_roi_bootstrap_block_stratified():
    """Regression for the unstratified-pool ROI bootstrap (C3).

    Block b1: one bet (pnl +1.0). Block b2: two dates, one bet each
    (pnl -1.0). Stratified: every replicate draws 1 date from b1 and 2 dates
    from b2, so ROI is exactly (1 - 1 - 1) / 3 = -1/3 in EVERY replicate.
    The old unstratified pool let a replicate draw b1's date three times
    (ROI = +1.0) or drop b1 entirely (ROI = -1.0).
    """
    from datetime import date as _date
    d1, d2, d3 = _date(2025, 5, 1), _date(2025, 5, 2), _date(2025, 5, 3)
    dates = [d1, d2, d3]
    blocks = ["b1", "b2", "b2"]
    pnl = [1.0, -1.0, -1.0]
    boot = me._roi_bootstrap(pnl, dates, blocks, n_boot=2000, seed=20261001)
    assert boot["point"] == pytest.approx(-1.0 / 3.0)
    assert boot["p2.5"] == pytest.approx(-1.0 / 3.0)
    assert boot["p97.5"] == pytest.approx(-1.0 / 3.0)
    boot2 = me._roi_bootstrap(pnl, dates, blocks, n_boot=2000, seed=20261001)
    assert boot == boot2
