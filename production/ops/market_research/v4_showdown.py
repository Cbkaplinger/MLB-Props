"""v4 showdown: PA sim on REAL lineups vs actuals (research, owner 2026-09-24).

Proves or kills the PA approach: for historical starts on dates with saved
RG lineups, rebuild the 9-slot order (batter IDs), attach as-of batter K
rates (hand-neutral k_rate_std — vs-hand split noted as follow-up), log5 vs
the pitcher's trailing K-rate, sim games, and score Brier per rung vs the
actual K. Contestants: v4_pa, poisson_point, ws1c_cal (frozen production).

Limits (labeled): 6 lineup dates on disk; hand-neutral batter rates;
300 sims/start (speed); TBF emergent (no TBF input).

Reads: data/processed/daily_lineups_*.parquet, batter_rolling.parquet,
  artifacts/live_scores/historical_scores_2025_2026.parquet.
Writes: artifacts/odds_log/v4_showdown_report.json.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
LINEUP_GLOB = "data/processed/daily_lineups_*.parquet"
BATTER_ROLLING = ROOT / "data" / "processed" / "batter_rolling.parquet"
SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
OUT = ROOT / "artifacts" / "odds_log" / "v4_showdown_report.json"
RUNGS = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _brier(ps, ys):
    ps = np.array(ps, dtype=float)
    ys = np.array(ys, dtype=float)
    return float(np.mean((ps - ys) ** 2)) if len(ps) else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-sims", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-starts", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    pa = _load("pa_sim", "production/ops/market_research/pa_sim.py")
    cs = _load("calibrate_showdown",
               "production/ops/market_research/calibrate_showdown.py")

    frames = []
    for f in sorted((ROOT / "data" / "processed").glob("daily_lineups_*.parquet")):
        frames.append(pl.scan_parquet(f).select(
            ["game_pk", "team", "batting_order", "batter",
             "away_probable_pitcher_id", "home_probable_pitcher_id",
             "away_team", "home_team"]).collect())
    lineups = pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()
    lineups = lineups.with_columns(pl.col("batter").cast(pl.Int64))
    bro = pl.scan_parquet(BATTER_ROLLING).select(
        ["batter", "game_date", "k_rate_std"]).collect()
    bro = bro.with_columns(pl.col("batter").cast(pl.Int64),
                           pl.col("game_date").cast(pl.Date))
    scores = pl.scan_parquet(SCORED).select(
        ["game_pk", "game_date", "pitcher", "player_name", "K", "k_rate_P10",
         "projected_tbf", "p_throws"] + [
            f"p_over_{str(r).replace('.', '_')}_cal" for r in RUNGS]).collect()
    scores = scores.with_columns(pl.col("game_date").cast(pl.Date))
    league = float(
        pl.scan_parquet(SCORED).select("K").collect()["K"].sum()
        / max(pl.scan_parquet(SCORED).select("PA").collect()["PA"].sum(), 1))

    starts = scores.filter(pl.col("game_pk").is_in(lineups["game_pk"].unique().to_list()))
    if args.max_starts:
        starts = starts.head(args.max_starts)
    acc: dict[str, dict[str, list]] = {}
    n = 0
    for row in starts.to_dicts():
        gd, gpk = row["game_date"], row["game_pk"]
        game_rows = lineups.filter(pl.col("game_pk") == gpk).to_dicts()
        if not game_rows:
            continue
        # Pitcher's own side via probable IDs; opponent = the other dugout.
        first = game_rows[0]
        try:
            pid = int(row["pitcher"])
        except (TypeError, ValueError):
            continue
        pitch_team = None
        try:
            if first.get("away_probable_pitcher_id") is not None and int(
                    first["away_probable_pitcher_id"]) == pid:
                pitch_team = str(first.get("away_team"))
            elif first.get("home_probable_pitcher_id") is not None and int(
                    first["home_probable_pitcher_id"]) == pid:
                pitch_team = str(first.get("home_team"))
        except (TypeError, ValueError):
            pitch_team = None
        if pitch_team is None:
            continue
        ordered = sorted(
            [r for r in game_rows if str(r.get("team")) != pitch_team
             and r.get("batting_order")],
            key=lambda r: int(r["batting_order"] or 99))[:9]
        if len(ordered) != 9:
            continue
        slots = ordered
        slot_rates = []
        ok = True
        for s in slots:
            past = bro.filter((pl.col("batter") == int(s["batter"]))
                              & (pl.col("game_date") < gd)).sort("game_date")
            if past.is_empty() or past["k_rate_std"][-1] is None:
                ok = False
                break
            try:
                slot_rates.append(float(past["k_rate_std"][-1]))
            except (TypeError, ValueError):
                ok = False
                break
        if not ok:
            continue
        try:
            p_pitch = float(row["k_rate_P10"])
            actual = float(row["K"])
            tbf = float(row["projected_tbf"])
        except (TypeError, ValueError):
            continue
        probs = pa.sim_over_probs(rng, slot_rates, p_pitch, league,
                                  RUNGS, args.n_sims)
        lam = p_pitch * tbf
        for rung in RUNGS:
            y = 1 if actual > rung else 0
            b = acc.setdefault(str(rung), {"v4": [], "poisson": [], "ws1c": [], "y": []})
            b["v4"].append(probs[rung])
            b["poisson"].append(cs.poisson_over(lam, rung))
            cal = row.get(f"p_over_{str(rung).replace('.', '_')}_cal")
            try:
                b["ws1c"].append(float(cal) if cal is not None else float("nan"))
            except (TypeError, ValueError):
                b["ws1c"].append(float("nan"))
            b["y"].append(y)
        n += 1
    rep: dict = {"built": "v4_showdown v1", "n_starts": n, "n_sims": args.n_sims,
                 "overall": {}, "by_rung": {}}
    for model in ("v4", "poisson", "ws1c"):
        ps, ys = [], []
        for rung in RUNGS:
            b = acc.get(str(rung), {})
            for p, y in zip(b.get(model, []), b.get("y", [])):
                try:
                    f = float(p)
                except (TypeError, ValueError):
                    continue
                if f != f:
                    continue
                ps.append(f)
                ys.append(int(y))
        rep["overall"][model] = {"n": len(ps), "brier": _brier(ps, ys) if ps else None}
    for rung in RUNGS:
        rep["by_rung"][str(rung)] = {}
        for model in ("v4", "poisson", "ws1c"):
            b = acc.get(str(rung), {})
            pairs = [(float(p), int(y)) for p, y in zip(b.get(model, []), b.get("y", []))
                     if p == p]
            rep["by_rung"][str(rung)][model] = {
                "n": len(pairs),
                "brier": _brier([p for p, _ in pairs], [y for _, y in pairs]) if pairs else None}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=2, default=str))
    print(json.dumps(rep["overall"], indent=1))
    print("n_starts:", n)


if __name__ == "__main__":
    main()
