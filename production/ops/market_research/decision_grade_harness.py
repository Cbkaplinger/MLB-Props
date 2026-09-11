"""Decision-grade harness: select policy on 2025, judge once on 2026.

Fresh-ground-truth engine (#89): paper ledger history is deprecated for
policy; universe panels + closes decide. Decision snapshot per row =
friend OPEN else paid MORNING (source recorded); model = live p_ours_cal;
grade vs paid CLOSE with actuals y.

Configs (56): floors {0.08..0.20} x veto {on/off} x probation {on/off}
x snap {best, morning}. Sides picked by max edge; veto holds 4.5-overs;
probation raises 2.5/3.5-over floors to 0.18 (production mirrors).

Metrics per config: Brier/skill-vs-close/ECE, CLV + xCLV, fair-price ROI/WR
(UPPER BOUND at vig-free prices — fills decide money truth), xROI (mean
taken edge), Sharpe/decay/Sortino on daily PnL.

SELECTION (2025 only): champion = max Brier skill with ROI >= 0 and
n_bets >= 200. JUDGMENT: champion's 2026 numbers, no re-pick, no second
rounds (peeking spends the judge).

Writes artifacts/odds_log/decision_grade_report.json. No live change.
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

from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.prob_calibration import expected_calibration_error  # noqa: E402
from join_keys import ODDS_DIR  # noqa: E402

PANEL = ODDS_DIR / "universe_panel_live.parquet"
STAKE = 50.0
FLOORS = [0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20]
PROB_BUMP = 0.18


def fair_to_amer(p: float) -> float:
    p = float(np.clip(p, 0.01, 0.99))
    return -100.0 * p / (1.0 - p) if p >= 0.5 else 100.0 * (1.0 - p) / p


def amer_profit(price: float, stake: float = STAKE) -> float:
    return stake * 100.0 / abs(price) if price < 0 else stake * price / 100.0


def sharpe_sortino(daily: np.ndarray) -> dict:
    out = {"sharpe": None, "sortino": None, "mean_daily": float(np.mean(daily)),
           "n_days": int(len(daily))}
    if len(daily) > 5 and float(np.std(daily)) > 0:
        out["sharpe"] = float(np.mean(daily) / np.std(daily) * np.sqrt(162.0))
        dn = daily[daily < 0]
        if len(dn) > 1 and float(np.std(dn)) > 0:
            out["sortino"] = float(np.mean(daily) / np.std(dn) * np.sqrt(162.0))
    return out


def run_year(d: pl.DataFrame, floor: float, veto: bool, prob: bool,
             snap: str) -> dict:
    pm = d["p_ours_cal"].to_numpy().astype(float)
    y = d["y"].to_numpy().astype(float)
    lines = d["line"].to_numpy().astype(float)
    gd = d["gd"].to_list()
    if snap == "morning":
        pd_ = d["p_book_morning"].to_numpy().astype(float)
        src = np.array(["morning"] * d.height)
    else:
        fo = d["p_friend_open"].to_numpy().astype(float)
        mo = d["p_book_morning"].to_numpy().astype(float)
        use_open = ~np.isnan(fo)
        pd_ = np.where(use_open, fo, mo)
        src = np.where(use_open, "open", "morning")
    pc = d["p_book_close"].to_numpy().astype(float)

    bets_p, bets_y, bets_eo, clv, xclv, xroi, sides, dayp = [], [], [], [], [], [], [], []
    bets_book = []
    daymap: dict[str, float] = {}
    n_open_src = 0
    for i in range(d.height):
        if np.isnan(pd_[i]) or np.isnan(pc[i]):
            continue
        eo = pm[i] - pd_[i]
        eu = (1.0 - pm[i]) - (1.0 - pd_[i])
        side = "over" if eo >= eu else "under"
        fl = floor
        if prob and side == "over" and lines[i] in (2.5, 3.5):
            fl = max(fl, PROB_BUMP)
        if veto and side == "over" and lines[i] == 4.5:
            continue
        edge = eo if side == "over" else eu
        if edge < fl:
            continue
        won = (y[i] == 1.0) if side == "over" else (y[i] == 0.0)
        ps = pm[i] if side == "over" else 1.0 - pm[i]
        bets_book.append(pc[i] if side == "over" else 1.0 - pc[i])
        price = fair_to_amer(pd_[i] if side == "over" else 1.0 - pd_[i])
        bets_p.append(ps)
        bets_y.append(1.0 if won else 0.0)
        # Canonical CLV sign (Python.market clv_pp): close minus decision.
        # Positive = the market moved toward our side after the decision
        # (#113 review caught decision-minus-close flipped). xCLV stays
        # model-minus-close ("model edge vs close") — documented pair.
        clv.append((pc[i] - pd_[i]) if side == "over" else ((1.0 - pc[i]) - (1.0 - pd_[i])))
        xclv.append((pm[i] - pc[i]) if side == "over" else ((1.0 - pm[i]) - (1.0 - pc[i])))
        xroi.append(edge)
        sides.append(side)
        pnl = amer_profit(price) if won else -STAKE
        daymap[gd[i]] = daymap.get(gd[i], 0.0) + pnl
        dayp.append(pnl)
        if src[i] == "open":
            n_open_src += 1
    rep: dict = {"n_bets": len(bets_p), "n_open_src": n_open_src}
    if not bets_p:
        return rep
    bp = np.array(bets_p)
    by = np.array(bets_y)
    rep["brier"] = float(np.mean((bp - by) ** 2))
    # Same-subset book Brier (#93 fix: NEVER compare BET-set config Brier
    # against full-panel book Brier — bet rows are selected hard).
    rep["book_brier_bets"] = float(np.mean((np.array(bets_book) - by) ** 2))
    rep["skill"] = rep["book_brier_bets"] - rep["brier"]
    e, _ = expected_calibration_error(by, bp)
    rep["ece"] = float(e)
    fair_n = len(bets_p)
    pnl_sum = float(np.sum(dayp))
    rep["roi_fair"] = pnl_sum / (fair_n * STAKE)
    rep["wr"] = float(np.mean(by))
    rep["pnl_fair"] = round(pnl_sum, 2)
    rep["clv_pp"] = float(np.mean(clv) * 100)
    rep["xclv_pp"] = float(np.mean(xclv) * 100)
    rep["xroi"] = float(np.mean(xroi))
    rep.update(sharpe_sortino(np.array(sorted(daymap.values()))))
    rep["over_share"] = float(np.mean([1.0 if s == "over" else 0.0 for s in sides]))
    return rep


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    df = pl.read_parquet(PANEL).filter(
        pl.col("p_ours_cal").is_not_null() & pl.col("y").is_not_null()
        & pl.col("p_book_close").is_not_null()).sort("gd")
    df = df.with_columns(pl.col("gd").str.slice(0, 4).alias("yr"))
    d25 = df.filter(pl.col("yr") == "2025")
    d26 = df.filter(pl.col("yr") == "2026")
    print(f"select-2025 n={d25.height} / judge-2026 n={d26.height}")

    rows = []
    for floor in FLOORS:
        for veto in (False, True):
            for prob in (False, True):
                for snap in ("best", "morning"):
                    r25 = run_year(d25, floor, veto, prob, snap)
                    rows.append({"floor": floor, "veto": veto, "prob": prob,
                                 "snap": snap, **{f"s25_{k}": v for k, v in r25.items()}})
    sel = [r for r in rows if r.get("s25_n_bets", 0) >= 200
           and (r.get("s25_roi_fair") or -99) >= 0
           and r.get("s25_skill") is not None]
    champ = max(sel, key=lambda r: r["s25_skill"]) if sel else None
    b25full = float(np.mean((d25["p_book_close"].to_numpy().astype(float)
                               - d25["y"].to_numpy().astype(float)) ** 2))
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(),
                 "n_configs": len(rows), "n_eligible": len(sel),
                 "book_brier_2025_fullpanel_reference_only": b25full,
                 "selection": rows,
                 "champion": None}
    if champ is not None:
        judged = run_year(d26, champ["floor"], champ["veto"], champ["prob"], champ["snap"])
        rep["champion"] = {k: champ[k] for k in ("floor", "veto", "prob", "snap")}
        rep["champion"]["select_2025"] = {k[4:]: champ[k] for k in champ if k.startswith("s25_")}
        rep["champion"]["judge_2026"] = judged
    out = ODDS_DIR / "decision_grade_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    if champ is not None:
        print("CHAMPION:", {k: champ[k] for k in ("floor", "veto", "prob", "snap")})
        print("select2025:", json.dumps(rep["champion"]["select_2025"], indent=1, default=str))
        print("judge2026:", json.dumps(rep["champion"]["judge_2026"], indent=1, default=str))
    else:
        print("no eligible champion (all ROI<0 or thin)")
        best = sorted([r for r in rows if r["s25_skill"] is not None],
                      key=lambda r: r["s25_skill"], reverse=True)[:5]
        for b in best:
            print({k: b[k] for k in ("floor", "veto", "prob", "snap")},
                  "skill=%.5f bets=%s roi=%s" % (b["s25_skill"], b.get("s25_n_bets"), b.get("s25_roi_fair")))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
