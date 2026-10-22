"""Decision-flip diagnostic: counts betting-relevant decision changes
between the registered and exact count aggregations.

Implements card_decision_flip_2026-10-21.md (with the section 11
amendment at f7263ff and the Chat 2 review fix at 8369d51).
SYNTHETIC-EXERCISED; real-outcome execution requires separate
authorization.

Reads the count_agg_eval_v1.parquet (produced by the Question A
diagnostic) which contains both arms' 24-bucket count PMFs per start.
For each registered milestone line, computes P(K >= line) from both
arms, determines directional signals, and counts flips.

v3.2 (Chat 2 repair): the bootstrap now uses PER-LINE row-aligned flip
vectors (the flat-list indexing bug is fixed - previously only line-6
flips were sampled); section 11 descriptives (per-line P(K>=line)
distribution summaries, uncertain-vs-clearly-one-side counts) are
emitted as declared.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pregame_pa_ext import batt_recency as br  # noqa: E402
import kcount_combiner as kc  # noqa: E402
import pregame_pa_ext.adapter as ad  # noqa: E402

MILESTONE_LINES = [(6, 6.5), (8, 8.5), (10, 10.5), (12, 12.5)]


def compute_decisions(pmf: np.ndarray, milestones) -> dict:
    """For each milestone line, compute the directional signal."""
    out = {}
    for m, line in milestones:
        line_int = int(np.ceil(line))
        p_ge = float(np.asarray(pmf)[line_int:].sum()) if line_int < len(pmf) else 0.0
        out[m] = {"p_ge": p_ge, "direction": "OVER" if p_ge > 0.5 else "UNDER"}
    return out


def flip_analysis(ev: pl.DataFrame, milestones) -> dict:
    """Per-line flip analysis + section 11 descriptives.

    Each start contributes one comparison per milestone line. The
    evaluation population is the card's 4,823 dev-eligible starts (both
    PMFs from the Question A diagnostic's persisted output)."""
    out = {}
    all_dp = {}  # per-line |DP| arrays for the descriptives
    for m, line in milestones:
        line_int = int(np.ceil(line))
        flips = 0
        u2o, o2u = 0, 0
        dp_vals = []
        p_ge_b_vals = []
        p_ge_c_vals = []
        for r in ev.iter_rows(named=True):
            pb = np.asarray(r["pmf_baseline"])
            pc = np.asarray(r["pmf_challenger"])
            p_ge_b = float(pb[line_int:].sum()) if line_int < len(pb) else 0.0
            p_ge_c = float(pc[line_int:].sum()) if line_int < len(pc) else 0.0
            dp_vals.append(abs(p_ge_c - p_ge_b))
            p_ge_b_vals.append(p_ge_b)
            p_ge_c_vals.append(p_ge_c)
            sig_b = 1 if p_ge_b > 0.5 else 0
            sig_c = 1 if p_ge_c > 0.5 else 0
            if sig_b != sig_c:
                flips += 1
                if sig_c > sig_b:
                    u2o += 1
                else:
                    o2u += 1
        dp_arr = np.asarray(dp_vals)
        p_ge_b_arr = np.asarray(p_ge_b_vals)
        p_ge_c_arr = np.asarray(p_ge_c_vals)
        n_flip = flips
        out[m] = {
            "flip_count": n_flip,
            "flip_pct": round(n_flip / ev.height * 100, 2) if ev.height else 0,
            "under_to_over": u2o,
            "over_to_under": o2u,
            "dp_mean": float(dp_arr.mean()) if len(dp_arr) else 0.0,
            "dp_median": float(np.median(dp_arr)) if len(dp_arr) else 0.0,
            "dp_max": float(dp_arr.max()) if len(dp_arr) else 0.0,
            "dp_min": float(dp_arr.min()) if len(dp_arr) else 0.0,
            "dp_p25": float(np.percentile(dp_arr, 25)) if len(dp_arr) else 0.0,
            "dp_p75": float(np.percentile(dp_arr, 75)) if len(dp_arr) else 0.0,
            "dp_lt_001": int((dp_arr < 0.01).sum()),
            "dp_001_to_005": int(((dp_arr >= 0.01) & (dp_arr < 0.05)).sum()),
            "dp_gte_005": int((dp_arr >= 0.05).sum()),
            "baseline_p_ge_min": float(p_ge_b_arr.min()) if len(p_ge_b_arr) else 0.0,
            "baseline_p_ge_median": float(np.median(p_ge_b_arr)) if len(p_ge_b_arr) else 0.0,
            "baseline_p_ge_mean": float(p_ge_b_arr.mean()) if len(p_ge_b_arr) else 0.0,
            "baseline_p_ge_max": float(p_ge_b_arr.max()) if len(p_ge_b_arr) else 0.0,
            "challenger_p_ge_min": float(p_ge_c_arr.min()) if len(p_ge_c_arr) else 0.0,
            "challenger_p_ge_median": float(np.median(p_ge_c_arr)) if len(p_ge_c_arr) else 0.0,
            "challenger_p_ge_mean": float(p_ge_c_arr.mean()) if len(p_ge_c_arr) else 0.0,
            "challenger_p_ge_max": float(p_ge_c_arr.max()) if len(p_ge_c_arr) else 0.0,
            "uncertain_both_within_001_of_half": int(sum(
                1 for b, c in zip(p_ge_b_arr, p_ge_c_arr)
                if abs(b - 0.5) < 0.01 and abs(c - 0.5) < 0.01)),
            "clearly_one_side_both_abs_gt_02": int(sum(
                1 for b, c in zip(p_ge_b_arr, p_ge_c_arr)
                if abs(b - 0.5) > 0.2 and abs(c - 0.5) > 0.2)),
        }
        all_dp[m] = dp_arr
    return out, all_dp


