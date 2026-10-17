"""F-6 regression: confirmation rows never enter development pooled
points or bootstrap draws (card C3.3/C3.7). Synthetic fixtures only.

Test inventory (reconciled 2026-10-14, F-6 completion pass):

- tests/test_f6_confirmation_exclusion.py (020d2d8): THREE tests mirroring
  the overnight-p2 run_ladder.py pooled estimator on its own synthetic
  helper -- these do NOT invoke market_eval.run_score and read no outputs.
- tests/test_f6_confirmation_separation.py (d3de304, this file): ONE
  helper-level test driving market_eval._slate_bootstrap directly on
  synthetic frames -- also NOT a run_score invocation.
- THIS module's run_score regression (below, added in the F-6 completion
  pass): invokes the ACTUAL run_score on a synthetic prep dir +
  start_metrics with both dev and confirm blocks, reads the WRITTEN
  output files, and asserts population separation end to end (dev
  invariance under confirm-only mutation, confirm serialization,
  per-population ROI/count summaries, loud unknown-label failure, count
  reconciliation, F-4 guard).
"""
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_eval as me
import test_score_end_to_end as e2e


def _synth_obs(n_dev_dates=6, rows_per_date=10, n_conf_dates=2):
    rows = []
    rid = 0
    for b, nd in (("block_2024H2", n_dev_dates),
                  ("block_2025H1", n_dev_dates),
                  ("confirm_2025H2", n_conf_dates)):
        for d in range(nd):
            date = "20%02d-0%d-15" % (24 if b != "confirm_2025H2" else 25,
                                     (d % 8) + 1)
            for r in range(rows_per_date):
                p = 0.2 + 0.05 * ((rid + d) % 5)
                rows.append({
                    "game_pk": rid, "pitcher": rid, "line": 5.5,
                    "side": "over" if r % 2 == 0 else "under",
                    "book": "B", "block": b, "game_date": date,
                    "y_over_win": 1.0 if (rid % 3) else 0.0,
                    "y_under_win": 0.0 if (rid % 3) else 1.0,
                    "y_push": 0.0, "p_h3_over": p, "p_h3_under": 1 - p,
                    "p_h3_push": 0.0, "p_l5_over": p - 0.02,
                    "p_l5_under": 1 - (p - 0.02), "p_l5_push": 0.0,
                    "p_mkt_over": p + 0.01, "p_mkt_under": 1 - (p + 0.01),
                    "p_mkt_push": 0.0, "_row": rid,
                })
                rid += 1
    import polars as pl
    return pl.DataFrame(rows)


def _score_frames(obs):
    """Mirror run_score's per-row loss construction (3-way Brier parts)."""
    import polars as pl
    out = {}
    for a, p_over, p_under in (("h3", "p_h3_over", "p_h3_under"),
                               ("l5", "p_l5_over", "p_l5_under")):
        out[a] = obs.select(
            ((pl.col(p_over) - pl.when(pl.col("side") == "over")
              .then(pl.col("y_over_win")).otherwise(pl.col("y_under_win")))
             ** 2 + (pl.col("p_h3_push") * 0) ** 2
             + (pl.col(p_under) - pl.when(pl.col("side") == "over")
                .then(pl.col("y_under_win")).otherwise(pl.col("y_over_win")))
             ** 2).alias("_b"))["_b"].to_numpy()
    return out


def test_f6_confirmation_exclusion_known_answer():
    obs = _synth_obs()
    vals = _score_frames(obs)
    slates = obs["game_date"].to_list()
    blocks = obs["block"].to_list()
    is_conf = np.array([b == "confirm_2025H2" for b in blocks])
    dev = ~is_conf
    boot_dev = me._slate_bootstrap(
        {k: v[dev] for k, v in vals.items()},
        [d for d, m in zip(slates, dev) if m],
        [b for b, m in zip(blocks, dev) if m], 500, 20261001)
    boot_conf = me._slate_bootstrap(
        {k: v[is_conf] for k, v in vals.items()},
        [d for d, m in zip(slates, is_conf) if m],
        [b for b, m in zip(blocks, is_conf) if m], 500, 20261001)
    # dev pooled point must equal the dev-only row mean, independent of
    # confirmation rows entirely
    for a in vals:
        dev_point = float(vals[a][dev].mean())
        assert abs(boot_dev[a]["point"] - dev_point) < 1e-12
    # mutating ALL confirmation losses must leave dev draws unchanged
    vals2 = {k: v.copy() for k, v in vals.items()}
    for k in vals2:
        vals2[k][is_conf] = 999.0
    boot_dev2 = me._slate_bootstrap(
        {k: v[dev] for k, v in vals2.items()},
        [d for d, m in zip(slates, dev) if m],
        [b for b, m in zip(blocks, dev) if m], 500, 20261001)
    for a in vals:
        assert np.array_equal(boot_dev[a + "_point" if False else
                                       np.array([0])] if False else
                              np.array([boot_dev[a]["point"]]),
                              np.array([boot_dev2[a]["point"]]))
    # confirm results DO change
    conf_changed = any(
        abs(me._slate_bootstrap(
            {k: v[is_conf] for k, v in vals2.items()},
            [d for d, m in zip(slates, is_conf) if m],
            [b for b, m in zip(blocks, is_conf) if m], 200,
            20261001)[a]["point"] - boot_conf[a]["point"]) > 1.0
        for a in vals)
    assert conf_changed


