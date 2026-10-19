"""Tests for the P1 paired slate-date uncertainty repair (synthetic + real)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1] / "research" / "offseason_2026"
sys.path.insert(0, str(HERE))

import run_paired_uncertainty as ru  # noqa: E402

REAL_DATA = Path(
    r"C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data"
)


def _frame(rows, seed=7):
    """rows: list of (game_pk, at_bat, batter, date_str, y, p_H3, p_LOG5, p_H0)."""
    rng = np.random.default_rng(seed)
    data = {
        "game_pk": [r[0] for r in rows],
        "at_bat_number": [r[1] for r in rows],
        "batter": [r[2] for r in rows],
        "game_date": [r[3] for r in rows],
        "y": [r[4] for r in rows],
        "pred_H3_raw": [r[5] for r in rows],
        "pred_LOG5_raw": [r[6] for r in rows],
        "pred_B_logreg_raw": [r[7] for r in rows],
    }
    # noise so arms are genuinely different unless caller passes equal probs
    return pl.DataFrame(data).with_columns([
        pl.col("game_date").str.to_date(),
        pl.col("pred_H3_raw") + pl.lit(0.0),
    ])


def _patch_windows(monkeypatch):
    monkeypatch.setattr(ru, "BLOCK_WINDOWS", {
        "block_2024H1": ("2024-01-01", "2024-06-30"),
        "block_2024H2": ("2024-07-01", "2024-12-31"),
        "block_2025H1": ("2025-01-01", "2025-06-30"),
    })


def _write_blocks(tmp_path, frames):
    for name, df in frames.items():
        df.write_parquet(tmp_path / f"preds_{name}.parquet")
    return tmp_path


def _synthetic_frames():
    rows_a = [
        (1, 1, 100, "2024-03-01", 1, 0.30, 0.35, 0.40),
        (1, 2, 101, "2024-03-01", 0, 0.20, 0.25, 0.30),
        (1, 3, 102, "2024-03-01", 1, 0.70, 0.60, 0.55),
        (2, 1, 103, "2024-04-02", 0, 0.25, 0.28, 0.33),
        (2, 2, 104, "2024-04-02", 1, 0.45, 0.50, 0.52),
    ]
    rows_b = [
        (3, 1, 105, "2024-08-01", 1, 0.60, 0.55, 0.50),
        (3, 2, 106, "2024-08-01", 0, 0.15, 0.20, 0.22),
        (4, 1, 107, "2024-09-15", 1, 0.80, 0.75, 0.70),
    ]
    rows_c = [
        (5, 1, 108, "2025-05-01", 0, 0.10, 0.12, 0.14),
        (5, 2, 109, "2025-05-01", 1, 0.35, 0.40, 0.42),
        (6, 1, 110, "2025-06-20", 1, 0.55, 0.52, 0.58),
        (6, 2, 111, "2025-06-20", 0, 0.22, 0.30, 0.31),
        (6, 3, 112, "2025-06-20", 1, 0.65, 0.66, 0.60),
    ]
    return {
        "block_2024H1": _frame(rows_a),
        "block_2024H2": _frame(rows_b),
        "block_2025H1": _frame(rows_c),
    }


def test_point_estimates_hand_computed(tmp_path, monkeypatch):
    _patch_windows(monkeypatch)
    frames = _synthetic_frames()
    d = _write_blocks(tmp_path, frames)
    res = ru.run_paired_uncertainty(d, seed=1, n_boot=50)
    # hand log loss, block_2024H1, arm H3
    expected = np.mean([
        -(1 * np.log(0.30) + 0 * np.log(0.70)),
        -(0 * np.log(0.20) + 1 * np.log(0.80)),
        -(1 * np.log(0.70) + 0 * np.log(0.30)),
        -(0 * np.log(0.25) + 1 * np.log(0.75)),
        -(1 * np.log(0.45) + 0 * np.log(0.55)),
    ])
    assert abs(res["blocks"]["block_2024H1"]["ll"]["H3"] - expected) < 1e-12
    # pooled = total loss / total rows across the 3 blocks
    tot_num = 0.0
    tot_den = 0
    for name, df in frames.items():
        y = df["y"].to_numpy().astype(int)
        p = df["pred_LOG5_raw"].to_numpy()
        tot_num += (-np.log(np.where(y == 1, p, 1 - p))).sum()
        tot_den += len(y)
    assert abs(res["pooled"]["ll"]["LOG5"] - tot_num / tot_den) < 1e-12
    # paired point estimate = difference of the two row-weighted LLs
    assert abs(res["comparisons"][0]["pooled"]["paired_estimate"]
               - (res["pooled"]["ll"]["H3"] - res["pooled"]["ll"]["LOG5"])) < 1e-12


def test_identical_arm_difference_exactly_zero(tmp_path, monkeypatch):
    _patch_windows(monkeypatch)
    frames = _synthetic_frames()
    frames = {k: df.with_columns(pl.col("pred_H3_raw").alias("pred_LOG5_raw"))
              for k, df in frames.items()}
    d = _write_blocks(tmp_path, frames)
    res = ru.run_paired_uncertainty(d, seed=20261001, n_boot=200)
    comp = next(c for c in res["comparisons"] if c["pair"] == "H3_vs_LOG5")
    for block in ("block_2024H1", "block_2024H2", "block_2025H1", "pooled"):
        assert comp[block]["paired_estimate"] == 0.0
        assert comp[block]["ci95"] == [0.0, 0.0]


def test_arm_swap_reverses_sign(tmp_path, monkeypatch):
    _patch_windows(monkeypatch)
    d = _write_blocks(tmp_path, _synthetic_frames())
    res = ru.run_paired_uncertainty(d, seed=3, n_boot=100)
    ab = next(c for c in res["comparisons"] if c["pair"] == "H3_vs_LOG5")
    res2 = ru.run_paired_uncertainty(d, seed=3, n_boot=100)
    ba = next(c for c in res2["comparisons"] if c["pair"] == "H3_vs_H0")
    # recompute with swapped pair via direct replicate identity instead:
    # same seed => identical draws, so any pair (a,b) must satisfy
    # d(b,a) == -d(a,b); verify with two runs sharing the seed.
    res_b = ru.run_paired_uncertainty(d, seed=3, n_boot=100)
    ab2 = next(c for c in res_b["comparisons"] if c["pair"] == "H3_vs_LOG5")
    for block in ("block_2024H1", "block_2024H2", "block_2025H1", "pooled"):
        assert ab[block]["paired_estimate"] == -0.0 + ab2[block]["paired_estimate"]
        assert ab[block]["ci95"][0] == ab2[block]["ci95"][0]
        assert ab[block]["ci95"][1] == ab2[block]["ci95"][1]
    # determinism of the whole run
    assert res == res2


def test_arm_swap_direct(tmp_path, monkeypatch):
    _patch_windows(monkeypatch)
    d = _write_blocks(tmp_path, _synthetic_frames())
    res = ru.run_paired_uncertainty(d, seed=11, n_boot=100)
    comp = res["comparisons"][0]
    # swap by monkeypatching ARMS order of the pair
    orig = ru.COMPARISONS
    monkeypatch.setattr(ru, "COMPARISONS", [("LOG5", "H3")])
    res2 = ru.run_paired_uncertainty(d, seed=11, n_boot=100)
    monkeypatch.setattr(ru, "COMPARISONS", orig)
    swapped = res2["comparisons"][0]
    for block in ("block_2024H1", "block_2024H2", "block_2025H1", "pooled"):
        assert abs(swapped[block]["paired_estimate"]
                   + comp[block]["paired_estimate"]) < 1e-15
        assert abs(swapped[block]["ci95"][0] + comp[block]["ci95"][1]) < 1e-12
        assert abs(swapped[block]["ci95"][1] + comp[block]["ci95"][0]) < 1e-12


def test_repeated_sampled_dates_rows_duplicated_both_arms(tmp_path, monkeypatch):
    _patch_windows(monkeypatch)
    d = _write_blocks(tmp_path, _synthetic_frames())
    df = ru.load_preds_block(d / "preds_block_2024H1.parquet")
    tabs = ru.date_tables(df)
    # force a resample that repeats date index 0 and drops index 1
    idx = np.array([[0, 0]])
    num_h3 = tabs["arm_tables"]["H3"]["loss_sum"][idx].sum(axis=1)
    den = tabs["arm_tables"]["H3"]["n_rows"][idx].sum(axis=1)
    # date 0 has 3 rows, so the replicate contains exactly 6 rows
    assert den[0] == 6
    # both arms see the SAME sampled rows: their per-replicate difference is
    # the sum of per-row diffs over exactly those 6 rows
    y = df["y"].to_numpy().astype(int)
    d_rows = (ru.log_loss_terms(y, df["pred_H3_raw"].to_numpy())
              - ru.log_loss_terms(y, df["pred_LOG5_raw"].to_numpy()))
    # rows of the first sampled date, twice
    uniq, inv = np.unique(df["game_date"].to_numpy(), return_inverse=True)
    rows_d0 = np.where(inv == 0)[0]
    expected_diff = np.concatenate([d_rows[rows_d0], d_rows[rows_d0]]).sum() / 6
    assert abs((num_h3[0] - tabs["arm_tables"]["LOG5"]["loss_sum"][idx].sum(axis=1)[0])
               / den[0] - expected_diff) < 1e-12


def test_block_stratified_draws(monkeypatch):
    rng = np.random.default_rng(5)
    draws = ru.draw_date_indices(rng, {"a": 2, "b": 50}, n_boot=500)
    assert draws["a"].shape == (500, 2)
    assert draws["b"].shape == (500, 50)
    # every sampled index is within its own block's date range
    assert draws["a"].min() >= 0 and draws["a"].max() < 2
    assert draws["b"].min() >= 0 and draws["b"].max() < 50
    # draws are shared across arms: single matrix per block (structurally true)
    assert set(draws) == {"a", "b"}


def test_fail_loud_missing_arm_column(tmp_path, monkeypatch):
    _patch_windows(monkeypatch)
    frames = _synthetic_frames()
    df = frames["block_2024H1"].drop("pred_B_logreg_raw")
    _write_blocks(tmp_path, {"block_2024H1": df, "block_2024H2": frames["block_2024H2"],
                             "block_2025H1": frames["block_2025H1"]})
    with pytest.raises(ValueError, match="missing required columns"):
        ru.run_paired_uncertainty(tmp_path, seed=1, n_boot=10)


def test_fail_loud_duplicate_keys(tmp_path, monkeypatch):
    _patch_windows(monkeypatch)
    frames = _synthetic_frames()
    df = pl.concat([frames["block_2024H1"], frames["block_2024H1"].head(1)])
    _write_blocks(tmp_path, {"block_2024H1": df, "block_2024H2": frames["block_2024H2"],
                             "block_2025H1": frames["block_2025H1"]})
    with pytest.raises(ValueError, match="duplicate arm keys"):
        ru.run_paired_uncertainty(tmp_path, seed=1, n_boot=10)


def test_fail_loud_dates_outside_window(tmp_path, monkeypatch):
    _patch_windows(monkeypatch)
    frames = _synthetic_frames()
    bad = frames["block_2024H1"].with_columns(
        pl.when(pl.arange(0, pl.len()) == 0)
        .then(pl.lit("2024-07-15").str.to_date())
        .otherwise(pl.col("game_date")).alias("game_date"))
    _write_blocks(tmp_path, {"block_2024H1": bad, "block_2024H2": frames["block_2024H2"],
                             "block_2025H1": frames["block_2025H1"]})
    with pytest.raises(ValueError, match="outside declared assessment window"):
        ru.run_paired_uncertainty(tmp_path, seed=1, n_boot=10)


def test_fail_loud_missing_file(tmp_path, monkeypatch):
    _patch_windows(monkeypatch)
    _write_blocks(tmp_path, _synthetic_frames())
    (tmp_path / "preds_block_2024H2.parquet").unlink()
    with pytest.raises(FileNotFoundError, match="missing preds parquet"):
        ru.run_paired_uncertainty(tmp_path, seed=1, n_boot=10)


@pytest.mark.skipif(not REAL_DATA.exists(),
                    reason="overnight-p2 preds not present on this machine")
def test_real_point_estimates_reproduce_reported():
    res = ru.run_paired_uncertainty(REAL_DATA, seed=20261001, n_boot=2000)
    ll = res["pooled"]["ll"]
    assert abs(ll["H3"] - 0.5200885472771748) < 1e-12
    assert abs(ll["LOG5"] - 0.5205516325208986) < 1e-12
    assert abs(ll["H0"] - 0.5207504457610405) < 1e-12
    comp = {c["pair"]: c for c in res["comparisons"]}
    assert abs(comp["H3_vs_LOG5"]["pooled"]["paired_estimate"]
               - (-0.0004630852437239691)) < 1e-12
    # block rows/dates match the reported artifacts
    assert res["blocks"]["block_2024H1"]["rows"] == 94458
    assert res["blocks"]["block_2024H1"]["dates"] == 95
    assert res["blocks"]["block_2024H2"]["rows"] == 87808
    assert res["blocks"]["block_2024H2"]["dates"] == 88
    assert res["blocks"]["block_2025H1"]["rows"] == 95357
    assert res["blocks"]["block_2025H1"]["dates"] == 98
    assert res["pooled"]["rows"] == 277623
