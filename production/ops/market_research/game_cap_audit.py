"""Per-game exposure cap audit on the juiced replay taken set (research).

Question: 533 games carry 2+ tickets (1,633 correlated pairs). What happens
if each game keeps only its best-edge ticket? Pre-registered vehicle:
keep-max-edge-per-event. Kill: capped ROI worse than full taken ROI.
Descriptive for the October slate-cap design; no live change.

Reads: juiced_replay_candidates.parquet + book_lines_pitcher.parquet
Writes: artifacts/odds_log/game_cap_report.json
"""

from __future__ import annotations

import datetime as dt
import importlib.util as _ilu
import json
import sys
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src" / "Python"))

_JK = REPO / "production" / "ops" / "market_research" / "join_keys.py"
_spec = _ilu.spec_from_file_location("join_keys", _JK)
assert _spec and _spec.loader
_jk = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_jk)

CAND = REPO / "artifacts" / "odds_log" / "juiced_replay_candidates.parquet"
OUT = REPO / "artifacts" / "odds_log" / "game_cap_report.json"


def roi(rows: list[dict]) -> dict:
    n = len(rows)
    stake = sum(float(r["stake_flat1u"] or 0.0) for r in rows)
    pnl = sum(float(r["pnl_flat1u"] or 0.0) for r in rows)
    return {"n": n, "roi": round(pnl / stake, 4) if stake else None,
            "pnl": round(pnl, 2),
            "wr": round(sum(1 for r in rows if r["won"]) / n, 3) if n else None}


def main() -> None:
    taken = (
        pl.read_parquet(CAND)
        .filter(pl.col("accepted") & pl.col("side").is_in(["over", "under"]))
        .to_dicts()
    )
    bl = (
        pl.read_parquet(REPO / "data" / "Odds-Historical" / "theoddsapi" / "book_lines_pitcher.parquet")
        .filter(pl.col("market") == "pitcher_strikeouts")
        .select(["event_id", "snapshot", "player", "line"])
        .to_dicts()
    )
    evdate = _jk.load_event_date_map()
    ev_index: dict[tuple, str] = {}
    for r in bl:
        ev_index[(_jk.sorted_key(r["player"]), float(r["line"]),
                  evdate.get(str(r["event_id"]), ""))] = str(r["event_id"])
    # attach event_id to taken tickets (same join as the confounder audit)
    by_event: dict[str, list] = {}
    unmapped = 0
    for r in taken:
        key = (_jk.sorted_key(r["player_name"]), float(r["line"]), str(r["gd"]))
        ev = ev_index.get(key)
        if ev is None:
            unmapped += 1
            ev = f"unmapped:{key[0]}:{key[1]}:{key[2]}"
        by_event.setdefault(ev, []).append(r)

    multi = {e: v for e, v in by_event.items() if len(v) > 1 and not e.startswith("unmapped")}
    pairs = sum(len(v) * (len(v) - 1) // 2 for v in multi.values())
    capped = []
    for ev, rows in by_event.items():
        if ev.startswith("unmapped") or len(rows) == 1:
            capped.extend(rows)
        else:
            capped.append(max(rows, key=lambda r: float(r["edge"] or 0.0)))

    full, cap = roi(taken), roi(capped)
    rep = {
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "taken_n": len(taken),
        "events": len(by_event),
        "multi_ticket_events": len(multi),
        "correlated_pairs": pairs,
        "unmapped_tickets": unmapped,
        "full": full,
        "keep_max_edge_per_event": cap,
        "volume_cut": round(1 - cap["n"] / full["n"], 3),
        "roi_delta_capped_minus_full": round(cap["roi"] - full["roi"], 4)
        if cap["roi"] is not None and full["roi"] is not None else None,
        "kill": "SURVIVE (measure further)"
        if cap["roi"] is not None and full["roi"] is not None and cap["roi"] >= full["roi"]
        else "KILL (cap costs ROI — correlation is real but cutting hurts)",
    }
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
