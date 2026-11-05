"""Probe which pre-game clock actually has posted MLB prop lines (paid Odds API).

Requests K-only (`pitcher_strikeouts`, regions=us) at commence-30h / -24h / -18h
for a small seeded sample of events, and records hit rate + vendor lag per clock.
Writes NOTHING to the canonical raw/snapshots cache — report goes to
`data/Odds-Historical/theoddsapi/_probe/open_clock_probe.json` (ignored dir).

Spend: ~20 events x 3 clocks x 10 credits = ~600 (empties may not spend).
Run: python production/ops/market_research/probe_open_clocks.py [--n 20] [--seed 7]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.env_load import load_project_dotenv  # noqa: E402

load_project_dotenv()
# .env currently carries THEODDS_API_KEY; the puller reads THEODDSAPI_KEY.
# Bridge in-process so the probe (and later pulls) work without renaming secrets.
if not os.getenv("THEODDSAPI_KEY", "").strip() and os.getenv("THEODDS_API_KEY", "").strip():
    os.environ["THEODDSAPI_KEY"] = os.getenv("THEODDS_API_KEY", "").strip()

from pull_oddsapi_historical import _get, discover_events  # noqa: E402

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

BASE = "https://api.the-odds-api.com/v4"
SPORT = "baseball_mlb"
PROBE_DIR = ROOT / "data" / "Odds-Historical" / "theoddsapi" / "_probe"
CLOCKS_H = (30, 24, 18)


def _req_ts(commence_iso: str, hours_before: int) -> str:
    dt = datetime.fromisoformat(str(commence_iso).replace("Z", "+00:00"))
    return (dt - timedelta(hours=hours_before)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _board_ts(commence_iso: str) -> str:
    """08:00 ET on game day. Regular season is entirely EDT (UTC-4), so a
    fixed offset is exact — no tz database needed."""
    dt = datetime.fromisoformat(str(commence_iso).replace("Z", "+00:00"))
    et_day = (dt - timedelta(hours=4)).date()
    return (datetime(et_day.year, et_day.month, et_day.day, 8, 0, 0)
            + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--clocks", default="30,24,18",
                    help="comma list of hours-before-commence to probe")
    ap.add_argument("--markets", default="pitcher_strikeouts",
                    help="comma list of markets to probe")
    ap.add_argument("--start", default="2025-04-01")
    ap.add_argument("--end", default="2026-09-15")
    args = ap.parse_args()
    CLOCKS = tuple(c.strip() for c in args.clocks.split(",") if c.strip())
    MARKETS = [m.strip() for m in args.markets.split(",") if m.strip()]
    if requests is None:
        raise SystemExit("requests is required")
    key = os.getenv("THEODDSAPI_KEY", "").strip()
    if not key:
        raise SystemExit("THEODDSAPI_KEY env missing (check .env naming).")
    session = requests.Session()
    state: dict = {}
    events = discover_events(session, key, args.start, args.end, state)
    with_ct = [e for e in events if e.get("commence_time")]
    rng = random.Random(args.seed)
    sample = rng.sample(with_ct, min(args.n, len(with_ct)))
    print(f"probing {len(sample)} events x {len(CLOCKS)} clocks, "
          f"quota remaining={state.get('remaining')}")

    rows: list[dict] = []
    for ev in sample:
        eid = ev["id"]
        for hrs in CLOCKS:
            tick = "board" if str(hrs) == "board" else f"-{hrs}h"
            ts = _board_ts(ev["commence_time"]) if tick == "board" \
                else _req_ts(ev["commence_time"], int(hrs))
            try:
                data, _ = _get(
                    session,
                    f"/historical/sports/{SPORT}/events/{eid}/odds",
                    {"apiKey": key, "date": ts, "regions": "us",
                     "markets": ",".join(MARKETS), "oddsFormat": "american"},
                    state)
            except Exception as exc:
                rows.append({"event_id": eid, "commence_time": ev["commence_time"],
                             "clock_h": hrs, "requested_ts": ts,
                             "error": str(exc)[:120]})
                continue
            payload = data.get("data", data) if isinstance(data, dict) else {}
            vendor_ts = data.get("timestamp", "") if isinstance(data, dict) else ""
            books = payload.get("bookmakers", []) if isinstance(payload, dict) else []
            got = sorted({m.get("key") for b in books for m in b.get("markets", [])})
            k_mkts = [m for b in books for m in b.get("markets", [])
                      if m.get("key") in MARKETS]
            n_out = sum(len(m.get("outcomes", [])) for m in k_mkts)
            lag_min = ""
            try:
                if vendor_ts:
                    v = datetime.fromisoformat(str(vendor_ts).replace("Z", "+00:00"))
                    r = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    lag_min = round((r - v).total_seconds() / 60.0, 1)
            except Exception:
                pass
            rows.append({"event_id": eid, "commence_time": ev["commence_time"],
                         "clock_h": hrs, "requested_ts": ts,
                         "vendor_ts": vendor_ts, "lag_min": lag_min,
                         "n_books": len(books), "markets_found": got,
                         "has_k": bool(k_mkts), "n_k_outcomes": n_out})
            time.sleep(0.4)

    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    out = PROBE_DIR / f"open_clock_probe_{'_'.join(str(c) for c in CLOCKS)}.json"
    out.write_text(json.dumps({"rows": rows, "remaining": state.get("remaining"),
                               "spent_observed": state.get("spent_observed"),
                               "markets": MARKETS},
                              indent=2), encoding="utf-8")
    print(f"quota remaining now={state.get('remaining')} "
          f"(spent_observed={state.get('spent_observed')})")
    for hrs in CLOCKS:
        sub = [r for r in rows if r.get("clock_h") == hrs and not r.get("error")]
        hits = [r for r in sub if r.get("has_k")]
        lags = [r["lag_min"] for r in hits if isinstance(r.get("lag_min"), (int, float))]
        avg_lag = round(sum(lags) / len(lags), 1) if lags else "-"
        avg_books = (round(sum(r["n_books"] for r in hits) / len(hits), 1)
                     if hits else "-")
        tick = "board" if str(hrs) == "board" else f"-{hrs}h"
        print(f"{tick}: {len(hits)}/{len(sub)} events with requested markets, "
              f"avg vendor lag {avg_lag} min, avg books {avg_books}")
        for mk in MARKETS:
            n = sum(1 for r in sub if mk in r.get("markets_found", []))
            print(f"    {mk}: {n}/{len(sub)}")
    print(f"report -> {out}")


if __name__ == "__main__":
    main()
