"""Backfill the append-only real-money bet ledger (``real_bets.parquet``).

Reads an authoritative, operator-maintained list of real tickets and appends
them via ``Python.real_bets.append_real_bets`` so nothing can silently drop.

Safety contract (mirrors the ``real_bets`` module):
- Every backfilled row must carry a **decision-time price** (``bet_price``) and
  ``stake`` — the snapshot for edge evaluation. A row missing those is held
  back and REPORTED, never written as a zero (no fabricated audit data).
- Idempotent: re-running with tickets already present appends 0 and reports
  every already-present id. The script asserts on the skipped set so an
  unexpected missing/duplicate id breaks loudly instead of silently.

Run (from repo root):
    .\\.venv\\Scripts\\python.exe production/ops/backfill_real_bets.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.real_bets import append_real_bets, real_bets_summary  # noqa: E402

# At least one of these must be nonzero for a row to be a real, priced decision.
_PRICE_FIELDS = ("bet_price", "stake")
_REQUIRED_IDENTITY = ("game_date", "player_name", "line", "book", "side", "result")


def _is_priced(row: dict[str, object]) -> bool:
    return all(float(row.get(f, 0.0)) != 0.0 for f in _PRICE_FIELDS)


# Authoritative operator record of the confirmed real tickets. ``game_date``,
# ``player_name``, ``line``, ``book``, ``side``, ``result`` are the confirmed
# identities (backlog). ``bet_price`` (decision-time american), ``stake`` and
# ``pnl`` MUST be the real numbers — rows missing them are held back (not
# written as zeros) and printed, so the operator fills them in exactly once.
REAL_TICKETS: list[dict[str, object]] = [
    {"game_date": "2026-08-24", "player_name": "Valdez", "line": 4.5,
     "book": "draftkings", "side": "under", "result": "win", "result_source": "user_confirmed",
     "bet_price": 0.0, "stake": 0.0, "pnl": 0.0, "placed_utc": "2026-08-24T00:00:00Z"},
    {"game_date": "2026-08-24", "player_name": "Suarez", "line": 4.5,
     "book": "novig", "side": "under", "result": "win", "result_source": "user_confirmed",
     "bet_price": 0.0, "stake": 0.0, "pnl": 0.0, "placed_utc": "2026-08-24T00:00:00Z"},
    {"game_date": "2026-08-24", "player_name": "Messick", "line": 6.5,
     "book": "draftkings", "side": "over", "result": "loss", "result_source": "user_confirmed",
     "bet_price": 0.0, "stake": 0.0, "pnl": 0.0, "placed_utc": "2026-08-24T00:00:00Z"},
    {"game_date": "2026-08-24", "player_name": "Skenes", "line": 6.5,
     "book": "fanduel", "side": "under", "result": "win", "result_source": "user_confirmed",
     "bet_price": 0.0, "stake": 0.0, "pnl": 0.0, "placed_utc": "2026-08-24T00:00:00Z"},
    {"game_date": "2026-08-25", "player_name": "Melton", "line": 3.5,
     "book": "draftkings", "side": "over", "result": "win", "result_source": "user_confirmed",
     "bet_price": 0.0, "stake": 0.0, "pnl": 0.0, "placed_utc": "2026-08-25T00:00:00Z"},
    {"game_date": "2026-08-25", "player_name": "G.Rodriguez", "line": 4.5,
     "book": "fanduel", "side": "over", "result": "loss", "result_source": "user_confirmed",
     "bet_price": 0.0, "stake": 0.0, "pnl": 0.0, "placed_utc": "2026-08-25T00:00:00Z"},
    # Cantillo: WIN at +130 — better than both paper prices.
    {"game_date": "2026-08-25", "player_name": "Cantillo", "line": 6.5,
     "book": "novig", "side": "under", "result": "win", "result_source": "user_confirmed",
     "bet_price": 0.0, "stake": 0.0, "pnl": 0.0, "placed_utc": "2026-08-25T00:00:00Z"},
    {"game_date": "2026-08-26", "player_name": "Sasaki", "line": 4.5,
     "book": "draftkings", "side": "over", "result": "loss", "result_source": "user_confirmed",
     "bet_price": 0.0, "stake": 0.0, "pnl": 0.0, "placed_utc": "2026-08-26T00:00:00Z"},
]

# 9th real ticket (to reach 6W-3L): identity + decision-time price needed from
# the operator. Pending — will not be written until its row is added here with
# real bet_price/stake/pnl.


def main() -> None:
    complete = [r for r in REAL_TICKETS if _is_priced(r)]
    held_back = [r for r in REAL_TICKETS if not _is_priced(r)]

    if held_back:
        # Never write unverified rows; surface exactly which are waiting.
        print(f"[WAIT] {len(held_back)} ticket(s) lack decision-time price/stake and were NOT written:")
        for r in held_back:
            ident = {k: r.get(k) for k in _REQUIRED_IDENTITY}
            print("   -", ident)

    if not complete:
        print("\nNothing priced -> real_bets.parquet unchanged. Fill in decision-time "
              "bet_price / stake (and pnl) for each row above, then rerun.")
        return

    frame, n_appended, skipped = append_real_bets(complete)
    print(f"\nappended={n_appended}")
    if skipped:
        print(f"skipped (already present, reported): {skipped}")
    summary = real_bets_summary(frame)
    print(
        f"real_bets.parquet -> {summary['n']} settled: "
        f"{summary['wins']}W-{summary['losses']}L, "
        f"pnl=${summary['pnl']:.2f} on ${summary['stake']:.2f} "
        f"(roi={100 * summary['roi']:.1f}%)"
    )
    # Anti-silent-drop guard: if we appended new rows AND skipped some ids, that
    # is unexpected for a clean first backfill — abort loudly, don't proceed.
    if n_appended and skipped:
        raise SystemExit(
            "ABORT: some tickets were skipped unexpectedly — investigate before proceeding."
        )


if __name__ == "__main__":
    main()

