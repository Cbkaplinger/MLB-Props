"""Universe join — scored frozen bundle x book panels (post hoc, research).

Reads (never re-scores):
  artifacts/live_scores/historical_scores_2025_2026.parquet (ours)
  data/Odds-Historical/theoddsapi/book_lines_pitcher.parquet (main+alt, morn+close)
  data/Odds-Open-Close-2025-2026/pitcher_*_open_2025_2026.csv (friend opens)

Keys: (gd, key_sorted, line) via join_keys.sorted_key on both sides.
Explodes scored starts to per-line rows (2.5-9.5), y = 1{K>line}.

Writes (ignored):
  artifacts/odds_log/universe_panel.parquet — one row per start x line
  artifacts/odds_log/universe_join_audit.json — n_in/n_matched/unmatched-why
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.market import american_to_implied_prob  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402
from join_keys import HIST, ODDS_DIR, load_event_date_map, read_consensus_cache, sorted_key  # noqa: E402
from analyze_book_skill import _devig_pair  # noqa: E402 (alt/friend panels only; mains read cache)

LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"


def devig_median_panel(market: str, snapshot: str, evdate: dict) -> pl.DataFrame:
    """Two-way devig-median consensus per (gd, key, line). Main markets only."""
    bk = pl.scan_parquet(HIST / "book_lines_pitcher.parquet").filter(
        (pl.col("market") == market) & (pl.col("snapshot") == snapshot)).collect()
    over = bk.filter(pl.col("side") == "over").select(
        ["event_id", "player_norm", "line", "book", "price"])
    under = bk.filter(pl.col("side") == "under").select(
        ["event_id", "player_norm", "line", "book", "price"])
    pairs = over.join(under, on=["event_id", "player_norm", "line", "book"], suffix="_u")
    rows = []
    for r in pairs.to_dicts():
        fo, _ = _devig_pair(r["price"], r["price_u"])
        if fo is not None:
            rows.append({"gd": evdate.get(r["event_id"], ""),
                         "key": sorted_key(r["player_norm"]),
                         "line": float(r["line"]), "fair": fo})
    if not rows:
        return pl.DataFrame({"gd": [], "key": [], "line": [], "fair": [], "n_books": []})
    pf = pl.DataFrame(rows).filter(pl.col("gd") != "")
    return pf.group_by(["gd", "key", "line"]).agg(
        pl.col("fair").median().alias("fair"), pl.len().alias("n_books"))


def alt_implicit_panel(snapshot: str, evdate: dict) -> pl.DataFrame:
    """Over-only vig-loaded median implicit per (gd, key, line). Labeled."""
    alt = pl.scan_parquet(HIST / "book_lines_pitcher.parquet").filter(
        (pl.col("market") == "pitcher_strikeouts_alternate")
        & (pl.col("snapshot") == snapshot) & (pl.col("side") == "over")).collect()
    rows = []
    for r in alt.to_dicts():
        try:
            ip = american_to_implied_prob(float(r["price"]))
        except (TypeError, ValueError):
            continue
        rows.append({"gd": evdate.get(r["event_id"], ""),
                     "key": sorted_key(r["player_norm"]),
                     "line": float(r["line"]), "fair": ip})
    pf = pl.DataFrame(rows).filter(pl.col("gd") != "")
    return pf.group_by(["gd", "key", "line"]).agg(
        pl.col("fair").median().alias("fair"), pl.len().alias("n_books"))


def friend_panel() -> pl.DataFrame:
    """Friend -12h opens, devigged per book then median. K + outs."""
    frames = []
    for f in ["pitcher_strikeouts_early_open_2025_2026.csv", "pitcher_outs_open_2025_2026.csv"]:
        fp = ROOT / "data" / "Odds-Open-Close-2025-2026" / f
        df = pl.scan_csv(fp, ignore_errors=True).select(
            ["game_date", "player_name", "line", "over_odds", "under_odds"]).collect()
        rows = []
        for r in df.to_dicts():
            try:
                po = 1.0 / american_to_implied_prob(float(r["over_odds"]))
            except (TypeError, ValueError):
                continue
            try:
                pu = 1.0 / american_to_implied_prob(float(r["under_odds"]))
            except (TypeError, ValueError):
                continue
            tot = po + pu
            if tot <= 0:
                continue
            rows.append({"gd": str(r["game_date"])[:10], "key": sorted_key(r["player_name"]),
                         "line": float(r["line"]), "fair": po / tot})
        if rows:
            frames.append(pl.DataFrame(rows))
    if not frames:
        return pl.DataFrame({"gd": [], "key": [], "line": [], "fair": [], "n_books": []})
    pf = pl.concat(frames)
    return pf.group_by(["gd", "key", "line"]).agg(
        pl.col("fair").median().alias("fair"), pl.len().alias("n_books"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=str, default=str(SCORED),
                    help="scored-starts parquet in (default: frozen scores)")
    ap.add_argument("--panel-out", type=str, default=str(ODDS_DIR / "universe_panel.parquet"),
                    help="output panel path (pass NEW path for variants)")
    ap.add_argument("--audit-out", type=str, default=str(ODDS_DIR / "universe_join_audit.json"),
                    help="output audit path (pass NEW path for variants)")
    args = ap.parse_args()
    evdate = load_event_date_map()
    print(f"event-date map: {len(evdate)} events")

    sc = pl.scan_parquet(args.scores).select(
        ["gd", "key_sorted", "player_name", "expected_K", "K",
         "p_over_2_5", "p_over_3_5", "p_over_4_5", "p_over_5_5",
         "p_over_6_5", "p_over_7_5", "p_over_8_5", "p_over_9_5",
         "p_over_2_5_cal", "p_over_3_5_cal", "p_over_4_5_cal", "p_over_5_5_cal",
         "p_over_6_5_cal", "p_over_7_5_cal", "p_over_8_5_cal", "p_over_9_5_cal",
         ]).collect()
    print(f"scored starts: {sc.height}")

    # explode to per-line rows (set-based)
    parts = []
    for ln in LINES:
        stem = str(ln).replace(".", "_")
        cols = ["gd", "key_sorted", "player_name", "expected_K", "K"]
        if f"p_over_{stem}" in sc.columns:
            cols.append(f"p_over_{stem}")
        if f"p_over_{stem}_cal" in sc.columns:
            cols.append(f"p_over_{stem}_cal")
        part = sc.select(cols).with_columns(pl.lit(ln).alias("line"))
        rename = {}
        if f"p_over_{stem}" in part.columns:
            rename[f"p_over_{stem}"] = "p_ours"
        if f"p_over_{stem}_cal" in part.columns:
            rename[f"p_over_{stem}_cal"] = "p_ours_cal"
        part = part.rename(rename)
        if "p_ours" not in part.columns:
            part = part.with_columns(pl.lit(None, dtype=pl.Float64).alias("p_ours"))
        if "p_ours_cal" not in part.columns:
            part = part.with_columns(pl.lit(None, dtype=pl.Float64).alias("p_ours_cal"))
        parts.append(part)
    ours = pl.concat(parts, how="diagonal_relaxed").filter(
        pl.col("p_ours").is_not_null() & pl.col("K").is_not_null()).with_columns(
        (pl.col("K").cast(pl.Float64) > pl.col("line")).cast(pl.Float64).alias("y"))
    print(f"ours line-points: {ours.height}")

    audit: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(),
                   "ours_line_points": ours.height, "sources": {}}
    panels = {"book_close": read_consensus_cache("pitcher_strikeouts", "close").rename({"fair": "fair"}),
              "book_morning": read_consensus_cache("pitcher_strikeouts", "morning"),
              "alt_close": alt_implicit_panel("close", evdate),
              "alt_morning": alt_implicit_panel("morning", evdate),
              "friend_open": friend_panel()}
    panel = ours.rename({"key_sorted": "key"})
    for name, pf in panels.items():
        m = panel.join(pf, on=["gd", "key", "line"], how="left").select("fair")
        matched = m.filter(pl.col("fair").is_not_null()).height
        panel = panel.join(pf.rename({"fair": f"p_{name}", "n_books": f"nb_{name}"}),
                           on=["gd", "key", "line"], how="left")
        audit["sources"][name] = {"book_props": pf.height, "matched": matched,
                                  "rate": matched / panel.height if panel.height else 0.0}
    out = Path(args.panel_out)
    panel.write_parquet(out)
    audit["panel_rows"] = panel.height
    audit["panel_path"] = str(out)
    atomic_write_text(Path(args.audit_out),
                      json.dumps(audit, indent=2, default=str))
    print(json.dumps(audit, indent=2, default=str))


if __name__ == "__main__":
    main()
