"""Kalshi K-ladder reader, KEYLESS (owner 2026-09-23).

Venue verdict (probed live 2026-09-23):
- SharpAPI free = DK + FD only (53/53 quotes).
- Polymarket = season leaders only. Skipped for CLV.
- Kalshi trading-api host = 401 without key. BUT the elections host
  (``api.elections.kalshi.com``, same API shape, NO auth — the same host
  the historical ``pull_kalshi_k_history.py`` lake came from) serves LIVE
  open markets keyless. Series ``KXMLBKS`` (``KXMLBKS-26SEP231310WSHDET``:
  date + teams), one ladder market per rung:
  title ``"Framber Valdez: 9+ strikeouts?"`` + ``floor_strike`` 8.5 +
  dollar prices. Marquee arms only — a second opinion, not the full slate.

- ``fetch_open_k_events``: open KXMLBKS events (today's K games).
- ``fetch_event_markets``: ladder markets for one event.
- ``parse_k_market``: defensive → panel row (player, line=floor_strike,
  over/under_prob). Prices prefer last, else bid midpoint.
- ``write_panel``: idempotent daily ``kalshi_panel_YYYY-MM-DD.parquet``
  (history accumulates; storage is the value — paid 9-book consensus stays
  canonical till the sub ends).

A key is NOT needed for any of this. (Trading-API key remains free
self-serve if order-book depth is ever wanted.)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

ELECTIONS_API = "https://api.elections.kalshi.com/trade-api/v2"
K_SERIES = "KXMLBKS"

PANEL_DIR_NAME = "odds_log"
PANEL_PREFIX = "kalshi_panel_"

TITLE_RE = re.compile(
    r"^(?P<player>.+?):\s*(?P<n>\d+)\+\s*strikeouts?\??\s*$", re.IGNORECASE)
EVENT_DATE_RE = re.compile(r"-(\d{2}[A-Z]{3}\d{2})")
MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
          "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def _get(url: str, timeout_s: float = 25.0) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": "MLB-Props/research",
                      "Content-Type": "application/json"},
        method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            out = json.loads(resp.read().decode("utf-8"))
            return out if isinstance(out, dict) else {}
    except Exception as exc:
        raise RuntimeError(f"kalshi GET failed: {url.split('?')[0]}: {exc!r}")


def fetch_open_k_events(*, base: str = ELECTIONS_API,
                        limit: int = 100) -> list[dict]:
    """Open KXMLBKS events (today's K games). Keyless."""
    payload = _get(f"{base}/events?series_ticker={K_SERIES}&status=open&limit={limit}")
    return payload.get("events") or []


def fetch_event_markets(event_ticker: str, *, base: str = ELECTIONS_API,
                        limit: int = 100) -> list[dict]:
    """Ladder markets for one event. Keyless."""
    payload = _get(f"{base}/markets?event_ticker={event_ticker}&status=open&limit={limit}")
    return payload.get("markets") or []


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def event_game_date(event_ticker: str) -> str | None:
    """KXMLBKS-26SEP231310WSHDET -> 2026-09-23 (None when unparseable).

    Ticker clock is YY + MMM + DD + HHMM (26 = 2026, 23 = day, 1310 = ET).
    """
    m = EVENT_DATE_RE.search(str(event_ticker or ""))
    if not m:
        return None
    try:
        yy, mon, dd = m.group(1)[:2], m.group(1)[2:5], m.group(1)[5:7]
        return f"20{yy}-{MONTHS[mon]:02d}-{int(dd):02d}"
    except (ValueError, KeyError):
        return None


def parse_k_market(market: dict, *, now_utc: str = "") -> dict | None:
    """One ladder market → panel row (pure, testable). None = skip."""
    title = str(market.get("title") or "")
    m = TITLE_RE.match(title)
    if m is None:
        return None
    line = _num(market.get("floor_strike"))
    if line is None:
        return None
    last = _num(market.get("last_price_dollars"))
    yes_bid = _num(market.get("yes_bid_dollars"))
    no_bid = _num(market.get("no_bid_dollars"))
    if last is not None:
        over_p, under_p = last, 1.0 - last
    elif yes_bid is not None and no_bid is not None:
        over_p = (yes_bid + (1.0 - no_bid)) / 2.0
        under_p = 1.0 - over_p
    else:
        return None
    return {
        "player_name": m.group("player").strip(),
        "line": line,
        "over_prob": round(over_p, 4),
        "under_prob": round(under_p, 4),
        "source": "kalshi",
        "market_ticker": str(market.get("ticker") or ""),
        "event_ticker": str(market.get("event_ticker") or ""),
        "title": title[:160],
        "fetched_at_utc": now_utc or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def write_panel(rows: list[dict], *, game_date: str,
                out_dir: Path | None = None,
                run_tag: str = "") -> Path:
    """Per-run panel write (atomic; owner 2026-09-24).

    One file per run (``kalshi_panel_YYYY-MM-DDTHHMMSS.parquet``), never one
    per day: a daily file gets overwritten by the next hourly run and the
    morning opens are lost. The join reads ``kalshi_panel_*.parquet`` and
    picks earliest-of-day (open) / latest-pre-tip (close) per key, so reruns
    and duplicates are harmless by construction.
    """
    from Python.odds_ledger import atomic_write_parquet  # noqa: E402

    import polars as pl  # noqa: E402

    target_dir = out_dir or (ROOT / "artifacts" / PANEL_DIR_NAME)
    target_dir.mkdir(parents=True, exist_ok=True)
    tag = run_tag or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    path = target_dir / f"{PANEL_PREFIX}{tag}.parquet"
    frame = pl.DataFrame(rows) if rows else pl.DataFrame(
        schema={"player_name": pl.Utf8, "line": pl.Float64,
                "over_prob": pl.Float64, "under_prob": pl.Float64,
                "source": pl.Utf8, "market_ticker": pl.Utf8,
                "event_ticker": pl.Utf8, "title": pl.Utf8,
                "fetched_at_utc": pl.Utf8})
    atomic_write_parquet(frame, path)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default="",
                    help="Slate date for the panel filename (default: today ET).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Fetch + parse, print coverage, write nothing.")
    ap.add_argument("--soft-fail", action="store_true",
                    help="Chain mode: any failure prints KALSHI-SOFT and exits 0 "
                         "(never fail a cron chain over a free sidecar).")
    args = ap.parse_args()
    from Python.odds_ledger import et_today  # noqa: E402

    day = args.date or et_today()
    try:
        events = fetch_open_k_events()
    except Exception as exc:  # noqa: BLE001
        print(f"KALSHI-SOFT: discovery failed ({exc!r}[:120]); skipping panel.")
        if args.soft_fail:
            return
        raise
    rows, skipped, events_hit = [], 0, 0
    for e in events:
        et = str(e.get("event_ticker") or "")
        gd = event_game_date(et)
        if gd is not None and gd != day[:10]:
            continue
        events_hit += 1
        try:
            markets = fetch_event_markets(et)
        except Exception as exc:  # noqa: BLE001
            print(f"KALSHI-SOFT: {et} markets failed ({exc!r}[:100]); continuing.")
            if not args.soft_fail:
                raise
            continue
        for mk in markets:
            row = parse_k_market(mk)
            if row is None:
                skipped += 1
            else:
                rows.append(row)
    print(f"kalshi K: {len(events)} open events, {events_hit} today, "
          f"{len(rows)} rungs, {skipped} skipped")
    if args.dry_run:
        for r in rows[:10]:
            print(f"  {r['player_name']} {r['line']:g} over={r['over_prob']:.2f}")
        print("(dry-run: nothing written)")
        return
    path = write_panel(rows, game_date=day)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
