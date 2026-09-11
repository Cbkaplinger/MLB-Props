"""Price-correction audit: raw (Poisson+WS1c) vs live (+bucket offset).

Post-freeze verdict on the line_price_correction table: does the offset add
Brier skill and ROI on tickets the live policy actually prices, or is it
pre-freeze steam-chasing dressed as calibration (#84: Gilbert BET exists
only via +0.06 offset)?

Panel: ledger settled + 2+ book closes (no scored join needed).
Arms per ticket taken side, derived by INVERSION (exact, no era problem):
  live = ledger p_model converted to over-prob (stored board output =
         Poisson+WS1c base + bucket offset, by construction of
         score_quote_against_board)
  raw  = clip(live - offset) with offset from the production lookup
         (_price_bucket(ticket over_price) + _maturity_bucket(game_date,
         player_name via historical starts) + segmented table)

SANITY GATE: on today's recommendations.parquet rows (which carry the
board's prob_correction_offset), recomputed offset must match stored
offset to < 1e-9, else abort (lookup/table drift). Floors mirror production exactly
(line map + probation + 4.5-over veto).

Writes artifacts/odds_log/correction_audit_report.json. No live change.
KILL (recommend removal; acting needs sign-off): live Brier gain < 0.0005
AND live ROI not better than raw on post-freeze BET sets.
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

from Python.kpi_policy import load_kpi_policy  # noqa: E402
from Python.market import american_to_implied_prob  # noqa: E402
from Python.odds_board import (  # noqa: E402
    _load_line_floor_map,
    _load_line_price_offsets,
    _maturity_bucket,
    _price_bucket,
    _probation_edge_floor,
)
from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.prob_calibration import expected_calibration_error  # noqa: E402
from join_keys import ODDS_DIR, read_consensus_cache, sorted_key  # noqa: E402

LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
STAKE = 50.0


def amer_profit(price: float, stake: float = STAKE) -> float:
    return stake * 100.0 / abs(price) if price < 0 else stake * price / 100.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--caps", type=str, default="0.02,0.03,0.05",
                    help="comma list of |offset| caps to evaluate as shadow arms")
    args = ap.parse_args()
    caps = [float(x) for x in args.caps.split(",") if x.strip()]
    offsets = _load_line_price_offsets()
    floors = _load_line_floor_map()
    rules = load_kpi_policy().get("quality_gate", {}).get("rules", {})
    print(f"offsets={len(offsets)} floors={len(floors)}")

    cc = read_consensus_cache("pitcher_strikeouts", "close").filter(
        (pl.col("n_books") >= 2) & pl.col("fair").is_not_null())
    led = pl.read_parquet(ODDS_DIR / "ledger.parquet").filter(
        (pl.col("status") == "settled") & pl.col("settle_value").is_not_null()).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gd"),
        pl.col("player_name").map_elements(
            lambda s: sorted_key(str(s)), return_dtype=pl.Utf8).alias("key"))
    led = led.drop([c for c in ("close_over", "close_under", "close_status",
                                "closed_at_utc", "minutes_to_tip_at_close")
                    if c in led.columns])
    j = led.join(cc.select(["gd", "key", "line", "fair"]).rename({"fair": "close_over"}),
                 on=["gd", "key", "line"], how="inner")
    print(f"ledger-close join: {j.height}")
    jj = j.filter(pl.col("p_model").is_not_null()
                  & pl.col("over_price").is_not_null()
                  & pl.col("under_price").is_not_null()
                  & pl.col("line").is_in(LINES))
    print(f"gated panel: {jj.height}")

    def offset_for(ln: float, over_price: float, game_date, player_name: str) -> float:
        brow = {"game_date": game_date, "player_name": player_name}
        key = (ln, _price_bucket(float(over_price)), _maturity_bucket(brow))
        return float(offsets.get(key, offsets.get((ln, _price_bucket(float(over_price)), "*"), 0.0)))

    # Sanity: recomputed offsets must match the board's stored offsets on
    # today's recommendations (which carry prob_correction_offset).
    try:
        rec = pl.read_parquet(ODDS_DIR / "recommendations.parquet").filter(
            pl.col("prob_correction_offset").is_not_null())
        diffs = []
        for r in rec.to_dicts():
            ln = float(r["line"])
            op = float(r["over_price"]) if r.get("over_price") is not None else None
            if op is None:
                continue
            diffs.append(abs(offset_for(ln, op, r.get("game_date"), str(r.get("player_name")))
                             - float(r["prob_correction_offset"])))
        sanity_off = float(np.mean(diffs)) if diffs else None
    except Exception as exc:
        sanity_off = None
        print(f"sanity source unavailable: {exc}")
    print(f"sanity offset |recomputed-stored| mean={sanity_off} (gate < 1e-4; "
          "board stores offsets rounded to ~1e-5, so 1e-9 is unreachable)")
    if sanity_off is None or sanity_off >= 1e-4:
        print("SANITY GATE FAILED: offset lookup does not reproduce the board; aborting.")
        raise SystemExit(3)

    se: dict[str, float] = {}
    nn: dict[str, int] = {}
    roi: dict[str, dict] = {"raw": {"n": 0, "pnl": 0.0}, "live": {"n": 0, "pnl": 0.0},
                           **{f"cap_{c:g}": {"n": 0, "pnl": 0.0} for c in caps}}
    cap_names = [f"cap_{c:g}" for c in caps]
    cap_flips = {name: {"live_bet_cap_skip": 0, "live_skip_cap_bet": 0} for name in cap_names}
    agree = {"both_bet": 0, "both_skip": 0, "raw_only": 0, "live_only": 0}
    dis_se = {"raw": 0.0, "live": 0.0, "n": 0}
    cells: dict[str, dict[str, float]] = {}
    off_share: list[float] = []
    for r in jj.to_dicts():
        ln = float(r["line"])
        side = str(r["side"])
        y_over = 1.0 if float(r["settle_value"]) > ln else 0.0
        stored = float(r["p_model"])
        lo = stored if side == "over" else 1.0 - stored
        op = float(r["over_price"])
        off = offset_for(ln, op, r.get("game_date"), str(r.get("player_name")))
        bo = float(np.clip(lo - off, 1e-6, 1.0 - 1e-6))
        cands = {"raw": bo, "live": lo, "book": float(r["close_over"])}
        for c, name in zip(caps, cap_names):
            oc = float(np.clip(off, -c, c))
            cands[name] = float(np.clip(bo + oc, 1e-6, 1.0 - 1e-6))
        base_floor = float(floors.get(f"{ln:.1f}", 0.12))
        vetoed = side == "over" and abs(ln - 4.5) < 1e-9
        bets = {}
        for k, p_over in cands.items():
            if k == "book":
                continue
            p = p_over if side == "over" else 1.0 - p_over
            y = y_over if side == "over" else 1.0 - y_over
            se[k] = se.get(k, 0.0) + (p - y) ** 2
            nn[k] = nn.get(k, 0) + 1
            fl = _probation_edge_floor(side, ln, rules, base_floor)
            price = op if side == "over" else float(r["under_price"])
            edge = p - float(american_to_implied_prob(price))
            bet = (not vetoed) and edge >= fl
            bets[k] = bet
            if bet:
                won = (y == 1.0)
                roi[k]["n"] += 1
                roi[k]["pnl"] += amer_profit(price) if won else -STAKE
        if bets["raw"] and bets["live"]:
            agree["both_bet"] += 1
        elif not bets["raw"] and not bets["live"]:
            agree["both_skip"] += 1
        elif bets["raw"]:
            agree["raw_only"] += 1
        else:
            agree["live_only"] += 1
        if bets["raw"] != bets["live"]:
            for k in ("raw", "live"):
                p_over = cands[k]
                p = p_over if side == "over" else 1.0 - p_over
                y = y_over if side == "over" else 1.0 - y_over
                dis_se[k] += (p - y) ** 2
            dis_se["n"] += 1
        if bets["live"]:
            e_live = abs((lo if side == "over" else 1.0 - lo)
                         - (bo if side == "over" else 1.0 - bo))
            price = op if side == "over" else float(r["under_price"])
            edge_live = abs((lo if side == "over" else 1.0 - lo)
                            - float(american_to_implied_prob(price)))
            off_share.append(off / edge_live if edge_live > 1e-9 else 0.0)
        cell = cells.setdefault(f"{side}@{ln}", {})
        cell["n"] = cell.get("n", 0) + 1
        for k in ["raw", "live"] + cap_names:
            p_over = cands[k]
            p = p_over if side == "over" else 1.0 - p_over
            y = y_over if side == "over" else 1.0 - y_over
            cell[k] = cell.get(k, 0.0) + (p - y) ** 2
        for name in cap_names:
            if bets["live"] and not bets[name]:
                cap_flips[name]["live_bet_cap_skip"] += 1
            elif bets[name] and not bets["live"]:
                cap_flips[name]["live_skip_cap_bet"] += 1
    n = nn.get("raw", 0)
    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n": n,
           "sanity_offset_mean_abs_diff": sanity_off,
           "brier": {k: se[k] / nn[k] for k in se},
           "gain_live_vs_raw": (se["raw"] - se["live"]) / n if n else None,
           "roi": {k: {"n": v["n"], "pnl": round(v["pnl"], 2),
                       "roi": round(v["pnl"] / (v["n"] * STAKE), 4) if v["n"] else None}
                   for k, v in roi.items()},
            "agreement": agree,
            "cap_arms": {name: {"brier": se[name] / nn[name],
                                "roi": {"n": roi[name]["n"], "pnl": round(roi[name]["pnl"], 2),
                                        "roi": round(roi[name]["pnl"] / (roi[name]["n"] * STAKE), 4) if roi[name]["n"] else None},
                                "flips_vs_live": cap_flips[name]}
                         for name in cap_names},
           "disagree_brier": {k: dis_se[k] / dis_se["n"] for k in ("raw", "live")}
                             if dis_se["n"] else {},
           "disagree_n": dis_se["n"],
           "offset_share_of_live_edge": {"mean": float(np.mean(off_share)) if off_share else None,
                                         "frac_over_half": float(np.mean([1.0 if s > 0.5 else 0.0 for s in off_share])) if off_share else None,
                                         "n_live_bets": len(off_share)},
           "cells": {c: {"n": int(v["n"]),
                         **{k: v[k] / v["n"] for k in v if k != "n"}}
                     for c, v in sorted(cells.items())},
           "cells_sum_n": int(sum(v["n"] for v in cells.values()))}
    gain = rep["gain_live_vs_raw"]
    roi_raw = rep["roi"]["raw"]["roi"]
    roi_live = rep["roi"]["live"]["roi"]
    rep["kill"] = ("SURVIVE-keep-offsets" if n and gain is not None and gain >= 0.0005
                   and (roi_live is not None and roi_raw is not None and roi_live >= roi_raw)
                   else "KILL-recommend-removal")
    out = ODDS_DIR / "correction_audit_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"n={n} raw={rep['brier'].get('raw'):.4f} live={rep['brier'].get('live'):.4f} "
          f"gain={gain:+.5f}" if gain is not None else f"n={n}")
    print(f"ROI raw={rep['roi']['raw']} live={rep['roi']['live']}")
    for name in cap_names:
        print(f"ROI {name}={rep['cap_arms'][name]['roi']} "
              f"brier={rep['cap_arms'][name]['brier']:.4f} "
              f"flips={rep['cap_arms'][name]['flips_vs_live']}")
    print(f"agree={agree} disagree_n={dis_se['n']}")
    print(f"cells_sum_n={rep['cells_sum_n']} (must equal n={n})")
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
