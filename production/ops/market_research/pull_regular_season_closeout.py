"""Regular-season closeout driver (paid Odds API; wraps pull_oddsapi_historical).

Pulls day-by-day from the day after current consensus-cache coverage through
END (default: yesterday - closes only exist post-game, so today/future dates
are REFUSED, never skipped: a premature pull would permanently record event
IDs in skipped_events.json and strand their closes forever).

Per day: pull (close+morning, closes-first inside the wrapped script) with a
per-day credit cap, then continue. At the end: normalize once + rebuild the
consensus cache, so ledger gates and research see the new days.

Season end: last pullable date is 2026-09-28 (regular season only —
postseason is never pulled, #104). Keep default END (yesterday) and re-run
every few days; after the season, one final run sweeps the last regular
games and coverage is final.

Spend: ~20 credits/event (close+morning). ~15 games/day ~= 300/day.
Global --quota-floor stops the loop long before billing pain.

Usage:
  python production/ops/market_research/pull_regular_season_closeout.py --help
  python production/ops/market_research/pull_regular_season_closeout.py --dry-run
  python production/ops/market_research/pull_regular_season_closeout.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

PULL = ROOT / "production" / "ops" / "market_research" / "pull_oddsapi_historical.py"
CACHE = ROOT / "production" / "ops" / "market_research" / "build_consensus_cache.py"
CACHE_PARQUET = ROOT / "data" / "Odds-Historical" / "theoddsapi" / "consensus_cache.parquet"
STATE_PATH = ROOT / "data" / "Odds-Historical" / "theoddsapi" / "pull_state.json"
SEASON_END = date(2026, 9, 28)  # regular season only — never pull postseason (#104)


def sh(args: list[str], dry: bool) -> int:
    print("+ " + " ".join(args))
    if dry:
        return 0
    r = subprocess.run(args, cwd=str(ROOT))
    return int(r.returncode)


def cache_max_gd() -> str | None:
    if not CACHE_PARQUET.exists():
        return None
    try:
        c = pl.scan_parquet(CACHE_PARQUET).select("gd").collect()
        return str(c["gd"].max()) if c.height else None
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default=None,
                    help="first date YYYY-MM-DD (default: day after cache max gd)")
    ap.add_argument("--end", default=None,
                    help="last date YYYY-MM-DD (default: yesterday; future refused)")
    ap.add_argument("--markets", default="pitcher_strikeouts,pitcher_outs",
                    help="comma list (default K + outs: outs is the workload market, "
                    "both dense; batter suite parked until a batter model exists)")
    ap.add_argument("--snapshots", default="close,morning")
    ap.add_argument("--day-budget", type=int, default=5000,
                    help="per-day --max-credits cap for the wrapped pull")
    ap.add_argument("--quota-floor", type=int, default=100000,
                    help="stop if observed remaining quota falls below this")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    today = date.today()
    yesterday = today - timedelta(days=1)
    start_s = args.start or ((date.fromisoformat(cache_max_gd()) + timedelta(days=1)).isoformat()
                             if cache_max_gd() else yesterday.isoformat())
    end_s = args.end or yesterday.isoformat()
    d0, d1 = date.fromisoformat(start_s), date.fromisoformat(end_s)
    if d1 > yesterday:
        print(f"REFUSING end={d1} after yesterday={yesterday}: closes do not exist yet; "
              "a premature pull would permanently skip those events. "
              f"Rerun when they are past (end defaults to yesterday).")
        raise SystemExit(2)
    if d1 > SEASON_END:
        print(f"REFUSING end={d1} past regular-season end={SEASON_END}: "
              "postseason is out of scope (backlog #104) — no playoff data, ever.")
        raise SystemExit(2)
    if d0 > d1:
        print(f"nothing to do: start={d0} after end={d1} (coverage current thru {cache_max_gd()}).")
        return

    py = sys.executable
    pulled_days = 0
    d = d0
    while d <= d1:
        ds = d.isoformat()
        rc = sh([py, str(PULL), "pull", "--snapshots", args.snapshots,
                 "--markets", args.markets, "--start", ds, "--end", ds,
                 "--max-credits", str(args.day_budget)], args.dry_run)
        if rc != 0:
            print(f"day {ds}: pull exited {rc}; stopping (resume re-runs this day).")
            raise SystemExit(1)
        pulled_days += 1
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            rem = state.get("remaining")
            if rem is not None and int(rem) < args.quota_floor:
                print(f"QUOTA FLOOR: remaining={rem} < {args.quota_floor}; stopping. "
                      "Resume later or upgrade plan.")
                raise SystemExit(2)
        except SystemExit:
            raise
        except Exception as exc:
            print(f"quota check unavailable ({exc}); continuing.")
        d += timedelta(days=1)
        if pulled_days >= 60:
            print("safety: 60 days in one run is enough; re-run to continue.")
            break
    print(f"days attempted: {pulled_days} ({start_s}..{d1})")
    if args.dry_run:
        print("dry-run: skipping normalize + cache rebuild.")
        return
    rc = sh([py, str(PULL), "normalize"], False)
    if rc != 0:
        raise SystemExit(1)
    rc = sh([py, str(CACHE)], False)
    if rc != 0:
        raise SystemExit(1)
    try:
        _grade = ROOT / "production" / "odds" / "grade_odds_ledger.py"
        rc = sh([py, str(_grade), "--attach-paid-clocks"], False)
        if rc != 0:
            print("paid-clocks attach warn-only: grade exited nonzero; rerun manually.")
    except Exception as exc:
        print(f"paid-clocks attach warn-only: {exc}")
    print(f"closeout complete: cache now thru {cache_max_gd()} "
          f"(utc {datetime.now(timezone.utc).isoformat()}).")


if __name__ == "__main__":
    main()
