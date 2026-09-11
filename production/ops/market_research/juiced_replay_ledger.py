"""Juiced frozen-model replay: 2025-present open/morning, rejected candidates.

Measurement only. Frozen p_ours_cal. No live policy change.

Decision clock: friend OPEN pair if both sides exist, else paid MORNING pair.
Book pick (realistic): DraftKings else FanDuel else first remaining US book
with a two-way quote. Edge uses multiplicative de-vig (same as the live
board). PnL uses the juiced American on the taken side.

Live policy applied as a FILTER only (floors + 4.5-over veto + 2.5/3.5
probation bump). Four shadow sizing arms on accepted tickets; rejected
rows kept with a reason. 2026 numbers are confirmatory (prior harness
peek) -- do not retune floors from this run.

  python production/ops/market_research/juiced_replay_ledger.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.market import (  # noqa: E402
    DEFAULT_KELLY_FRACTION,
    bet_pnl,
    clv_pp,
    evaluate_side,
    size_in_units,
)
from Python.odds_ledger import atomic_write_parquet, atomic_write_text  # noqa: E402
from join_keys import HIST, ODDS_DIR, load_event_date_map, sorted_key  # noqa: E402

FRIEND = (
    ROOT / "data" / "Odds-Open-Close-2025-2026"
    / "pitcher_strikeouts_early_open_2025_2026.csv"
)
FLOOR_PATH = Path(__file__).with_name("line_floor_policy.json")
PANEL = ODDS_DIR / "universe_panel_live.parquet"
OUT_PARQUET = ODDS_DIR / "juiced_replay_candidates.parquet"
OUT_REPORT = ODDS_DIR / "juiced_replay_report.json"

UNIT = 50.0
LIVE_BASE_FLOOR = 0.12
PROBATION_BUMP = 0.18
BOOK_PREF = {
    "draftkings": 0,
    "fanduel": 1,
    "betmgm": 2,
    "fanatics": 3,
    "bovada": 4,
    "betonlineag": 5,
    "betrivers": 6,
    "williamhill_us": 7,
    "mybookieag": 8,
}

# Pre-registered edge bands for the flat-unit arm (not a live rule).
BANDS = ((0.18, 2.0), (0.12, 1.5), (0.0, 1.0))


def _floors() -> dict[float, float]:
    raw = json.loads(FLOOR_PATH.read_text(encoding="utf-8"))
    return {float(k): float(v) for k, v in raw.get("line_edge_floors", {}).items()}


def _pref(book: str) -> int:
    return int(BOOK_PREF.get(str(book), 99))


def _event_frame(evdate: dict[str, str]) -> pl.DataFrame:
    return pl.DataFrame(
        {"event_id": list(evdate.keys()), "gd": list(evdate.values())}
    )


def _two_way_paid(snapshot: str, ev: pl.DataFrame) -> pl.DataFrame:
    bk = pl.scan_parquet(HIST / "book_lines_pitcher.parquet").filter(
        (pl.col("market") == "pitcher_strikeouts")
        & (pl.col("snapshot") == snapshot)
        & pl.col("line").is_not_null()
        & pl.col("price").is_not_null()
    ).collect()
    bk = bk.join(ev, on="event_id", how="left").filter(
        pl.col("gd").is_not_null() & (pl.col("gd") != "")
    ).with_columns(
        pl.col("player_norm").map_elements(sorted_key, return_dtype=pl.Utf8).alias("key")
    )
    over = bk.filter(pl.col("side") == "over").select(
        ["gd", "key", "line", "book", "event_id", "price"]
    ).rename({"price": "over_amer"})
    under = bk.filter(pl.col("side") == "under").select(
        ["gd", "key", "line", "book", "price"]
    ).rename({"price": "under_amer"})
    pairs = over.join(under, on=["gd", "key", "line", "book"])
    pairs = pairs.with_columns(
        pl.col("book").map_elements(_pref, return_dtype=pl.Int64).alias("pref")
    )
    return (
        pairs.sort(["gd", "key", "line", "pref", "book"])
        .group_by(["gd", "key", "line"], maintain_order=True)
        .first()
        .select(["gd", "key", "line", "book", "event_id", "over_amer", "under_amer"])
        .rename({
            "book": f"{snapshot}_book",
            "event_id": f"{snapshot}_event_id",
            "over_amer": f"{snapshot}_over",
            "under_amer": f"{snapshot}_under",
        })
    )


def _two_way_friend() -> pl.DataFrame:
    if not FRIEND.exists():
        return pl.DataFrame(schema={
            "gd": pl.Utf8, "key": pl.Utf8, "line": pl.Float64,
            "open_book": pl.Utf8, "open_over": pl.Int64, "open_under": pl.Int64,
        })
    fo = pl.read_csv(FRIEND).filter(
        pl.col("over_odds").is_not_null() & pl.col("under_odds").is_not_null()
        & pl.col("line").is_not_null()
    ).with_columns(
        pl.col("game_date").cast(pl.Utf8).alias("gd"),
        pl.col("player_name").map_elements(sorted_key, return_dtype=pl.Utf8).alias("key"),
        pl.col("bookmaker").map_elements(_pref, return_dtype=pl.Int64).alias("pref"),
    )
    return (
        fo.sort(["gd", "key", "line", "pref", "bookmaker"])
        .group_by(["gd", "key", "line"], maintain_order=True)
        .first()
        .select([
            "gd", "key", "line",
            pl.col("bookmaker").alias("open_book"),
            pl.col("over_odds").alias("open_over"),
            pl.col("under_odds").alias("open_under"),
        ])
    )


def live_floor(line: float, side: str, floors: dict[float, float]) -> float:
    fl = float(floors.get(round(float(line), 1), LIVE_BASE_FLOOR))
    if side == "over" and round(float(line), 1) in (2.5, 3.5):
        fl = max(fl, PROBATION_BUMP)
    return fl


def policy_reason(side: str, line: float, edge: float, floors: dict[float, float]) -> str:
    if side == "over" and round(float(line), 1) == 4.5:
        return "veto_4_5_over"
    fl = live_floor(line, side, floors)
    if edge < fl:
        return "below_floor"
    return ""


def band_units(edge: float) -> float:
    for thresh, u in BANDS:
        if float(edge) >= thresh:
            return float(u)
    return 1.0


def size_arms(p_side: float, american: float, edge: float, floor: float) -> dict:
    flat = UNIT
    band = UNIT * band_units(edge)
    live = size_in_units(
        p_side, american, edge=edge, edge_floor=floor, unit_dollars=UNIT,
        kelly_frac=DEFAULT_KELLY_FRACTION,
    )
    # Robust: shrink p 50% toward a coin-flip, then half-size extreme edges.
    p_shrunk = 0.5 * float(p_side) + 0.5 * 0.5
    robust = size_in_units(
        p_shrunk, american, edge=edge, edge_floor=floor, unit_dollars=UNIT,
        kelly_frac=DEFAULT_KELLY_FRACTION,
    )
    r_stake = float(robust["stake"])
    if float(edge) >= 0.20:
        r_stake *= 0.5
    return {
        "stake_flat1u": flat,
        "stake_band": band,
        "stake_kelly": float(live["stake"]),
        "units_kelly": float(live["units"]),
        "stake_robust": r_stake,
    }


def _summarize(rows: list[dict], stake_key: str) -> dict:
    acc = [r for r in rows if r["accepted"] and r.get(stake_key)]
    if not acc:
        return {"n": 0}
    pnl_key = "pnl_" + stake_key.removeprefix("stake_")
    pnl = np.array([r[pnl_key] for r in acc], dtype=float)
    stake = np.array([r[stake_key] for r in acc], dtype=float)
    clv = np.array([r["clv_pp"] for r in acc if r.get("clv_pp") is not None], dtype=float)
    wr = float(np.mean([1.0 if r["won"] else 0.0 for r in acc]))
    out = {
        "n": len(acc),
        "n_reject": int(sum(1 for r in rows if not r["accepted"])),
        "stake_sum": round(float(stake.sum()), 2),
        "pnl": round(float(pnl.sum()), 2),
        "roi": float(pnl.sum() / stake.sum()) if float(stake.sum()) > 0 else None,
        "wr": wr,
        "over_share": float(np.mean([1.0 if r["side"] == "over" else 0.0 for r in acc])),
        "mean_edge": float(np.mean([r["edge"] for r in acc])),
        "n_clv": int(clv.size),
        "mean_clv_pp": float(np.mean(clv)) if clv.size else None,
        "open_share": float(np.mean([1.0 if r["snap"] == "open" else 0.0 for r in acc])),
    }
    return out


def _cell(rows: list[dict], line: float, side: str) -> dict:
    sub = [r for r in rows if r["accepted"] and r["side"] == side
           and round(float(r["line"]), 1) == line]
    skip = [r for r in rows if (not r["accepted"]) and r["side"] == side
            and round(float(r["line"]), 1) == line]
    if not sub:
        return {"n_taken": 0, "n_reject": len(skip)}
    pnl = sum(r["pnl_flat1u"] for r in sub)
    stake = sum(r["stake_flat1u"] for r in sub)
    wr = float(np.mean([1.0 if r["won"] else 0.0 for r in sub]))
    return {
        "n_taken": len(sub),
        "n_reject": len(skip),
        "roi_flat1u": float(pnl / stake) if stake else None,
        "wr": wr,
        "mean_edge": float(np.mean([r["edge"] for r in sub])),
        "pnl_flat1u": round(float(pnl), 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    floors = _floors()
    evdate = load_event_date_map()
    ev = _event_frame(evdate)
    print("attaching paid morning/close two-way pairs...")
    morning = _two_way_paid("morning", ev)
    close = _two_way_paid("close", ev)
    print(f"morning pairs {morning.height} close pairs {close.height}")
    friend = _two_way_friend()
    print(f"friend open pairs {friend.height}")

    env_path = HIST / "snapshot_envelope.parquet"
    invalid = set()
    if env_path.exists():
        env = pl.read_parquet(env_path).filter(
            (pl.col("snapshot") == "close")
            & (pl.col("lag_vendor_vs_commence_sec") < 0)
        )
        invalid = set(env["event_id"].to_list())
        print(f"close_invalid events {len(invalid)}")

    uni = pl.read_parquet(PANEL).filter(
        pl.col("p_ours_cal").is_not_null()
        & pl.col("y").is_not_null()
        & pl.col("p_book_close").is_not_null()
    )
    print(f"universe close-matched {uni.height}")
    j = (
        uni.join(morning, on=["gd", "key", "line"], how="left")
        .join(close, on=["gd", "key", "line"], how="left")
        .join(friend, on=["gd", "key", "line"], how="left")
    )

    rows: list[dict] = []
    for rec in j.iter_rows(named=True):
        pm = float(rec["p_ours_cal"])
        line = float(rec["line"])
        y = float(rec["y"])
        use_open = rec.get("open_over") is not None and rec.get("open_under") is not None
        if use_open:
            snap, book = "open", rec.get("open_book")
            oa, ua = float(rec["open_over"]), float(rec["open_under"])
        elif rec.get("morning_over") is not None and rec.get("morning_under") is not None:
            snap, book = "morning", rec.get("morning_book")
            oa, ua = float(rec["morning_over"]), float(rec["morning_under"])
        else:
            rows.append({
                "gd": rec["gd"], "key": rec["key"], "line": line,
                "accepted": False, "reason": "no_two_way_price",
                "side": "", "edge": None, "snap": None,
            })
            continue
        try:
            over_ev = evaluate_side(pm, oa, ua, "over")
            under_ev = evaluate_side(1.0 - pm, oa, ua, "under")
        except (ValueError, ZeroDivisionError):
            rows.append({
                "gd": rec["gd"], "key": rec["key"], "line": line,
                "accepted": False, "reason": "bad_price",
                "side": "", "edge": None, "snap": snap,
            })
            continue
        best = over_ev if float(over_ev["edge"]) >= float(under_ev["edge"]) else under_ev
        side = str(best["side"])
        edge = float(best["edge"])
        p_side = float(best["p_model"])
        amer = float(best["price_american"])
        reason = policy_reason(side, line, edge, floors)
        accepted = reason == ""
        won = (y == 1.0) if side == "over" else (y == 0.0)
        fl = live_floor(line, side, floors)
        arms = size_arms(p_side, amer, edge, fl) if accepted else {
            "stake_flat1u": 0.0, "stake_band": 0.0,
            "stake_kelly": 0.0, "units_kelly": 0.0, "stake_robust": 0.0,
        }
        # Half-size counterfactual for 2.5/3.5 overs that would have been taken.
        half_ok = (side == "over" and round(line, 1) in (2.5, 3.5) and accepted)
        clv_val = None
        close_invalid = False
        ceid = rec.get("close_event_id")
        if ceid and ceid in invalid:
            close_invalid = True
        if rec.get("close_over") is not None and rec.get("close_under") is not None and not close_invalid:
            try:
                c_over = evaluate_side(pm, float(rec["close_over"]), float(rec["close_under"]), "over")
                p_close = float(c_over["p_market"]) if side == "over" else 1.0 - float(c_over["p_market"])
                p_bet = float(best["p_market"])
                clv_val = clv_pp(p_close, p_bet) * 100.0
            except (ValueError, ZeroDivisionError, TypeError):
                clv_val = None
        row = {
            "gd": rec["gd"], "key": rec["key"], "player_name": rec.get("player_name"),
            "line": line, "side": side, "snap": snap, "book": book,
            "yr": str(rec["gd"])[:4],
            "p_ours_cal": pm, "y": y, "won": bool(won),
            "edge": edge, "price": amer, "p_mkt": float(best["p_market"]),
            "accepted": accepted, "reason": reason or "taken",
            "floor": fl, "close_invalid": close_invalid, "clv_pp": clv_val,
            **arms,
            "pnl_flat1u": bet_pnl(arms["stake_flat1u"], amer, won=won) if accepted else 0.0,
            "pnl_band": bet_pnl(arms["stake_band"], amer, won=won) if accepted else 0.0,
            "pnl_kelly": bet_pnl(arms["stake_kelly"], amer, won=won) if accepted else 0.0,
            "pnl_robust": bet_pnl(arms["stake_robust"], amer, won=won) if accepted else 0.0,
            "half_size_2_5_3_5": half_ok,
        }
        rows.append(row)

    taken = [r for r in rows if r.get("accepted")]
    frame = pl.DataFrame(rows)
    atomic_write_parquet(frame, OUT_PARQUET)

    def year_slice(yr: str | None) -> list[dict]:
        if yr is None:
            return rows
        return [r for r in rows if r.get("yr") == yr]

    # Probation counterfactuals on the SAME accepted-over-else universe:
    # A = live (2.5/3.5 overs taken if they clear floor)
    # B = skip all 2.5/3.5 overs
    # C = take them at 0.5u
    def probation_pack(src: list[dict]) -> dict:
        a = [r for r in src if r.get("accepted")]
        b = [r for r in a if not (
            r["side"] == "over" and round(float(r["line"]), 1) in (2.5, 3.5))]
        def roi(lst: list[dict], stake_mult: dict[str, float] | None = None) -> dict:
            if not lst:
                return {"n": 0}
            pnl = 0.0
            stake = 0.0
            wins = 0
            for r in lst:
                sm = 1.0
                if stake_mult and r["side"] == "over" and round(float(r["line"]), 1) in (2.5, 3.5):
                    sm = stake_mult.get("o2535", 1.0)
                pnl += float(r["pnl_flat1u"]) * sm
                stake += float(r["stake_flat1u"]) * sm
                wins += 1 if r["won"] else 0
            return {
                "n": len(lst),
                "roi": float(pnl / stake) if stake else None,
                "wr": wins / len(lst),
                "pnl": round(pnl, 2),
            }
        return {
            "A_live_take": roi(a),
            "B_skip_2_5_3_5_over": roi(b),
            "C_half_size_2_5_3_5_over": roi(a, {"o2535": 0.5}),
            "cell_2_5_over": _cell(src, 2.5, "over"),
            "cell_3_5_over": _cell(src, 3.5, "over"),
            "cell_2_5_under": _cell(src, 2.5, "under"),
            "cell_3_5_under": _cell(src, 3.5, "under"),
        }

    reasons = {}
    for r in rows:
        k = str(r.get("reason") or "")
        reasons[k] = reasons.get(k, 0) + 1

    n_open = sum(1 for r in taken if r.get("snap") == "open")
    n_morn = sum(1 for r in taken if r.get("snap") == "morning")
    books = {}
    for r in taken:
        b = str(r.get("book") or "")
        books[b] = books.get(b, 0) + 1

    fill_dkfd = []
    for r in rows:
        if r.get("accepted") and r.get("book") not in ("draftkings", "fanduel"):
            rr = dict(r)
            rr["accepted"] = False
            rr["reason"] = "book_not_dk_fd"
            fill_dkfd.append(rr)
        else:
            fill_dkfd.append(r)

    by_book = {}
    for b, _n in sorted(books.items(), key=lambda kv: -kv[1]):
        sub = [r for r in taken if r.get("book") == b]
        pnl = sum(float(r["pnl_flat1u"]) for r in sub)
        stake = sum(float(r["stake_flat1u"]) for r in sub)
        clvs = [r["clv_pp"] for r in sub if r.get("clv_pp") is not None]
        by_book[b] = {
            "n": len(sub),
            "roi": float(pnl / stake) if stake else None,
            "wr": float(np.mean([1.0 if r["won"] else 0.0 for r in sub])),
            "mean_clv_pp": float(np.mean(clvs)) if clvs else None,
            "open_share": float(np.mean([1.0 if r["snap"] == "open" else 0.0 for r in sub])),
        }

    rep = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contract": {
            "model": "frozen p_ours_cal universe_panel_live",
            "edge": "two-way multiplicative de-vig at juiced book pair",
            "decision": "friend open else paid morning",
            "book": "DK else FD else next US book with two-way quote (canonical per owner 2026-09-11)",
            "dk_fd_only": "sensitivity, not the headline",
            "policy": "live floors + 4.5-over veto + 2.5/3.5 probation bump",
            "sizing_arms": ["flat1u", "edge_band", "kelly_1_16", "robust_kelly"],
            "label_2026": "confirmatory -- do not retune live policy",
            "fills": "unmodeled; paper juiced prices",
        },
        "n_candidates": len(rows),
        "n_taken": len(taken),
        "reject_reasons": reasons,
        "taken_by_snap": {"open": n_open, "morning": n_morn},
        "taken_by_book": books,
        "taken_by_book_flat1u": by_book,
        "n_close_invalid_flagged": int(sum(1 for r in rows if r.get("close_invalid"))),
        "n_taken_close_invalid": int(sum(1 for r in taken if r.get("close_invalid"))),
        "all": {
            "flat1u": _summarize(rows, "stake_flat1u"),
            "band": _summarize(rows, "stake_band"),
            "kelly_1_16": _summarize(rows, "stake_kelly"),
            "robust_kelly": _summarize(rows, "stake_robust"),
        },
        "realistic_dk_fd_only": {
            "note": "DK else FD; drop BetRivers/other fallback. Closer to live fill path.",
            "flat1u": _summarize(fill_dkfd, "stake_flat1u"),
            "kelly_1_16": _summarize(fill_dkfd, "stake_kelly"),
        },
        "y2025": {
            "flat1u": _summarize(year_slice("2025"), "stake_flat1u"),
            "kelly_1_16": _summarize(year_slice("2025"), "stake_kelly"),
        },
        "y2026_confirmatory": {
            "flat1u": _summarize(year_slice("2026"), "stake_flat1u"),
            "kelly_1_16": _summarize(year_slice("2026"), "stake_kelly"),
        },
        "probation_2_5_3_5": {
            "all": probation_pack(rows),
            "y2025": probation_pack(year_slice("2025")),
            "y2026_confirmatory": probation_pack(year_slice("2026")),
        },
    }
    atomic_write_text(OUT_REPORT, json.dumps(rep, indent=2, default=str))
    print(json.dumps({
        "n_candidates": rep["n_candidates"],
        "n_taken": rep["n_taken"],
        "reasons": reasons,
        "all_flat1u": rep["all"]["flat1u"],
        "all_kelly": rep["all"]["kelly_1_16"],
        "y2025_flat": rep["y2025"]["flat1u"],
        "y2026_flat": rep["y2026_confirmatory"]["flat1u"],
        "dk_fd_only": rep["realistic_dk_fd_only"]["flat1u"],
        "by_book": by_book,
        "probation_all": rep["probation_2_5_3_5"]["all"],
    }, indent=2, default=str))
    print(f"wrote {OUT_PARQUET}")
    print(f"wrote {OUT_REPORT}")


if __name__ == "__main__":
    main()
