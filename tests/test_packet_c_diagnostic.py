"""Synthetic tests for the Packet C diagnostic runner
(run_packet_c_diagnostic.py) at the reviewed definitions (ecda692).

Hand-computed expectations on a 2-row fixture (both y=1 and y=0),
bin-boundary convention ([lo, hi) on the registered model deciles),
and invalid-input refusal. NO real-artifact execution, NO lake query.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"))
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"
                       / "pregame_pa_ext"))

from pregame_pa_ext import run_packet_c_diagnostic as rc  # noqa: E402


def _pmf_for_p_over(p_over: float) -> list[float]:
    """24-bucket PMF with EXACTLY p_over mass above 4.5 (buckets 5..23),
    spread uniformly -> model_p_over == p_over by the half-line tail."""
    pmf = [0.0] * 24
    for b in range(5, 24):
        pmf[b] = p_over / 19.0
    for b in range(0, 5):
        pmf[b] = (1.0 - p_over) / 5.0
    return pmf


def _rows_frame():
    """Two paired starts with hand-computable values:
    row A: p_model 0.8, p_consensus 0.6, K=6 (y=1)
    row B: p_model 0.3, p_consensus 0.4, K=2 (y=0)
    """
    rows = []
    for (gpk, side, pid, pm, pc, k) in (
            (1, "home", 100, 0.8, 0.6, 6.0),
            (2, "away", 200, 0.3, 0.4, 2.0)):
        rows.append({"game_pk": gpk, "side": side, "pitcher": pid,
                     "game_date": "2025-04-10", "block": "block_2025H1",
                     "realized_k": k, "line": 4.5,
                     "pmf_baseline": _pmf_for_p_over(pm), "p_over": pc,
                     "n_books": 3})
    return pl.DataFrame(rows)


def _write_inputs(tmp_path):
    rows = _rows_frame()
    p1 = tmp_path / "benchmark_model_rows.parquet"
    rows.write_parquet(p1)
    p2 = tmp_path / "benchmark_summary.json"
    p2.write_text("{}", encoding="utf-8")
    return {"benchmark_model_rows": (p1, rc.sha256_file(p1)),
            "benchmark_summary": (p2, rc.sha256_file(p2))}


def _wire(monkeypatch, tmp_path, pins):
    monkeypatch.setattr(rc, "FILE_PINS", pins)
    monkeypatch.setattr(rc, "BENCH_ROWS_PATH", pins["benchmark_model_rows"][0])
    monkeypatch.setattr(rc, "BENCH_SUMMARY_PATH", pins["benchmark_summary"][0])


ACK = "--execution-ack", rc.EXECUTION_ACK_TOKEN


def test_summary_hand_computed_both_y(tmp_path, monkeypatch):
    pins = _write_inputs(tmp_path)
    _wire(monkeypatch, tmp_path, pins)
    out = tmp_path / "out"
    assert rc.main([*ACK, "--out-dir", str(out)]) == 0
    s = json.loads((out / rc.OUTPUT_SUMMARY).read_text(encoding="utf-8"))
    assert s["n_rows"] == 2
    dd = s["directional_disagreement"]
    # signed diffs: +0.2 (y=1 row), -0.1 (y=0 row)
    assert abs(dd["mean"] - 0.05) < 1e-12
    assert abs(dd["median"] - 0.05) < 1e-12
    assert abs(dd["mean_pp"] - 5.0) < 1e-10
    # mean(p - y): model (0.8-1)+(0.3-0) = +0.05; consensus (0.6-1)+(0.4-0) = 0.0
    assert abs(s["mean_p_minus_y"]["model"] - 0.05) < 1e-12
    assert abs(s["mean_p_minus_y"]["consensus"]) < 1e-12
    # extremity: model (0.3+0.2)/2 = 0.25; consensus (0.1+0.1)/2 = 0.10
    ext = s["extremity"]
    assert abs(ext["model"] - 0.25) < 1e-12
    assert abs(ext["consensus"] - 0.10) < 1e-12
    assert abs(ext["delta_model_minus_consensus"] - 0.15) < 1e-12
    # fixed-threshold shares: model row A on/above 0.25 -> 0.5; consensus 0.0
    assert ext["share_abs_p_minus_half_gte_threshold"]["model"] == 0.5
    assert ext["share_abs_p_minus_half_gte_threshold"]["consensus"] == 0.0
    # both y values present in the population by construction
    assert s["definitions"]["y"] == "1{realized_k > line}"


def test_bin_boundary_convention(tmp_path, monkeypatch):
    """Registered convention: buckets are [lo, hi) with -inf/+inf ends.
    With duplicated model probabilities an interior decile edge lands
    EXACTLY on the duplicated value; that value must fall in the UPPER
    bucket (its lo), never duplicated or dropped."""
    p = np.asarray([0.1, 0.2, 0.2, 0.4])
    qs = rc._registered_decile_edges(p)
    # an interior decile edge lands exactly on the duplicated 0.2
    assert any(abs(q - 0.2) < 1e-12 for q in qs)
    assignments = {}
    for i in range(rc.N_BUCKETS_RELIABILITY):
        mask = (p >= qs[i]) & (p < qs[i + 1])
        for v in p[mask]:
            assignments[float(v)] = i
    # 0.2 sits ON an edge: [lo, hi) puts it in the UPPER bucket
    assert assignments[0.2] == max(i for i in range(rc.N_BUCKETS_RELIABILITY)
                                   if qs[i] <= 0.2)
    assert len(assignments) == 3  # 0.1, 0.2, 0.4 - every value once


def test_main_entry_bins_persisted(tmp_path, monkeypatch):
    pins = _write_inputs(tmp_path)
    _wire(monkeypatch, tmp_path, pins)
    out = tmp_path / "out"
    assert rc.main([*ACK, "--out-dir", str(out)]) == 0
    bins = pl.read_parquet(out / rc.OUTPUT_BUCKETS)
    assert bins.height >= 1
    assert set(bins.columns) >= {"bucket", "n", "p_model_mean",
                                 "p_consensus_mean",
                                 "observed_over_rate",
                                 "mean_p_minus_y_model",
                                 "mean_p_minus_y_consensus"}
    # every preserved row counted across buckets
    assert bins["n"].sum() == 2
    # receipt-final-last discipline
    assert (out / "receipt_final.json").exists()
    assert (out / "receipt_initial.json").exists()


def test_hash_mismatch_refuses_before_outputs(tmp_path, monkeypatch):
    pins = _write_inputs(tmp_path)
    p2 = pins["benchmark_summary"][0]
    pins["benchmark_summary"] = (p2, "0" * 64)  # broken pin
    _wire(monkeypatch, tmp_path, pins)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="changed"):
        rc.main([*ACK, "--out-dir", str(out)])
    assert not out.exists()  # refused BEFORE any output creation


def test_missing_column_refuses(tmp_path, monkeypatch):
    pins = _write_inputs(tmp_path)
    rows = _write_inputs.__wrapped__ if False else None
    p1 = pins["benchmark_model_rows"][0]
    df = pl.read_parquet(p1).drop("p_over")
    df.write_parquet(p1)
    pins["benchmark_model_rows"] = (p1, rc.sha256_file(p1))
    _wire(monkeypatch, tmp_path, pins)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="missing required column"):
        rc.main([*ACK, "--out-dir", str(out)])
    assert not (out / rc.OUTPUT_SUMMARY).exists()


def test_existing_destination_refuses(tmp_path, monkeypatch):
    pins = _write_inputs(tmp_path)
    _wire(monkeypatch, tmp_path, pins)
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(ValueError, match="write-once"):
        rc.main([*ACK, "--out-dir", str(out)])


def test_ack_gate(tmp_path, monkeypatch):
    pins = _write_inputs(tmp_path)
    _wire(monkeypatch, tmp_path, pins)
    with pytest.raises(ValueError, match="acknowledgement"):
        rc.main(["--execution-ack", "WRONG", "--out-dir",
                 str(tmp_path / "out")])
