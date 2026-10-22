"""Decision-flip diagnostic: counts betting-relevant decision changes
between the registered and exact count aggregations.

Implements card_decision_flip_2026-10-21.md. SYNTHETIC-EXERCISED;
real-outcome execution requires separate authorization.

Reads the count_agg_eval_v1.parquet (produced by the Question A
diagnostic) which contains both arms' 24-bucket count PMFs per start.
For each registered milestone line, computes P(K >= line) from both
arms, determines directional signals, and counts flips.
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


def count_rps(p_k, k):
    return kc.count_rps(np.asarray(p_k, dtype=float), k)


def compute_decisions(pmf: np.ndarray, milestones) -> dict:
    """For each milestone line, compute the directional signal."""
    out = {}
    for m, line in milestones:
        line_int = int(np.ceil(line))
        p_ge = float(np.asarray(pmf)[line_int:].sum()) if line_int < len(pmf) else 0.0
        out[m] = {"p_ge": p_ge, "direction": "OVER" if p_ge > 0.5 else "UNDER"}
    return out


def flip_analysis(ev: pl.DataFrame, milestones) -> dict:
    """Count flips between baseline and challenger directional signals."""
    out = {}
    for m, line in milestones:
        line_int = int(np.ceil(line))
        flips = 0
        u2o, o2u = 0, 0
        dp_vals = []
        for r in ev.iter_rows(named=True):
            pb = np.asarray(r["pmf_baseline"])
            pc = np.asarray(r["pmf_challenger"])
            p_ge_b = float(pb[line_int:].sum()) if line_int < len(pb) else 0.0
            p_ge_c = float(pc[line_int:].sum()) if line_int < len(pc) else 0.0
            dp = abs(p_ge_c - p_ge_b)
            dp_vals.append(dp)
            sig_b = 1 if p_ge_b > 0.5 else 0
            sig_c = 1 if p_ge_c > 0.5 else 0
            if sig_b != sig_c:
                flips += 1
                if sig_c > sig_b:
                    u2o += 1
                else:
                    o2u += 1
        dp_arr = np.asarray(dp_vals)
        out[m] = {
            "flip_count": flips,
            "flip_pct": round(flips / ev.height * 100, 2),
            "under_to_over": u2o,
            "over_to_under": o2u,
            "dp_mean": float(dp_arr.mean()),
            "dp_median": float(np.median(dp_arr)),
            "dp_max": float(dp_arr.max()),
        }
    return out


def run_flip_diagnostic(eval_parquet, out_dir, *,
                        n_boot: int = 2000, seed: int = 20261001) -> dict:
    """Run the decision-flip diagnostic on the count_agg_eval_v1 parquet."""
    from collections import defaultdict
    eval_parquet = Path(eval_parquet)
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)

    ev = pl.read_parquet(eval_parquet)
    dates = ev["game_date"].to_list()

    per_line = {}
    all_flips = []
    for m, line in MILESTONE_LINES:
        line_int = int(np.ceil(line))
        flips = []
        dirs = []
        for r in ev.iter_rows(named=True):
            pb = np.asarray(r["pmf_baseline"])
            pc = np.asarray(r["pmf_challenger"])
            p_ge_b = float(pb[line_int:].sum()) if line_int < len(pb) else 0.0
            p_ge_c = float(pc[line_int:].sum()) if line_int < len(pc) else 0.0
            sig_b = 1 if p_ge_b > 0.5 else 0
            sig_c = 1 if p_ge_c > 0.5 else 0
            if sig_b != sig_c:
                flips.append(1)
                dirs.append("OVER" if sig_c > sig_b else "UNDER")
            else:
                flips.append(0)
                dirs.append("same")
        all_flips.extend(flips)
        dp_arr = np.asarray([abs(
            float(np.asarray(ev[r["__idx"]]["pmf_challenger"] if False else
                             ev[ev["game_pk"] == r["game_pk"]][
                                 "pmf_challenger"][0])[line_int:].sum())
            - float(np.asarray(ev[ev["game_pk"] == r["game_pk"]][
                "pmf_baseline"][0])[line_int:].sum()))
            for r in []]) if False else None
        # compute |DP| from the PMFs directly
        dp_list = []
        for r2 in ev.iter_rows(named=True):
            pb2 = np.asarray(r2["pmf_baseline"])
            pc2 = np.asarray(r2["pmf_challenger"])
            p_ge_b2 = float(pb2[line_int:].sum()) if line_int < len(pb2) else 0.0
            p_ge_c2 = float(pc2[line_int:].sum()) if line_int < len(pc2) else 0.0
            dp_list.append(abs(p_ge_c - p_ge_b))
        dp_arr = np.asarray(dp_list)
        per_line[str(line)] = {
            "flip_count": sum(flips), "flip_pct":
            round(sum(flips) / len(flips) * 100, 2),
            "directions": dirs,
            "dp_mean": float(dp_arr.mean()),
            "dp_median": float(np.median(dp_arr)),
            "dp_max": float(dp_arr.max()),
            "dp_lt_001": int((dp_arr < 0.01).sum()),
            "dp_001_to_005": int(((dp_arr >= 0.01) & (dp_arr < 0.05)).sum()),
            "dp_gte_005": int((dp_arr >= 0.05).sum()),
        }

    # slate-date-clustered bootstrap on the total flip proportion
    slate_idx = defaultdict(list)
    for i, dd in enumerate(dates):
        slate_idx[dd].append(i)
    rng = np.random.default_rng(seed)
    boot_props = np.empty(n_boot)
    for rep in range(n_boot):
        boot_rows = []
        for dd in sorted(slate_idx.keys()):
            indices = slate_idx[dd]
            if indices:
                pick = rng.integers(0, len(indices))
                boot_rows.extend([indices[pick]])
        boot_props[rep] = (np.mean([all_flips[i] for i in boot_rows])
                           if boot_rows else 0.0)
    total_flips = sum(per_line[str(line)]["flip_count"] for _, line in MILESTONE_LINES)
    obs_prop = total_flips / ev.height if ev.height else 0.0

    receipt = {
        "inputs": {
            "count_agg_eval_v1_parquet": ad.sha256_file(eval_parquet),
        },
        "outputs": {
            "flip_analysis.json": None,  # filled after write
        },
        "population": {
            "n_starts": ev.height,
            "milestones": [m for m, _ in MILESTONE_LINES],
        },
    }

    result = {
        "per_line": {str(m): v for m, v in per_line.items()},
        "total_flips": total_flips,
        "bootstrap": {
            "n_boot": n_boot, "seed": seed,
            "flip_proportion": obs_prop,
            "ci95": [float(np.percentile(boot_props, 2.5)),
                     float(np.percentile(boot_props, 97.5))],
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
