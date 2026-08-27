"""Settle odds-ledger tickets and print accept/deny threshold curve.

Settle by ticket id, pitcher name+date, or pull K from MLB Stats API when
``pitcher_games`` lags Savant.

Examples:
    python production/odds/grade_odds_ledger.py --settle "Logan Webb,2026-07-29,4"
    python production/odds/grade_odds_ledger.py --close "Logan Webb,2026-07-29,+115,-120"
    python production/odds/grade_odds_ledger.py --curve
    python production/odds/grade_odds_ledger.py --status
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Windows cp1252 consoles cannot encode polars' box-drawing characters; force
# UTF-8 output so the threshold curve / reports never crash on print.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

from Python.market import bet_pnl, bootstrap_mean_ci  # noqa: E402
from Python.odds_ledger import (  # noqa: E402
    LEDGER_PATH,
    apply_close,
    apply_settle,
    apply_void,
    dedupe_ledger_props,
    load_ledger,
    run_threshold_curve,
    save_ledger,
    settled_bets,
)

GATE_NEXT_N_PATH = LEDGER_PATH.parent / "gate_next_n_comparison.parquet"


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
    """Return settle stat bundle for ``pitcher_id`` in ``game_pk``.

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
            ip_raw = pitching.get("inningsPitched")
            ip = None
            outs = None
            if ip_raw is not None:
                try:
                    ip_str = str(ip_raw)
                    ip = float(ip_str)
                    whole, frac = ip_str.split(".", 1) if "." in ip_str else (ip_str, "0")
                    outs = int(whole) * 3 + int(frac)
                except Exception:  # noqa: BLE001
                    ip = None
                    outs = None
            h_allowed = pitching.get("hits")
            bb_allowed = pitching.get("baseOnBalls")
            if so is not None:
                return {
                    "so": float(so),
                    "ip": float(ip) if ip is not None else None,
                    "outs": float(outs) if outs is not None else None,
                    "hits_allowed": float(h_allowed) if h_allowed is not None else None,
                    "walks_allowed": float(bb_allowed) if bb_allowed is not None else None,
                    "game_final": game_final,
                    "appeared": True,
                }
            return {"so": None, "game_final": game_final, "appeared": bool(pitching)}
    return {"so": None, "game_final": game_final, "appeared": False}


def _fetch_k_from_api(game_pk: int, pitcher_id: int) -> float | None:
    return _fetch_pitcher_result(game_pk, pitcher_id)["so"]


def _write_gate_next_n_artifact(ledger: pl.DataFrame, *, next_n: int) -> None:
    """Write baseline-vs-gated comparison snapshot for latest settled window."""
    settled = settled_bets(ledger)
    if settled.is_empty():
        return

    # One row per prop in analysis artifacts; keep this consistent with curve/CLV views.
    settled = dedupe_ledger_props(settled)
    if settled.is_empty():
        return

    time_col = "closed_at_utc" if "closed_at_utc" in settled.columns else "logged_at_utc"
    if time_col in settled.columns:
        settled = settled.with_columns(
            pl.col(time_col).cast(pl.Utf8).fill_null("").alias("_sort_ts")
        ).sort("_sort_ts")
    window = settled.tail(max(1, int(next_n)))

    with_flags = window.with_columns(
        pl.col("note")
        .cast(pl.Utf8)
        .fill_null("")
        .str.contains("quality_gate_hold=")
        .alias("is_gated_hold"),
        pl.col("stake").cast(pl.Float64).fill_null(0.0).alias("_stake"),
        pl.col("unit_dollars").cast(pl.Float64).fill_null(0.0).alias("_unit"),
        pl.col("bet_price").cast(pl.Float64).fill_null(0.0).alias("_price"),
        pl.col("pnl").cast(pl.Float64).fill_null(0.0).alias("_actual_pnl"),
        pl.col("result").cast(pl.Utf8).fill_null("").alias("_result"),
    )

    rows = with_flags.select(
        ["is_gated_hold", "_stake", "_unit", "_price", "_actual_pnl", "_result"]
    ).to_dicts()
    baseline_pnls: list[float] = []
    baseline_stakes: list[float] = []
    for r in rows:
        stake = float(r["_stake"])
        result = str(r["_result"])
        won = result == "win"
        if bool(r["is_gated_hold"]):
            # Counterfactual: if the gate had not held this ticket, stake one unit.
            stake = float(r["_unit"])
        baseline_stakes.append(stake)
        baseline_pnls.append(float(bet_pnl(stake, float(r["_price"]), won=won)))

    actual_stake_sum = float(with_flags["_stake"].sum())
    actual_pnl_sum = float(with_flags["_actual_pnl"].sum())
    baseline_stake_sum = float(sum(baseline_stakes))
    baseline_pnl_sum = float(sum(baseline_pnls))
    n_held = int(with_flags.filter(pl.col("is_gated_hold")).height)

    led_bytes = LEDGER_PATH.read_bytes() if LEDGER_PATH.exists() else b""
    ledger_sha = hashlib.sha256(led_bytes).hexdigest() if led_bytes else None
    first_date = (
        str(with_flags["game_date"][0])
        if "game_date" in with_flags.columns and with_flags.height
        else None
    )
    last_date = (
        str(with_flags["game_date"][-1])
        if "game_date" in with_flags.columns and with_flags.height
        else None
    )

    snapshot = pl.DataFrame(
        [
            {
                "snapshot_utc": datetime.now(timezone.utc).isoformat(),
                "ledger_sha256": ledger_sha,
                "window_n": int(with_flags.height),
                "window_target_n": int(next_n),
                "window_first_game_date": first_date,
                "window_last_game_date": last_date,
                "n_gate_holds": n_held,
                "n_actual_bets": int(with_flags.height - n_held),
                "actual_stake_sum": actual_stake_sum,
                "actual_pnl_sum": actual_pnl_sum,
                "actual_roi": (actual_pnl_sum / actual_stake_sum) if actual_stake_sum > 0 else None,
                "baseline_stake_sum": baseline_stake_sum,
                "baseline_pnl_sum": baseline_pnl_sum,
                "baseline_roi": (baseline_pnl_sum / baseline_stake_sum)
                if baseline_stake_sum > 0
                else None,
                "gate_pnl_delta": actual_pnl_sum - baseline_pnl_sum,
            }
        ]
    )

    if GATE_NEXT_N_PATH.exists():
        hist = pl.read_parquet(GATE_NEXT_N_PATH)
        out = pl.concat([hist, snapshot], how="diagonal_relaxed")
        if "ledger_sha256" in out.columns:
            out = out.unique(subset=["ledger_sha256", "window_target_n"], keep="last")
    else:
        out = snapshot
    out.write_parquet(GATE_NEXT_N_PATH)
    print(
        f"wrote {GATE_NEXT_N_PATH.name} "
        f"(latest window_n={with_flags.height}, n_gate_holds={n_held})"
    )


