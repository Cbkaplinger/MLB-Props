"""Kalshi K-market reader, key-gated (owner 2026-09-23).

Venue verdict (probed 2026-09-23):
- SharpAPI free = DK + FD only (verified: 53/53 quotes today).
- Polymarket = season-leader K markets only, NO per-game pitcher lines.
  Useless for CLV. Skipped (recheck occasionally).
- Kalshi market reads need an API key (401 unauthenticated), but keys are
  FREE self-serve (kalshi.com → API) — unlike Novig's rep-gated trading
  access. Kalshi lists per-game pitcher strikeout over/unders (marquee
  arms; partial coverage like the books' featured set).

This module (NO key in repo/chat; ``KALSHI_API_KEY`` env → Modal Secret
``mlb-props-keys`` in prod, ``.env`` laptop-only):
- ``fetch_open_k_markets``: paginated discovery of open markets, client-side
  filter to pitcher-K lines (ticker-scheme agnostic).
- ``parse_k_market``: defensive parse (field names vary) → panel row
  (player, line, over_prob, under_prob). Unparseable = skipped + counted.
- ``write_panel``: idempotent daily panel
  ``artifacts/odds_log/kalshi_panel_YYYY-MM-DD.parquet`` (history
  accumulates; the watcher pattern — storage is the value).
- Shape risk: Kalshi's exact JSON field names are verified on the first
  KEYED run via ``--probe`` (dumps raw shape, writes nothing). Parser
  accepts every known alias; unknown shapes skip loud (counted, printed).

Coverage caveat: marquee arms only — enriches consensus where present,
never the full slate. Paid OddsAPI 9-book consensus stays canonical until
the sub ends; this is the free-forever second opinion.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

KALSHI_API = "https://trading-api.kalshi.com/trade-api/v2"
DEMO_API = "https://demo-api.kalshi.co/trade-api/v2"

PANEL_DIR_NAME = "odds_log"
PANEL_PREFIX = "kalshi_panel_"

# "Sale over 7.5 Ks", "Skubal 6+ strikeouts", "K's" variants.
K_TITLE = re.compile(
    r"(?P<player>[A-Z][A-Za-z.'\- ]+?)\s+"
    r"(?:over|under|o/u|>|<|\+)?\s*"
    r"(?P<line>\d+(?:\.\d+)?)\s*(?:Ks?|strikeouts?)",
    re.IGNORECASE,
)


class KalshiAuthError(RuntimeError):
    """No API key — free self-serve at kalshi.com → API, then retry."""


def api_key() -> str:
    key = os.getenv("KALSHI_API_KEY", "").strip()
    if not key:
        raise KalshiAuthError(
            "KALSHI_API_KEY not set. Free self-serve: kalshi.com → API → "
            "create key. Prod: add to Modal Secret 'mlb-props-keys'. "
            "Laptop: .env (gitignored). Never chat/repo.")
    return key


def _get(url: str, key: str, timeout_s: float = 20.0) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {key}",
                      "User-Agent": "MLB-Props/research",
                      "Content-Type": "application/json"},
        method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            out = json.loads(resp.read().decode("utf-8"))
            return out if isinstance(out, dict) else {}
    except Exception as exc:
        raise RuntimeError(f"kalshi GET failed: {url.split('?')[0]}: {exc!r}")


def fetch_open_markets(*, key: str, base: str = KALSHI_API, limit: int = 200,
                       max_pages: int = 20) -> tuple[list[dict], int]:
    """Paginate open markets. Returns (markets, n_pages). Never filters."""
    markets: list[dict] = []
    cursor: str | None = None
    pages = 0
    for _ in range(max_pages):
        url = f"{base}/markets?limit={limit}&status=open"
        if cursor:
            url += f"&cursor={cursor}"
        payload = _get(url, key)
        batch = payload.get("markets") or []
        markets.extend(batch)
        pages += 1
        cursor = payload.get("cursor")
        if not cursor:
            break
    return markets, pages


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_k_market(market: dict, *, now_utc: str = "") -> dict | None:
    """Defensive parse of one market to a K panel row (pure, testable).

    Accepts alias field names; returns None (skip) when the market is not a
    parseable pitcher-K line. Prices prefer last_price, else yes_bid/no_bid
    midpoint, else yes_ask implied.
    """
    title = str(market.get("title") or market.get("name") or "")
    m = K_TITLE.search(title)
    if m is None:
        return None
    line = _num(m.group("line"))
    if line is None:
        return None
    yes_bid = _num(market.get("yes_bid"))
    no_bid = _num(market.get("no_bid"))
    last = _num(market.get("last_price"))
    yes_ask = _num(market.get("yes_ask"))
    if last is not None:
        over_p, under_p = last / 100.0, 1.0 - last / 100.0
    elif yes_bid is not None and no_bid is not None:
        over_p = (yes_bid + (100.0 - no_bid)) / 2.0 / 100.0
        under_p = 1.0 - over_p
    elif yes_ask is not None:
        over_p, under_p = yes_ask / 100.0, 1.0 - yes_ask / 100.0
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
                out_dir: Path | None = None) -> Path:
    """Idempotent daily panel write (atomic). Returns the path."""
    from Python.odds_ledger import atomic_write_parquet  # noqa: E402

    import polars as pl  # noqa: E402

    target_dir = out_dir or (ROOT / "artifacts" / PANEL_DIR_NAME)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{PANEL_PREFIX}{game_date[:10]}.parquet"
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
    ap.add_argument("--probe", action="store_true",
                    help="Dump raw open-markets shape (first keyed run), write nothing.")
    ap.add_argument("--date", default="",
                    help="Slate date for the panel filename (default: today ET).")
    ap.add_argument("--demo", action="store_true", help="Use the demo API host.")
    args = ap.parse_args()
    key = api_key()
    base = DEMO_API if args.demo else KALSHI_API
    markets, pages = fetch_open_markets(key=key, base=base)
    print(f"kalshi open markets: {len(markets)} ({pages} pages)")
    if args.probe:
        print(json.dumps(markets[:3], indent=1, default=str)[:3000])
        print("(probe only — nothing written; use the shape to confirm the parser)")
        return
    from Python.odds_ledger import et_today  # noqa: E402

    day = args.date or et_today()
    rows, skipped = [], 0
    for m in markets:
        row = parse_k_market(m)
        if row is None:
            skipped += 1
        else:
            rows.append(row)
    path = write_panel(rows, game_date=day)
    print(f"kalshi K panel: {len(rows)} rows, {skipped} skipped -> {path}")


if __name__ == "__main__":
    main()
