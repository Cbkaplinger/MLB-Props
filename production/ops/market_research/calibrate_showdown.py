"""Calibration showdown: v2 posterior vs Poisson-point vs WS1c-cal (research).

Owner 2026-09-24: v2 must PROVE itself against frozen production on ACTUAL
results before anything wires anywhere. Three contestants, same starts,
same rungs, chrono-safe throughout:
  - poisson_point: Poisson(k_rate_P10 x projected_tbf) — production pre-cal.
  - ws1c_cal: p_over_*_cal columns — frozen production (live calibration).
  - v2_posterior: Beta trailing-10 K-rate x Normal TBF x Binomial K.

Metrics per rung: Brier, logloss (clipped), ECE (10 bins). Sliced overall,
by rung, and by archetype (power/standard — same cuts as ladder_sim).
Betting metrics (ROI/CLV/Sharpe) need book lines + stakes: not here (paper
ladder tracker owns those once rungs price against real books).

Reads: artifacts/live_scores/historical_scores_2025_2026.parquet.
Writes: artifacts/odds_log/ladder_showdown_report.json.

Usage:
  python production/ops/market_research/calibrate_showdown.py [--n-sims 500] [--seed 0]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
OUT = ROOT / "artifacts" / "odds_log" / "ladder_showdown_report.json"
K_LADDER = ROOT / "data" / "Odds-Historical" / "kalshi" / "k_ladder.parquet"
K_CLOSES = ROOT / "data" / "Odds-Historical" / "kalshi" / "k_closes.parquet"

RUNGS = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
CAL_COLS = {r: f"p_over_{str(r).replace('.', '_')}_cal" for r in RUNGS}
EPS = 1e-6


def _norm(name: object) -> str:
    s = " ".join(str(name or "").lower().split())
    # Scores store "Last, First" (Assad, Javier); books/Kalshi use First Last.
    if "," in s:
        last, _, first = s.partition(",")
        s = f"{first.strip()} {last.strip()}".strip()
    return s


def kalshi_close_map() -> dict[tuple[str, str, float], float]:
    """(game_date, norm-player, line) -> close fair over (pure I/O boundary).

    Bridges k_closes market tickers (KXMLBKS-<event>-<code>-<rung>, rung N =
    "N+" = over N-0.5) through the ladder (event_ticker + rung -> game_date,
    player). Returns {} when the lake files are absent.
    """
    import re

    out: dict[tuple[str, str, float], float] = {}
    try:
        ladder = pl.scan_parquet(K_LADDER).select(
            ["event_ticker", "rung", "game_date", "player_norm"]).collect()
        closes = pl.scan_parquet(K_CLOSES).select(
            ["market_ticker", "close_fair_over"]).collect()
    except Exception:
        return out
    ev_by_key: dict[tuple[str, int], tuple[str, str]] = {}
    for r in ladder.to_dicts():
        try:
            ev_by_key[(str(r["event_ticker"]), int(r["rung"]))] = (
                str(r["game_date"])[:10], _norm(r["player_norm"]))
        except (TypeError, ValueError, KeyError):
            continue
    for r in closes.to_dicts():
        m = re.match(r"^(KXMLBKS-[A-Z0-9]+)-[A-Z0-9]+-(\d+)$",
                     str(r.get("market_ticker") or ""))
        if not m:
            continue
        rung = int(m.group(2))
        hit = ev_by_key.get((m.group(1), rung))
        if hit is None:
            continue
        try:
            out[(hit[0], hit[1], float(rung) - 0.5)] = float(r["close_fair_over"])
        except (TypeError, ValueError):
            continue
    return out


def _load_ladder_sim():
    spec = importlib.util.spec_from_file_location(
        "ladder_sim",
        ROOT / "production" / "ops" / "market_research" / "ladder_sim.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ladder_sim"] = mod
    spec.loader.exec_module(mod)
    return mod


def poisson_over(lam: float, rung: float) -> float:
    """P(K > rung) for Poisson(lam) via the CDF sum (stdlib only)."""
    if lam <= 0:
        return 0.0
    k = int(math.floor(rung))
    term, cdf = math.exp(-lam), math.exp(-lam)
    for i in range(1, k + 1):
        term *= lam / i
        cdf += term
    return max(0.0, min(1.0, 1.0 - cdf))


def brier(ps: list[float], ys: list[int]) -> float:
    return float(np.mean([(p - y) ** 2 for p, y in zip(ps, ys)]))


def logloss(ps: list[float], ys: list[int]) -> float:
    return float(np.mean([
        -(y * math.log(min(max(p, EPS), 1 - EPS))
          + (1 - y) * math.log(min(max(1 - p, EPS), 1 - EPS)))
        for p, y in zip(ps, ys)]))


def ece(ps: list[float], ys: list[int], n_bins: int = 10) -> float:
    tot, err = len(ps), 0.0
    if not tot:
        return float("nan")
    for b in range(n_bins):
        idx = [i for i, p in enumerate(ps) if b / n_bins <= p < (b + 1) / n_bins
               or (b == n_bins - 1 and p == 1.0)]
        if not idx:
            continue
        mp = sum(ps[i] for i in idx) / len(idx)
        my = sum(ys[i] for i in idx) / len(idx)
        err += len(idx) / tot * abs(mp - my)
    return err


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-sims", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    ls = _load_ladder_sim()

    df = pl.scan_parquet(SCORED).select(
        ["game_date", "pitcher", "player_name", "K", "PA", "k_rate_P10",
         "projected_tbf"] + list(CAL_COLS.values())).collect().sort(
        ["pitcher", "game_date"])
    a0, b0 = ls.league_prior(df)
    tbf_sd = float(df.select(
        pl.col("projected_tbf").cast(pl.Float64)).to_series().std() or 3.0)

    by_pitcher: dict = {}
    for pid, grp in df.group_by("pitcher", maintain_order=True):
        by_pitcher[pid] = grp.to_dicts()
    # Archetype cuts from trailing rate/spread pools (same as ladder_sim).
    rates_pool, spread_pool, scoped = [], [], []
    for pid, rows in by_pitcher.items():
        for i in range(1, len(rows)):
            k, pa, rates = ls.trailing_k_pa(rows, i)
            if pa <= 0:
                continue
            kr, spread = k / pa, float(np.std(rates)) if len(rates) > 1 else 0.0
            rates_pool.append(kr)
            spread_pool.append(spread)
            scoped.append((rows[i], k, pa, kr, spread))
    rate_cut = float(np.quantile(rates_pool, 0.5))
    spread_cut = float(np.median(spread_pool))

    acc: dict[str, dict[str, dict[str, list]]] = {}
    kalshi_pairs: dict[str, list[tuple[float, int]]] = {}
    kmap = kalshi_close_map()
    for row, k, pa, kr, spread in scoped:
        try:
            actual_k = float(row["K"])
            tbf_mean = float(row["projected_tbf"])
            lam_point = float(row["k_rate_P10"]) * tbf_mean
        except (TypeError, ValueError):
            continue
        arch = ls.archetype(kr, spread, rate_cut, spread_cut)
        probs_v2 = ls.sim_start_over_probs(
            rng, k, pa, tbf_mean, tbf_sd, a0, b0, args.n_sims)
        gd = str(row["game_date"])[:10]
        pname = _norm(row.get("player_name"))
        for rung in RUNGS:
            y = 1 if actual_k > rung else 0
            cal = row.get(CAL_COLS[rung])
            try:
                p_cal = float(cal) if cal is not None else None
            except (TypeError, ValueError):
                p_cal = None
            bucket = acc.setdefault(arch, {}).setdefault(str(rung),
                {"poisson": [], "ws1c": [], "v2": [], "y": []})
            bucket["poisson"].append(poisson_over(lam_point, rung))
            bucket["v2"].append(probs_v2[rung])
            if p_cal is not None:
                bucket["ws1c"].append(p_cal)
                bucket["y"].append(y)
            else:
                bucket["ws1c"].append(float("nan"))
                bucket["y"].append(y)
            kf = kmap.get((gd, pname, float(rung)))
            if kf is not None:
                kalshi_pairs.setdefault(str(rung), []).append((kf, y))
    rep: dict = {"built": "ladder_showdown v1", "n_sims": args.n_sims,
                 "n_starts": len(scoped), "overall": {}, "by_archetype": {}}

    def _metrics(pairs: list[tuple[float, int]]) -> dict:
        ps = [p for p, _ in pairs]
        ys = [y for _, y in pairs]
        if not ps:
            return {"n": 0, "brier": None, "logloss": None, "ece": None}
        return {"n": len(ps), "brier": round(brier(ps, ys), 5),
                "logloss": round(logloss(ps, ys), 5),
                "ece": round(ece(ps, ys), 5)}

    def _clean(vals: list) -> list[float]:
        out = []
        for v in vals:
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if f == f:  # drop NaN
                out.append(f)
        return out

    for model in ("poisson", "ws1c", "v2"):
        pairs_all: list[tuple[float, int]] = []
        for arch in ("power", "standard"):
            pairs_arch: list[tuple[float, int]] = []
            for rung in RUNGS:
                b = acc.get(arch, {}).get(str(rung), {})
                for p, y in zip(b.get(model, []), b.get("y", [])):
                    try:
                        f = float(p)
                    except (TypeError, ValueError):
                        continue
                    if f != f:  # NaN (ws1c gaps) — drop the PAIR, keep alignment
                        continue
                    pairs_arch.append((f, int(y)))
                    pairs_all.append((f, int(y)))
            rep["by_archetype"].setdefault(arch, {})[model] = _metrics(pairs_arch)
        rep["overall"][model] = _metrics(pairs_all)
    # Kalshi closes (4th contestant): overall + by rung (no archetype — the
    # lake join is name+date, independent of our trailing windows).
    # Kalshi closes (4th contestant): overall + by rung (no archetype — the
    # lake join is name+date, independent of our trailing windows).
    # DATA-QUALITY CAVEAT (owner 2026-09-24): k_closes.close_fair_over spans
    # only [0.23, 0.69] (std 0.068) — close-anchored construction with almost
    # no resolution. Brier ≈ base-rate variance is EXPECTED, not a verdict on
    # Kalshi. The LIVE ladder (yes_price full 0-1) is the usable source going
    # forward; these numbers are reported for completeness, not ranking.
    kpairs_all: list[tuple[float, int]] = []
    rep["kalshi"] = {"by_rung": {}, "match_note": "k_closes x k_ladder bridge"}
    for rung in RUNGS:
        rep["kalshi"]["by_rung"][str(rung)] = _metrics(
            kalshi_pairs.get(str(rung), []))
        kpairs_all.extend(kalshi_pairs.get(str(rung), []))
    rep["kalshi"]["overall"] = _metrics(kpairs_all)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=2, default=str))
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
