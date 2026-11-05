"""Bounded production-board sample for 2023/2024 (owner-authorized).

Max 10 events-equivalent exposure, hard 10k-credit ceiling. Uses the
PER-DATE historical odds endpoint (one request returns all events for
that date) to test:
  1. availability of the fixed 12:00Z (8am ET, all-EDT) board clock
     in 2023 and 2024;
  2. whether the per-date endpoint returns MORE events than the cached
     event index (the missing-305/277-games question);
  3. book/market coverage at the board clock;
  4. actual quota cost per request (headers).

6 sample dates: 2 missing-heavy 2023 days, 2 missing-heavy 2024 days,
2 healthy July days (controls). Day/night mix within dates is inherent
(12:00Z board precedes both). ASCII-only; never prints the key.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props")
sys.path.insert(0, str(ROOT / "production" / "ops" / "market_research"))
sys.path.insert(0, str(ROOT / "src"))

import pull_oddsapi_historical as poh  # noqa: E402

import requests  # noqa: E402

DATES = ["2023-05-12", "2023-05-15", "2023-07-04",
         "2024-04-01", "2024-04-08", "2024-07-04"]
ALL_MARKETS = sorted(poh.PITCHER_MARKETS | poh.BATTER_MARKETS)
OUT = Path(r"C:\Users\ckaplinger\MLB-Props-Research\odds-archive-acceptance-20261006\board_sample_results.json")


def main() -> int:
    session = requests.Session()
    state = poh._load_state()
    key = poh._key()
    print("quota before:", state.get("remaining"))
    results = []
    for day in DATES:
        # board clock: 12:00Z (8am ET, all-EDT rule for the regular season)
        ts = "%sT12:00:00Z" % day
        try:
            data, headers = poh._get(
                session,
                "/historical/sports/%s/odds" % poh.SPORT,
                {"apiKey": key, "date": ts, "regions": "us",
                 "markets": ",".join(ALL_MARKETS), "oddsFormat": "american"},
                state)
            payload = data.get("data", data)
            events = payload if isinstance(payload, list) else []
            n_books = [len(e.get("bookmakers", [])) for e in events]
            mk = set()
            n_alt_events = 0
            for e in events:
                has_alt = False
                for bk in e.get("bookmakers", []):
                    for m in bk.get("markets", []):
                        mk.add(m.get("key", ""))
                        if m.get("key") == "pitcher_strikeouts_alternate":
                            has_alt = True
                n_alt_events += 1 if has_alt else 0
            returned_ts = data.get("timestamp")
            # cached event-index count for this date
            idx = ROOT / "data" / "Odds-Historical" / "theoddsapi" / "raw" / "event_index" / ("%s.json" % day)
            idx_n = 0
            if idx.exists():
                j = json.loads(idx.read_text(encoding="utf-8"))
                items = j.get("data", j.get("events", []))
                if isinstance(items, dict):
                    items = items.get("events", [])
                idx_n = len(items)
            entry = {"date": day, "requested_board_ts": ts,
                     "returned_ts": returned_ts,
                     "events_returned": len(events),
                     "event_index_events": idx_n,
                     "extra_vs_index": len(events) - idx_n,
                     "books_per_event_minmax": [min(n_books), max(n_books)]
                     if n_books else None,
                     "markets_returned": len(mk),
                     "altK_events": n_alt_events,
                     "remaining": headers.get("x-requests-remaining")}
        except Exception as exc:
            entry = {"date": day, "error": str(exc)[:140]}
        results.append(entry)
        print(json.dumps(entry, default=str))
    state = poh._load_state()
    out = {"results": results,
           "quota_after": {"remaining": state.get("remaining"),
                           "spent_observed": state.get("spent_observed")},
           "markets_requested": ALL_MARKETS,
           "ceiling_credits": 10000}
    OUT.write_text(json.dumps(out, indent=2), encoding="ascii")
    print("quota after:", state.get("remaining"))
    print("report:", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
