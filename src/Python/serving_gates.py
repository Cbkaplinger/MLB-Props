"""Serving freshness gates, fail-LOUD edition (DATA-1A, owner 2026-09-23).

Broader freeze (2026-09-18): no automatic interventions anywhere. These
gates NEVER suppress a ledger write or a page — they return warnings that
callers banner into messages, force flips-only pages, and record in run
manifests. A human reads them and decides.

Checks (all read-only, never raise):
- ``recommendations.parquet``: exists, slate_date == today (ET), fresh mtime.
- ``last_log.json``: ``build_meta.rolling_max_date`` within 2 days.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RECS_NAME = "recommendations.parquet"
LAST_LOG_NAME = "last_log.json"
MAX_RECS_AGE_H = 6.0
MAX_ROLLING_STALE_D = 2


def _utcnow() -> datetime:
    now = datetime.now(timezone.utc)
    return now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)


def check_serving(
    odds_dir: str | Path,
    today_et: str,
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Return ``{"ok": bool, "warnings": [...]}``. Never raises."""
    warnings: list[str] = []
    now = now_utc or _utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    day = str(today_et)[:10]
    try:
        return _check(Path(odds_dir), day, now, warnings)
    except Exception as exc:  # noqa: BLE001 — a gate must never crash a chain
        warnings.append(f"serving-gate errored (fail-open): {exc!r}"[:200])
        return {"ok": False, "warnings": warnings}


def _check(
    odds_dir: Path, day: str, now: datetime, warnings: list[str]
) -> dict[str, Any]:
    recs = odds_dir / RECS_NAME
    if not recs.exists():
        warnings.append("recommendations.parquet missing")
    else:
        try:
            import polars as pl

            frame = pl.read_parquet(recs, columns=["game_date"])
            dates = frame["game_date"].cast(pl.Utf8).str.slice(0, 10).unique().to_list()
            if day not in dates:
                warnings.append(
                    f"recommendations slate {sorted(dates)[-1] if dates else '?'} != today {day}")
        except Exception as exc:  # noqa: BLE001 — unreadable board is itself the warning
            warnings.append(f"recommendations.parquet unreadable: {exc!r}"[:160])
        try:
            age_h = (now.timestamp() - recs.stat().st_mtime) / 3600.0
            if age_h > MAX_RECS_AGE_H:
                warnings.append(f"recommendations.parquet age {age_h:.1f}h > {MAX_RECS_AGE_H:g}h")
        except OSError:
            pass
    last_log = odds_dir / LAST_LOG_NAME
    try:
        meta = json.loads(last_log.read_text(encoding="utf-8")).get("build_meta", {})
        max_s = str(meta.get("rolling_max_date") or "")[:10]
        latest = datetime.strptime(max_s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        stale_days = (now - latest).days
        if stale_days > MAX_ROLLING_STALE_D:
            warnings.append(
                f"projection rolling_max {max_s} stale {stale_days}d > {MAX_ROLLING_STALE_D}d")
    except (OSError, ValueError):
        warnings.append("last_log rolling_max missing/unparseable")
    return {"ok": not warnings, "warnings": warnings}
