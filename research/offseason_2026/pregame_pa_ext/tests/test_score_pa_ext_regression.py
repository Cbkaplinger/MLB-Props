"""Regression tests for the score_pa_ext.py secondary-bootstrap frame fix.

Defect (attempt full_run-1): the secondary descriptive bootstrap read the
uniq_{h3,l5}_{rps,logscore} columns from `lab`, but those columns exist only
on `cmp` (the v3 metrics join built inside the machinery-equivalence gate).
The first real execution crashed with

    polars.exceptions.ColumnNotFoundError: "uniq_h3_rps" not found

BEFORE any output file was written (run log preserved at
C:\\Users\\ckaplinger\\MLB-Props-Research\\pregame-pa-ext-v1\\outputs\\
full_run\\scoring_run_log.txt, sha256 0741080...).

Fix under test: the uniq_* side is read from `cmp`; both frames are sorted
on the full start key (game_date, game_pk, side, pitcher) and an explicit
cmp/lab key-alignment assert runs before the bootstrap.

All tests here are synthetic. No frozen-card input (payload / preds / v3
metrics) is read; only the shared machinery modules are imported.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

WORK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORK / "scripts"))
import paext_core as core  # noqa: E402
import score_pa_ext  # noqa: E402

KEY_COLS = ["game_date", "game_pk", "side", "pitcher"]
N_DATES = 2
STARTS_PER_DATE = 2
N_STARTS = N_DATES * STARTS_PER_DATE
SEED = 20261014

PREDS_SCHEMA = {"game_pk": pl.Int64, "pitcher": pl.Int64,
                "game_date": pl.Date, "y": pl.Int8}


def _old_paired(lab: pl.DataFrame, a: str, b: str, dates) -> dict:
    """The DEFECTED pairing, verbatim from pre-fix score_pa_ext.py: both
    sides read from `lab`. Kept only to demonstrate the crash."""
    return core.v1.slate_bootstrap(
        lab[a].to_numpy() - lab[b].to_numpy(), dates)


def _fixed_paired(lab: pl.DataFrame, cmp: pl.DataFrame, a: str, b: str,
                  dates) -> dict:
    """The FIXED pairing: uniq_* side read from `cmp` (key-aligned)."""
    return core.v1.slate_bootstrap(
        lab[a].to_numpy() - cmp[b].to_numpy(), dates)


def _synthetic_world():
    rng = np.random.default_rng(SEED)
    starts = []
    pk = 100
    for d in (date(2024, 7, 8), date(2024, 7, 9)):
        for side in ("Top", "Bot"):
            starts.append({"game_pk": pk, "side": side, "pitcher": 500 + pk,
                           "game_date": d})
            pk += 1
    bf_rows, preds_rows, payload_rows, uniq_rows = [], [], [], []
    for s in starts:
        n_bf = int(rng.integers(18, 23))
        ys = rng.integers(0, 2, size=n_bf)
        k_real = int(ys.sum())
        bf_rows.append({**s, "realized_bf": n_bf})
        for j, y in enumerate(ys):
            preds_rows.append({"game_pk": s["game_pk"],
                               "pitcher": s["pitcher"],
                               "game_date": s["game_date"], "y": int(y)})
        bf37 = rng.dirichlet(np.full(37, 0.7))
        row = {**s,
               **{f"pmf37_{j}": float(bf37[j]) for j in range(37)}}
        for tag in ("h3_raw", "l5_raw"):
            p, mean_k, _, _ = core.start_count_pmf(
                rng.uniform(0.15, 0.35, 9), bf37)
            row.update({f"pmf_{tag}_{k}": float(p[k])
                        for k in range(core.K_MAX)})
            row[f"mean_k_{tag}"] = float(mean_k)
        for tag in ("h3_cal", "l5_cal"):
            row.update({f"p_{tag}_{i}": float(rng.uniform(0.15, 0.35))
                        for i in range(1, 10)})
        payload_rows.append(row)
        # accepted v3 uniq_* metrics recomputed from the SAME stored cal
        # probs + stored bf37 so the <=1e-12 bit-identity gate passes
        u = {**s}
        for tag, base in (("h3_cal", "h3"), ("l5_cal", "l5")):
            p9 = np.array([row[f"p_{tag}_{i}"] for i in range(1, 10)])
            p, mean_k, _, _ = core.start_count_pmf(p9, bf37)
            u[f"uniq_{base}_rps"] = core.count_rps(p, k_real)
            u[f"uniq_{base}_logscore"] = core.count_logscore(p, k_real)
            u[f"uniq_{base}_err_mean_k"] = float(mean_k) - float(k_real)
        uniq_rows.append(u)
    payload = pl.DataFrame(payload_rows)
    v3 = pl.DataFrame(uniq_rows)
    bf_forecasts = pl.DataFrame(bf_rows)
    preds = pl.DataFrame(preds_rows, schema=PREDS_SCHEMA)
    return payload, v3, bf_forecasts, preds


@pytest.fixture(scope="module")
def scorer_env(tmp_path_factory):
    payload, v3, bf_forecasts, preds = _synthetic_world()
    work = tmp_path_factory.mktemp("paext_score")
    (work / "data").mkdir()
    (work / "reports").mkdir()
    bfw = work / "bfw"
    p2data = work / "p2data"
    bfw.mkdir()
    p2data.mkdir()
    bf_forecasts.write_parquet(bfw / "bf_forecasts.parquet")
    block_files = list(core.PREDS.values())
    for i, fname in enumerate(block_files):
        (preds if i == 0 else preds.clear()).write_parquet(p2data / fname)
    payload_path = work / "data" / "predictor_payload.parquet"
    payload.write_parquet(payload_path)
    import hashlib
    sha = hashlib.sha256(payload_path.read_bytes()).hexdigest()
    manifest_path = work / "manifest.json"
    manifest_path.write_text(json.dumps(
        {"payload": {"sha256": sha, "rows": N_STARTS}}), encoding="ascii")
    v3_path = work / "start_metrics_v3.parquet"
    v3.write_parquet(v3_path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(core, "PAYLOAD", payload_path)
        mp.setattr(core, "MANIFEST", manifest_path)
        mp.setattr(core, "BFW", bfw)
        mp.setattr(core, "P2_DATA", p2data)
        mp.setattr(core, "EXPECTED_N_STARTS", N_STARTS)
        mp.setattr(score_pa_ext, "WORK", work)
        mp.setattr(score_pa_ext, "V3_METRICS", v3_path)
        yield {"work": work, "payload": payload, "v3": v3,
               "bf_forecasts": bf_forecasts}


def _lab_without_uniq(payload: pl.DataFrame) -> pl.DataFrame:
    """The scorer's lab state at bootstrap time: payload + realized labels
    + raw-arm per-start metrics; NO uniq_* columns (they live on cmp)."""
    fc = payload.select(
        "game_pk", "side", "pitcher", "game_date")
    realized = fc.with_columns(
        pl.int_range(0, fc.height).alias("realized_k"))
    lab = payload.join(realized, on=KEY_COLS, how="inner").sort(KEY_COLS)
    k_all = lab["realized_k"].to_numpy()
    cols = {}
    for tag in ("h3_raw", "l5_raw"):
        pk_all = lab.select(core.PMF_COLS[tag]).to_numpy()
        cols[f"{tag}_rps"] = [core.count_rps(pk, int(k))
                              for pk, k in zip(pk_all, k_all)]
        cols[f"{tag}_logscore"] = [core.count_logscore(pk, int(k))
                                   for pk, k in zip(pk_all, k_all)]
    return lab.with_columns(
        *[pl.Series(name, vals) for name, vals in cols.items()])


def test_reproduces_missing_uniq_column_failure(scorer_env):
    """(a) The defected code path reads uniq_* from lab and must crash with
    exactly the ColumnNotFoundError recorded in the full_run-1 run log."""
    lab = _lab_without_uniq(scorer_env["payload"])
    dates = lab["game_date"].to_numpy()
    assert "uniq_h3_rps" not in lab.columns
    with pytest.raises(pl.exceptions.ColumnNotFoundError,
                       match='"uniq_h3_rps" not found'):
        _old_paired(lab, "h3_raw_rps", "uniq_h3_rps", dates)


def test_fixed_bootstrap_reads_from_cmp_with_key_alignment(scorer_env):
    """(b) With the fix, the secondary bootstrap runs from cmp: both arms
    resample over the same slate dates and the paired diffs are exact."""
    payload = scorer_env["payload"]
    lab = _lab_without_uniq(payload)
    cmp = lab.join(
        scorer_env["v3"], on=KEY_COLS, how="inner", suffix="_v3")
    assert cmp.height == N_STARTS
    # scorer's alignment guard: sorted cmp keys must equal sorted lab keys
    cmp = cmp.sort(KEY_COLS)
    assert cmp.select(KEY_COLS).equals(lab.select(KEY_COLS))
    dates = lab["game_date"].to_numpy()
    results = {}
    for tag, base in (("h3_raw", "h3"), ("l5_raw", "l5")):
        for metric in ("rps", "logscore"):
            results[f"{tag}_{base}_{metric}"] = _fixed_paired(
                lab, cmp, f"{tag}_{metric}", f"uniq_{base}_{metric}", dates)
    # both arms paired over the SAME slate dates
    n_dates = {r["n_dates"] for r in results.values()}
    assert n_dates == {N_DATES}
    # diffs reproduce exactly from the aligned frames
    for tag, base in (("h3_raw", "h3"), ("l5_raw", "l5")):
        for metric in ("rps", "logscore"):
            r = results[f"{tag}_{base}_{metric}"]
            want = float((lab[f"{tag}_{metric}"].to_numpy()
                          - cmp[f"uniq_{base}_{metric}"].to_numpy()).mean())
            assert r["mean_row_weighted"] == pytest.approx(want, abs=0.0)
            assert len(r["ci95"]) == 2
            assert all(np.isfinite(r["ci95"]))
            assert 0.0 <= r["share_resamples_diff_below_zero"] <= 1.0
    # a misaligned cmp (shuffled rows) must FAIL the alignment guard
    assert not cmp.reverse().select(KEY_COLS).equals(lab.select(KEY_COLS))


def test_full_scorer_end_to_end(scorer_env):
    """(c) Full scorer in a temp directory: all output files written,
    report.json complete, all bootstrap/aggregate values finite, and the
    fixed secondary comparisons present with the bit-identity gate PASS."""
    score_pa_ext.main()
    work = scorer_env["work"]
    out_parquet = work / "data" / "start_metrics_paext.parquet"
    report_path = work / "report_scored.json"
    summary_path = work / "reports" / "scoring_summary.txt"
    assert out_parquet.exists() and report_path.exists()
    assert summary_path.exists()
    report = json.loads(report_path.read_text(encoding="ascii"))
    assert report["n_starts"] == N_STARTS
    assert report["label_join_exclusions"] == {"n_no_pas": 0,
                                               "n_bf_mismatch": 0}
    assert report["bootstrap"]["n"] == core.BOOT_N
    assert report["bootstrap"]["seed"] == core.BOOT_SEED
    assert report["bootstrap"]["unit"] == "slate-date (game_date)"
    for tag in ("h3_cal", "l5_cal"):
        bid = report["machinery_bit_identity_vs_v3_uniq"][tag]
        assert bid["rps_max_abs_diff"] <= 1e-12
        assert bid["logscore_max_abs_diff"] <= 1e-12
        assert bid["mean_k_max_abs_diff"] <= 1e-12
    expected_keys = (
        ["h3_raw_minus_l5_raw_rps", "h3_raw_minus_l5_raw_logscore"]
        + [f"h3_raw_minus_l5_raw_brier_ge{m}" for m in core.MILESTONES]
        + [f"{t}_minus_v3uniq_{b}_{m}"
           for t, b in (("h3_raw", "h3"), ("l5_raw", "l5"))
           for m in ("rps", "logscore")])
    assert sorted(report["bootstrap_results"]) == sorted(expected_keys)
    for key, b in report["bootstrap_results"].items():
        assert np.isfinite(b["mean_row_weighted"]), key
        assert np.all(np.isfinite(b["ci95"])), key
        assert b["n_dates"] == N_DATES, key
    for tag in ("h3_raw", "l5_raw"):
        assert report["aggregate"][tag] and all(
            np.isfinite(v) for v in report["aggregate"][tag].values())
    m = pl.read_parquet(out_parquet)
    assert m.height == N_STARTS
    for tag in ("h3_raw", "l5_raw"):
        for col in (f"{tag}_rps", f"{tag}_logscore",
                    f"{tag}_rmse_mean_k",
                    *[f"{tag}_brier_ge{ms}" for ms in core.MILESTONES]):
            assert np.isfinite(m[col].to_numpy()).all(), col
    summary = summary_path.read_text(encoding="ascii")
    assert "pregame-pa-ext-v1 SCORING summary" in summary
    assert str(N_STARTS) in summary
