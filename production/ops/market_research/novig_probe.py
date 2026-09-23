"""Novig Stage-1 probe: fill-availability preview (owner 2026-09-23).

Read-only. Resolves today's BET signals (recommendations.parquet) to Novig
open markets (PITCHER_STRIKEOUTS) and writes an append-only tick table
``artifacts/odds_log/novig_ticks_YYYY-MM-DD.parquet``: which signals have a
fillable Novig market + outcome right now.

Keyless behavior: NO creds → prints NOVIG-SKIP and exits 0 (chain-safe).
With creds: QA-first by default (``--prod`` for production). Network failure
in chain mode (``--soft-fail``, used by the hourly chain) prints NOVIG-SOFT
and exits 0 — a free sidecar never fails a cron chain. Manual runs default
loud (raise) so a broken probe is visible.

Stage 2+ (paper loop, $5 shadow, $50) each need their own owner order.
``novig_client.place_order`` stays blocked until Stage 3.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from Python.novig_client import (  # noqa: E402
    K_MARKET_TYPES,
    NovigAuthError,
    NovigClient,
    load_config,
    resolve_market,
)
from Python.odds_ledger import atomic_write_parquet, et_today  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"
RECS_NAME = "recommendations.parquet"
TICKS_PREFIX = "novig_ticks_"


def _bet_signals(slate: str) -> list[dict]:
    """Today's BET rows (player, line, side). Empty when no board yet."""
    rec_path = ODDS_DIR / RECS_NAME
    if not rec_path.exists():
        return []
    rec = pl.read_parquet(rec_path)
    if rec.is_empty() or "recommendation" not in rec.columns:
        return []
    rec = rec.with_columns(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gdate"))
    bets = rec.filter(
        (pl.col("gdate") == slate[:10])
        & (pl.col("recommendation").cast(pl.Utf8).str.to_uppercase() == "BET"))
    out = []
    for r in bets.to_dicts():
        try:
            out.append({"player_name": str(r["player_name"]),
                        "line": float(r["line"]),
                        "side": str(r.get("best_side") or "").lower()})
        except (TypeError, ValueError, KeyError):
            continue
    return out


def probe(*, slate: str, qa: bool,
          client: NovigClient | None = None) -> tuple[list[dict], dict]:
    """Resolve every BET signal to a Novig market (pure I/O boundary).

    Returns (ticks, audit). Raises NovigAuthError without creds, RuntimeError
    on network failure (caller decides loud vs soft).
    """
    client = client or NovigClient(load_config(qa=qa))
    signals = _bet_signals(slate)
    markets: list[dict] = []
    for market_type in K_MARKET_TYPES:
        try:
            markets.extend(client.open_markets(market_type=market_type))
        except RuntimeError:
            if not markets:
                raise
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ticks, n_hit = [], 0
    for s in signals:
        hit = resolve_market(markets, player_name=s["player_name"],
                             line=s["line"], side=s["side"])
        if hit is not None and hit.get("market_id"):
            n_hit += 1
        ticks.append({
            "slate_date": slate[:10], "player_name": s["player_name"],
            "line": s["line"], "side": s["side"],
            "market_id": (hit or {}).get("market_id"),
            "outcome_id": (hit or {}).get("outcome_id"),
            "available": bool(hit is not None and hit.get("market_id")),
            "fetched_at_utc": now,
        })
    return ticks, {"n_signals": len(signals), "n_markets": len(markets),
                   "n_available": n_hit}


def write_ticks(ticks: list[dict], *, slate: str,
                out_dir: Path | None = None) -> Path:
    """Idempotent daily tick table (atomic). Returns the path."""
    target_dir = out_dir or ODDS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{TICKS_PREFIX}{slate[:10]}.parquet"
    frame = pl.DataFrame(ticks) if ticks else pl.DataFrame(schema={
        "slate_date": pl.Utf8, "player_name": pl.Utf8, "line": pl.Float64,
        "side": pl.Utf8, "market_id": pl.Utf8, "outcome_id": pl.Utf8,
        "available": pl.Boolean, "fetched_at_utc": pl.Utf8})
    atomic_write_parquet(frame, path)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default="",
                    help="Slate date (default: today ET).")
    ap.add_argument("--prod", action="store_true",
                    help="Production NBX (default: QA).")
    ap.add_argument("--soft-fail", action="store_true",
                    help="Chain mode: skip/failure prints NOVIG-SKIP/SOFT and exits 0.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Resolve + print, write nothing.")
    args = ap.parse_args()
    slate = args.date or et_today()
    try:
        ticks, audit = probe(slate=slate, qa=not args.prod)
    except NovigAuthError as exc:
        print(f"NOVIG-SKIP: {exc}")
        return
    except RuntimeError as exc:
        print(f"NOVIG-SOFT: probe failed ({exc!r}[:160]); skipping.")
        if args.soft_fail:
            return
        raise
    print(f"novig probe: {audit['n_available']}/{audit['n_signals']} BET signals "
          f"fillable across {audit['n_markets']} open K markets")
    if args.dry_run:
        for t in ticks:
            mark = "FILLABLE" if t["available"] else "no-market"
            print(f"  {mark} {t['player_name']} {t['line']:g} {t['side']}")
        print("(dry-run: nothing written)")
        return
    path = write_ticks(ticks, slate=slate)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
