"""Monte Carlo vs reality gate (pre-registered, research).

Compares MC-implied P(over) against the live Poisson+WS1c config on the
universe close-matched panel: Brier (gate >= 0.0005 gain), ECE/MCE, and the
4.5/5.5 bleed cells. Same subset throughout (SOP 8).

Reads: universe_panel_live (p_ours_cal, y, line) + historical_scores (k_rate,
projected_tbf) + hook table. MC: 1000 sims/start, PA draws at k_rate with
hook-table pull hazard (labeled approximations).
Writes: artifacts/odds_log/mc_reality_report.json. No live change.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util as _ilu
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src" / "Python"))

_JK = REPO / "production" / "ops" / "market_research" / "join_keys.py"
_spec = _ilu.spec_from_file_location("join_keys", _JK)
assert _spec and _spec.loader
_jk = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_jk)

UNI = REPO / "artifacts" / "odds_log" / "universe_panel_live.parquet"
SCORED = REPO / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
HOOK = REPO / "artifacts" / "odds_log" / "hook_pull_table.parquet"
OUT = REPO / "artifacts" / "odds_log" / "mc_reality_report.json"

PITCHES_PER_PA = 3.85
MAX_PA = 40


def ece_mce(pairs: list[tuple[float, float]], k: int = 10) -> tuple[float, float]:
    pairs = sorted(pairs, key=lambda r: r[0])
    n = len(pairs)
    e = m = 0.0
    for i in range(k):
        b = pairs[i * n // k:(i + 1) * n // k]
        if not b:
            continue
        acc = sum(r[1] for r in b) / len(b)
        conf = sum(r[0] for r in b) / len(b)
        e += abs(acc - conf) * len(b) / n
        m = max(m, abs(acc - conf))
    return round(e, 4), round(m, 4)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-sims", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    hook = {(r["pitch_band"], r["tto_band"], r["score_band"], r["inning_band"]): float(r["pull_rate"])
            for r in pl.read_parquet(HOOK).to_dicts()}

    def pull_prob(pitches: int, tto: int) -> float:
        pb = "0-49" if pitches < 50 else ("50-74" if pitches < 75 else ("75-89" if pitches < 90 else ("90-99" if pitches < 100 else "100+")))
        tb = str(min(tto, 3)) if tto < 4 else "4+"
        ib = "1-3" if pitches < 50 else ("4-6" if pitches < 90 else "7+")
        return hook.get((pb, tb, "close", ib), 0.10)

    sc = {(str(r["game_date"])[:10], _jk.sorted_key(r["pitcher_name"])): (float(r["k_rate_pred"]), float(r["projected_tbf"]))
          for r in pl.scan_parquet(SCORED).select(["game_date", "pitcher_name", "k_rate_pred", "projected_tbf"]).collect().to_dicts()
          if r["k_rate_pred"] is not None and r["projected_tbf"] is not None}
    uni = (pl.scan_parquet(UNI).select(["gd", "key", "line", "y", "p_ours_cal"]).collect().to_dicts())

    se_live = se_mc = 0.0
    pairs_live: list = []
    pairs_mc: list = []
    cells: dict[str, dict] = {}
    n = 0
    for r in uni:
        try:
            line = float(r["line"])
            y = float(r["y"])
            plive = float(r["p_ours_cal"])
        except (TypeError, ValueError):
            continue
        hit = sc.get((str(r["gd"]), _jk.sorted_key(r["key"])))
        if hit is None or not 0.0 < plive < 1.0:
            continue
        kr0, tbf = hit
        kr = float(np.clip(kr0, 0.02, 0.5))
        alive = np.ones(args.n_sims, dtype=bool)
        ks = np.zeros(args.n_sims, dtype=np.int32)
        for pa in range(MAX_PA):
            pitches = int((pa + 1) * PITCHES_PER_PA)
            hp = pull_prob(pitches, pa // 9 + 1)
            alive[alive & (rng.random(args.n_sims) < hp)] = False
            act = alive
            if not act.any():
                break
            ks[act] += (rng.random(args.n_sims)[act] < kr).astype(np.int32)
        p_mc = float((ks.astype(float) > line).mean())
        se_live += (plive - y) ** 2
        se_mc += (p_mc - y) ** 2
        pairs_live.append((plive, y))
        pairs_mc.append((p_mc, y))
        n += 1
        c = cells.setdefault(f"@{line}", {"n": 0, "b": 0.0, "o": 0.0})
        c["n"] += 1
        c["b"] += (plive - y) ** 2
        c["o"] += (p_mc - y) ** 2
    e_live, m_live = ece_mce(pairs_live)
    e_mc, m_mc = ece_mce(pairs_mc)
    gain = (se_live - se_mc) / n if n else None
    rep = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "n": n, "n_sims": args.n_sims,
           "brier_live": round(se_live / n, 4) if n else None,
           "brier_mc": round(se_mc / n, 4) if n else None,
           "gain_mc_vs_live": round(gain, 5) if gain is not None else None,
           "ece_live": e_live, "mce_live": m_live, "ece_mc": e_mc, "mce_mc": m_mc,
           "cells": {c: {"n": v["n"], "live": round(v["b"] / v["n"], 4), "mc": round(v["o"] / v["n"], 4)}
                     for c, v in sorted(cells.items())},
           "kill": "SURVIVE (overlay/proposal next)"
           if gain is not None and gain >= 0.0005 else "KILL (MC does not beat live config)"}
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
