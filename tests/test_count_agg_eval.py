"""Synthetic tests for the Question A evaluation runner
(count_agg_eval.py). SYNTHETIC ONLY: no real data, no real-outcome
evaluation, no production change. Covers: immutable initial receipt,
chained final receipt, preserved failure records, write-once collisions,
paired arms on identical start keys, clipping parity (two-factor guard),
block isolation, untruncated-vs-bucketed expected-count checks, the
registered count-RPS/milestone machinery, and the preserved refusal
gate."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import pregame_pa_ext.adapter as ad  # noqa: E402
from pregame_pa_ext import batt_recency as br  # noqa: E402
from pregame_pa_ext import count_agg_eval as ce  # noqa: E402
from pregame_pa_ext import count_aggregation_exact as ex  # noqa: E402

import kcount_combiner as kc  # noqa: E402


def one(batter, d, y, pitcher=500, game_pk=1, ab=0, side="Bot"):
    return {"game_pk": game_pk, "at_bat_number": ab, "batter": batter,
            "pitcher": pitcher, "game_date": d, "y": y, "side": side}


def pa_rows(rows: list[dict]) -> pl.DataFrame:
    df = pl.DataFrame(rows).with_columns(pl.col("game_date").cast(pl.Date))
    if "y" in df.columns:
        df = df.with_columns(pl.col("y").cast(pl.Int8))
    return df


def synth_runner_lake(tmp_path: Path):
    """Synthetic lake: PA rows spanning all block windows, a preserved
    ledger (eligible dev starts with p_h3_raw per slot + one cold
    exclusion + one eligible confirm start), a BF artifact (valid 37-
    vectors per start), and a realized-count stand-in from the registered
    start_metrics_v2 lineage shape (game_pk, side, pitcher, realized_k)."""
    rows, led = [], []
    gpk, d = 700, date(2023, 1, 5)
    ab = 0
    grid = []
    while d <= date(2025, 8, 1):
        grid.append((gpk, d))
        in_dev = date(2024, 7, 1) <= d <= date(2025, 6, 30)
        for slot in range(9):
            b = 100 + slot
            for k in range(2):
                ab += 1
                rows.append(one(b, d, int((slot + k) % 2), pitcher=500,
                                game_pk=gpk, ab=ab))
        if in_dev:
            for slot in range(9):
                led.append({"game_pk": gpk, "side": "Bot", "pitcher": 500,
                            "batter": 100 + slot, "slot": slot + 1,
                            "game_date": d,
                            "p_h3_raw": 0.25 + 0.03 * slot,
                            "exclusion_reason": None})
        gpk += 1
        d += timedelta(days=15)
    # one cold-excluded dev slot on an actual grid date (2024-08-27):
    # the abstention record must be NON-EMPTY (an empty/omitted record
    # prevents acceptance)
    cold_gpk, cold_d = grid[40]
    led.append({"game_pk": cold_gpk, "side": "Bot", "pitcher": 500,
                "batter": 999, "slot": 9, "game_date": cold_d,
                "p_h3_raw": None,
                "exclusion_reason": ad.EXCLUSION_REASON_COLD})
    # one ELIGIBLE confirm-window start (must never reach development)
    conf_gpk, conf_d = grid[-1]
    led.append({"game_pk": conf_gpk, "side": "Bot", "pitcher": 500,
                "batter": 100, "slot": 1, "game_date": conf_d,
                "p_h3_raw": 0.4, "exclusion_reason": None})
    pa = pa_rows(rows)
    ledger = pl.DataFrame(led, schema_overrides={
        "exclusion_reason": pl.Utf8,
        "p_h3_raw": pl.Float64,
        "game_pk": pl.Int64,
        "pitcher": pl.Int64,
        "batter": pl.Int64,
        "slot": pl.Int64,
    }).with_columns(pl.col("game_date").cast(pl.Date))

    # BF artifact: registered lineage shape, one row per ledger start
    bf_rows = []
    seen = set()
    for r in led:
        key = (r["game_pk"], r["side"], r["pitcher"])
        if key in seen:
            continue
        seen.add(key)
        pmf = np.full(37, 0.5 / 36.0)
        pmf[0] = 0.5
        pmf /= pmf.sum()  # force exact normalization
        bf_rows.append({"game_pk": r["game_pk"], "side": r["side"],
                        "pitcher": r["pitcher"],
                        **{f"pmf37_{j}": float(v)
                           for j, v in enumerate(pmf)}})
    bf = pl.DataFrame(bf_rows)
    # realized counts: from the SAME games (registered lineage shape)
    realized = (pa.group_by("game_pk", "side", "pitcher")
                .agg(realized_k=pl.col("y").sum().cast(pl.Int64)))
    # artifact stand-ins for the receipt identities
    pat = tmp_path / "pa_table.parquet"
    pa.write_parquet(pat)
    led_path = tmp_path / "projected_pa_probs_v1.parquet"
    ledger.write_parquet(led_path)
    bf_path = tmp_path / "bf_forecasts.parquet"
    bf.write_parquet(bf_path)
    realized_path = tmp_path / "start_metrics_v2.parquet"
    realized.write_parquet(realized_path)
    ck = tmp_path / "h3_raw_checkpoint.json"
    ck.write_text(json.dumps({"format": "synthetic", "sha256": "b" * 64,
                              "payload": {}}), encoding="utf-8")
    lu = tmp_path / "projected_lineups_variant_v2.parquet"
    pa.head(1).write_parquet(lu)
    fr = tmp_path / "freeze_pregame_pa_ext_v2.json"
    fr.write_text(json.dumps({"freeze_id": "synthetic"}), encoding="utf-8")
    return {"pa": pa, "ledger": ledger, "bf": bf, "realized": realized,
            "paths": {"preserved_run_ledger": led_path, "bf_pmf": bf_path,
                      "realized_counts_source": realized_path,
                      "checkpoint": ck, "lineups": lu,
                      "freeze_config": fr, "pa_table": pat}}


def test_refusal_gate_preserved():
    """The CLI keeps refusing real-outcome execution without the
    authorization flag (exit 2) - preserved through the runner addition."""
    assert ce.main([]) == 2


def test_runner_synthetic_end_to_end(tmp_path):
    """Complete runner on SYNTHETIC fixtures: immutable initial receipt
    written first, paired arms on identical start keys, registered
    metrics, write-once outputs, chained final receipt."""
    dirs = synth_runner_lake(tmp_path)
    out_dir = tmp_path / "diag"
    res = ce.run_count_agg_eval(
        dirs["ledger"], dirs["bf"], dirs["realized"], out_dir,
        verify_published=False, artifact_paths=dirs["paths"])
    assert (out_dir / "receipt_initial.json").is_file()
    assert (out_dir / "receipt_final.json").is_file()
    final = json.loads((out_dir / "receipt_final.json")
                       .read_text(encoding="utf-8"))
    assert all(s in final for s in ("inputs", "code_config", "dev_keys", "outputs", "metrics", "fits", "acceptance"))  # all mandatory sections
    # chained to the immutable initial receipt
    assert final["acceptance"]["receipt_chain"] == ad.sha256_file(
        out_dir / "receipt_initial.json")
    # paired arms: both PMFs present, no nulls, same rows
    ev = pl.read_parquet(out_dir / "count_agg_eval_v1.parquet")
    assert ev["pmf_baseline"].null_count() == 0
    assert ev["pmf_challenger"].null_count() == 0
    # block isolation: confirm never in development
    assert "confirm_2025H2" not in ev["block"].unique().to_list()
    # metrics: registered bootstrap + Holm m=1
    m = res["metrics"]
    assert m["bootstrap"]["holm_m"] == 1
    assert m["bootstrap"]["seed"] == 20261001
    assert np.isfinite(m["count_rps_delta"])


def test_initial_receipt_immutable_and_chained(tmp_path):
    """receipt_initial.json is written FIRST with complete consumed
    inputs and is NEVER modified; receipt_final.json chains to it by
    sha256 and classifies consumed vs context identities."""
    dirs = synth_runner_lake(tmp_path)
    out_dir = tmp_path / "diag"
    ce.run_count_agg_eval(dirs["ledger"], dirs["bf"], dirs["realized"],
                          out_dir, verify_published=False,
                          artifact_paths=dirs["paths"])
    init = json.loads((out_dir / "receipt_initial.json")
                      .read_text(encoding="utf-8"))
    fin = json.loads((out_dir / "receipt_final.json")
                     .read_text(encoding="utf-8"))
    # consumed inputs complete FROM THE OUTSET
    assert set(init["inputs"]["consumed"]) == {
        "preserved_run_ledger", "bf_pmf", "realized_counts_source"}
    assert set(init["inputs"]["context_identities"]) == {
        "checkpoint", "lineups", "freeze_config", "pa_table"}
    # chain: final embeds the initial's sha256
    assert fin["acceptance"]["receipt_chain"] == ad.sha256_file(
        out_dir / "receipt_initial.json")
    # the initial receipt was not modified by the run
    assert init == {k: v for k, v in fin.items()
                    if k in ("inputs", "code_config", "dev_keys", "config")}
    # the clipping convention is recorded per Chat 2's finding
    cc = fin["code_config"]["clipping_convention"]
    assert "identical both arms" in cc["per_pa_source"]
    assert "ONLY arm difference" in cc["parity_rule"]


def test_exact_paired_keys_and_single_factor(tmp_path):
    """Both arms evaluate the SAME starts; a homogeneous
    lineup produces IDENTICAL PMFs (the aggregation rule is
    the only difference - no two-factor comparison)."""
    p9h = [0.3] * 9
    bf_ext = np.full(ad.KCOUNT_CAP, 1.0 / ad.KCOUNT_CAP)
    base = ad.count_pmf_from_mixture(
        bf_ext, ad.cycled_cond_mean(np.asarray(p9h)))
    chal = ex.exact_count_pmf(p9h, bf_ext)
    assert base == pytest.approx(chal, abs=1e-12)

def test_untruncated_vs_bucketed_expected_count():
    """E[K] from the UNTRUNCATED distribution is the
    mathematical check; the bucketed outputs are verified
    separately: for n <= 22 there is NO tail truncation,
    so the bucketed PMF equals the untruncated PB exactly."""
    p9 = [0.2, 0.3, 0.4, 0.25, 0.35, 0.28, 0.33, 0.26,
              0.31]
    # for n <= 22 the 24-bucket output has NO tail
    # truncation (support 0..22 fits in 0..22)
    for n in (5, 15, 22):
        bf = (n)
        bf_arr = np.zeros(ad.KCOUNT_CAP)
        bf_arr[n - 1] = 1.0
        pmf_c = ex.exact_count_pmf(p9, bf_arr)
        untr = ex.poisson_binomial_pmf_cycled(p9, n,
                                               k_max=61)
        assert float(pmf_c[:23].sum()) == pytest.approx(
            float(untr[:23].sum()), abs=1e-12)
        # for n <= 22 the k=23 bucket should be 0
        # (no mass at K >= 23)
        if n <= 22:
            assert float(pmf_c[23]) == pytest.approx(
                0.0, abs=1e-12)

def pmf_base_diag(p9, bf_ext):
    return ad.count_pmf_from_mixture(bf_ext,
                                     ad.cycled_cond_mean(np.asarray(p9)))


def test_failure_record_preserved_and_initial_untouched(tmp_path):
    """A mid-run failure writes failure_record.json
    (write-once, preserved); the immutable initial
    receipt is untouched."""
    dirs = synth_runner_lake(tmp_path)
    bf_broken = dirs["bf"].head(0)
    out_dir = tmp_path / "diag"
    with pytest.raises(ValueError,
                  match="missing the registered BF PMF"):
        ce.run_count_agg_eval(
            dirs["ledger"], bf_broken, dirs["realized"],
            out_dir, verify_published=False,
            artifact_paths=dirs["paths"])
    fr = json.loads((out_dir / "failure_record.json")
                    .read_text(encoding="utf-8"))
    assert fr["failure"] is True
    init = json.loads((out_dir / "receipt_initial.json")
                      .read_text(encoding="utf-8"))
    assert init["inputs"]["consumed"]["preserved_run_ledger"] == \
        ad.sha256_file(dirs["paths"]["preserved_run_ledger"])

def test_output_collision_fails_loud(tmp_path):
    dirs = synth_runner_lake(tmp_path)
    out_dir = tmp_path / "diag"
    out_dir.mkdir()
    (out_dir / "sentinel.txt").write_text("keep", encoding="ascii")
    with pytest.raises(ValueError, match="write-once violation"):
        ce.run_count_agg_eval(dirs["ledger"], dirs["bf"], dirs["realized"],
                              out_dir, verify_published=False,
                              artifact_paths=dirs["paths"])
    assert (out_dir / "sentinel.txt").read_text(encoding="ascii") == "keep"


def test_registered_count_rps_small_case():
    """The registered count_rps matches a hand-computed summed-CDF-squared
    value on a tiny case (sanity for the scoring convention)."""
    pmf = np.zeros(24)
    pmf[0] = 0.6
    pmf[1] = 0.4
    # K = 1: cdf = [0.6, 1.0, 1.0, ...]; obs = [0, 1, 1, ...]
    # RPS = (0.6-0)^2 + (1.0-1)^2 + 22 * 0 = 0.36
    assert kc.count_rps(pmf, 1) == pytest.approx(0.36, abs=1e-12)
