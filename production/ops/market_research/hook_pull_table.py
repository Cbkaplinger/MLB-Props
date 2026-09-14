"""Hook pull-probability table from Savant pbp (descriptive research, no live change).

P(pulled after this batter | pitches thrown, times-through-order, score diff,
inning band). This table is the pull decision a future at-bat Monte Carlo
needs at each simulated batter. v1 uses score diff + counts only (no bullpen
rest, no pitcher random effects — scoped follow-ups, not promises).

Reads: data/Savant-Data/regular/<year>/statcast_<year>_regular.parquet
Writes: artifacts/odds_log/hook_pull_report.json (+ pull table parquet)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[3]
SAV = REPO / "data" / "Savant-Data" / "regular"
OUT_JSON = REPO / "artifacts" / "odds_log" / "hook_pull_report.json"
OUT_PARQ = REPO / "artifacts" / "odds_log" / "hook_pull_table.parquet"


def pitch_bucket(p: int) -> str:
    if p < 50:
        return "0-49"
    if p < 75:
        return "50-74"
    if p < 90:
        return "75-89"
    if p < 100:
        return "90-99"
    return "100+"


def score_bucket(d: int) -> str:
    if d <= -3:
        return "trailing3+"
    if d >= 3:
        return "leading3+"
    return "close"


def inning_bucket(i: int) -> str:
    if i <= 3:
        return "1-3"
    if i <= 6:
        return "4-6"
    return "7+"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2025,2026")
    args = ap.parse_args()
    years = [y.strip() for y in args.years.split(",") if y.strip()]

    frames = []
    for y in years:
        fp = SAV / y / f"statcast_{y}_regular.parquet"
        frames.append(
            pl.scan_parquet(fp)
            .select(["game_pk", "pitcher", "at_bat_number", "pitch_number",
                     "inning", "bat_score", "fld_score"])
            .collect()
        )
    pbp = pl.concat(frames)

    # One row per (game, pitcher, PA): pitches used, TTO, score diff, pulled?
    pa = (
        pbp.group_by(["game_pk", "pitcher", "at_bat_number"])
        .agg(
            pl.col("pitch_number").max().alias("pa_pitches"),
            pl.col("inning").first().alias("inning"),
            (pl.col("fld_score").first() - pl.col("bat_score").first()).alias("score_diff"),
        )
        .sort(["game_pk", "pitcher", "at_bat_number"])
    )
    d = pa.to_dicts()
    rows = []
    # Walk PAs in order; cumulative pitches + TTO vs this pitcher; pulled if the
    # next PA in this game goes to a different pitcher or this was his last PA.
    idx_by_game: dict = {}
    for i, r in enumerate(d):
        idx_by_game.setdefault((r["game_pk"], r["pitcher"]), []).append(i)
    for (g, p), idxs in idx_by_game.items():
        cum = 0
        game_pa_after = None
        # find the PA index right after this pitcher's last PA in this game
        last = idxs[-1]
        nxt = d[last + 1] if last + 1 < len(d) and d[last + 1]["game_pk"] == g else None
        for t, i in enumerate(idxs):
            r = d[i]
            cum += int(r["pa_pitches"] or 0)
            is_last = (t == len(idxs) - 1)
            # pulled mid-game if another pitcher appears later in this game
            pulled = False
            if is_last and nxt is not None and nxt["pitcher"] != p:
                pulled = True
            rows.append({
                "pitches": cum,
                "tto": t // 9 + 1,
                "score_diff": int(r["score_diff"] or 0),
                "inning": int(r["inning"] or 0),
                "pulled": pulled,
            })

    full = pl.DataFrame(rows).with_columns(
        pl.col("pitches").map_elements(pitch_bucket, return_dtype=pl.String).alias("pitch_band"),
        pl.col("score_diff").map_elements(score_bucket, return_dtype=pl.String).alias("score_band"),
        pl.col("inning").map_elements(inning_bucket, return_dtype=pl.String).alias("inning_band"),
        pl.col("tto").map_elements(lambda t: str(min(int(t), 4)) if int(t) < 4 else "4+", return_dtype=pl.String).alias("tto_band"),
    )
    table = (
        full.group_by(["pitch_band", "tto_band", "score_band", "inning_band"])
        .agg(pl.len().alias("n"), pl.col("pulled").mean().alias("pull_rate"))
        .sort(["pitch_band", "tto_band", "score_band", "inning_band"])
    )
    overall = float(full["pulled"].mean())
    cells = table.to_dicts()
    thin = [c for c in cells if c["n"] < 200]
    hot = sorted([c for c in cells if c["n"] >= 500], key=lambda c: c["pull_rate"], reverse=True)[:5]
    report = {
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "years": years,
        "n_pa": full.height,
        "overall_pull_rate": round(overall, 4),
        "n_cells": len(cells),
        "n_thin_cells": len(thin),
        "hottest_cells": [{**c, "pull_rate": round(c["pull_rate"], 3)} for c in hot],
        "note": "v1 descriptive pull table for the post-season Monte Carlo design. "
                "No bullpen-rest, no pitcher random effects. No live use.",
    }
    OUT_JSON.write_text(json.dumps(report, indent=2))
    table.write_parquet(OUT_PARQ)
    print(f"wrote {OUT_JSON} + {OUT_PARQ}")
    print(f"n_pa={full.height} overall_pull={overall:.4f} cells={len(cells)} thin={len(thin)}")


if __name__ == "__main__":
    main()
