"""Shared join keys for book-vs-model research (post hoc only).

Two name orders exist in the wild: L3 training rows are family-first
("Allen Logan"); vendors/ledger are given-first ("Logan Allen").
Canonical ``norm_player_name`` is lowercase-ASCII only and does NOT reorder,
so research joins MUST use :func:`sorted_key` on both sides. Never "fix" this
by editing the canonical normalizer (production behavior depends on it).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import norm_player_name  # noqa: E402

HIST = ROOT / "data" / "Odds-Historical" / "theoddsapi"
ODDS_DIR = ROOT / "artifacts" / "odds_log"
EVENT_DATE_MAP = ODDS_DIR / "event_date_map.json"


def sorted_key(s: str | None) -> str:
    """Order-invariant name key: lowercase ASCII, tokens sorted."""
    return " ".join(sorted(norm_player_name(str(s or "")).split()))


def load_event_date_map() -> dict[str, str]:
    """event_id -> commence date (cached JSON; rebuilt when missing)."""
    if EVENT_DATE_MAP.exists():
        try:
            return json.loads(EVENT_DATE_MAP.read_text(encoding="utf-8"))
        except Exception:
            pass
    evdate: dict[str, str] = {}
    for fp in sorted((HIST / "raw" / "event_index").glob("*.json")):
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for ev in d.get("data", d.get("events", [])):
            if isinstance(ev, dict) and ev.get("id"):
                ct = str(ev.get("commence_time", ""))[:10]
                if ct:
                    evdate[ev["id"]] = ct
    try:
        ODDS_DIR.mkdir(parents=True, exist_ok=True)
        EVENT_DATE_MAP.write_text(json.dumps(evdate), encoding="utf-8")
    except OSError:
        pass
    return evdate


CONSENSUS_CACHE = HIST / "consensus_cache.parquet"


def read_consensus_cache(market: str, snapshot: str) -> pl.DataFrame:
    """Precomputed devig-median consensus (gd, key, line, fair, n_books).

    Built by build_consensus_cache.py. All research reads this — never
    re-devig per script (SOP hardening 2026-09-10).
    """
    return pl.scan_parquet(CONSENSUS_CACHE).filter(
        (pl.col("market") == market) & (pl.col("snapshot") == snapshot)).collect()
