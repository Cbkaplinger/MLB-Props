"""Glicko-style pitcher ratings from L3 starts (descriptive research, no live change).

Each starter carries a rating R (K-rate scale) plus an uncertainty RD that
shrinks with observed PA and grows with layoff. Empirical-Bayes form of the
Glicko idea: estimate + uncertainty, not a point. v1 is opponent-unadjusted
(raw K-rate vs league prior); opponent adjustment is a scoped v2.

Reads: data/processed/pitcher_training.parquet (game_date, pitcher_name, K, PA)
Writes: artifacts/odds_log/glicko_ratings_report.json (+ current ratings table)
Kill (SOP stability gate): YoY correlation of R < 0.7 -> parked, not promoted.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[3]
L3 = REPO / "data" / "processed" / "pitcher_training.parquet"
OUT_JSON = REPO / "artifacts" / "odds_log" / "glicko_ratings_report.json"
OUT_PARQ = REPO / "artifacts" / "odds_log" / "glicko_ratings_current.parquet"

PRIOR_PA = 300.0  # one ~season-equivalent of league prior/person
RD_FLOOR = 0.004
RD_START = 0.030  # debut uncertainty on the K-rate scale
LAYOFF_GROWTH_PER_DAY = 0.00004  # RD grows slowly between starts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prior-pa", type=float, default=PRIOR_PA)
    args = ap.parse_args()

    df = (
        pl.read_parquet(L3)
        .filter(pl.col("PA").is_not_null() & (pl.col("PA") > 0))
        .select(["game_date", "pitcher_name", "K", "PA"])
        .sort(["pitcher_name", "game_date"])
        .to_dicts()
    )
    league = sum(float(r["K"]) for r in df) / max(1.0, sum(float(r["PA"]) for r in df))

    state: dict[str, dict] = {}
    snapshots: dict[str, list] = {}  # pitcher -> [(year, R)]
    for r in df:
        name = str(r["pitcher_name"])
        gd = r["game_date"]
        year = int(str(gd)[:4])
        k, pa = float(r["K"]), float(r["PA"])
        st = state.get(name)
        if st is None:
            st = {"k_sum": 0.0, "pa_sum": 0.0, "last_gd": None, "rd": RD_START}
            state[name] = st
        if st["last_gd"] is not None:
            try:
                gap = (gd - st["last_gd"]).days
            except Exception:
                gap = 5
            st["rd"] = min(RD_START, st["rd"] + max(0, gap) * LAYOFF_GROWTH_PER_DAY)
        st["k_sum"] += k
        st["pa_sum"] += pa
        eff = args.prior_pa + st["pa_sum"]
        st["R"] = (args.prior_pa * league + st["k_sum"]) / eff
        st["rd"] = max(RD_FLOOR, 1.0 / (eff**0.5) * (league**0.5))
        st["last_gd"] = gd
        snaps = snapshots.setdefault(name, [])
        if not snaps or snaps[-1][0] != year:
            snaps.append((year, st["R"]))
        else:
            snaps[-1] = (year, st["R"])

    # YoY stability of year-end R (SOP gate).
    xs, ys = [], []
    for _name, snaps in snapshots.items():
        d = dict(snaps)
        for y in (2024, 2025):
            if y in d and y + 1 in d:
                xs.append(d[y])
                ys.append(d[y + 1])
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / n
    vx = sum((a - mx) ** 2 for a in xs) / n
    vy = sum((b - my) ** 2 for b in ys) / n
    yoy = cov / ((vx * vy) ** 0.5) if vx > 0 and vy > 0 else 0.0

    current = [
        {"pitcher": name, "R": round(st["R"], 4), "RD": round(st["rd"], 4),
         "pa_seen": round(st["pa_sum"], 1)}
        for name, st in sorted(state.items(), key=lambda kv: kv[1]["R"], reverse=True)
    ]
    wide = [c for c in current if c["RD"] >= 0.015]
    report = {
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "league_k_rate": round(league, 4),
        "prior_pa": args.prior_pa,
        "n_pitchers": len(current),
        "yoy_pairs": n,
        "yoy_corr_R": round(yoy, 3),
        "stability_gate": "PASS (>=0.7)" if yoy >= 0.7 else "FAIL (<0.7, parked)",
        "n_wide_RD": len(wide),
        "top5": current[:5],
        "bottom5": current[-5:],
        "note": "v1 opponent-unadjusted. No live use: descriptive table for the "
                "October rating-with-uncertainty design.",
    }
    OUT_JSON.write_text(json.dumps(report, indent=2))
    pl.DataFrame(current).write_parquet(OUT_PARQ)
    print(f"wrote {OUT_JSON} + {OUT_PARQ}")
    print(f"YoY r={yoy:.3f} (n={n}) -> {report['stability_gate']}")


if __name__ == "__main__":
    main()
