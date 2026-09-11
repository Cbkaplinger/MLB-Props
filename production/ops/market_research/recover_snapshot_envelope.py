"""Recover vendor snapshot envelopes from raw Odds API JSON ($0).

The historical event-odds response wraps each pull in
``timestamp / previous_timestamp / next_timestamp`` plus ``data``.
``pull_oddsapi_historical.normalize`` currently reconstructs ``snapshot_ts``
as commence-5min/-5h/-30h from the inner event and drops the wrapper.
Those wrapper keys are already on disk in every cached JSON.

Standing spec: docs/reference/oddsapi_replay_architecture.md
Inventory: docs/reference/reports/oddsapi_replay_inventory_2026-09-11.md

This script never calls the API. It walks
``data/Odds-Historical/theoddsapi/raw/snapshots/{close,morning,open}/``
and writes ``snapshot_envelope.parquet`` next to the book-line files.

Research-only. Frozen model untouched. No live policy change.

  python production/ops/market_research/recover_snapshot_envelope.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.odds_ledger import atomic_write_parquet, atomic_write_text  # noqa: E402
from pull_oddsapi_historical import RAW_DIR, OUT_DIR, _snapshot_ts  # noqa: E402

SNAPS = ("close", "morning", "open")
OUT = OUT_DIR / "snapshot_envelope.parquet"
REPORT = ROOT / "artifacts" / "odds_log" / "snapshot_envelope_report.json"


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _sec(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return (a - b).total_seconds()


def load_rows() -> list[dict]:
    rows: list[dict] = []
    for snap in SNAPS:
        folder = RAW_DIR / "snapshots" / snap
        if not folder.exists():
            continue
        for fp in folder.glob("*.json"):
            try:
                payload = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            inner = payload.get("data", payload)
            if not isinstance(inner, dict):
                continue
            books = inner.get("bookmakers") or []
            markets: list[str] = []
            book_keys: list[str] = []
            last_updates: list[datetime] = []
            for bk in books:
                if not isinstance(bk, dict):
                    continue
                key = str(bk.get("key") or "")
                if key:
                    book_keys.append(key)
                lu = _parse(bk.get("last_update"))
                if lu is not None:
                    last_updates.append(lu)
                for mk in bk.get("markets") or []:
                    if isinstance(mk, dict) and mk.get("key"):
                        markets.append(str(mk["key"]))
            commence = inner.get("commence_time") or ""
            vendor_ts = payload.get("timestamp") or ""
            reconstructed = ""
            try:
                if commence:
                    reconstructed = _snapshot_ts(str(commence), snap)
            except Exception:
                reconstructed = ""
            vt = _parse(vendor_ts)
            ct = _parse(commence)
            rt = _parse(reconstructed)
            max_book = max(last_updates) if last_updates else None
            rows.append({
                "event_id": str(inner.get("id") or fp.stem),
                "snapshot": snap,
                "vendor_timestamp": vendor_ts,
                "previous_timestamp": payload.get("previous_timestamp") or "",
                "next_timestamp": payload.get("next_timestamp") or "",
                "commence_time": commence,
                "home_team": inner.get("home_team") or "",
                "away_team": inner.get("away_team") or "",
                "n_books": len(book_keys),
                "n_market_listings": len(markets),
                "books": ",".join(sorted(set(book_keys))),
                "markets": ",".join(sorted(set(markets))),
                "reconstructed_ts": reconstructed,
                "lag_vendor_vs_commence_sec": _sec(ct, vt),
                "lag_recon_vs_vendor_sec": _sec(rt, vt),
                "lag_max_book_vs_vendor_sec": _sec(max_book, vt) if max_book else None,
                "has_envelope": bool(vendor_ts),
            })
    return rows


def _pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return float(s[i])


def summarize(frame: pl.DataFrame) -> dict:
    rep: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_rows": int(frame.height),
        "by_snapshot": {},
        "envelope_rate": float(frame["has_envelope"].mean()) if frame.height else 0.0,
    }
    for snap, sub in frame.group_by("snapshot"):
        snap_name = snap[0] if isinstance(snap, tuple) else snap
        lags = [float(x) for x in sub["lag_vendor_vs_commence_sec"].drop_nulls().to_list()]
        recon = [float(x) for x in sub["lag_recon_vs_vendor_sec"].drop_nulls().to_list()]
        minutes = [x / 60.0 for x in lags]
        recon_sec = recon
        rep["by_snapshot"][str(snap_name)] = {
            "n": int(sub.height),
            "n_envelope": int(sub["has_envelope"].sum()),
            "n_books_mean": float(sub["n_books"].mean()) if sub.height else 0.0,
            "vendor_vs_commence_min": {
                "n": len(minutes),
                "min": min(minutes) if minutes else None,
                "p10": _pct(minutes, 0.10),
                "p50": _pct(minutes, 0.50),
                "p90": _pct(minutes, 0.90),
                "max": max(minutes) if minutes else None,
            },
            "recon_minus_vendor_sec": {
                "n": len(recon_sec),
                "min": min(recon_sec) if recon_sec else None,
                "p50": _pct(recon_sec, 0.50),
                "p90": _pct(recon_sec, 0.90),
                "max": max(recon_sec) if recon_sec else None,
            },
        }
    return rep


def main() -> None:
    rows = load_rows()
    if not rows:
        raise SystemExit("no snapshot JSON found under raw/snapshots/")
    frame = pl.DataFrame(rows)
    atomic_write_parquet(frame, OUT)
    rep = summarize(frame)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(REPORT, json.dumps(rep, indent=2, default=str))
    print(json.dumps(rep, indent=2))
    print(f"wrote {OUT} ({frame.height} rows)")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
