"""Ladder sim v2: K-rate posterior x TBF bootstrap (paper research, no live change).

Owner 2026-09-24: 10k sims of FIXED inputs = the Poisson you started with
(zero new signal). Signal comes from varying the inputs per sim:
  (a) pitcher true-talent K-rate ~ Beta posterior (trailing-10 starts +
      league prior, chrono-safe — only earlier games feed each start);
  (b) TBF ~ team hook randomness around projected_tbf (monte_carlo v1
      showed hooks cut deeper than marathons extend: MC mean -0.29).

Per sim: draw k_rate, draw TBF, draw K ~ Binomial(TBF, k_rate). Tails per
rung vs the Poisson point model, split by data-defined archetype:
  power = trailing K% >= 25th-pctile-high AND game-to-game spread above
  median (Sale/Misiorowski/Snell bucket); else standard.

Answers: do power arms carry fatter tails than Poisson says (ladder
candidates), and where does Poisson overprice (v1 says right-tail over
lines)? Paper only — feeds the October paper-ladder, never the board.

Reads: artifacts/live_scores/historical_scores_2025_2026.parquet
  (K, PA, k_rate_P10, projected_tbf per start).
Writes: artifacts/odds_log/ladder_sim_report.json.

Usage:
  python production/ops/market_research/ladder_sim.py [--n-sims 2000] [--seed 0]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
OUT = ROOT / "artifacts" / "odds_log" / "ladder_sim_report.json"

RUNGS = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
TRAIL_N = 10
PRIOR_PA = 200.0  # league-prior strength (Glicko lesson: partial seasons need it)


def league_prior(df: pl.DataFrame) -> tuple[float, float]:
    """Beta prior from global K/PA (empirical Bayes, one number)."""
    k = float(df["K"].sum())
    pa = float(df["PA"].sum())
    rate = k / pa if pa > 0 else 0.22
    return rate * PRIOR_PA, (1.0 - rate) * PRIOR_PA


def trailing_k_pa(rows: list[dict], idx: int) -> tuple[float, float, list[float]]:
    """Trailing-10 K/PA strictly before rows[idx] (chrono-safe)."""
    prior = [r for r in rows[max(0, idx - TRAIL_N):idx]]
    k = float(sum(float(r["K"] or 0.0) for r in prior))
    pa = float(sum(float(r["PA"] or 0.0) for r in prior))
    rates = [float(r["K"] or 0.0) / float(r["PA"] or 1.0) for r in prior]
    return k, pa, rates


def archetype(k_rate: float, spread: float, rate_cut: float,
              spread_cut: float) -> str:
    """power = high trailing K% AND high game-to-game spread."""
    return "power" if (k_rate >= rate_cut and spread >= spread_cut) else "standard"


def sim_start_over_probs(rng: np.random.Generator, k: float, pa: float,
                         tbf_mean: float, tbf_sd: float, a0: float, b0: float,
                         n_sims: int) -> dict[float, float]:
    """Posterior-predictive P(K > rung): Beta K-rate x Normal TBF x Binomial K."""
    if pa <= 0 or tbf_mean <= 0:
        return {r: float("nan") for r in RUNGS}
    rates = rng.beta(a0 + k, b0 + max(pa - k, 0.0), size=n_sims)
    tbfs = np.clip(rng.normal(tbf_mean, max(tbf_sd, 1.0), size=n_sims), 9, 45).astype(int)
    ks = rng.binomial(tbfs, np.clip(rates, 1e-4, 1.0 - 1e-4))
    return {r: float((ks > r).mean()) for r in RUNGS}


def sim_start_over_probs_joint(
        rng: np.random.Generator, pairs: list[tuple[float, float]],
        tbf_mean: float, n_sims: int) -> dict[float, float]:
    """v3 joint bootstrap (owner 2026-09-24): resample (K, PA) PAIRS intact.

    Rate and workload are jointly caused (high-K outings run up pitches →
    earlier hooks); v2's independent Beta x Normal severs that link and
    biases tails. Here each sim draws ONE real recent game and Binomial-
    smooths it at projected TBF: the empirical joint (including the
    workload-rate link) survives nonparametrically. Empty history → NaNs.
    """
    if not pairs or tbf_mean <= 0:
        return {r: float("nan") for r in RUNGS}
    ks = np.array([p[0] for p in pairs], dtype=float)
    pas = np.array([p[1] for p in pairs], dtype=float)
    pick = rng.integers(0, len(pairs), size=n_sims)
    rates = ks[pick] / np.maximum(pas[pick], 1.0)
    tbf = int(round(tbf_mean))
    draws = rng.binomial(max(tbf, 1), np.clip(rates, 1e-4, 1.0 - 1e-4))
    return {r: float((draws > r).mean()) for r in RUNGS}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-sims", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    df = pl.scan_parquet(SCORED).select(
        ["game_date", "pitcher", "player_name", "K", "PA",
         "projected_tbf"]).collect().sort(["pitcher", "game_date"])
    a0, b0 = league_prior(df)
    tbf_sd = float(df.select(
        pl.col("projected_tbf").cast(pl.Float64)).to_series().std() or 3.0)

    by_pitcher: dict = {}
    for pid, grp in df.group_by("pitcher", maintain_order=True):
        by_pitcher[pid] = grp.to_dicts()
    all_rates, all_spreads = [], []
    scoped: list[tuple] = []
    for pid, rows in by_pitcher.items():
        for i in range(1, len(rows)):
            k, pa, rates = trailing_k_pa(rows, i)
            if pa <= 0:
                continue
            kr = k / pa
            spread = float(np.std(rates)) if len(rates) > 1 else 0.0
            all_rates.append(kr)
            all_spreads.append(spread)
            prior = rows[max(0, i - TRAIL_N):i]
            pairs = [(float(r["K"] or 0.0), float(r["PA"] or 0.0)) for r in prior]
            scoped.append((pid, rows[i], k, pa, kr, spread, pairs))
    # Power = top-half rate AND top-half spread (data-defined, owner 2026-09-24).
    rate_cut = float(np.quantile(all_rates, 0.5)) if all_rates else 0.25
    spread_cut = float(np.median(all_spreads)) if all_spreads else 0.05

    tails: dict[str, dict[str, list]] = {"power": {}, "standard": {}}
    joint: dict[str, dict[str, list]] = {"power": {}, "standard": {}}
    counts = {"power": 0, "standard": 0}
    for pid, row, k, pa, kr, spread, pairs in scoped:
        arch = archetype(kr, spread, rate_cut, spread_cut)
        tbf = row.get("projected_tbf")
        try:
            tbf_mean = float(tbf) if tbf is not None else 0.0
        except (TypeError, ValueError):
            tbf_mean = 0.0
        probs = sim_start_over_probs(rng, k, pa, tbf_mean, tbf_sd, a0, b0,
                                     args.n_sims)
        for rung, p in probs.items():
            tails[arch].setdefault(str(rung), []).append(p)
        for rung, p in sim_start_over_probs_joint(
                rng, pairs, tbf_mean, args.n_sims).items():
            joint[arch].setdefault(str(rung), []).append(p)
        counts[arch] += 1
    summary = {}
    for arch in ("power", "standard"):
        summary[arch] = {
            "n_starts": counts[arch],
            "mean_over": {r: round(float(np.nanmean(v)), 4)
                          for r, v in sorted(tails[arch].items())},
            "mean_over_joint": {r: round(float(np.nanmean(v)), 4)
                                for r, v in sorted(joint[arch].items())},
        }
    rep = {
        "built": "ladder_sim v2",
        "n_sims": args.n_sims,
        "seed": args.seed,
        "prior_pa": PRIOR_PA,
        "rate_cut": round(rate_cut, 4),
        "spread_cut": round(spread_cut, 4),
        **summary,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=2, default=str))
    print(json.dumps({k: v for k, v in rep.items() if k != "mean_over"},
                     indent=1, default=str)[:800])
    for arch in ("power", "standard"):
        print(arch, summary[arch]["n_starts"],
              ["%.3f" % summary[arch]["mean_over"][str(r)] for r in (4.5, 6.5, 8.5)],
              "joint:",
              ["%.3f" % summary[arch]["mean_over_joint"][str(r)] for r in (4.5, 6.5, 8.5)])


if __name__ == "__main__":
    main()
