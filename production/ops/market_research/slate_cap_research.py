"""Slate-cap SHADOW research (no live change).

Question: the juiced taken set carries same-game correlation (game_cap:
547 multi-ticket events, 1,683 pairs; slate_shock: 533 games with 2+
tickets, 1,633 pairs). Which cap vehicle, if any, cuts exposure without
cutting the money engine (the 0.12-0.18 edge band = 94% of PnL)?

Shadow only: reads juiced_replay_candidates.parquet (accepted taken rows),
slate_shock_report.json (environment cross-check), and the paid lake for
joins. Writes artifacts/odds_log/slate_cap_report.json and prints it.
Touches no live file (kpi_policy.json, odds_board.py unchanged by design).

Vehicles, each vs uncapped on the SAME taken set (stake_flat1u/pnl_flat1u):
  (a) per-game COUNT cap: keep top-N per event by edge, N = 1,2,3,4.
      N=1 reuses the game_cap_audit vehicle verbatim; N=2,3 confirm its
      menu (cap2 n=1625, cap3 n=1913); N=4 is the extra menu point.
  (b) per-game STAKE cap: per event, keep top-edge tickets while the
      running game stake stays <= $X, for X in 100/150/200. Minimum one
      ticket per game is always kept (fail-safe, documented).
  (c) common-shock FLAG (descriptive, not a cap): tickets on games whose
      evening total >= 9.5 are flagged via the slate_shock_join roster +
      evening-median-total logic; report flagged vs unflagged ROI.

Pre-registered kill rule (in KILL_RULE, echoed into the report): a cap
vehicle SURVIVES only if capped ROI >= full ROI AND the 0.12-0.18 band
share of capped PnL stays >= 90%. The flag vehicle is descriptive and
gets no kill verdict.

Reads: artifacts/odds_log/juiced_replay_candidates.parquet
       artifacts/odds_log/slate_shock_report.json (cross-check only)
       data/Odds-Historical/theoddsapi/book_lines_pitcher.parquet (events)
       data/Odds-Historical/theoddsapi/featured_totals.parquet (totals)
Writes: artifacts/odds_log/slate_cap_report.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util as _ilu
import json
import sys
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src" / "Python"))


def _load(name: str, rel: str):
    mod_path = REPO / rel
    spec = _ilu.spec_from_file_location(name, mod_path)
    assert spec and spec.loader
    mod = _ilu.module_from_spec(spec)
    _spec_loader = spec.loader
    _spec_loader.exec_module(mod)
    return mod


_jk = _load("join_keys", "production/ops/market_research/join_keys.py")
_ssj = _load(
    "slate_shock_join", "production/ops/market_research/slate_shock_join.py"
)

CAND = REPO / "artifacts" / "odds_log" / "juiced_replay_candidates.parquet"
SHOCK = REPO / "artifacts" / "odds_log" / "slate_shock_report.json"
GAME_CAP = REPO / "artifacts" / "odds_log" / "game_cap_report.json"
BOOK_LINES = (
    REPO / "data" / "Odds-Historical" / "theoddsapi" / "book_lines_pitcher.parquet"
)
OUT = REPO / "artifacts" / "odds_log" / "slate_cap_report.json"

COUNT_NS = (1, 2, 3, 4)
STAKE_XS = (100.0, 150.0, 200.0)
HIGH_TOTAL_DEFAULT = 9.5
BAND_LO, BAND_HI = 0.12, 0.18
BAND_FLOOR = 0.90

KILL_RULE = (
    "A cap vehicle SURVIVES only if capped ROI >= full taken ROI "
    "AND the 0.12-0.18 edge-band share of capped PnL stays >= 90%. "
    "Otherwise KILL. The common-shock flag is descriptive (no verdict)."
)


def stats(rows: list[dict]) -> dict:
    n = len(rows)
    stake = sum(float(r["stake_flat1u"] or 0.0) for r in rows)
    pnl = sum(float(r["pnl_flat1u"] or 0.0) for r in rows)
    return {
        "n": n,
        "roi": round(pnl / stake, 4) if stake else None,
        "pnl": round(pnl, 2),
        "wr": round(sum(1 for r in rows if r["won"]) / n, 3) if n else None,
    }


def band_pnl(rows: list[dict]) -> float:
    return sum(
        float(r["pnl_flat1u"] or 0.0)
        for r in rows
        if BAND_LO <= float(r["edge"] or 0.0) < BAND_HI
    )


def band_share(rows: list[dict]) -> float | None:
    pnl = sum(float(r["pnl_flat1u"] or 0.0) for r in rows)
    if pnl <= 0:
        return None
    return round(band_pnl(rows) / pnl, 4)


def verdict(capped: dict, full_roi: float, share: float | None) -> str:
    if (
        capped["roi"] is not None
        and capped["roi"] >= full_roi
        and share is not None
        and share >= BAND_FLOOR
    ):
        return "SURVIVE"
    return "KILL"


def attach_events_gamecap(taken: list[dict]) -> dict[str, list]:
    """Group taken rows by event_id (game_cap_audit join, verbatim logic)."""
    bl = (
        pl.read_parquet(BOOK_LINES)
        .filter(pl.col("market") == "pitcher_strikeouts")
        .select(["event_id", "snapshot", "player", "line"])
        .to_dicts()
    )
    evdate = _jk.load_event_date_map()
    ev_index: dict[tuple, str] = {}
    for r in bl:
        ev_index[
            (
                _jk.sorted_key(r["player"]),
                float(r["line"]),
                evdate.get(str(r["event_id"]), ""),
            )
        ] = str(r["event_id"])
    by_event: dict[str, list] = {}
    unmapped = 0
    for r in taken:
        key = (_jk.sorted_key(r["player_name"]), float(r["line"]), str(r["gd"]))
        ev = ev_index.get(key)
        if ev is None:
            unmapped += 1
            ev = f"unmapped:{key[0]}:{key[1]}:{key[2]}"
        by_event.setdefault(ev, []).append(r)
    return {"by_event": by_event, "unmapped": unmapped}


def attach_totals(taken_df: pl.DataFrame) -> pl.DataFrame:
    """Attach evening median total per event (slate_shock_join logic)."""
    roster, _ = _ssj.build_event_roster()
    totals = pl.scan_parquet(
        REPO / "data" / "Odds-Historical" / "theoddsapi" / "featured_totals.parquet"
    ).collect()
    ev_totals = _ssj.evening_event_totals(totals)
    bridged = taken_df.join(roster, on=["gd", "key"], how="left")
    return bridged.join(ev_totals, on="event_id", how="left")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Shadow slate-cap research: count/stake caps + "
        "common-shock flag on the juiced taken set. No live change."
    )
    ap.add_argument(
        "--high-total",
        type=float,
        default=HIGH_TOTAL_DEFAULT,
        help="Evening-total threshold flagging common-shock games (default 9.5).",
    )
    ap.add_argument(
        "--out",
        type=str,
        default=str(OUT),
        help="Report JSON path (default artifacts/odds_log/slate_cap_report.json).",
    )
    args = ap.parse_args()

    taken_df = pl.read_parquet(CAND).filter(
        pl.col("accepted") & pl.col("side").is_in(["over", "under"])
    )
    taken = taken_df.to_dicts()
    full = stats(taken)
    assert full["roi"] is not None
    full_roi: float = full["roi"]
    full_band = band_pnl(taken)
    full_share = band_share(taken)

    rep: dict = {
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "contract": "Shadow research only. No live change: kpi_policy.json, "
        "odds_board.py, and all live files untouched.",
        "kill_rule": KILL_RULE,
        "taken_n": len(taken),
        "full": {**full, "band_0.12_0.18_pnl": round(full_band, 2),
                 "band_share_of_pnl": full_share},
    }

    # Vehicle (a) + (b): per-game groups via the game_cap_audit event join.
    grp = attach_events_gamecap(taken)
    by_event = grp["by_event"]
    rep["events"] = len(by_event)
    rep["unmapped_tickets"] = grp["unmapped"]

    count_caps = {}
    for n in COUNT_NS:
        kept: list[dict] = []
        for ev, rows in by_event.items():
            if ev.startswith("unmapped") or len(rows) <= n:
                kept.extend(rows)
            else:
                top = sorted(rows, key=lambda r: float(r["edge"] or 0.0),
                             reverse=True)[:n]
                kept.extend(top)
        s = stats(kept)
        share = band_share(kept)
        retained = round(band_pnl(kept) / full_band, 4) if full_band else None
        count_caps[f"top{n}_per_event"] = {
            **s,
            "volume_cut": round(1 - s["n"] / full["n"], 3) if full["n"] else None,
            "roi_delta_capped_minus_full": round(s["roi"] - full_roi, 4)
            if s["roi"] is not None else None,
            "band_share_of_pnl": share,
            "band_pnl_retained": retained,
            "verdict": verdict(s, full_roi, share),
        }
    rep["count_caps"] = count_caps

    stake_caps = {}
    for x in STAKE_XS:
        kept = []
        for ev, rows in by_event.items():
            ordered = sorted(rows, key=lambda r: float(r["edge"] or 0.0),
                             reverse=True)
            run = 0.0
            picked: list[dict] = []
            for r in ordered:
                st = float(r["stake_flat1u"] or 0.0)
                if picked and run + st > x:
                    break
                picked.append(r)
                run += st
                if run >= x:
                    break
            kept.extend(picked)
        s = stats(kept)
        share = band_share(kept)
        retained = round(band_pnl(kept) / full_band, 4) if full_band else None
        stake_caps[f"game_stake_le_{int(x)}"] = {
            **s,
            "volume_cut": round(1 - s["n"] / full["n"], 3) if full["n"] else None,
            "roi_delta_capped_minus_full": round(s["roi"] - full_roi, 4)
            if s["roi"] is not None else None,
            "band_share_of_pnl": share,
            "band_pnl_retained": retained,
            "verdict": verdict(s, full_roi, share),
        }
    rep["stake_caps"] = stake_caps

    # Vehicle (c): common-shock flag via slate_shock_join roster + totals.
    with_total = attach_totals(taken_df)
    rows_all = with_total.to_dicts()
    flagged = [r for r in rows_all
               if r.get("total_line") is not None
               and float(r["total_line"]) >= float(args.high_total)]
    unflagged = [r for r in rows_all
                 if r.get("total_line") is not None
                 and float(r["total_line"]) < float(args.high_total)]
    no_total = [r for r in rows_all if r.get("total_line") is None]
    rep["common_shock_flag"] = {
        "threshold": float(args.high_total),
        "flagged_high_total": {**stats(flagged),
                               "band_share_of_pnl": band_share(flagged)},
        "unflagged_rest": {**stats(unflagged),
                           "band_share_of_pnl": band_share(unflagged)},
        "no_total": stats(no_total),
        "verdict": "DESCRIPTIVE (flag only, never a cap)",
    }

    # Cross-checks against the frozen on-disk reports (exact-match audit).
    try:
        gc = json.loads(GAME_CAP.read_text(encoding="utf-8"))
    except OSError:
        gc = {}
    try:
        sh = json.loads(SHOCK.read_text(encoding="utf-8"))
    except OSError:
        sh = {}
    rep["cross_check"] = {
        "game_cap_report_top1": gc.get("keep_max_edge_per_event"),
        "top1_match": (
            gc.get("keep_max_edge_per_event") == {
                k: count_caps["top1_per_event"][k]
                for k in ("n", "roi", "pnl", "wr")
            }
            if gc.get("keep_max_edge_per_event") else None
        ),
        "slate_shock_high": (sh.get("high_total_split") or {}).get("high"),
        "slate_shock_rest": (sh.get("high_total_split") or {}).get("rest"),
    }

    out_path = Path(args.out)
    out_path.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
