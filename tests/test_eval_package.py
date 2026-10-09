"""Tests for the reusable evaluation package (synthetic artifacts)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import eval_package as ev  # noqa: E402
import kcount_combiner as kc  # noqa: E402
import run_kcount_integration_2023 as rkc  # noqa: E402


def synth_run(tmp_path, n=40, seed=5):
    rng = np.random.default_rng(seed)
    rows, pkA, pkB = [], [], []
    for i in range(n):
        pa = int(rng.integers(12, 30))
        pk_a = rkc.point_exposure_pmf(pa, 0.22)
        pk_b = rkc.point_exposure_pmf(pa, 0.24)
        kk = int(rng.choice(24, p=pk_a / pk_a.sum()))
        pkA.append(pk_a)
        pkB.append(pk_b)
        rows.append({
            "origin": "2023-04-15" if i < n // 2 else "2023-07-01",
            "game_pk": 1000 + i, "pitcher": 500 + (i % 7),
            "game_date": "2023-05-%02d" % (1 + i % 28),
            "PA": pa, "K": kk,
            "rps_A": kc.count_rps(pk_a, kk),
            "rps_B": kc.count_rps(pk_b, kk),
            "mean_A": 0.22 * pa, "mean_B": 0.24 * pa,
        })
    d = tmp_path
    d.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_csv(d / "predictions.csv")
    cols = (["pkA_%02d" % i for i in range(24)]
            + ["pkB_%02d" % i for i in range(24)])
    pl.DataFrame(np.hstack([np.vstack(pkA), np.vstack(pkB)]),
                 schema=cols).write_parquet(d / "pmfs.parquet")
    return d / "predictions.csv", d / "pmfs.parquet"


def test_evaluate_metrics_sanity(tmp_path):
    pc, pp = synth_run(tmp_path, n=400, seed=11)
    m = ev.evaluate(pc, pp, ["A", "B"],
                    mean_cols={"A": "mean_A", "B": "mean_B"},
                    claim_ids={"TEST-1": "synthetic demo"})
    assert m["n"] == 400
    assert m["verification"]["A"]["status"] == "OK"
    assert m["verification"]["B"]["status"] == "OK"
    for a in ("A", "B"):
        assert 0 < m["arms"][a]["mean_logscore"] < 50
        assert m["arms"][a]["logscore_floor_rows"] == 0
        assert "ge12" in m["arms"][a]["ladder"]
        assert 0.7 < m["arms"][a]["variance_accounting"][
            "ratio_obs_over_total"] < 1.3
        assert sum(m["arms"][a]["pit"]["hist"]) == 400
    assert set(m["by_origin"]) == {"2023-04-15", "2023-07-01"}
    assert m["claim_ids"]["TEST-1"] == "synthetic demo"
    assert len(m["artifact_hashes"]["predictions_csv"]) == 64


def test_evaluate_detects_tampering(tmp_path):
    pc, pp = synth_run(tmp_path)
    rows = pl.read_csv(pc)
    rows = rows.with_columns(pl.col("rps_A") + 0.5)
    rows.write_csv(pc)
    m = ev.evaluate(pc, pp, ["A"])
    assert m["verification"]["A"]["status"] == "MISMATCH"


def test_evaluate_rejects_duplicate_identity(tmp_path):
    pc, pp = synth_run(tmp_path)
    rows = pl.read_csv(pc)
    pmfs = pl.read_parquet(pp)
    dup_r = rows.head(1)
    dup_p = pmfs.head(1)
    pl.concat([rows, dup_r]).write_csv(pc)
    pl.concat([pmfs, dup_p]).write_parquet(pp)
    with pytest.raises(ValueError, match="canonical identity"):
        ev.evaluate(pc, pp, ["A"])


def test_write_report_and_metrics(tmp_path):
    pc, pp = synth_run(tmp_path)
    m = ev.evaluate(pc, pp, ["A", "B"])
    ev.write_metrics(m, tmp_path / "metrics.json")
    ev.write_report(m, tmp_path / "report.md", "Test report")
    assert (tmp_path / "metrics.json").exists()
    txt = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Arm A" in txt and "By origin" in txt


def synth_slices_run(tmp_path, n=120, seed=9):
    rng = np.random.default_rng(seed)
    rows, pkA = [], []
    for i in range(n):
        pa = int(rng.integers(5, 32))
        pk_a = rkc.point_exposure_pmf(pa, 0.22)
        kk = int(rng.choice(24, p=pk_a / pk_a.sum()))
        pkA.append(pk_a)
        month = "04" if i % 3 == 0 else ("09" if i % 3 == 1 else "07")
        rows.append({
            "origin": "2024-04-15" if i < n // 2 else "2024-09-01",
            "game_pk": 2000 + i, "pitcher": 700 + (i % 11),
            "game_date": "2024-%s-%02d" % (month, 1 + i % 28),
            "PA": pa, "K": kk,
            "prior_n_pitcher": [0, 10, 200][(i // 11) % 3],
            "rps_A": kc.count_rps(pk_a, kk),
            "mean_A": 0.22 * pa, "EN60": float(pa),
        })
    d = tmp_path
    d.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_csv(d / "predictions.csv")
    pl.DataFrame(np.vstack(pkA),
                 schema=["pkA_%02d" % i for i in range(24)]
                 ).write_parquet(d / "pmfs.parquet")
    return d / "predictions.csv", d / "pmfs.parquet"


def test_evaluate_slices_membership_and_metrics(tmp_path):
    pc, pp = synth_slices_run(tmp_path)
    s = ev.evaluate_slices(pc, pp, ["A"], mean_cols={"A": "mean_A"})
    assert s["n"] == 120
    assert s["skipped"] == []
    assert s["april"]["A"]["n"] == 40
    assert s["september"]["A"]["n"] == 40
    assert s["career_debut"]["A"]["n"] > 30
    assert s["sparse_history"]["A"]["n"] > 30
    assert s["returning_prior_season"]["A"]["n"] > 30
    assert s["short_outing_lt9"]["A"]["n"] > 0
    a = s["april"]["A"]
    assert abs(a["bf_bias"]) < 0.01
    assert a["mean_pred_var"] > 0
    assert sum(a["pit_hist"]) == 40
    for name in ("career_debut", "sparse_history",
                 "returning_prior_season", "season_debut"):
        assert s[name]["A"]["n"] > 0


def test_evaluate_slices_skips_without_columns(tmp_path):
    pc, pp = synth_run(tmp_path)
    s = ev.evaluate_slices(pc, pp, ["A"])
    assert any("prior_n" in x for x in s["skipped"])
    assert any("bf metrics" in x for x in s["skipped"])
    assert "april" in s and "upper_milestone_ge12" in s
    assert "career_debut" not in s


def test_write_report_with_slices(tmp_path):
    pc, pp = synth_slices_run(tmp_path)
    m = ev.evaluate(pc, pp, ["A"], mean_cols={"A": "mean_A"})
    s = ev.evaluate_slices(pc, pp, ["A"], mean_cols={"A": "mean_A"})
    ev.write_report(m, tmp_path / "report.md", "Slice report",
                    slices=s)
    txt = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Permanent slices" in txt and "career_debut" in txt
