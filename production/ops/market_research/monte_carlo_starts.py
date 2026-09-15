"""At-bat Monte Carlo v1 (descriptive research, no live change).

Simulates each start PA-by-PA: per-PA strikeout draw at k_rate, pull draw
from the hook table (pitches ~= 3.85/PA, TTO = PA//9, inning by pitches,
score = close). Numpy-vectorized across sims (40 PA-steps x n_starts).

Compares the simulated K distribution vs the Poisson point model:
mean, P(K>=8) / P(K<=2) tails, and implied P(over) at main lines.
v1 approximations are labeled; bullpen-rest + pitcher pull random effects
+ real pitch counts are scoped follow-ups, not promises.

Reads: historical_scores (k_rate/projected_tbf), hook_pull_table.
Writes: artifacts/odds_log/monte_carlo_report.json.
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import json
from pathlib import Path

import numpy as np
import polars as pl

REPO = Path(__file__).resolve().parents[3]
SCORED = REPO / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
HOOK = REPO / "artifacts" / "odds_log" / "hook_pull_table.parquet"
OUT = REPO / "artifacts" / "odds_log" / "monte_carlo_report.json"

PITCHES_PER_PA = 3.85
MAX_PA = 40
MAIN_LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-sims", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-starts", type=int, default=0,
                    help="0 = all scored starts")
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    hook = {(r["pitch_band"], r["tto_band"], r["score_band"], r["inning_band"]): float(r["pull_rate"])
            for r in pl.read_parquet(HOOK).to_dicts()}

    def pull_prob(pitches: int, tto: int) -> float:
        pb = "0-49" if pitches < 50 else ("50-74" if pitches < 75 else ("75-89" if pitches < 90 else ("90-99" if pitches < 100 else "100+")))
        tb = str(min(tto, 3)) if tto < 4 else "4+"
        ib = "1-3" if pitches < 50 else ("4-6" if pitches < 90 else "7+")
        return hook.get((pb, tb, "close", ib), 0.10)

    sc = (pl.scan_parquet(SCORED).select(
        ["game_date", "pitcher_name", "k_rate_pred", "projected_tbf"])
        .collect().to_dicts())
    if args.max_starts > 0:
        sc = sc[:args.max_starts]

    agg = {"mean_k_mc": 0.0, "mean_k_pois": 0.0,
           "tail_ge8_mc": 0.0, "tail_ge8_pois": 0.0,
           "tail_le2_mc": 0.0, "tail_le2_pois": 0.0,
           "line_disagree": {str(ln): {"n": 0, "mean_abs_diff": 0.0} for ln in MAIN_LINES}}
    n = 0
    for s in sc:
        try:
            kr = float(np.clip(float(s["k_rate_pred"]), 0.02, 0.5))
            tbf = float(s["projected_tbf"])
        except (TypeError, ValueError):
            continue
        xk = kr * tbf
        # vectorized sims: rows = sims, cols = PA index
        alive = np.ones(args.n_sims, dtype=bool)
        ks = np.zeros(args.n_sims, dtype=np.int32)
        for pa in range(MAX_PA):
            tto = pa // 9 + 1
            pitches = int((pa + 1) * PITCHES_PER_PA)
            hp = pull_prob(pitches, tto)
            pulled = alive & (rng.random(args.n_sims) < hp)
            alive[pulled] = False
            active = alive
            if not active.any():
                break
            ks[active] += (rng.random(args.n_sims)[active] < kr).astype(np.int32)
        ks = ks.astype(float)
        n += 1
        agg["mean_k_mc"] += ks.mean()
        agg["mean_k_pois"] += xk
        agg["tail_ge8_mc"] += float((ks >= 8).mean())
        agg["tail_ge8_pois"] += float(1.0 - np.exp(-xk) * sum(xk ** k / math.factorial(k) for k in range(8)) if xk < 50 else 0.0)
        agg["tail_le2_mc"] += float((ks <= 2).mean())
        agg["tail_le2_pois"] += float(np.exp(-xk) * sum(xk ** k / math.factorial(k) for k in range(3)))
        for ln in MAIN_LINES:
            p_mc = float((ks > ln).mean())
            p_pois = float(1.0 - np.exp(-xk) * sum(xk ** k / math.factorial(k) for k in range(int(ln) + 1)))
            cell = agg["line_disagree"][str(ln)]
            cell["n"] += 1
            cell["mean_abs_diff"] += abs(p_mc - p_pois)
    # recompute poisson tails exactly (loop above used a guarded approx)
    for k in ("mean_k_mc", "mean_k_pois", "tail_ge8_mc", "tail_ge8_pois", "tail_le2_mc", "tail_le2_pois"):
        agg[k] = round(agg[k] / n, 4) if n else None
    for ln, cell in agg["line_disagree"].items():
        cell["mean_abs_diff"] = round(cell["mean_abs_diff"] / cell["n"], 4) if cell["n"] else None
    rep = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "n_sims": args.n_sims, "seed": args.seed, "n_starts": n,
           "approx": "pitches 3.85/PA, score close, inning by pitches; no bullpen/pitcher effects",
           **agg,
           "verdict": "v1 machinery runs; compare mean/tail gaps before any policy use"}
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