def run_flip_diagnostic(eval_parquet, out_dir, *,
                        n_boot: int = 2000, seed: int = 20261001) -> dict:
    """Run the decision-flip diagnostic on the count_agg_eval_v1 parquet.
    Write-once; receipt initial written first."""
    from collections import defaultdict
    eval_parquet = Path(eval_parquet)
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)

    ev = pl.read_parquet(eval_parquet)
    dates = ev["game_date"].to_list()

    per_line, all_dp = flip_analysis(ev, MILESTONE_LINES)

    # per-line bootstrap using the REGISTERED helper (correct clustered
    # resampling: dates drawn with replacement, cluster multiplicities
    # preserved, all rows from each selected date instance included)
    cmp_mod = br.load_registered_comparison()
    dates = ev["game_date"].to_list()
    blocks = ev["block"].to_list()
    per_line_boot_cis = {}
    for m, line in MILESTONE_LINES:
        line_int = int(np.ceil(line))
        vec = np.zeros(ev.height, dtype=np.float64)
        for row_i, r in enumerate(ev.iter_rows(named=True)):
            pb = np.asarray(r["pmf_baseline"])
            pc = np.asarray(r["pmf_challenger"])
            p_ge_b = float(pb[line_int:].sum()) if line_int < len(pb) else 0.0
            p_ge_c = float(pc[line_int:].sum()) if line_int < len(pc) else 0.0
            sig_b = 1 if p_ge_b > 0.5 else 0
            sig_c = 1 if p_ge_c > 0.5 else 0
            vec[row_i] = float(sig_c != sig_b)
        res = cmp_mod.slate_date_draws(
            {"flip_ind": vec}, dates, blocks, n_boot=n_boot, seed=seed)
        replicates = res[:, 0]
        obs_prop = float(np.mean(vec)) if len(vec) else 0.0
        per_line_boot_cis[str(m)] = {
            "observed_flip_proportion": obs_prop,
            "ci95": [float(np.percentile(replicates, 2.5)),
                     float(np.percentile(replicates, 97.5))],
        }

    total_flips = sum(per_line[m]["flip_count"] for m, _ in MILESTONE_LINES)
    obs_prop = total_flips / ev.height if ev.height else 0.0

    receipt = {
        "inputs": {
            "count_agg_eval_v1_parquet": ad.sha256_file(eval_parquet),
        },
        "outputs": {
            "flip_analysis.json": None,
        },
        "population": {
            "n_starts": ev.height,
            "milestones": [m for m, _ in MILESTONE_LINES],
        },
    }

    result = {
        "per_line": {str(m): v for m, v in per_line.items()},
        "total_flips": total_flips,
        "per_line_bootstrap": per_line_boot_cis,
        "bootstrap": {
            "n_boot": n_boot, "seed": seed,
            "flip_proportion": obs_prop,
            "note": ("supplementary; the per-line bootstrap CIs above "
                     "are the declared per-line intervals"),
        },
        "provenance": receipt,
    }

    out_path = out_dir / "flip_analysis.json"
    out_path.write_text(json.dumps(result, indent=1, sort_keys=True),
                        encoding="utf-8")
    return result


def main(argv=None) -> int:
    print("Decision-flip diagnostic: implementation pending review. "
          "No real-outcome evaluation authorized.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
