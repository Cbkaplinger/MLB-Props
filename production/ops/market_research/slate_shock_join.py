"""Slate common-shock join (research only, owner GO 2026-09-11).

Joins featured game totals (slate ENVIRONMENT) onto the juiced-replay taken
set via vendor event_id. Totals NEVER enter p_ours and NEVER select tickets.
Output feeds correlation-aware exposure caps (step 6 of the filter order),
which today are heuristic 12u/20u slate caps that assume tickets are
independent. Example of the failure mode: two K-unders on the same Coors
slate losing to one weather shock is ONE correlated loss, not two
independent ones.

Read-only over the paid lake; writes only:
  artifacts/odds_log/slate_shock_report.json
  docs/reference/reports/slate_shock_join_2026-09-11.md
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
HIST = ROOT / "data" / "Odds-Historical" / "theoddsapi"
CANDIDATES = ROOT / "artifacts" / "odds_log" / "juiced_replay_candidates.parquet"
BOOK_LINES = HIST / "book_lines_pitcher.parquet"
FRIEND = ROOT / "data" / "Odds-Open-Close-2025-2026" / "pitcher_strikeouts_early_open_2025_2026.csv"
TOTALS = HIST / "featured_totals.parquet"
ENVELOPE = HIST / "snapshot_envelope.parquet"
OUT_JSON = ROOT / "artifacts" / "odds_log" / "slate_shock_report.json"
OUT_MD = ROOT / "docs" / "reference" / "reports" / "slate_shock_join_2026-09-11.md"

FRIEND_END = "2026-07-10"
HIGH_TOTAL = 9.5


def sorted_key(name: str | None) -> str | None:
    """Order-invariant lowercase token key (family-first vs given-first safe)."""
    if name is None:
        return None
    cleaned = "".join(ch if ch.isalnum() or ch == " " else " " for ch in str(name).lower())
    toks = cleaned.split()
    if not toks:
        return None
    return " ".join(sorted(toks))


def book_norm(book: str | None) -> str | None:
    if book is None:
        return None
    return str(book).lower().replace(" ", "")


def evening_event_totals(totals: pl.DataFrame) -> pl.DataFrame:
    """One row per event: DK/FD median evening total, else all-book median."""
    eve = totals.filter(pl.col("clock") == "evening")
    dkfd = (
        eve.filter(pl.col("book").is_in(["draftkings", "fanduel"]))
        .group_by("event_id")
        .agg(
            pl.col("line").median().alias("total_dkfd"),
            pl.len().alias("n_dkfd_rows"),
        )
    )
    allb = (
        eve.group_by("event_id").agg(
            pl.col("line").median().alias("total_all"),
            pl.col("book").n_unique().alias("n_books"),
        )
    )
    out = allb.join(dkfd, on="event_id", how="left").with_columns(
        pl.when(pl.col("total_dkfd").is_not_null())
        .then(pl.col("total_dkfd"))
        .otherwise(pl.col("total_all"))
        .alias("total_line")
    )
    return out.select(["event_id", "total_line", "total_dkfd", "total_all", "n_books"])


def build_event_roster() -> tuple[pl.DataFrame, dict]:
    """Map (gd, pitcher_sorted_key) -> event_id from friend + paid lake."""
    diag: dict = {}
    friend = pl.scan_csv(FRIEND).select(
        ["game_date", "pitcher_name", "event_id"]
    ).collect()
    friend = friend.with_columns(
        pl.col("pitcher_name").map_elements(sorted_key, return_dtype=pl.String).alias("key"),
    )
    roster_friend = friend.select(
        pl.col("game_date").alias("gd"), "key", "event_id"
    ).unique()
    diag["roster_friend_rows"] = len(roster_friend)

    lines = (
        pl.scan_parquet(BOOK_LINES)
        .filter(
            (pl.col("market") == "pitcher_strikeouts")
            & (pl.col("snapshot") == "morning")
        )
        .select(["player_norm", "event_id"])
        .collect()
        .unique()
    )
    lines = lines.with_columns(
        pl.col("player_norm").map_elements(sorted_key, return_dtype=pl.String).alias("key"),
    )
    env = pl.scan_parquet(ENVELOPE).select(["event_id", "commence_time"]).collect().unique()
    # Vendor stamps ET wall-time with a Z suffix (19:05 ET, not UTC); the date
    # part is the game date. Validated below by mismatch rate vs tickets.
    env = env.with_columns(pl.col("commence_time").str.slice(0, 10).alias("gd"))
    roster_paid = (
        lines.join(env, on="event_id", how="left")
        .select(["gd", "key", "event_id"])
        .unique()
    )
    diag["roster_paid_rows"] = len(roster_paid)
    roster = pl.concat([roster_friend, roster_paid]).unique()
    dupes = (
        roster.group_by(["gd", "key"])
        .agg(pl.col("event_id").n_unique().alias("n_events"))
        .filter(pl.col("n_events") > 1)
    )
    diag["ambiguous_gd_key"] = len(dupes)
    # Doubleheaders: keep first event, flag the count. Rare by construction.
    roster = roster.sort("event_id").unique(subset=["gd", "key"], keep="first")
    diag["roster_rows"] = len(roster)
    return roster, diag


def _roi(rows: pl.DataFrame) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0, "roi": None, "wr": None, "pnl": 0.0}
    stake = float(rows["stake_flat1u"].sum())
    pnl = float(rows["pnl_flat1u"].sum())
    return {
        "n": n,
        "roi": round(pnl / stake, 4) if stake else None,
        "wr": round(float(rows["won"].mean()), 4),
        "pnl": round(pnl, 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--high-total", type=float, default=HIGH_TOTAL)
    args = ap.parse_args()

    taken = (
        pl.scan_parquet(CANDIDATES)
        .filter(pl.col("accepted") == True)  # noqa: E712
        .select(["gd", "key", "line", "side", "book", "snap", "won",
                 "stake_flat1u", "pnl_flat1u", "edge"])
        .collect()
    )
    n_taken = len(taken)
    roster, diag = build_event_roster()
    bridged = taken.join(roster, on=["gd", "key"], how="left")
    n_matched = int(bridged.filter(pl.col("event_id").is_not_null()).height)
    totals = pl.scan_parquet(TOTALS).collect()
    ev_totals = evening_event_totals(totals)
    diag["events_with_evening_total"] = int(ev_totals.height)
    final = bridged.join(ev_totals, on="event_id", how="left")
    n_with_total = int(final.filter(pl.col("total_line").is_not_null()).height)

    report: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contract": "totals are slate environment for exposure caps only; "
                    "never a K feature, never a selector",
        "n_taken": n_taken,
        "n_matched_event": n_matched,
        "match_rate": round(n_matched / n_taken, 4) if n_taken else None,
        "n_with_total": n_with_total,
        "roster_diag": diag,
    }

    usable = final.filter(pl.col("total_line").is_not_null())
    # Same-game clustering: games carrying 2+ of our tickets.
    per_game = (
        usable.group_by(["event_id", "total_line"])
        .agg(pl.len().alias("n_tickets"),
             pl.col("pnl_flat1u").sum().alias("pnl"))
        .sort("n_tickets", descending=True)
    )
    multi = per_game.filter(pl.col("n_tickets") >= 2)
    report["same_game"] = {
        "n_games_with_2plus": int(len(multi)),
        "n_tickets_in_multi": int(multi["n_tickets"].sum()) if len(multi) else 0,
        "pairs": int((multi["n_tickets"] * (multi["n_tickets"] - 1) // 2).sum())
        if len(multi) else 0,
        "pnl_multi": round(float(multi["pnl"].sum()), 2) if len(multi) else 0.0,
        "by_game": [
            {"total": r["total_line"], "n": r["n_tickets"], "pnl": round(r["pnl"], 2)}
            for r in per_game.head(15).to_dicts()
        ],
    }
    # High-total vs rest (descriptive; NOT a cap recommendation).
    hi = usable.filter(pl.col("total_line") >= float(args.high_total))
    lo = usable.filter(pl.col("total_line") < float(args.high_total))
    report["high_total_split"] = {
        "threshold": float(args.high_total),
        "high": _roi(hi),
        "rest": _roi(lo),
    }
    # Slate concentration.
    per_slate = (
        usable.group_by("gd")
        .agg(pl.len().alias("n_tickets"),
             pl.col("event_id").n_unique().alias("n_games"),
             pl.col("total_line").median().alias("median_total"))
        .sort("n_tickets", descending=True)
    )
    report["slate_concentration"] = {
        "n_slates": int(len(per_slate)),
        "max_tickets_one_slate": int(per_slate["n_tickets"].max()) if len(per_slate) else 0,
        "median_tickets_per_slate": float(per_slate["n_tickets"].median()) if len(per_slate) else 0.0,
        "top_slates": per_slate.head(10).to_dicts(),
    }

    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Slate common-shock join — 2026-09-11",
        "",
        "> Research only (owner GO). Totals are slate environment for exposure",
        "> caps, never a K feature or selector. JSON: `artifacts/odds_log/slate_shock_report.json`.",
        "> Next actions: `docs/EXECUTION_BACKLOG.md`.",
        "",
        f"- Taken tickets matched to a vendor event: **{n_matched}/{n_taken}** "
        f"({report['match_rate']}); with an evening total: **{n_with_total}**.",
        f"- Same-game clustering: **{report['same_game']['n_games_with_2plus']}** games carried "
        f"2+ tickets ({report['same_game']['n_tickets_in_multi']} tickets, "
        f"{report['same_game']['pairs']} correlated pairs, "
        f"pnl {report['same_game']['pnl_multi']}).",
        f"- High-total (≥{args.high_total}) vs rest: "
        f"{report['high_total_split']['high']} vs {report['high_total_split']['rest']}.",
        f"- Slate concentration: {report['slate_concentration']['n_slates']} slates, "
        f"max {report['slate_concentration']['max_tickets_one_slate']} tickets on one slate.",
        "",
        "Ambiguous (gd, pitcher) doubleheaders: "
        f"{diag['ambiguous_gd_key']} (first event kept).",
        "",
        "What this authorizes: NOTHING live. It sizes the correlation problem the",
        "12u/20u heuristic caps are ignoring. Caps come from the October program.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "slate_concentration"},
                     indent=1)[:2000])


if __name__ == "__main__":
    main()
