"""Append-only real-money bet ledger (``real_bets.parquet``).

Deliberately SEPARATE from the paper-sim ``ledger.parquet``: this file holds
only tickets that went to real money, with the price/stake as they stood at
decision time (not at close). It never mutates paper-sim labels.

Key guarantee: **no ticket can silently drop.** ``append_real_bets`` returns an
explicit ``(frame, n_appended, skipped_ids)`` tuple; any row whose deterministic
``ticket_id`` already exists is returned in ``skipped_ids`` rather than melting
into the frame. Callers (backfill script, tests) must assert on the skipped set
so a missing batch (the 8/24 failure mode) can never go unnoticed again.

Schema notes
------------
- ``bet_price`` is the decision-time American price (e.g. -120) the bettor
  actually took — the snapshot for edge evaluation, not the closing line.
- ``result`` is one of ``win|loss|push|pending``; ``pnl`` is signed dollars on
  that ticket; ``result_source`` records who/how it was graded.
- ``status`` tracks open vs settled so a real bettor can append the decision
  at placement time and fill in the outcome later (append-only).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from Python import config
from Python.odds_ledger import stable_ticket_id

ODDS_DIR = config.OUTPUT_DIR / "odds_log"
REAL_BETS_PATH = ODDS_DIR / "real_bets.parquet"
META_PATH = ODDS_DIR / "last_real_bets.json"

# Columns every real-ticket row must carry (decision-time snapshot + audit).
REQUIRED_KEYS = (
    "game_date",
    "player_name",
    "line",
    "book",
    "side",
    "bet_price",
    "stake",
    "result",
    "result_source",
    "placed_utc",
)

# Fixed field/type contract so the append-only schema never drifts silently.
SCHEMA_TYPES: dict[str, type] = {
    "ticket_id": str,
    "game_date": str,
    "player_name": str,
    "line": float,
    "book": str,
    "side": str,
    "bet_price": float,
    "stake": float,
    "result": str,
    "result_source": str,
    "pnl": float,
    "status": str,
    "placed_utc": str,
    "closed_at_utc": str,
    "note": str,
}

# Column set written to parquet for every row (stable, independent of input).
_FINAL_KEYS = [
    "ticket_id", "game_date", "player_name", "line", "book", "side",
    "bet_price", "stake", "result", "result_source", "pnl", "status",
    "placed_utc", "closed_at_utc", "note",
]

def _coerce(row: dict[str, Any]) -> dict[str, Any]:
    """Fill defaults and coerce types for one real-bet row."""
    game_date = str(row["game_date"])[:10]
    out: dict[str, Any] = {
        "ticket_id": str(row.get("ticket_id") or stable_ticket_id(
            game_date=game_date,
            player_name=str(row["player_name"]),
            line=float(row["line"]),
            book=str(row["book"]),
            side=str(row["side"]),
        )),
        "game_date": game_date,
        "player_name": str(row["player_name"]),
        "line": float(row["line"]),
        "book": str(row["book"]),
        "side": str(row["side"]).lower(),
        "bet_price": float(row["bet_price"]),
        "stake": float(row["stake"]),
        "result": str(row.get("result") or "pending").lower(),
        "result_source": str(row.get("result_source") or "unverified"),
        "pnl": float(row.get("pnl") or 0.0),
        "status": str(row.get("status") or "settled").lower(),
        "placed_utc": str(row.get("placed_utc") or datetime.now(timezone.utc).isoformat()),
        "closed_at_utc": str(row.get("closed_at_utc") or ""),
        "note": str(row.get("note") or ""),
    }
    return {k: out[k] for k in _FINAL_KEYS}


def load_real_bets(path: Path = REAL_BETS_PATH) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    return pl.read_parquet(path)


def _write_meta(path: Path, n_rows: int = 0) -> None:
    META_PATH.write_text(
        json.dumps(
            {
                "path": str(path),
                "n_rows": n_rows,
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def append_real_bets(
    rows: Iterable[dict[str, Any]],
    *,
    path: Path = REAL_BETS_PATH,
) -> tuple[pl.DataFrame, int, list[str]]:
    """Append real-bet rows, returning ``(frame, n_appended, skipped_ids)``.

    Append-only and idempotent per deterministic ``ticket_id``: rows whose id
    is already in the ledger are returned in ``skipped_ids`` and NOT written.
    No row can silently drop — callers must account for every skipped id.
    """
    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    ledger = load_real_bets(path)
    existing: set[str] = (
        set(ledger["ticket_id"].to_list()) if not ledger.is_empty() else set()
    )

    fresh: list[dict[str, Any]] = []
    skipped: list[str] = []
    in_batch: set[str] = set()
    for raw in rows:
        row = _coerce(raw)
        tid = row["ticket_id"]
        if tid in existing or tid in in_batch:
            skipped.append(tid)
            continue
        in_batch.add(tid)
        fresh.append(row)

    if fresh:
        batch = pl.DataFrame(fresh)
        if ledger.is_empty():
            frame = batch
        else:
            frame = pl.concat([ledger, batch], how="diagonal_relaxed")
        frame.write_parquet(path)
        _write_meta(path, frame.height)
    else:
        frame = ledger

    return frame, len(fresh), skipped


def real_bets_summary(frame: pl.DataFrame | None = None) -> dict[str, float | int]:
    """PnL / stake / ROI / record for the real-bet ledger (settled rows)."""
    if frame is None:
        frame = load_real_bets()
    if frame.is_empty():
        return {"n": 0, "wins": 0, "losses": 0, "pushes": 0, "pnl": 0.0, "stake": 0.0, "roi": 0.0}
    settled = frame.filter(pl.col("result") != "pending")
    if settled.is_empty():
        return {"n": 0, "wins": 0, "losses": 0, "pushes": 0, "pnl": 0.0, "stake": 0.0, "roi": 0.0}
    wins = settled.filter(pl.col("result") == "win").height
    losses = settled.filter(pl.col("result") == "loss").height
    pushes = settled.filter(pl.col("result") == "push").height
    pnl = float(settled["pnl"].sum())
    stake = float(settled["stake"].sum())
    return {
        "n": settled.height,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "pnl": pnl,
        "stake": stake,
        "roi": (pnl / stake) if stake else 0.0,
    }

