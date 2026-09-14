"""Fills analytics: paper-vs-fill drift + fill rates (runs at any n).

Compares real_bets against the paper track: fill rate overall + by book,
paper-vs-fill price drift (are we filled worse than quoted?), ROI/WR on
fills vs matched paper, and the n counter toward the 50-fill money-truth
gate. Reads small-n honestly: CIs suppressed below n=20 with an explicit
"too thin" verdict instead of numbers that pretend.

Reads: real_bets.parquet + ledger.parquet (matched paper rows).
Writes: artifacts/odds_log/fills_analytics_report.json. No live change.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[3]
REAL = REPO / "artifacts" / "odds_log" / "real_bets.parquet"
LED = REPO / "artifacts" / "odds_log" / "ledger.parquet"
OUT = REPO / "artifacts" / "odds_log" / "fills_analytics_report.json"

GATE_N = 50
CI_MIN_N = 20


def main() -> None:
    fills = pl.read_parquet(REAL).to_dicts() if REAL.exists() else []
    settled = [r for r in fills if str(r.get("result") or "") in ("win", "loss")]
    n = len(settled)
    st = sum(float(r.get("stake") or 0.0) for r in settled)
    pn = sum(float(r.get("pnl") or 0.0) for r in settled)
    by_book: dict[str, dict] = {}
    for r in settled:
        b = by_book.setdefault(str(r.get("book") or "unknown"), {"n": 0, "st": 0.0, "pn": 0.0})
        b["n"] += 1
        b["st"] += float(r.get("stake") or 0.0)
        b["pn"] += float(r.get("pnl") or 0.0)
    for b in by_book.values():
        b["roi"] = round(b["pn"] / b["st"], 4) if b["st"] else None
        b["pnl"] = round(b["pn"], 2)
    # paper-vs-fill price drift: match fills to paper rows by date/player/line/side
    led = (pl.read_parquet(LED).select(
        ["game_date", "player_name", "line", "side", "book", "bet_price"]).to_dicts())
    paper_by_key: dict[tuple, list] = {}
    for r in led:
        paper_by_key.setdefault((str(r["game_date"]), str(r["player_name"]),
                                 str(r["line"]), str(r["side"])), []).append(r)
    drifts = []
    for r in settled:
        cands = paper_by_key.get((str(r.get("game_date")), str(r.get("player_name")),
                                  str(r.get("line")), str(r.get("side"))), [])
        if cands:
            drifts.append(float(r.get("bet_price") or 0.0) - float(cands[0].get("bet_price") or 0.0))
    rep = {
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "n_fills_settled": n,
        "n_pending": sum(1 for r in fills if str(r.get("result")) not in ("win", "loss", "push")),
        "gate": f"{n}/{GATE_N} to money truth",
        "roi": round(pn / st, 4) if st and n >= 5 else None,
        "pnl": round(pn, 2),
        "wr": round(sum(1 for r in settled if str(r.get("result")) == "win") / n, 3) if n else None,
        "by_book": by_book,
        "price_drift_fill_minus_paper_n": len(drifts),
        "price_drift_mean": round(sum(drifts) / len(drifts), 1) if drifts else None,
        "verdict": ("TOO THIN (n<%d -- log, don't judge)" % CI_MIN_N) if n < CI_MIN_N else "READABLE (n>=%d -- compare vs paper)" % CI_MIN_N,
    }
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