# ---------------------------------------------------------------------------
# F-6 completion regression: invoke the ACTUAL run_score and read the
# WRITTEN outputs (synthetic prep + start_metrics, dev AND confirm blocks)
# ---------------------------------------------------------------------------

F6_DEV_DATES = [date(2024, 8, 1), date(2025, 2, 1)]
F6_CONFIRM_DATE = date(2025, 8, 1)


def _write_f6_synth(tmp_path, mutate_confirm=False):
    """Synthetic prep dir + start_metrics with BOTH dev and confirm blocks:

    - dev:  game_pk 1 (block_2024H2, 2024-08-01) and game_pk 2
      (block_2025H1, 2025-02-01), each with over+under side rows
    - confirm: game_pk 3 (confirm_2025H2, 2025-08-01), over+under
    - paper bets: dev bet (pk1 over @ +150) + confirm bet (pk3 over @ +150)
    - realized K: pk1=7, pk2=5 (dev); pk3=7 (confirm) -> both bets win

    mutate_confirm=True changes ONLY confirm-block data: realized_k 7 -> 3
    (flips the confirm bet win -> lose) and confirm H3/LOG5 probs shifted.
    """
    c1o = e2e._contract(1, 100, True, 5.5, "over", 150, 2.5,
                        0.4, 0.6, 0.4, 0.3, 0.7, F6_DEV_DATES[0])
    c1u = e2e._contract(1, 100, True, 5.5, "under", -200, 1.5,
                        0.4, 0.6, 0.4, 0.3, 0.7, F6_DEV_DATES[0])
    c2o = e2e._contract(2, 200, True, 5.5, "over", 150, 2.5,
                        0.4, 0.6, 0.4, 0.3, 0.7, F6_DEV_DATES[1],
                        block="block_2025H1")
    c2u = e2e._contract(2, 200, True, 5.5, "under", -200, 1.5,
                        0.4, 0.6, 0.4, 0.3, 0.7, F6_DEV_DATES[1],
                        block="block_2025H1")
    c3o = e2e._contract(3, 300, True, 5.5, "over", 150, 2.5,
                        0.4, 0.6, 0.4, 0.3, 0.7, F6_CONFIRM_DATE,
                        block="confirm_2025H2")
    c3u = e2e._contract(3, 300, True, 5.5, "under", -200, 1.5,
                        0.4, 0.6, 0.4, 0.3, 0.7, F6_CONFIRM_DATE,
                        block="confirm_2025H2")
    matched = pl.DataFrame(
        [c1o, c1u, c2o, c2u, c3o, c3u], schema=e2e.MC_COLS)
    if mutate_confirm:
        matched = matched.with_columns(
            pl.when(pl.col("block") == "confirm_2025H2")
            .then(pl.col("p_h3_win") - 0.3)
            .otherwise(pl.col("p_h3_win")).alias("p_h3_win"),
            pl.when(pl.col("block") == "confirm_2025H2")
            .then(pl.col("p_h3_lose") + 0.3)
            .otherwise(pl.col("p_h3_lose")).alias("p_h3_lose"),
            pl.when(pl.col("block") == "confirm_2025H2")
            .then(pl.col("p_l5_win") + 0.25)
            .otherwise(pl.col("p_l5_win")).alias("p_l5_win"),
            pl.when(pl.col("block") == "confirm_2025H2")
            .then(pl.col("p_l5_lose") - 0.25)
            .otherwise(pl.col("p_l5_lose")).alias("p_l5_lose"),
        )
    bets = matched.filter(
        (pl.col("game_pk").is_in([1, 3])) & (pl.col("side") == "over")
    ).with_columns(
        pl.col("pair_ts").alias("quote_ts"),
        pl.lit(1.0).alias("stake_units"),
        pl.lit(None, dtype=pl.Datetime("us", "UTC")).alias("close_quote_ts"),
        pl.lit(None, dtype=pl.Int64).alias("close_price"),
        pl.lit(None, dtype=pl.Float64).alias("clv_pct"),
    ).select(e2e.BET_COLS)
    realized = {1: 7, 2: 5, 3: 3 if mutate_confirm else 7}
    sm_rows = [
        {"game_pk": gpk, "side": "Top", "pitcher": p, "realized_k": realized[gpk]}
        for gpk, p in ((1, 100), (2, 200), (3, 300))
    ]
    sm_cols = (["game_pk", "side", "pitcher", "realized_k"]
               + ["base_h3_" + c for c in me.PERSISTED_COUNT_COLS]
               + ["base_l5_" + c for c in me.PERSISTED_COUNT_COLS])
    sm = pl.DataFrame(
        {c: ([0.5] * len(sm_rows) if c.startswith("base_") else
             [r.get(c, None) for r in sm_rows]) for c in sm_cols}
    )
    prep = tmp_path / ("prep2" if mutate_confirm else "prep")
    prep.mkdir()
    matched.write_parquet(prep / "matched_contracts.parquet")
    bets.write_parquet(prep / "paper_bets.parquet")
    manifest = {
        "outputs_sha256_16": {
            f: me.sha256_16(prep / f)
            for f in ["matched_contracts.parquet", "paper_bets.parquet"]
        }
    }
    (prep / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    sm_path = tmp_path / ("sm2.parquet" if mutate_confirm else "sm.parquet")
    sm.write_parquet(sm_path)
    return prep, sm_path


def _read_outputs(out):
    rd = lambda f: json.loads((out / f).read_text(encoding="utf-8"))
    return {
        "boot": rd("bootstrap.json"),
        "skill": rd("skill_metrics.json"),
        "confirm": rd("confirm_metrics.json"),
        "summary": rd("score_summary.json"),
        "ledger": pl.read_parquet(out / "bets_ledger.parquet"),
    }


def test_f6_run_score_population_separation_end_to_end(tmp_path):
    """Full regression against the ACTUAL run_score with WRITTEN outputs:

    (1) both dev and confirm blocks scored; counts reconcile exactly
        (dev + confirm rows = total, no silent row loss);
    (2) confirmation metrics are SERIALIZED (bootstrap.json `confirm` key
        AND confirm_metrics.json) with own bootstrap + effective counts;
    (3) a confirm-ONLY mutation (confirm realized K + predicted probs)
        leaves every dev point/CI, dev skill block, dev ROI, and dev count
        summary BIT-IDENTICAL while confirmation metrics change;
    (4) ledger rows carry the population label.
    """
    prep, sm = _write_f6_synth(tmp_path)
    out = tmp_path / "score"
    me.run_score(prep, sm, out, seed=20261001, n_boot=200)
    a = _read_outputs(out)

    # ---- counts reconcile: dev + confirm = total ----
    eff = a["skill"]["effective_counts"]
    assert eff["dev_rows"] == 4 and eff["confirm_rows"] == 2
    assert eff["dev_rows"] + eff["confirm_rows"] == eff["contract_side_rows"]
    assert sorted(eff["rows_by_block"]) == [
        "block_2024H2", "block_2025H1", "confirm_2025H2"]
    assert a["summary"]["bets"]["n"] == 2
    assert (a["summary"]["bets_by_population"]["dev"]["n"]
            + a["summary"]["bets_by_population"]["confirm"]["n"]) == 2

    # ---- confirmation metrics serialized, with own bootstrap + counts ----
    assert a["confirm"]["population"] == ["confirm_2025H2"]
    assert a["confirm"]["n_rows"] == 2
    assert a["confirm"]["n_dates"] == 1
    assert set(a["confirm"]["h3_minus_l5"]) == {"point", "p2.5", "p97.5"}
    assert a["boot"]["confirm"]["n_rows"] == 2
    assert a["boot"]["confirm"]["h3_minus_l5"] == a["confirm"]["h3_minus_l5"]
    assert a["skill"]["confirm"]["n_rows"] == 2
    assert a["skill"]["confirm"]["per_tier"]["A_verified_clock"]["n_rows"] == 2

    # ---- ledger carries the population label ----
    led = a["ledger"].sort("game_pk")
    assert dict(zip(led["game_pk"].to_list(),
                    led["population"].to_list())) == {1: "dev", 3: "confirm"}

    # ---- confirm-only mutation ----
    prep2, sm2 = _write_f6_synth(tmp_path, mutate_confirm=True)
    out2 = tmp_path / "score2"
    me.run_score(prep2, sm2, out2, seed=20261001, n_boot=200)
    b = _read_outputs(out2)

    # dev points/CIs/skill/ROI/counts BIT-IDENTICAL
    assert b["boot"]["brier"] == a["boot"]["brier"]
    assert b["boot"]["paper_roi"]["dev"] == a["boot"]["paper_roi"]["dev"]
    assert b["skill"]["dev"] == a["skill"]["dev"]
    assert b["skill"]["effective_counts"] == a["skill"]["effective_counts"]
    assert (b["summary"]["bets_by_population"]["dev"]
            == a["summary"]["bets_by_population"]["dev"])
    assert b["summary"]["skill_headline"] == a["summary"]["skill_headline"]
    assert (b["skill"]["count_layer_persisted_reused"]["dev"]
            == a["skill"]["count_layer_persisted_reused"]["dev"])

    # confirmation metrics CHANGE and stay serialized
    assert b["confirm"]["brier"] != a["confirm"]["brier"]
    assert b["confirm"]["h3_minus_l5"] != a["confirm"]["h3_minus_l5"]
    assert b["boot"]["confirm"]["brier"] != a["boot"]["confirm"]["brier"]
    assert (b["skill"]["confirm"]["brier_skill_vs_market"]
            != a["skill"]["confirm"]["brier_skill_vs_market"])
    assert (b["boot"]["paper_roi"]["confirm"]
            != a["boot"]["paper_roi"]["confirm"])  # win -> lose flip
    assert (b["summary"]["bets_by_population"]["confirm"]["roi_per_bet"]
            != a["summary"]["bets_by_population"]["confirm"]["roi_per_bet"])
    assert b["summary"]["confirm_headline"]["brier_h3"] != \
        a["summary"]["confirm_headline"]["brier_h3"]


def test_f6_run_score_unknown_block_label_fails_loud(tmp_path):
    """An unregistered block label must fail loud BEFORE any output."""
    prep, sm = _write_f6_synth(tmp_path)
    matched = pl.read_parquet(prep / "matched_contracts.parquet").with_columns(
        pl.when(pl.col("game_pk") == 3)
        .then(pl.lit("block_mystery"))
        .otherwise(pl.col("block")).alias("block")
    )
    bad = tmp_path / "prep_bad"
    bad.mkdir()
    matched.write_parquet(bad / "matched_contracts.parquet")
    import shutil
    shutil.copyfile(prep / "paper_bets.parquet", bad / "paper_bets.parquet")
    (bad / "manifest.json").write_text(json.dumps({
        "outputs_sha256_16": {
            f: me.sha256_16(bad / f)
            for f in ["matched_contracts.parquet", "paper_bets.parquet"]
        }
    }), encoding="utf-8")
    with pytest.raises(me.PopulationLabelError) as ei:
        me.run_score(bad, sm, tmp_path / "score_bad", n_boot=50)
    msg = str(ei.value)
    assert "block_mystery" in msg
    assert "confirm_2025H2" in msg  # names the registered set
    assert not (tmp_path / "score_bad").exists()


def test_f6_run_score_null_block_label_fails_loud(tmp_path):
    """Null block labels are unknown too (fail loud, named as <null>)."""
    prep, sm = _write_f6_synth(tmp_path)
    matched = pl.read_parquet(prep / "matched_contracts.parquet").with_columns(
        pl.when(pl.col("game_pk") == 2)
        .then(pl.lit(None, dtype=pl.String).alias("block"))
        .otherwise(pl.col("block"))
    )
    bad = tmp_path / "prep_null"
    bad.mkdir()
    matched.write_parquet(bad / "matched_contracts.parquet")
    import shutil
    shutil.copyfile(prep / "paper_bets.parquet", bad / "paper_bets.parquet")
    (bad / "manifest.json").write_text(json.dumps({
        "outputs_sha256_16": {
            f: me.sha256_16(bad / f)
            for f in ["matched_contracts.parquet", "paper_bets.parquet"]
        }
    }), encoding="utf-8")
    with pytest.raises(me.PopulationLabelError) as ei:
        me.run_score(bad, sm, tmp_path / "score_null", n_boot=50)
    assert "<null>" in str(ei.value)


def test_f6_opt_in_guard_remains_effective(tmp_path, capsys):
    """F-4 guard still fires: --score without the flag refuses (exit 2)
    before reading inputs or writing outputs, even with valid fixtures."""
    prep, sm = _write_f6_synth(tmp_path)
    out = tmp_path / "score_refused"
    rc = me.main([
        "--score", "--prep-dir", str(prep), "--start-metrics", str(sm),
        "--score-dir", str(out),
    ])
    assert rc == 2
    assert not out.exists()
    assert "--i-accept-outcome-scoring" in capsys.readouterr().err
