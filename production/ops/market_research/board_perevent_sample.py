"""Per-event board-clock sample for 2023/2024 (owner-authorized).

The per-date odds endpoint rejects player props (422), so the production-
board backfill must use the PER-EVENT endpoint. This sample tests exactly
that: 10 events (5 x 2023, 5 x 2024, spanning early/late season),
requested at the production board clock 12:00Z (8am ET, fixed UTC-4, valid
all-EDT for 2023-24), all 15 registered markets, region us.

Hard ceiling 10,000 credits. Raw payloads cached under
raw/snapshots/board_2023_24/<eid>.json so the future backfill never
re-spends them. Quota-header costs recorded per request.
Error strings are REDACTED (no key/URL fragments printed).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props")
sys.path.insert(0, str(ROOT / "production" / "ops" / "market_research"))
sys.path.insert(0, str(ROOT / "src"))

import pull_oddsapi_historical as poh  # noqa: E402
import requests  # noqa: E402

DATES = ["2023-05-12", "2023-05-15", "2023-07-04", "2023-09-15",
         "2023-10-01", "2024-04-01", "2024-04-08", "2024-07-04",
         "2024-08-15", "2024-09-22"]
ALL_MARKETS = sorted(poh.PITCHER_MARKETS | poh.BATTER_MARKETS)
OUT = Path(r"C:\Users\ckaplinger\MLB-Props-Research\odds-archive-acceptance-20261006\board_perevent_sample.json")


def board_ts_2023_24(commence: str) -> str:
    """8am ET on the ET game date; fixed UTC-4 (all 2023-24 games EDT)."""
    dt = datetime.fromisoformat(commence.replace("Z", "+00:00"))
    et_day = (dt - timedelta(hours=4)).date()
    return "%sT12:00:00Z" % et_day.isoformat()


def main() -> int:
    session = requests.Session()
    state = poh._load_state()
    key = poh._key()
    print("quota before:", state.get("remaining"))
    results = []
    for day in DATES:
        evs = poh.discover_events(session, key, day, day, state)
        if not evs:
            results.append({"date": day, "error": "no events in index"})
            print(day, "no events")
            continue
        ev = min(evs, key=lambda e: e["commence_time"])
        ts = board_ts_2023_24(ev["commence_time"])
        entry = {"date": day, "event_id": ev["id"],
                 "commence_time": ev["commence_time"],
                 "requested_board_ts": ts}
        try:
            data, headers = poh._get(
                session,
                "/historical/sports/%s/events/%s/odds" % (poh.SPORT, ev["id"]),
                {"apiKey": key, "date": ts, "regions": "us",
                 "markets": ",".join(ALL_MARKETS), "oddsFormat": "american"},
                state)
            payload = data.get("data", data)
            books = payload.get("bookmakers", [])
            mk = set()
            n_alt_events = 0
            lines_alt = set()
            for bk in books:
                for m in bk.get("markets", []):
                    mk.add(m.get("key", ""))
                    if m.get("key") == "pitcher_strikeouts_alternate":
                        n_alt_events = 1
                        for oc in m.get("outcomes", []):
                            if oc.get("point") is not None:
                                lines_alt.add(oc["point"])
            entry.update({
                "status": "ok",
                "returned_ts": data.get("timestamp"),
                "n_books": len(books),
                "markets_returned": len(mk),
                "altK_present": bool(n_alt_events),
                "altK_distinct_lines": sorted(lines_alt),
                "requested_cost_last_header":
                    headers.get("x-requests-last"),
                "remaining": headers.get("x-requests-remaining")})
            cache = poh.RAW_DIR / "snapshots" / "board_2023_24" / \
                ("%s.json" % ev["id"])
            if not cache.exists():
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(data), encoding="utf-8")
        except Exception as exc:
            entry.update({"status": "error",
                          "error_type": type(exc).__name__,
                          "error_redacted": str(exc)[:40].split("?")[0]})
        results.append(entry)
        print(json.dumps(entry, default=str))
    state = poh._load_state()
    out = {"results": results,
           "quota_after": {"remaining": state.get("remaining"),
                           "spent_observed": state.get("spent_observed")},
           "ceiling_credits": 10000}
    OUT.write_text(json.dumps(out, indent=2), encoding="ascii")
    print("quota after:", state.get("remaining"))
    print("report:", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
