"""SharpAPI odds fetch for MLB pitcher strikeouts (REST; free-tier safe).

Uses ``SHARPAPI_KEY`` from the environment. Prefer REST over the SDK here —
``account.me()`` in sharpapi 0.4.0 currently fails pydantic validation on free
tier ``features`` lists.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SHARP_API_BASE = "https://api.sharpapi.io/api/v1"
DEFAULT_MARKET = "player_strikeouts"

# ---------------------------------------------------------------------------
# Client-side rate limiting.
# SharpAPI enforces per-key limits (Free=12 req/min, Hobby=120, Pro=300, ...).
# Polling/pagination hot-loops (close_watcher ticks, aux probes, open poll)
# can burst well past the window and trip 429s, whose retry cannot recover a
# big overrun. We therefore throttle every request to a safe floor so callers
# stay under their tier window regardless of how aggressively they loop.
# MIN_INTERVAL_S is intentionally conservative: 12/min -> one request / 6s.
# Blocking each request also serializes concurrent racers (the pagination loop
# and the aux probe share this time base), which prevents interleaved bursts.
# ---------------------------------------------------------------------------
import threading

_RATE_LIMIT_LOCK = threading.Lock()
_MIN_REQUEST_INTERVAL_S = float(os.getenv("SHARPAPI_MIN_INTERVAL_S", "6.0"))
_LAST_REQUEST_TS = 0.0


def _rate_limit_wait() -> None:
    """Block until at least ``_MIN_REQUEST_INTERVAL_S`` since the last request."""
    global _LAST_REQUEST_TS
    with _RATE_LIMIT_LOCK:
        now = time.time()
        wait = _LAST_REQUEST_TS + _MIN_REQUEST_INTERVAL_S - now
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST_TS = time.time()


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
        _rate_limit_wait()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            if exc.code == 429 and attempt + 1 < max_retries:
                # 429 means the server is already rate-limited. Back off a bit
                # MORE than a nominal tick so the window can drain, then retry.
                # Repeated 429s still raise below so they are never silently
                # swallowed into a long silent hang.
                time.sleep(20 * (attempt + 1))
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
    """Paginate ``GET /odds`` and return raw row dicts.

    Every request is gated by the module-level rate limiter, so a pagination
    loop can never burst past the per-key window. ``sleep_s`` is an additional
    per-page pause that is already covered by the limiter's minimum interval,
    so it defaults to 0 to avoid double-sleeping; callers that pass a larger
    value still get it as a floor.
    """
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


_QUOTE_FIELDS = [f.name for f in fields(StrikeoutQuote)]


def write_quotes_parquet(quotes: list[StrikeoutQuote], path: str | Path) -> Path:
    """Persist a fetched quote set atomically with a fetch timestamp.

    Shared-fetch contract (#113.3): one SharpAPI fetch feeds both board
    scoring and open polling, so both consumers price identically.
    """
    import polars as pl

    path = Path(path)
    rows = []
    for q in quotes:
        d = asdict(q)
        d["fetched_at_utc"] = datetime.now(timezone.utc).isoformat()
        rows.append(d)
    frame = pl.DataFrame(rows, schema={**{k: pl.String for k in _QUOTE_FIELDS
                                          if k not in ("line", "over_american",
                                                       "under_american", "is_main_line")},
                                       "line": pl.Float64, "over_american": pl.Float64,
                                       "under_american": pl.Float64, "is_main_line": pl.Boolean,
                                       "fetched_at_utc": pl.String})
    if frame.is_empty():
        frame = pl.DataFrame(schema=frame.schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.close()
        frame.write_parquet(tmp)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def read_quotes_parquet(
    path: str | Path, *, max_age_min: float | None = 30.0,
) -> list[StrikeoutQuote]:
    """Load a shared quote set; refuse stale files unless max_age_min=None.

    Raises FileNotFoundError (missing) or ValueError (stale) so callers fall
    back to a live fetch explicitly — never silently price off old quotes.
    """
    import polars as pl

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no shared quotes at {path}")
    frame = pl.read_parquet(path)
    if max_age_min is not None and "fetched_at_utc" in frame.columns:
        try:
            stamped = frame["fetched_at_utc"].drop_nulls()
            if not stamped.is_empty():
                age = (datetime.now(timezone.utc)
                       - datetime.fromisoformat(str(stamped[0]))).total_seconds() / 60.0
                if age > float(max_age_min):
                    raise ValueError(
                        f"shared quotes {age:.1f}m old > {max_age_min}m; refusing")
        except ValueError:
            raise
        except Exception:
            pass
    out = []
    for r in frame.to_dicts():
        kw = {k: r.get(k) for k in _QUOTE_FIELDS}
        kw["line"] = float(kw["line"])
        kw["over_american"] = float(kw["over_american"])
        kw["under_american"] = float(kw["under_american"])
        kw["is_main_line"] = bool(kw["is_main_line"])
        out.append(StrikeoutQuote(**kw))
    return out
