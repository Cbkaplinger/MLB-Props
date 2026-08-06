"""Settle odds-ledger tickets and print accept/deny threshold curve.

Settle by ticket id, pitcher name+date, or pull K from MLB Stats API when
``pitcher_games`` lags Savant.

Examples:
    python production/grade_odds_ledger.py --settle "Logan Webb,2026-07-29,4"
    python production/grade_odds_ledger.py --close "Logan Webb,2026-07-29,+115,-120"
    python production/grade_odds_ledger.py --curve
    python production/grade_odds_ledger.py --status
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import urlopen

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python.market import bootstrap_mean_ci  # noqa: E402
from Python.odds_ledger import (  # noqa: E402
    LEDGER_PATH,
    apply_close,
    apply_settle,
    apply_void,
    load_ledger,
    run_threshold_curve,
    save_ledger,
    settled_bets,
)


def _parse_settle(raw: str) -> tuple[str, str, float]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        raise SystemExit(f"Bad --settle {raw!r}; expected Name,YYYY-MM-DD,K")
    return parts[0], parts[1], float(parts[2])


def _parse_close(raw: str) -> tuple[str, str, float, float]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise SystemExit(f"Bad --close {raw!r}; expected Name,YYYY-MM-DD,over,under")
    return parts[0], parts[1], float(parts[2]), float(parts[3])


def _find_tickets(ledger: pl.DataFrame, name: str, game_date: str) -> list[dict]:
    key = name.lower()
    hits = ledger.filter(
        (pl.col("game_date").cast(pl.Utf8).str.contains(game_date))
        & (pl.col("player_name").str.to_lowercase().str.contains(key.split()[-1], literal=True))
    )
    return hits.to_dicts()


def _fetch_pitcher_result(game_pk: int, pitcher_id: int) -> dict:
    """Return ``{so, game_final, appeared}`` for ``pitcher_id`` in ``game_pk``.

    ``appeared=False`` with ``game_final=True`` means the game finished but the
    pitcher never recorded a pitching stat line (scratch, rainout/rescheduled
    with a different starter, bullpen game, etc.) — a void, not a pending
    settle that will eventually resolve.
    """
    try:
        with urlopen(
            f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live",
            timeout=20,
        ) as resp:
            feed = json.loads(resp.read().decode())
    except Exception:  # noqa: BLE001
        return {"so": None, "game_final": False, "appeared": False}
    status = feed.get("gameData", {}).get("status", {})
    game_final = str(status.get("abstractGameState") or "") == "Final"
    detailed = str(status.get("detailedState") or "")
    if detailed in {"Postponed", "Cancelled", "Suspended"}:
        return {"so": None, "game_final": True, "appeared": False, "detailed": detailed}
    teams = feed.get("liveData", {}).get("boxscore", {}).get("teams", {})
    for side in ("away", "home"):
        for _, pdata in teams.get(side, {}).get("players", {}).items():
            if int(pdata.get("person", {}).get("id") or 0) != int(pitcher_id):
                continue
            pitching = pdata.get("stats", {}).get("pitching", {})
            so = pitching.get("strikeOuts")
            if so is not None:
                return {"so": float(so), "game_final": game_final, "appeared": True}
            return {"so": None, "game_final": game_final, "appeared": bool(pitching)}
    return {"so": None, "game_final": game_final, "appeared": False}


def _fetch_k_from_api(game_pk: int, pitcher_id: int) -> float | None:
    return _fetch_pitcher_result(game_pk, pitcher_id)["so"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--settle", action="append", default=[], help="Name,date,K")
    p.add_argument("--close", action="append", default=[], help="Name,date,over,under")
    p.add_argument("--curve", action="store_true", help="Print threshold curve on settled bets")
    p.add_argument("--status", action="store_true", help="Summarize ledger")
    p.add_argument("--auto-settle-api", action="store_true", help="Fill missing K via MLB API")
    p.add_argument(
        "--void",
        action="append",
        default=[],
        help="Name,date — mark ticket(s) void/no-action (scratch, PPD, etc.)",
    )
    p.add_argument(
        "--void-scratches",
        action="store_true",
        help=(
            "With --auto-settle-api: auto-void open tickets whose game is Final/"
            "Postponed/Cancelled but the pitcher never recorded a pitching line "
            "(probable-starter scratch) instead of leaving them open forever"
        ),
    )
    args = p.parse_args()

    if not LEDGER_PATH.exists() and not args.status:
        raise SystemExit(f"No ledger at {LEDGER_PATH}. Log quotes first.")

    ledger = load_ledger() if LEDGER_PATH.exists() else pl.DataFrame()

    if args.status or (not args.settle and not args.close and not args.curve and not args.auto_settle_api):
        if ledger.is_empty():
            print("ledger empty")
            return
        print(f"ledger={LEDGER_PATH}  n={ledger.height}")
        if "status" in ledger.columns:
            print(ledger["status"].value_counts())
        settled = settled_bets(ledger)
        if settled.height:
            pnl = float(settled["pnl"].sum())
            print(f"settled={settled.height}  total_pnl=${pnl:+.2f}")
            clvs = [c for c in settled["clv_pp"].to_list() if c is not None]
            if len(clvs) >= 5:
                m, lo, hi = bootstrap_mean_ci([float(x) for x in clvs])
                print(f"mean CLV={m:+.4f}  bootCI=({lo:+.4f},{hi:+.4f})  n_clv={len(clvs)}")
        return

    for raw in args.close:
        name, gdate, over, under = _parse_close(raw)
        tickets = _find_tickets(ledger, name, gdate)
        if not tickets:
            raise SystemExit(f"No ticket for close {raw!r}")
        for t in tickets:
            ledger = apply_close(
                ledger,
                ticket_id=t["ticket_id"],
                close_over=over,
                close_under=under,
            )
            print(f"close set: {t['player_name']} {t['side']} {t['line']}")

    for raw in args.void:
        name, gdate = (p.strip() for p in raw.split(",", 1))
        tickets = _find_tickets(ledger, name, gdate)
        if not tickets:
            raise SystemExit(f"No ticket for void {raw!r}")
        for t in tickets:
            if t.get("status") in {"settled", "void"}:
                print(f"already {t['status']}: {t['ticket_id']}")
                continue
            ledger = apply_void(ledger, ticket_id=t["ticket_id"], reason="manual")
            print(f"voided: {t['player_name']} ({gdate})")

    for raw in args.settle:
        name, gdate, k = _parse_settle(raw)
        tickets = _find_tickets(ledger, name, gdate)
        if not tickets:
            raise SystemExit(f"No ticket for settle {raw!r}")
        for t in tickets:
            if t.get("status") == "settled":
                print(f"already settled: {t['ticket_id']}")
                continue
            ledger = apply_settle(ledger, ticket_id=t["ticket_id"], settle_value=k)
            print(f"settled: {t['player_name']} K={k}")

    if args.auto_settle_api and not ledger.is_empty():
        open_rows = ledger.filter(pl.col("status") == "open")
        for t in open_rows.to_dicts():
            pk, pid = t.get("game_pk"), t.get("pitcher")
            if pk is None or pid is None:
                continue
            res = _fetch_pitcher_result(int(pk), int(pid))
            if res["so"] is not None:
                ledger = apply_settle(ledger, ticket_id=t["ticket_id"], settle_value=res["so"])
                print(f"API settle: {t['player_name']} K={res['so']}")
            elif args.void_scratches and res["game_final"] and not res["appeared"]:
                reason = res.get("detailed") or "scratched"
                ledger = apply_void(ledger, ticket_id=t["ticket_id"], reason=reason)
                print(f"API void ({reason}): {t['player_name']}")

    save_ledger(ledger)

    if args.curve:
        curve = run_threshold_curve(ledger)
        if curve.is_empty():
            print("No settled bets for curve yet.")
            return
        print(curve)
        settled = settled_bets(ledger)
        print(f"n_settled={settled.height}  (exploratory until n>=100 + time-split freeze)")


if __name__ == "__main__":
    main()
