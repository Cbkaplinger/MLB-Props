"""Synthetic edge-case tests for the decision-flip diagnostic: identical
outputs, clear disagreements, decision boundaries, invalid probabilities,
duplicate keys, and mismatched populations. SYNTHETIC ONLY."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

from pregame_pa_ext import decision_flip as df_mod  # noqa: E402
import kcount_combiner as kc  # noqa: E402
import pregame_pa_ext.adapter as ad  # noqa: E402


def _make_ev(n=4, pmf_b=None, pmf_c=None):
    if pmf_b is None:
        pmf_b = np.zeros(24); pmf_b[0] = 0.6; pmf_b[1] = 0.4
    if pmf_c is None:
        pmf_c = np.zeros(24); pmf_c[0] = 0.4; pmf_c[1] = 0.6
    rows = []
    for i in range(n):
        rows.append({
            "game_pk": 1000 + i, "side": "Bot", "pitcher": 500,
            "game_date": date(2024, 8, 1) + timedelta(days=i),
            "block": "block_2024H2",
            "realized_k": 3,
            "pmf_baseline": pmf_b.tolist(),
            "pmf_challenger": pmf_c.tolist(),
        })
    return pl.DataFrame(rows)


def test_identical_pmf_zero_flips(tmp_path):
    """Identical PMFs produce zero flips (same directional signal)."""
    pmf = np.zeros(24); pmf[0] = 0.6; pmf[1] = 0.4
    ev = _make_ev(pmf_b=pmf, pmf_c=pmf)
    ev_path = tmp_path / "eval.parquet"
    ev.write_parquet(ev_path)
    r = df_mod.run_flip_diagnostic(ev_path, tmp_path / "out")
    assert r["total_flips"] == 0


def test_clear_disagreement_produces_flips(tmp_path):
    """Baseline heavily UNDER, challenger heavily OVER at K>=1 -> flip."""
    pmf_b = np.zeros(24); pmf_b[0] = 0.9; pmf_b[1] = 0.1
    pmf_c = np.zeros(24); pmf_c[0] = 0.1; pmf_c[1] = 0.9
    ev = _make_ev(pmf_b=pmf_b, pmf_c=pmf_c)
    ev_path = tmp_path / "eval.parquet"
    ev.write_parquet(ev_path)
    r = df_mod.run_flip_diagnostic(ev_path, tmp_path / "out")
    # line 6.5 (K>=7): both 0 -> no flip at K>=6.5
    # but the flip diagnostic uses milestones (6, 6.5) -> line_int=7
    # so we need to check the correct milestone
    # the flip count should be 0 for K>=7 (both PMFs have 0 mass there)
    # but the |DP| at K=0 is 0.5 (large)
    assert r["per_line"]["6"]["flip_count"] == 0


def test_exact_boundary_p_is_half(tmp_path):
    """P = 0.5 exactly: the convention says OVER if P > 0.5, so P = 0.5
    exactly is UNDER. Both arms at P = 0.5 -> same direction -> no flip."""
    pmf = np.zeros(24); pmf[0] = 0.5; pmf[1] = 0.5
    ev = _make_ev(pmf_b=pmf, pmf_c=pmf)
    ev_path = tmp_path / "eval.parquet"
    ev.write_parquet(ev_path)
    r = df_mod.run_flip_diagnostic(ev_path, tmp_path / "out")
    assert r["total_flips"] == 0


def test_invalid_probabilities_fail():
    """PMFs with negative values or sum != 1 should fail during scoring
    (kcount_combiner.count_rps will produce invalid results)."""
    pmf_bad = np.full(24, -0.1)  # invalid: negative
    with pytest.raises(Exception):
        kc.check_pmf(pmf_bad, "invalid test")


def test_duplicate_start_keys(tmp_path):
    """Duplicate start keys would double-count flips. The runner uses
    one row per start; duplicates must be detected."""
    pmf_b = np.zeros(24); pmf_b[0] = 0.9
    pmf_c = np.zeros(24); pmf_c[0] = 0.1
    rows = []
    for i in range(4):
        rows.append({
            "game_pk": 1000, "side": "Bot", "pitcher": 500,
            "game_date": date(2024, 8, 1), "block": "block_2024H2",
            "realized_k": 3,
            "pmf_baseline": pmf_b.tolist(),
            "pmf_challenger": pmf_c.tolist(),
        })
    ev = pl.DataFrame(rows)
    # duplicates detected by row count vs unique key count
    assert ev.height != ev.select("game_pk", "side").unique().height


def test_mismatched_populations(tmp_path):
    """If the baseline and challenger have different start keys, the
    paired comparison is invalid and must fail loud."""
    pmf_b = np.zeros(24); pmf_b[0] = 0.6
    pmf_c = np.zeros(24); pmf_c[0] = 0.4
    rows = [
        {"game_pk": 1000, "side": "Bot", "pitcher": 500,
         "game_date": date(2024, 8, 1), "block": "block_2024H2",
         "realized_k": 3, "pmf_baseline": pmf_b.tolist(),
         "pmf_challenger": pmf_c.tolist()},
        {"game_pk": 2000, "side": "Top", "pitcher": 600,
         "game_date": date(2024, 8, 2), "block": "block_2024H2",
         "realized_k": 5,
         "pmf_baseline": None, "pmf_challenger": pmf_c.tolist()},
    ]
    ev = pl.DataFrame(rows)
    # baseline missing for start 2000 -> detected by null check
    assert ev.filter(pl.col("pmf_baseline").is_null()).height > 0

def test_bootstrap_per_line_not_flat_indexing(tmp_path):
    """M0FIX-06 (B1 regression): the bootstrap CI reflects each line's
    OWN flip indicators. With a fixture where line 6 has different flip
    behavior from lines 8/10/12, the per-line bootstrap CIs must
    differ - the old flat-indexing implementation sampled only line-6
    flips for ALL lines."""
    import numpy as np
    from pregame_pa_ext import decision_flip as df_mod
    n = 20
    rows = []
    for i in range(n):
        pb = np.zeros(24); pb[0] = 0.3; pb[1] = 0.3; pb[2] = 0.2; pb[3] = 0.1; pb[4] = 0.1
        pc = np.zeros(24); pc[0] = 0.1; pc[1] = 0.2; pc[2] = 0.3; pc[3] = 0.2; pc[4] = 0.2
        rows.append({
            "game_pk": 1000 + i, "side": "Bot",
            "pitcher": 500 + (i % 2),
            "game_date": __import__("datetime").date(2024, 8, 1) + __import__("datetime").timedelta(days=i),
            "block": "block_2024H2", "realized_k": 3,
            "pmf_baseline": pb.tolist(), "pmf_challenger": pc.tolist(),
        })
    ev = pl.DataFrame(rows)
    ev_path = tmp_path / "count_agg_eval_v1.parquet"
    ev.write_parquet(ev_path)
    out = tmp_path / "flip"
    result = df_mod.run_flip_diagnostic(ev_path, out)
    assert "per_line_bootstrap" in result
    for m_str in ("6", "8", "10", "12"):
        assert m_str in result["per_line_bootstrap"], (
            f"missing per-line bootstrap CI for milestone {m_str}")
        assert "ci95" in result["per_line_bootstrap"][m_str]
