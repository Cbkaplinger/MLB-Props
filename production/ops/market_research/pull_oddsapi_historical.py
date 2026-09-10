"""Paid historical book-odds backfill via the-odds-api.com (NOT theoddsapi.com).

Fills the exact gap the free sources cannot: 2025 season + DK/FD book CLOSES
(Kalshi starts Mar 2026 and is exchange, not books; friend CSVs are opens only).

Credit model (verify live headers; trust billing, not docs):
  historical event odds = 10 credits x regions x markets x events x snapshots.
  ~4,860 events (2025+2026) x 1 region x 1 market x 1 snapshot ~= 48.6k credits.
  => close-only fits the $59/100k plan. Close+morning needs $119/5M.
  Each extra market (outs/hits/walks) multiplies the same way: expansion is pull #2.

Safety (money protection):
  --estimate  : count events + print credit math, spend NOTHING snapshot-wise.
  --max-credits + 10% buffer hard stop read from x-requests-remaining headers.
  Pull order is closes-first: if the budget runs hot, mornings get cut, never closes.
  Raw JSON is cached forever under data/Odds-Historical/theoddsapi/ (ignored);
  re-normalization never re-spends.

Requires THEODDSAPI_KEY env (paid plan; historical is paid-only).
Pulls pitcher_strikeouts by default; --markets for expansion (verify keys live:
unused keys still burn the per-market credit).

Examples:
  python production/ops/market_research/pull_oddsapi_historical.py --estimate --start 2025-03-01 --end 2026-09-01
  python production/ops/market_research/pull_oddsapi_historical.py --pull --snapshots close --start 2025-03-01 --end 2025-10-31
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import atomic_write_parquet, atomic_write_text, norm_player_name  # noqa: E402
from Python.env_load import load_project_dotenv  # noqa: E402

# .env so THEODDSAPI_KEY is available when run from Task Scheduler / bare shells.
load_project_dotenv()

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

BASE = "https://api.the-odds-api.com/v4"
SPORT = "baseball_mlb"
OUT_DIR = ROOT / "data" / "Odds-Historical" / "theoddsapi"
RAW_DIR = OUT_DIR / "raw"
STATE_PATH = OUT_DIR / "pull_state.json"
CREDITS_PER_EVENT_SNAPSHOT = 10  # x regions x markets; re-check via headers


def _key() -> str:
    key = os.getenv("THEODDSAPI_KEY", "").strip()
    if not key:
        raise SystemExit("THEODDSAPI_KEY env is missing (paid plan required for historical).")
    return key


def _get(session, path: str, params: dict, state: dict,
         retries: int = 5) -> tuple[dict | list, dict]:
    # 429 backoff: historical is low-traffic but parallel chunk-runs share one
    # quota; never crash a 5k-event pull on rate-limit — sleep it out.
    last_err: Exception | None = None
    for attempt in range(max(1, retries)):
        r = session.get(BASE + path, params=params, timeout=30)
        if r.status_code == 429:
            last_err = RuntimeError(f"429 {path}")
            time.sleep(5.0 * (attempt + 1))
            continue
        r.raise_for_status()
        headers = {k: r.headers.get(k) for k in
                   ("x-requests-remaining", "x-requests-used", "x-requests-last")}
        try:
            last = int(headers.get("x-requests-last") or 0)
        except (TypeError, ValueError):
            last = 0
        state["spent_observed"] = int(state.get("spent_observed", 0)) + last
        rem = headers.get("x-requests-remaining")
        try:
            state["remaining"] = int(rem) if rem is not None else state.get("remaining")
        except (TypeError, ValueError):
            pass
        _save_state(state)
        return r.json(), headers
    raise last_err if last_err is not None else RuntimeError(f"GET failed {path}")


def _save_state(state: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        atomic_write_text(STATE_PATH, json.dumps(state, indent=2, default=str))
    except OSError:
        # Parallel chunk-runs share this advisory file (quota tracking only);
        # a lost write is harmless — per-event cache files are the real resume
        # mechanism and never collide. Do not crash a pull on this.
        pass


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _dates(start: str, end: str) -> list[str]:
    out, d = [], datetime.fromisoformat(start).date()
    stop = datetime.fromisoformat(end).date()
    while d <= stop:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def discover_events(session, key: str, start: str, end: str,
                    state: dict) -> list[dict]:
    """List historical event ids via per-date snapshots (credit-guarded)."""
    events: dict[str, dict] = {}
    for day in _dates(start, end):
        cache = RAW_DIR / "event_index" / f"{day}.json"
        if cache.exists():
            data = json.loads(cache.read_text(encoding="utf-8"))
        else:
            data, _ = _get(session,
                            f"/historical/sports/{SPORT}/events",
                            {"apiKey": key, "date": f"{day}T12:00:00Z"},
                            state)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data), encoding="utf-8")
            time.sleep(0.3)
        items = data.get("data", data.get("events", []))
        if isinstance(items, dict):
            items = items.get("events", [])
        for ev in items:
            eid = ev.get("id")
            if eid and eid not in events:
                events[eid] = {"id": eid,
                               "commence_time": ev.get("commence_time", ""),
                               "home": ev.get("home_team", ""),
                               "away": ev.get("away_team", "")}
    return list(events.values())


def cmd_estimate(args) -> None:
    if requests is None:
        raise SystemExit("requests is required")
    session = requests.Session()
    state = _load_state()
    events = discover_events(session, _key(), args.start, args.end, state)
    n_markets = len([m for m in args.markets.split(",") if m.strip()])
    n_snaps = len([s for s in args.snapshots.split(",") if s.strip()])
    per_snap = len(events) * CREDITS_PER_EVENT_SNAPSHOT * n_markets
    total = per_snap * n_snaps
    print(f"events: {len(events)}  markets: {n_markets}  snapshots: {n_snaps}")
    print(f"estimated credits: {total} (+ discovery already spent: "
          f"{state.get('spent_observed', 0)})")
    for plan, credits in (("$30", 20000), ("$59", 100000), ("$119", 5000000)):
        print(f"  {plan}/{credits}: {'FITS' if total <= credits else 'TOO SMALL'}")
    print(f"observed remaining quota: {state.get('remaining')}")


def _snapshot_ts(commence_iso: str, which: str) -> str:
    dt = datetime.fromisoformat(str(commence_iso).replace("Z", "+00:00"))
    if which == "close":
        dt = dt - timedelta(minutes=5)  # last pre-commence snapshot
    elif which == "morning":
        dt = dt - timedelta(hours=5)
    else:  # open: first-seen line, ~30h before first pitch
        dt = dt - timedelta(hours=30)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd_pull(args) -> None:
    if requests is None:
        raise SystemExit("requests is required")
    key = _key()
    session = requests.Session()
    state = _load_state()
    budget = int(args.max_credits)
    floor = int(budget * 0.10)  # hard stop: keep 10% buffer, never strand mid-pull
    events = discover_events(session, key, args.start, args.end, state)
    markets = [m.strip() for m in args.markets.split(",") if m.strip()]
    snaps = [s.strip() for s in args.snapshots.split(",") if s.strip()]
    print(f"pull: {len(events)} events x {markets} x {snaps}, budget {budget} (floor {floor})")
    n_done = 0
    # Snapshot-OUTER loop: ALL closes complete before ANY morning starts, so a
    # budget floor always strands mornings, never closes.
    skip_path = RAW_DIR / "skipped_events.json"
    try:
        skipped: set = set(json.loads(skip_path.read_text(encoding="utf-8"))) if skip_path.exists() else set()
    except Exception:
        skipped = set()
    for snap in snaps:
        for ev in events:
            if state.get("remaining") is not None and int(state["remaining"]) <= floor:
                print(f"BUDGET FLOOR HIT (remaining={state['remaining']}); stopping. "
                      "Re-run later or upgrade plan. Closes-first order kept.")
                return
            eid = ev["id"]
            if eid in skipped:
                continue
            cache = RAW_DIR / "snapshots" / snap / f"{eid}.json"
            if cache.exists():
                continue
            ts = _snapshot_ts(ev.get("commence_time", ""), snap)
            try:
                data, _ = _get(
                    session,
                    f"/historical/sports/{SPORT}/events/{eid}/odds",
                    {"apiKey": key, "date": ts, "regions": args.regions,
                     "markets": ",".join(markets), "oddsFormat": "american"},
                    state)
            except Exception as exc:
                # Dead event IDs (postponed/duplicates in the index) 404 —
                # record and move on; never crash a 5k-event pull on one game.
                print(f"skip {eid} ({snap}): {str(exc)[:120]}")
                skipped.add(eid)
                skip_path.parent.mkdir(parents=True, exist_ok=True)
                skip_path.write_text(json.dumps(sorted(skipped)), encoding="utf-8")
                continue
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data), encoding="utf-8")
            time.sleep(0.15)
            n_done += 1
            if n_done % 100 == 0:
                print(f"[{snap}] events: {n_done}/{len(events)} remaining={state.get('remaining')}", flush=True)
    print(f"done: {n_done}/{len(events)} remaining={state.get('remaining')}")
    normalize(args)


PITCHER_MARKETS = {
    "pitcher_strikeouts", "pitcher_outs", "pitcher_hits_allowed",
    "pitcher_earned_runs", "pitcher_strikeouts_alternate", "pitcher_walks",
}
BATTER_MARKETS = {
    "batter_home_runs", "batter_hits", "batter_total_bases", "batter_rbis",
    "batter_walks", "batter_hits_runs_rbis", "batter_runs_scored",
    "batter_singles", "batter_strikeouts",
}


def _market_bucket(market: str) -> str:
    if market in PITCHER_MARKETS:
        return "pitcher"
    if market in BATTER_MARKETS:
        return "batter"
    return "other"


def normalize(args) -> pl.DataFrame:
    """Raw snapshots -> book-line parquet, SPLIT into pitcher/batter files.

    Two canonical files (per user 2026-09-08): book_lines_pitcher.parquet and
    book_lines_batter.parquet, each carrying a `market` column. Everything is
    Polars-native (build rows -> pl.DataFrame -> atomic write). Unknown markets
    land in book_lines_other.parquet and should be audited, never dropped.
    """
    rows: list[dict] = []
    for fp in sorted((RAW_DIR / "snapshots").rglob("*.json")):
        snap = fp.parent.name
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        payload = data.get("data", data)
        books = payload.get("bookmakers", payload.get("bookmakers", [])) if isinstance(payload, dict) else []
        # Vendor does not echo the requested snapshot timestamp (verified
        # 2026-09-09: no timestamp key in payload). Reconstruct the exact
        # requested ts deterministically: commence - 5min/5h/30h by snapshot.
        ts = ""
        try:
            if isinstance(payload, dict) and payload.get("commence_time"):
                ts = _snapshot_ts(str(payload["commence_time"]), snap)
        except Exception:
            ts = ""
        for bk in books:
            book = bk.get("key", "")
            for mk in bk.get("markets", []):
                for oc in mk.get("outcomes", []):
                    rows.append({
                        "event_id": (payload.get("id", "") if isinstance(payload, dict) else ""),
                        "snapshot": snap,
                        "snapshot_ts": ts,
                        "book": book,
                        "market": mk.get("key", ""),
                        "player": oc.get("description") or oc.get("participant") or "",
                        "player_norm": norm_player_name(
                            oc.get("description") or oc.get("participant") or ""),
                        "line": oc.get("point"),
                        "side": str(oc.get("name", "")).lower(),
                        "price": oc.get("price"),
                    })
    if not rows:
        print("normalized rows: 0 (nothing pulled yet)")
        return pl.DataFrame()
    frame = pl.DataFrame(rows)
    for bucket in ("pitcher", "batter", "other"):
        if bucket == "pitcher":
            m = pl.col("market").is_in(PITCHER_MARKETS)
        elif bucket == "batter":
            m = pl.col("market").is_in(BATTER_MARKETS)
        else:
            m = pl.col("market").is_in(PITCHER_MARKETS | BATTER_MARKETS).not_()
        sub = frame.filter(m)
        out = OUT_DIR / f"book_lines_{bucket}.parquet"
        if not sub.is_empty():
            atomic_write_parquet(sub, out)
            print(f"normalized {bucket} rows: {sub.height} -> {out}")
    return frame


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["estimate", "pull", "normalize"])
    p.add_argument("--start", default="2025-03-01")
    p.add_argument("--end", default="2026-09-01")
    p.add_argument("--markets", default="pitcher_strikeouts")
    p.add_argument("--snapshots", default="close",
                   help="comma list of close[,morning,open]")
    p.add_argument("--regions", default="us")
    p.add_argument("--max-credits", type=int, default=100000)
    args = p.parse_args()
    if args.command == "estimate":
        cmd_estimate(args)
    elif args.command == "pull":
        cmd_pull(args)
    elif args.command == "normalize":
        normalize(args)


if __name__ == "__main__":
    main()
