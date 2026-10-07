"""Bounded 2023-2024 historical availability probe (paid, ~750 credits).

Owner-ordered pre-cancellation verification 2026-10-06:
1. Event discovery on 6 sample dates (2 pre-boundary, 3 boundary-week, 1 in 2024).
2. Event-odds for 4 events x ALL 15 registered markets x close snapshot
   (plus one morning request on the 2023-05-04 event).
3. Verify 2023-05-03 as the practical earliest player-prop boundary.
4. Record bookmaker coverage + returned market keys + quota headers.

Close-snapshot payloads of real events are cached into the standard raw
lake (raw/snapshots/close/<eid>.json) so the future full pull never
re-spends them. Pre-boundary 404s pre-populate the skip ledger.

ASCII-only output. Never prints the API key.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pull_oddsapi_historical as poh  # noqa: E402

ALL_MARKETS = sorted(poh.PITCHER_MARKETS | poh.BATTER_MARKETS)
DATES = ["2023-04-28", "2023-04-29", "2023-05-03", "2023-05-04",
         "2023-05-05", "2024-07-12"]
PROBE_REPORT = ROOT / "data" / "Odds-Historical" / "theoddsapi" / "_probe" / "probe_2023_2024.json"


def main() -> int:
    import requests
    key = poh._key()
    session = requests.Session()
    state = poh._load_state()
    print("key present: True (value withheld)")
    print("quota before: remaining=%s spent_observed=%s"
          % (state.get("remaining"), state.get("spent_observed")))

    # 1. discovery (cached forever per date)
    discovery = {}
    for day in DATES:
        evs = poh.discover_events(session, key, day, day, state)
        discovery[day] = len(evs)
        print("discover %s: %d events" % (day, len(evs)))

    def first_event(day: str) -> dict | None:
        evs = poh.discover_events(session, key, day, day, state)
        return min(evs, key=lambda e: e["commence_time"]) if evs else None

    targets = {}
    for day in ("2023-04-29", "2023-05-03", "2023-05-04", "2024-07-12"):
        ev = first_event(day)
        targets[day] = ev
        print("probe event %s: %s" % (day, ev["id"] if ev else None))

    # 2. event-odds probes
    results = []
    for day, ev in targets.items():
        if ev is None:
            results.append({"day": day, "event": None})
            continue
        ts = poh._snapshot_ts(ev["commence_time"], "close")
        entry = {"day": day, "event_id": ev["id"],
                 "commence_time": ev["commence_time"], "close_ts": ts}
        try:
            data, headers = poh._get(
                session,
                "/historical/sports/%s/events/%s/odds" % (poh.SPORT, ev["id"]),
                {"apiKey": key, "date": ts, "regions": "us",
                 "markets": ",".join(ALL_MARKETS), "oddsFormat": "american"},
                state)
            payload = data.get("data", data)
            books = payload.get("bookmakers", []) if isinstance(payload, dict) else []
            mk = set()
            nb = 0
            for bk in books:
                nb += 1
                for m in bk.get("markets", []):
                    mk.add(m.get("key", ""))
            entry.update({"status": "ok", "n_books": nb,
                          "markets_returned": sorted(mk),
                          "markets_missing": sorted(set(ALL_MARKETS) - mk),
                          "remaining": headers.get("x-requests-remaining")})
            if day != "2023-04-29":  # cache real close snapshots into the lake
                cache = poh.RAW_DIR / "snapshots" / "close" / ("%s.json" % ev["id"])
                if not cache.exists():
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_text(json.dumps(data), encoding="utf-8")
                    entry["cached_to_lake"] = True
        except Exception as exc:
            entry.update({"status": "error", "error": str(exc)[:160]})
            if day == "2023-04-29":
                # pre-populate the skip ledger so the full pull never retries
                skip_path = poh.RAW_DIR / "skipped_events.json"
                try:
                    skipped = set(json.loads(skip_path.read_text(encoding="utf-8")))
                except Exception:
                    skipped = set()
                skipped.add(ev["id"])
                skip_path.parent.mkdir(parents=True, exist_ok=True)
                skip_path.write_text(json.dumps(sorted(skipped)), encoding="utf-8")
                entry["added_to_skip_ledger"] = True
        results.append(entry)
        print("probe %s %s: %s" % (day, entry.get("status"),
                                   entry.get("n_books", entry.get("error", ""))))

    # one morning snapshot on the 2023-05-04 event (availability check)
    ev = targets.get("2023-05-04")
    morning = {"day": "2023-05-04", "snapshot": "morning"}
    if ev:
        ts = poh._snapshot_ts(ev["commence_time"], "morning")
        try:
            data, headers = poh._get(
                session,
                "/historical/sports/%s/events/%s/odds" % (poh.SPORT, ev["id"]),
                {"apiKey": key, "date": ts, "regions": "us",
                 "markets": ",".join(ALL_MARKETS), "oddsFormat": "american"},
                state)
            payload = data.get("data", data)
            books = payload.get("bookmakers", []) if isinstance(payload, dict) else []
            mk = set()
            for bk in books:
                for m in bk.get("markets", []):
                    mk.add(m.get("key", ""))
            morning.update({"status": "ok", "n_books": len(books),
                            "markets_returned": sorted(mk)})
        except Exception as exc:
            morning.update({"status": "error", "error": str(exc)[:160]})
    results.append(morning)
    print("morning probe:", morning.get("status"), morning.get("n_books"))

    state = poh._load_state()
    report = {
        "purpose": "pre-cancellation 2023-2024 availability verification",
        "discovery_events_by_date": discovery,
        "probes": results,
        "quota_after": {"remaining": state.get("remaining"),
                        "spent_observed": state.get("spent_observed")},
        "markets_requested": ALL_MARKETS,
    }
    PROBE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    PROBE_REPORT.write_text(json.dumps(report, indent=2), encoding="ascii")
    print("quota after: remaining=%s spent_observed=%s"
          % (state.get("remaining"), state.get("spent_observed")))
    print("report: %s" % PROBE_REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
