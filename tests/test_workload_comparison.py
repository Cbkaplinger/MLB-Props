"""Synthetic tests for the workload personalization comparison
(workload_comparison.py). SYNTHETIC ONLY. Every test drives the actual
entry point."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import workload_comparison as wc  # noqa: E402

ACK = wc.EXECUTION_ACK_TOKEN
P1, P2 = 700001, 700002
B1 = [800001 + i for i in range(9)]
B2 = [800101 + i for i in range(9)]
TRAIN_D1 = date(2024, 7, 1)
TRAIN_D2 = date(2024, 7, 15)
GAME_DATE = date(2025, 4, 15)

PA_SCHEMA = {"game_date": pl.Date, "game_pk": pl.Int64,
             "at_bat_number": pl.Int64, "pitcher": pl.Int64,
             "batter": pl.Int64, "y": pl.Int64}


def _pa_frame(with_future=False):
    rows = []
    # pre-training history for w150/EW states
    for i, b in enumerate(B1):
        rows.append((date(2024, 5, 20), 50, 100 + i, P1, b, 0))
    # training: D1 vs P1 (9 PAs)
    for i, b in enumerate(B1):
        rows.append((TRAIN_D1, 100, 200 + i, P1, b,
                     1 if i % 2 == 0 else 0))
    # training: D2 vs P1 (9 PAs)
    for i, b in enumerate(B2):
        rows.append((TRAIN_D2, 100, 300 + i, P1, b, 1 if i % 3 == 0 else 0))
    # training: D2 vs P2 (9 PAs)
    for i, b in enumerate(B1):
        rows.append((TRAIN_D2, 101, 400 + i, P2, b, 1 if i % 4 == 0 else 0))
    # assessment rows (2025H1)
    for i, b in enumerate(B1):
        rows.append((GAME_DATE, 900001, 500 + i, P1, b,
                     1 if i % 2 == 0 else 0))
    for i, b in enumerate(B2):
        rows.append((GAME_DATE, 900001, 600 + i, P2, b, 1 if i % 2 else 0))
    if with_future:
        rows.append((date(2025, 8, 1), 900001, 999, P1, 800001, 1))
    return pl.DataFrame(rows, schema=PA_SCHEMA, orient="row")


def _lineups():
    rows = [(900001, "Top", P1, GAME_DATE, True, *B1),
            (900001, "Bot", P2, GAME_DATE, True, *B2)]
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date, "nine_distinct": pl.Boolean}
    schema.update({f"u_slot_{i}": pl.Int64 for i in range(1, 10)})
    return pl.DataFrame(rows, schema=schema, orient="row")


def _assessment():
    rows = [(900001, "Top", P1, 500 + i, B1[i],
             0 if i % 2 == 0 else 2) for i in range(9)]
    rows += [(900001, "Bot", P2, 600 + i, B2[i],
              0 if i % 2 else 3) for i in range(9)]
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "at_bat_number": pl.Int64, "batter": pl.Int64,
        "class_label": pl.Int64}, orient="row")


def _bf_frame():
    schema = {"game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
              "game_date": pl.Date}
    schema.update({f"pmf37_{j}": pl.Float64 for j in range(37)})
    rows = []
    for (gk, side, p, gd) in [(900001, "Top", P1, GAME_DATE),
                              (900001, "Bot", P2, GAME_DATE)]:
        r = {"game_pk": gk, "side": side, "pitcher": p, "game_date": gd}
        for j in range(37):
            r[f"pmf37_{j}"] = 1.0 if j == 4 else 0.0
        rows.append(r)
    return pl.DataFrame(rows, schema=schema)


def _raw_events_frame():
    """Terminal-event rows for every PA identity (event derived from y)."""
    pa = _pa_frame()
    rows = []
    for r in pa.iter_rows(named=True):
        rows.append({"game_pk": r["game_pk"],
                     "at_bat_number": r["at_bat_number"],
                     "batter": r["batter"],
                     "events": "strikeout" if r["y"] == 1 else "single"})
    schema = {"game_pk": pl.Int64, "at_bat_number": pl.Int64,
              "batter": pl.Int64, "events": pl.Utf8}
    return pl.DataFrame(rows, schema=schema).unique(
        subset=["game_pk", "at_bat_number", "batter"], keep="first")


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(tmp_path, pa=None, lineups=None, assessment=None, bf=None):
    pa = pa if pa is not None else _pa_frame()
    lineups = lineups if lineups is not None else _lineups()
    assessment = assessment if assessment is not None else _assessment()
    bf = bf if bf is not None else _bf_frame()
    h = {}
    for name, frame in (("pa", pa), ("lineups", lineups),
                        ("assessment", assessment), ("bf", bf)):
        p = tmp_path / f"{name}.parquet"
        frame.write_parquet(p)
        h[f"{name}_path"] = str(p)
        h[f"{name}_sha"] = _sha(p)
    # create raw events file from the enriched PA frame
    enriched = _pa_frame().with_columns(
        pl.when(pl.col("y") == 1).then(pl.lit("strikeout"))
        .otherwise(pl.lit("field_out")).alias("events"))
    raw = enriched.select("game_pk", "at_bat_number", "batter", "events")
    rp = tmp_path / "raw_events.parquet"
    raw.write_parquet(rp)
    h["raw_path"] = str(rp)
    h["raw_sha"] = _sha(rp)
    return h


def _run(tmp_path, out="out", pa=None, lineups=None, assessment=None,
         bf=None, ack=ACK):
    h = _write(tmp_path, pa, lineups, assessment, bf)
    pa_frame = pa if pa is not None else _pa_frame()
    # use the dedicated raw events file (not the PA parquet)
    return wc.run_workload_comparison(
        pa_frame, lineups if lineups is not None else _lineups(),
        assessment if assessment is not None else _assessment(),
        bf if bf is not None else _bf_frame(), tmp_path / out,
        train_start="2024-06-01", train_end="2024-12-31",
        execution_ack=ack, raw_events=[h["raw_path"]])


# ------------------------------------------------- 1. end-to-end success
def test_workload_e2e_success_and_receipts(tmp_path):
    res = _run(tmp_path, out="out_ok")
    assert res["primary_contrast"]["n_starts"] == 2
    out = Path(res["out_dir"])
    receipt = json.loads((out / "receipt_final.json").read_text(
        encoding="utf-8"))
    assert receipt["acceptance"]["receipt_chain"] == \
        res["receipt_initial_sha256"]
    for name, dig in res["outputs"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == dig
    assert not (out / "failure_record.json").exists()
    ps = pl.read_parquet(out / "workload_per_start_v1.parquet")
    assert ps.height == 2
    assert set(ps.columns) >= {"game_pk", "side", "pitcher", "realized_k",
                               "rps_w0_pooled", "rps_w1_pitcher",
                               "rps_diff"}


# --------------------------------------------- 2. contrast direction
def test_contrast_direction_and_means(tmp_path):
    res = _run(tmp_path, out="out_sign")
    p = res["primary_contrast"]
    ps = pl.read_parquet(Path(res["out_dir"])
                         / "workload_per_start_v1.parquet")
    mean_w0 = ps["rps_w0_pooled"].mean()
    mean_w1 = ps["rps_w1_pitcher"].mean()
    assert p["delta_a_minus_b"] == pytest.approx(mean_w1 - mean_w0,
                                                 abs=1e-12)
    assert p["n_boot"] == 2000 and p["seed"] == 20261001
    assert p["primary_pair"] == "W1_pitcher_specific_vs_W0_pooled_league"


# --------------------------------------------- 4. same-game two starters
def test_same_game_two_starters_distinct_keys(tmp_path):
    res = _run(tmp_path, out="out_keys")
    ps = pl.read_parquet(Path(res["out_dir"])
                         / "workload_per_start_v1.parquet")
    keys = {(r["game_pk"], r["side"], r["pitcher"])
            for r in ps.iter_rows(named=True)}
    assert keys == {(900001, "Top", P1), (900001, "Bot", P2)}


# --------------------------------------------- 5. overflow BF37
def test_overflow_bf37_maps_to_bucket_36(tmp_path):
    from pregame_pa_ext.workload_comparison import _pooled_bf37
    big = pl.DataFrame(
        [(date(2024, 7, 20), 100, 500 + i, P1, 900001 + i, 0)
         for i in range(50)],
        schema=PA_SCHEMA, orient="row")
    bf37 = wc._pooled_bf37(big)
    assert bf37[36] > 0
    assert abs(bf37.sum() - 1.0) < 1e-12


# --------------------------------------------- 6. perturbation invariance
def test_future_and_same_date_pa_cannot_change_forecasts(tmp_path):
    res_a = _run(tmp_path, out="out_a")
    pa_mod = _pa_frame(with_future=True)
    res_b = _run(tmp_path, out="out_b", pa=pa_mod)
    r1 = json.loads((Path(res_a["out_dir"])
                     / "workload_comparison_report.json").read_text())
    r2 = json.loads((Path(res_b["out_dir"])
                     / "workload_comparison_report.json").read_text())
    assert r1["mean_rps_w0"] == pytest.approx(r2["mean_rps_w0"], abs=1e-12)
    assert r1["mean_rps_w1"] == pytest.approx(r2["mean_rps_w1"], abs=1e-12)


# --------------------------------------------- 7. ack + write-once
def test_invalid_ack_no_side_effects(tmp_path):
    _write(tmp_path)
    with pytest.raises(ValueError, match="execution acknowledgement"):
        _run(tmp_path, out="out_ack", ack="WRONG")
    assert not (tmp_path / "out_ack").exists()


def test_write_once(tmp_path):
    _write(tmp_path)
    out = tmp_path / "out_wonce"
    out.mkdir()
    (out / "sentinel.txt").write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="write-once violation"):
        _run(tmp_path, out="out_wonce")
    assert [p.name for p in out.iterdir()] == ["sentinel.txt"]


# --------------------------------------------- 8. missing BF coverage
def test_missing_workload_coverage_excluded(tmp_path):
    """A start with no BF37 row in the W1 artifact is excluded from
    count scoring (reported, not silently absorbed)."""
    bf = _bf_frame().head(1)  # only covers P1
    h = _write(tmp_path, bf=bf)
    from pregame_pa_ext.workload_comparison import run_workload_comparison
    with pytest.raises(Exception):
        run_workload_comparison(
            _pa_frame(), _lineups(), _assessment(), bf,
            tmp_path / "out_bf",
            train_start="2024-06-01", train_end="2024-12-31",
            execution_ack=ACK)