def _status_counts_ascii(ledger: pl.DataFrame) -> list[str]:
    """Return plain ASCII status-count lines for robust terminal output."""
    counts = (
        ledger.group_by("status")
        .agg(pl.len().alias("count"))
        .sort("count", descending=True)
        .to_dicts()
    )
    return [f"status={r['status']} count={int(r['count'])}" for r in counts]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--settle", action="append", default=[], help="Name,date,K")
    p.add_argument("--close", action="append", default=[], help="Name,date,over,under")
    p.add_argument("--curve", action="store_true", help="Print threshold curve on settled bets")
    p.add_argument("--status", action="store_true", help="Summarize ledger")
    p.add_argument("--auto-settle-api", action="store_true", help="Fill missing K via MLB API")
    p.add_argument(
        "--gate-next-n",
        type=int,
        default=100,
        help=(
            "Window size for baseline-vs-gated artifact over latest settled props; "
            "written to artifacts/odds_log/gate_next_n_comparison.parquet"
        ),
    )
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

    did_status_only = (
        not args.settle
        and not args.close
        and not args.curve
        and not args.auto_settle_api
        and not args.void
    )
    if args.status or did_status_only:
        if ledger.is_empty():
            print("ledger empty")
            if did_status_only:
                return
        else:
            print(f"ledger={LEDGER_PATH}  n={ledger.height}")
            if "status" in ledger.columns:
                for line in _status_counts_ascii(ledger):
                    print(line)
            settled = settled_bets(ledger)
            if settled.height:
                pnl = float(settled["pnl"].sum())
                print(f"settled={settled.height}  total_pnl=${pnl:+.2f}")
                clvs = [c for c in settled["clv_pp"].to_list() if c is not None]
                if len(clvs) >= 5:
                    m, lo, hi = bootstrap_mean_ci([float(x) for x in clvs])
                    print(f"mean CLV={m:+.4f}  bootCI=({lo:+.4f},{hi:+.4f})  n_clv={len(clvs)}")
        if did_status_only:
            _write_gate_next_n_artifact(ledger, next_n=max(1, int(args.gate_next_n)))
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
            ledger = apply_settle(
                ledger,
                ticket_id=t["ticket_id"],
                settle_value=k,
                settle_context={"strikeouts": k},
            )
            print(f"settled: {t['player_name']} K={k}")

    if args.auto_settle_api and not ledger.is_empty():
        open_rows = ledger.filter(pl.col("status") == "open")
        for t in open_rows.to_dicts():
            pk, pid = t.get("game_pk"), t.get("pitcher")
            if pk is None or pid is None:
                continue
            res = _fetch_pitcher_result(int(pk), int(pid))
            if res["so"] is not None:
                ledger = apply_settle(
                    ledger,
                    ticket_id=t["ticket_id"],
                    settle_value=res["so"],
                    settle_context={
                        "ip": res.get("ip"),
                        "outs": res.get("outs"),
                        "hits_allowed": res.get("hits_allowed"),
                        "walks_allowed": res.get("walks_allowed"),
                        "strikeouts": res.get("so"),
                    },
                )
                print(f"API settle: {t['player_name']} K={res['so']}")
            elif args.void_scratches and res["game_final"] and not res["appeared"]:
                reason = res.get("detailed") or "scratched"
                ledger = apply_void(ledger, ticket_id=t["ticket_id"], reason=reason)
                print(f"API void ({reason}): {t['player_name']}")

    save_ledger(ledger)
    _write_gate_next_n_artifact(ledger, next_n=max(1, int(args.gate_next_n)))

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
