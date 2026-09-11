"""Featured MLB totals -- slate environment, not a K feature.

Whole-slate historical odds (NOT the per-event prop endpoint):
  10 credits x regions x markets per timestamp.
Owner GO 2026-09-11. Clock labels are calendar-ET, not first-pitch closes.

  python production/ops/market_research/pull_featured_totals.py estimate
  python production/ops/market_research/pull_featured_totals.py pull --max-credits 20000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.odds_ledger import atomic_write_parquet, atomic_write_text  # noqa: E402
from pull_oddsapi_historical import (  # noqa: E402
    BASE,
    OUT_DIR,
    RAW_DIR,
    SPORT,
    _get,
    _key,
    _load_state,
)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

INDEX_DIR = RAW_DIR / "event_index"
FEAT_RAW = RAW_DIR / "featured" / "totals"
OUT_PARQUET = OUT_DIR / "featured_totals.parquet"
CREDITS_PER_SNAP = 10  # us x totals

# Calendar clocks (UTC). These are slate-environment stamps, not K closes.
# morning = 12:00 ET; evening = 19:55 ET (east-night first-pitch neighborhood).
CLOCKS = {
    "morning": "T16:00:00Z",
    "evening": "T23:55:00Z",
}


def request_ts(day: str, clock: str) -> str:
    suffix = CLOCKS[clock]
    return f"{day}{suffix}"


def index_game_days() -> list[str]:
    """Days whose event_index lists at least one commence on that UTC date."""
    days: list[str] = []
    if not INDEX_DIR.exists():
        return days
    for fp in sorted(INDEX_DIR.glob("*.json")):
        day = fp.stem
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = data.get("data", data.get("events", []))
        if isinstance(items, dict):
            items = items.get("events", [])
        if any(str(ev.get("commence_time", ""))[:10] == day for ev in items):
            days.append(day)
    return days


def cmd_estimate() -> None:
    days = index_game_days()
    n_clocks = len(CLOCKS)
    total = len(days) * n_clocks * CREDITS_PER_SNAP
    state = _load_state()
    print(f"game_days: {len(days)}  clocks: {n_clocks}  credits_est: {total}")
    if days:
        print(f"span: {days[0]} -> {days[-1]}")
    print(f"observed remaining quota: {state.get('remaining')}")
    print("clocks: morning=12:00 ET, evening=19:55 ET (not first-pitch)")
    print("purpose: slate correlation / pace / common-shock -- not a K feature")


def cmd_pull(max_credits: int) -> None:
    if requests is None:
        raise SystemExit("requests is required")
    key = _key()
    session = requests.Session()
    state = _load_state()
    floor = int(max_credits * 0.10)
    days = index_game_days()
    print(f"pull featured totals: {len(days)} days x {list(CLOCKS)} "
          f"budget {max_credits} (floor {floor})")
    n_done = 0
    n_skip_cache = 0
    for clock in CLOCKS:
        for day in days:
            rem = state.get("remaining")
            if rem is not None and int(rem) <= floor:
                print(f"BUDGET FLOOR HIT (remaining={rem}); stopping.")
                cmd_normalize()
                return
            cache = FEAT_RAW / clock / f"{day}.json"
            if cache.exists():
                n_skip_cache += 1
                continue
            ts = request_ts(day, clock)
            try:
                data, _ = _get(
                    session,
                    f"/historical/sports/{SPORT}/odds",
                    {"apiKey": key, "date": ts, "regions": "us",
                     "markets": "totals", "oddsFormat": "american"},
                    state,
                )
            except Exception as exc:
                print(f"skip {day} {clock}: {str(exc)[:120]}")
                continue
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data), encoding="utf-8")
            time.sleep(0.15)
            n_done += 1
            if n_done % 50 == 0:
                print(f"[{clock}] pulled {n_done} remaining={state.get('remaining')}",
                      flush=True)
    print(f"done new={n_done} cached={n_skip_cache} remaining={state.get('remaining')}")
    cmd_normalize()


def cmd_normalize() -> pl.DataFrame:
    rows: list[dict] = []
    if not FEAT_RAW.exists():
        print("normalized rows: 0 (nothing pulled yet)")
        return pl.DataFrame()
    for fp in sorted(FEAT_RAW.rglob("*.json")):
        clock = fp.parent.name
        day = fp.stem
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        vendor_ts = payload.get("timestamp") if isinstance(payload, dict) else None
        prev_ts = payload.get("previous_timestamp") if isinstance(payload, dict) else None
        next_ts = payload.get("next_timestamp") if isinstance(payload, dict) else None
        events = payload.get("data", []) if isinstance(payload, dict) else payload
        if not isinstance(events, list):
            events = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            eid = ev.get("id", "")
            commence = ev.get("commence_time", "")
            home = ev.get("home_team", "")
            away = ev.get("away_team", "")
            for bk in ev.get("bookmakers") or []:
                book = bk.get("key", "")
                for mk in bk.get("markets") or []:
                    if mk.get("key") != "totals":
                        continue
                    for oc in mk.get("outcomes") or []:
                        rows.append({
                            "gd": day,
                            "clock": clock,
                            "request_ts": request_ts(day, clock),
                            "vendor_timestamp": vendor_ts,
                            "previous_timestamp": prev_ts,
                            "next_timestamp": next_ts,
                            "event_id": eid,
                            "commence_time": commence,
                            "home": home,
                            "away": away,
                            "book": book,
                            "side": str(oc.get("name", "")).lower(),
                            "line": oc.get("point"),
                            "price": oc.get("price"),
                        })
    if not rows:
        print("normalized rows: 0")
        return pl.DataFrame()
    frame = pl.DataFrame(rows)
    atomic_write_parquet(frame, OUT_PARQUET)
    n_days = frame.select("gd").n_unique()
    n_events = frame.select("event_id").n_unique()
    print(f"normalized {frame.height} rows / {n_events} events / {n_days} days -> {OUT_PARQUET}")
    return frame


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["estimate", "pull", "normalize"])
    p.add_argument("--max-credits", type=int, default=20000)
    args = p.parse_args()
    if args.command == "estimate":
        cmd_estimate()
    elif args.command == "pull":
        cmd_pull(args.max_credits)
    else:
        cmd_normalize()


if __name__ == "__main__":
    main()
