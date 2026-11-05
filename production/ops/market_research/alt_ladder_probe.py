"""Alt-ladder probe (descriptive, no live change).

Sibling to alt_curve_measure.py using the SAME inputs, SAME frozen live
config (Poisson + WS1c, nearest-map outside 2.5-9.5), and SAME book join
(main-market over closes, median across books) so every row below sits on
the same subsets as alt_curve_report.json. Same-subset comparisons only:
over vs under outcome rates at one line share the exact same starts; do
not compare ROI across lines with different n as if they were one pool.

ONE new table: per-line per-side blind economics at flat $50 on book alt
closes where coverage exists. Book alt is over-only and vig-loaded (no
devig possible -- labeled on every row). Over legs have a real book price
so ROI is measurable. Under legs have NO book price at any alt line, so
under ROI is null by construction; the under outcome win rate is shown
price-free (needs no price) purely to document what an under leg would
have needed to beat.

Pre-registered kill rule (ladder legs are OFF-GRID rungs -- lines outside
the main 2.5-9.5 grid a pitcher is priced at; in-grid lines are the main
line itself, not ladder legs):
  OVER  SURVIVE iff some off-grid line has n >= 100 AND its blind-over
        ROI beats the best in-grid (2.5-9.5, n >= 100) blind-over ROI
        (the single best-edge line sizing would just take). Else KILL.
  UNDER SURVIVE iff some off-grid line has n >= 100 AND a priced under
        leg beats the same benchmark. With an over-only book this is
        impossible. Else KILL.

Reads: historical_scores, L3 actuals, book_lines_pitcher closes.
Writes: artifacts/odds_log/alt_ladder_report.json. No live change.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util as _ilu
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import polars as pl

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

from Python.count_layer import p_strikeouts_ge  # noqa: E402
from Python.market import american_to_implied_prob, bet_pnl  # noqa: E402

_JK = REPO / "production" / "ops" / "market_research" / "join_keys.py"
_spec = _ilu.spec_from_file_location("join_keys", _JK)
assert _spec and _spec.loader
_jk = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_jk)

SCORED = REPO / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
L3 = REPO / "data" / "processed" / "pitcher_training.parquet"
CALIB = REPO / "artifacts" / "models" / "prob_calibration_ws1c_platt_20260910_012559.joblib"
OUT = REPO / "artifacts" / "odds_log" / "alt_ladder_report.json"

ALT_LINES = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5, 14.5]
MAIN_GRID = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
MAIN_MAP = {"2_5": 2.5, "3_5": 3.5, "4_5": 4.5, "5_5": 5.5,
            "6_5": 6.5, "7_5": 7.5, "8_5": 8.5, "9_5": 9.5}
UNIT = 50.0
MIN_N = 100


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()

    bundle = joblib.load(CALIB)
    maps = {ln: bundle.line_maps[k] for k, ln in MAIN_MAP.items()}

    def cal(kr: float, tbf: float, ln: float) -> float:
        raw = float(p_strikeouts_ge(ln, k_rate=np.array([kr]),
                                    projected_tbf=np.array([tbf]), family="poisson")[0])
        anchor = min(MAIN_MAP.values(), key=lambda m: abs(m - ln))
        return float(maps[anchor].transform(np.array([raw]))[0])

    sc = (pl.scan_parquet(SCORED).select(
        ["game_pk", "pitcher_name", "game_date", "k_rate_pred", "projected_tbf"])
        .collect().to_dicts())
    actual: dict[tuple, float] = {}
    for r in pl.read_parquet(L3).select(["game_date", "pitcher_name", "K"]).to_dicts():
        actual[(str(r["game_date"])[:10], _jk.sorted_key(r["pitcher_name"]))] = float(r["K"])

    evdate = _jk.load_event_date_map()
    book_p: dict[tuple, list[float]] = {}
    book_px: dict[tuple, list[float]] = {}
    for r in (pl.read_parquet(REPO / "data" / "Odds-Historical" / "theoddsapi" / "book_lines_pitcher.parquet")
              .filter((pl.col("market") == "pitcher_strikeouts") & (pl.col("snapshot") == "close"))
              .to_dicts()):
        if r.get("side") != "over":
            continue
        try:
            ln = float(r["line"])
            px = float(r["price"])
            p = american_to_implied_prob(px)
        except (TypeError, ValueError):
            continue
        key = (evdate.get(str(r["event_id"]), ""), _jk.sorted_key(r["player"]), ln)
        book_p.setdefault(key, []).append(p)
        book_px.setdefault(key, []).append(px)
    book_med = {k: sorted(v)[len(v) // 2] for k, v in book_p.items()}
    book_medx = {k: sorted(v)[len(v) // 2] for k, v in book_px.items()}

    per_line: dict[str, dict] = {}
    pool_pnl = 0.0
    pool_stake = 0.0
    for ln in ALT_LINES:
        n = 0
        over_w = 0
        under_w = 0
        pnl = 0.0
        edge_sum = 0.0
        px_list: list[float] = []
        for s in sc:
            try:
                kr = float(np.clip(float(s["k_rate_pred"]), 0.02, 0.5))
                tbf = float(s["projected_tbf"])
            except (TypeError, ValueError):
                continue
            gd = str(s["game_date"])[:10]
            skey = _jk.sorted_key(s.get("pitcher_name") or "")
            k = actual.get((gd, skey))
            if k is None:
                continue
            b = book_med.get((gd, skey, ln))
            if b is None:
                continue
            px = book_medx[(gd, skey, ln)]
            won_over = bool(k > ln)
            pnl += bet_pnl(UNIT, px, won=won_over)
            n += 1
            over_w += 1 if won_over else 0
            under_w += 1 if not won_over else 0
            edge_sum += cal(kr, tbf, ln) - b
            px_list.append(px)
        if n == 0:
            per_line[str(ln)] = {"n": 0, "over": None, "under": None,
                                 "note": "no book alt close at this line"}
            continue
        stake = UNIT * n
        roi = pnl / stake
        med_px = sorted(px_list)[len(px_list) // 2]
        per_line[str(ln)] = {
            "n": n,
            "over": {"roi": round(roi, 4), "pnl": round(pnl, 2),
                     "wr": round(over_w / n, 4),
                     "median_american": med_px,
                     "mean_edge_vs_vigloaded_pp": round(100 * edge_sum / n, 2),
                     "note": "blind over at book alt close; edge vs vig-loaded implied (no devig)"},
            "under": {"roi": None, "pnl": None,
                      "wr_outcome_price_free": round(under_w / n, 4),
                      "note": "no under alt price exists (over-only book); ROI unpriceable"},
        }
        if ln in MAIN_GRID:
            pool_pnl += pnl
            pool_stake += stake

    bench = round(pool_pnl / pool_stake, 4) if pool_stake else None

    over_survive = None
    best_in = None
    for ln in MAIN_GRID:
        cell = per_line[str(ln)]
        if cell["n"] >= MIN_N and cell["over"]:
            if best_in is None or cell["over"]["roi"] > best_in[1]:
                best_in = (ln, cell["over"]["roi"])
    over_detail = "no off-grid alt line with n>=100 exists"
    if best_in is not None:
        beaten = None
        for ln in ALT_LINES:
            if ln in MAIN_GRID:
                continue
            cell = per_line[str(ln)]
            if cell["n"] >= MIN_N and cell["over"] and cell["over"]["roi"] > best_in[1]:
                beaten = (ln, cell["over"]["roi"])
                break
        if beaten:
            over_survive = beaten
            over_detail = ("off-grid line %.1f blind-over ROI %+.4f beats best "
                           "in-grid %.1f (%+.4f) with n>=100"
                           % (beaten[0], beaten[1], best_in[0], best_in[1]))
        else:
            thin = ", ".join("%.1f n=%d" % (ln, per_line[str(ln)]["n"])
                             for ln in ALT_LINES if ln not in MAIN_GRID)
            over_detail = ("no off-grid alt line has n>=100 (%s); best in-grid "
                           "is %.1f (%+.4f) -- nothing to test"
                           % (thin, best_in[0], best_in[1]))
    over_verdict = "SURVIVE" if over_survive else "KILL"
    if over_survive:
        over_detail = ("line %.1f blind-over ROI %+.4f beats main-grid %+.4f with n>=100"
                       % (over_survive[0], over_survive[1], bench))

    under_verdict = "KILL"
    under_detail = ("no under alt price exists at any line 0.5-14.5 "
                    "(over-only book); under legs are unpriceable")

    rep = {
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "contract": ("same inputs/config/join as alt_curve_measure.py; blind $50 "
                     "per (start, line) with book alt close; over-only vig-loaded "
                     "(no devig); same-subset only"),
        "unit_dollars": UNIT,
        "min_n": MIN_N,
        "main_grid_benchmark": {"lines": MAIN_GRID, "blind_over_roi": bench,
                                "stake": round(pool_stake, 2),
                                "pnl": round(pool_pnl, 2)},
        "per_line": per_line,
        "verdicts": {
            "over_ladder": {"verdict": over_verdict, "reason": over_detail},
            "under_ladder": {"verdict": under_verdict, "reason": under_detail},
        },
        "kill_rule": ("OVER SURVIVE iff an off-grid line with n>=100 beats "
                      "the best in-grid (2.5-9.5, n>=100) blind-over ROI; "
                      "UNDER SURVIVE iff a priced under leg does the same "
                      "(impossible on an over-only book)"),
    }
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
