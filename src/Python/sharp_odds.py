"""SharpAPI odds fetch for MLB pitcher strikeouts (REST; free-tier safe).

Uses ``SHARPAPI_KEY`` from the environment. Prefer REST over the SDK here —
``account.me()`` in sharpapi 0.4.0 currently fails pydantic validation on free
tier ``features`` lists.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

SHARP_API_BASE = "https://api.sharpapi.io/api/v1"
DEFAULT_MARKET = "player_strikeouts"


@dataclass(frozen=True)
class StrikeoutQuote:
    """Paired over/under strikeout prices for one pitcher at one book/line."""

    player_name: str
    line: float
    over_american: float
    under_american: float
    sportsbook: str
    home_team: str
    away_team: str
    event_id: str | None
    event_start_time: str | None
    is_main_line: bool


def get_api_key() -> str:
    key = (os.getenv("SHARPAPI_KEY") or "").strip()
    if not key:
        raise SystemExit(
            "SHARPAPI_KEY missing. Add it to repo-root .env "
            "(see .env.example) and retry."
        )
    return key


def _get_json(
    path: str,
    params: dict[str, Any],
    api_key: str,
    *,
    max_retries: int = 3,
) -> dict[str, Any]:
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{SHARP_API_BASE}{path}?{q}"
    req = urllib.request.Request(url, headers={"X-API-Key": api_key})
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            if exc.code == 429 and attempt + 1 < max_retries:
                time.sleep(10 * (attempt + 1))
                last_err = exc
                continue
            raise SystemExit(f"SharpAPI HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            if attempt + 1 < max_retries:
                time.sleep(2 * (attempt + 1))
                last_err = exc
                continue
            raise SystemExit(f"SharpAPI network error: {exc}") from exc
    raise SystemExit(f"SharpAPI failed after retries: {last_err}")


def fetch_odds_rows(
    *,
    league: str = "mlb",
    market: str = DEFAULT_MARKET,
    sportsbook: str | None = None,
    is_live: bool | None = False,
    limit: int = 200,
    max_pages: int = 20,
    sleep_s: float = 0.15,
) -> list[dict[str, Any]]:
    """Paginate ``GET /odds`` and return raw row dicts."""
    api_key = get_api_key()
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(max_pages):
        params: dict[str, Any] = {
            "league": league,
            "market": market,
            "limit": limit,
        }
        if sportsbook:
            params["sportsbook"] = sportsbook
        if is_live is not None:
            params["is_live"] = str(is_live).lower()
        if cursor:
            params["cursor"] = cursor
        payload = _get_json("/odds", params, api_key)
        batch = payload.get("data") or []
        rows.extend(batch)
        pag = payload.get("pagination") or {}
        if not pag.get("has_more"):
            break
        cursor = pag.get("next_cursor")
        if not cursor:
            break
        time.sleep(sleep_s)
    return rows


def pair_strikeout_quotes(
    rows: list[dict[str, Any]],
    *,
    main_only: bool = True,
) -> list[StrikeoutQuote]:
    """Collapse raw over/under rows into paired quotes."""
    buckets: dict[tuple[str, str, float, str], dict[str, Any]] = {}
    for r in rows:
        if r.get("market_type") != "player_strikeouts":
            continue
        if main_only and r.get("is_main_line") is False:
            continue
        name = (r.get("player_name") or "").strip()
        line = r.get("line")
        book = (r.get("sportsbook") or "").strip()
        side = (r.get("selection_type") or "").lower()
        amer = r.get("odds_american")
        if not name or line is None or not book or amer is None:
            continue
        if side not in ("over", "under"):
            continue
        key = (name.lower(), book, float(line), str(r.get("event_id") or ""))
        slot = buckets.setdefault(
            key,
            {
                "player_name": name,
                "line": float(line),
                "sportsbook": book,
                "home_team": r.get("home_team") or "",
                "away_team": r.get("away_team") or "",
                "event_id": r.get("event_id"),
                "event_start_time": r.get("event_start_time"),
                "is_main_line": bool(r.get("is_main_line")),
            },
        )
        slot[side] = float(amer)

    out: list[StrikeoutQuote] = []
    for slot in buckets.values():
        if "over" not in slot or "under" not in slot:
            continue
        out.append(
            StrikeoutQuote(
                player_name=slot["player_name"],
                line=slot["line"],
                over_american=slot["over"],
                under_american=slot["under"],
                sportsbook=slot["sportsbook"],
                home_team=slot["home_team"],
                away_team=slot["away_team"],
                event_id=slot.get("event_id"),
                event_start_time=slot.get("event_start_time"),
                is_main_line=slot["is_main_line"],
            )
        )
    return out


def fetch_mlb_strikeout_quotes(
    *,
    sportsbook: str | None = None,
    main_only: bool = True,
    is_live: bool | None = False,
) -> list[StrikeoutQuote]:
    rows = fetch_odds_rows(
        league="mlb",
        market=DEFAULT_MARKET,
        sportsbook=sportsbook,
        is_live=is_live,
    )
    return pair_strikeout_quotes(rows, main_only=main_only)
