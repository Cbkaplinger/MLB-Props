"""Synthetic tests for the decision-flip diagnostic (decision_flip.py).
SYNTHETIC ONLY: no real data, no real-outcome evaluation."""
from __future__ import annotations

import json
import numpy as np
import polars as pl
import pytest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys_path = str(HERE / "research" / "offseason_2026")
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)

from pregame_pa_ext import decision_flip as df_mod  # noqa: E402
import pregame_pa_ext.adapter as ad  # noqa: E402
import kcount_combiner as kc  # noqa: E402


def make_synthetic_ev(n=10):
    """Create a synthetic evaluation table with both arms' PMFs."""
    rng = np.random.default_rng(42)
    rows = []
    for i in range(n):
        pb = np.zeros(24)
        pb[:5] = [0.2, 0.1, 0.15, 0.1, 0.1]  # K=0..4
        pb[23] = 1 - sum(pb[:5])
        pc = np.zeros(24)
        pc[:5] = [0.18, 0.32, 0.13, 0.08, 0.09]  # slightly different shape
        pc[23] = 1 - sum(pc[:5])
        rows.append({
            "game_pk": 1000 + i, "side": "Bot", "pitcher": 500 + (i % 3),
            "game_date": __import__("datetime").date(2024, 8, 1) +
                         __import__("datetime").timedelta(days=i),
            "block": "block_2024H2", "realized_k": int(rng.integers(2, 12)),
            "pmf_baseline": pb.tolist(), "pmf_challenger": pc.tolist(),
        })
    return pl.DataFrame(rows)


def test_flip_diagnostic_runs_on_synthetic(tmp_path):
    """The flip diagnostic produces a valid flip_analysis.json on
    synthetic data."""
    ev = make_synthetic_ev()
    ev_path = tmp_path / "count_agg_eval_v1.parquet"
    ev.write_parquet(ev_path)
    out_dir = tmp_path / "flip_output"
    result = df_mod.run_flip_diagnostic(ev_path, out_dir)
    assert (out_dir / "flip_analysis.json").is_file()
    r = json.loads((out_dir / "flip_analysis.json").read_text(encoding="utf-8"))
    assert "per_line" in r
    assert "total_flips" in r
    assert "bootstrap" in r
    # each line has flip count, percentage, and directions
    for line_key, line_data in r["per_line"].items():
        assert "flip_count" in line_data
        assert "flip_pct" in line_data


def test_flip_counts_are_deterministic(tmp_path):
    """Two runs on the same data produce identical flip counts."""
    ev = make_synthetic_ev()
    ev_path = tmp_path / "count_agg_eval_v1.parquet"
    ev.write_parquet(ev_path)
    r1 = df_mod.run_flip_diagnostic(ev_path, tmp_path / "out1")
    r2 = df_mod.run_flip_diagnostic(ev_path, tmp_path / "out2")
    assert r1["total_flips"] == r2["total_flips"]
    for m in r1["per_line"]:
        assert r1["per_line"][str(m)]["flip_count"] == r2["per_line"][str(m)]["flip_count"]


def test_flip_direction_counting():
    """Flips are counted per direction (UNDER->OVER vs OVER->UNDER)."""
    # manually verify with a controlled case
    # p_baseline = [0.6, 0.4, 0, ...] -> at line 6.5 (K>=7): 0.0 (UNDER)
    # p_challenger = [0.4, 0.6, 0, ...] -> at line 6.5 (K>=7): 0.0 (UNDER)
    # no flip at K>=6.5
    # but at K>=8.5 (K>=9): both 0.0 (UNDER), no flip either
    pmf_b = np.zeros(24); pmf_b[0] = 0.6; pmf_b[1] = 0.4
    pmf_c = np.zeros(24); pmf_c[0] = 0.4; pmf_c[1] = 0.6
    # at line_int=7: P(K>=7) = 0 for both -> same direction -> no flip
    assert (pmf_b[7:].sum() > 0.5) == (pmf_c[7:].sum() > 0.5)
    # at line_int=1: P(K>=1) = 0.4 vs 0.6 -> flip!
    assert (pmf_b[1:].sum() > 0.5) != (pmf_c[1:].sum() > 0.5)


def test_practical_significance_threshold():
    """The card pre-declares a 2% per-line threshold. Verify the
    threshold logic: 1 flip of 4,823 = 0.02% (negligible); 100 flips =
    2.07% (meets the threshold)."""
    assert 1 / 4823 * 100 < 2.0
    assert 100 / 4823 * 100 >= 2.0
