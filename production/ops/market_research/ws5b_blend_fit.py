"""WS5b v2 — fit slot blend BEFORE judging spread (post hoc, research).

v1 confounded mean+spread (fixed 50/50). v2: slot_p = w*batter + (1-w)*pitcher,
grid w on TRAIN dates (Brier vs binomial baseline, all lines pooled), judge
best-w on TEST dates. If best-w still loses to binomial, spread is dead.

Writes artifacts/odds_log/ws5b_v2_report.json. No live change.
Kill: best-w test Brier >= binomial (retire Poisson-binomial).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.count_layer import over_threshold, p_strikeouts_ge  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402
from ws5b_poisson_binomial import pb_sf  # noqa: E402

SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
BAT = ROOT / "data" / "processed" / "batter_rolling.parquet"
ODDS_DIR = ROOT / "artifacts" / "odds_log"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
CUT = "2026-05-23"
GRID = [0.0, 0.25, 0.5, 0.75, 1.0]


def collect():
    sc = pl.scan_parquet(SCORED).select(
        ["gd", "game_pk", "pitcher", "p_throws", "K",
         "k_rate_pred", "projected_tbf", "is_home", "home_team", "away_team"]).collect().filter(
        pl.col("K").is_not_null() & pl.col("k_rate_pred").is_not_null()
        & pl.col("projected_tbf").is_not_null() & (pl.col("projected_tbf") > 0))
    bat = pl.scan_parquet(BAT).select(
        ["game_pk", "bat_team", "lineup_slot", "stand", "is_initial_lineup",
         "k_rate_std_vL", "k_rate_std_vR"]).collect().filter(pl.col("is_initial_lineup"))
    out = []
    for r in sc.to_dicts():
        opp = r["away_team"] if r["is_home"] else r["home_team"]
        slots = bat.filter((pl.col("game_pk") == r["game_pk"]) & (pl.col("bat_team") == opp)).sort("lineup_slot")
        if slots.height < 9:
            continue
        hand = "vR" if str(r["p_throws"]).upper().startswith("R") else "vL"
        kr = float(r["k_rate_pred"])
        tbf = int(round(float(r["projected_tbf"])))
        brat = []
        for s in slots.head(9).to_dicts():
            b = s[f"k_rate_std_{hand}"]
            brat.append(float(b) if b is not None else kr)
        out.append({"gd": r["gd"], "K": float(r["K"]), "kr": kr, "tbf": tbf, "brat": brat})
    return out


def brier_starts(rows, w, fam) -> float:
    se, n = 0.0, 0
    for r in rows:
        probs = np.array([w * b + (1 - w) * r["kr"] for b in r["brat"]])
        trials = np.array([probs[i % 9] for i in range(max(r["tbf"], 1))])
        for ln in LINES:
            if fam == "pb":
                p = pb_sf(trials, ln)
            else:
                p = float(p_strikeouts_ge(ln, k_rate=np.array([r["kr"]]),
                                          projected_tbf=np.array([r["tbf"]]), family="binomial")[0])
            y = 1.0 if r["K"] > ln else 0.0
            se += (p - y) ** 2
            n += 1
    return se / n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args()
    rows = collect()
    print(f"starts: {len(rows)}")
    tr = [r for r in rows if r["gd"] <= CUT]
    te = [r for r in rows if r["gd"] > CUT]
    base_tr = brier_starts(tr, 0.5, "bin")
    base_te = brier_starts(te, 0.5, "bin")
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "cut": CUT,
                 "n_train": len(tr), "n_test": len(te),
                 "binomial_train": base_tr, "binomial_test": base_te, "grid": []}
    print(f"binomial train {base_tr:.4f} test {base_te:.4f}")
    for w in GRID:
        btr = brier_starts(tr, w, "pb")
        rep["grid"].append({"w": w, "train": btr})
        print(f"w={w}: train pb brier={btr:.4f}")
    best = min(rep["grid"], key=lambda d: d["train"])
    bte = brier_starts(te, best["w"], "pb")
    rep["best_w"] = best["w"]
    rep["pb_test"] = bte
    print(f"best w={best['w']}: test pb={bte:.4f} vs binom={base_te:.4f}")
    rep["kill"] = "SURVIVE" if bte < base_te - 0.0005 else "KILL"
    out = ODDS_DIR / "ws5b_v2_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
