"""2025-lock selection (prereg 2026-09-11, owner order: Execute).

Scores the pre-registered policy family on the 2025 slice of the canonical
juiced candidates ONLY. In-memory filtering is exact: every below_floor row
already carries side/edge/book/price/won (verified), acceptance is monotone
in floor/cap/premium, flat stakes are constant $50, and the dkfd universe
equals the DK/FD subset (next-book pref picks DK/FD first when present).

Champion rule (prereg): max LCB_95(ROI) on slate-clustered block bootstrap
(gd resample, 2000 draws), subject to CLV mean >= 0, no single line x side
cell > 40% of PnL, DK+FD subset ROI same sign, n >= 200. 2026 is judged
once afterwards, disclosed-peek labeled. NOTHING here touches production.

Writes: artifacts/odds_log/select_2025_report.json (ignored, regenerable).
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

from Python.market import bet_pnl  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
CANDIDATES = ROOT / "artifacts" / "odds_log" / "juiced_replay_candidates.parquet"
OUT_JSON = ROOT / "artifacts" / "odds_log" / "select_2025_report.json"

UNIT = 50.0
PROBATION_BUMP = 0.18
N_BOOT = 2000
SEED = 20260911
MIN_N = 200

FLOORS = (0.08, 0.10, 0.12)
CAPS = (0.18, 0.20, 0.24)
SIDES = ("both", "lean")
BOOKS = ("next", "dkfd")


def floor_for(line: float, side: str, uniform: float) -> float:
    fl = float(uniform)
    if str(side) == "over" and round(float(line), 1) in (2.5, 3.5):
        fl = max(fl, PROBATION_BUMP)
    return fl


def take_mask(
    df: pl.DataFrame,
    uniform: float,
    cap: float,
    side_rule: str,
    book_universe: str,
) -> pl.Series:
    """Boolean mask of taken rows under a candidate config (veto always on)."""
    m = (
        (pl.col("reason") != "no_two_way_price")
        & (pl.col("reason") != "bad_price")
        & ~((pl.col("side") == "over") & (pl.col("line").round(1) == 4.5))
    )
    if book_universe == "dkfd":
        m = m & pl.col("book").is_in(["draftkings", "fanduel"])
    return m


def apply_config(df: pl.DataFrame, uniform: float, cap: float,
                 side_rule: str, book_universe: str) -> pl.DataFrame:
    """Return taken rows under config with flat-$50 economics recomputed."""
    base = df.filter(take_mask(df, uniform, cap, side_rule, book_universe))
    if len(base) == 0:
        return base
    prem = 0.04 if side_rule == "lean" else 0.0
    rows = []
    for r in base.iter_rows(named=True):
        fl = floor_for(float(r["line"]), str(r["side"]), uniform)
        if str(r["side"]) == "over":
            fl += prem
        if float(r["edge"]) < fl:
            continue
        if float(r["edge"]) >= float(cap):
            continue
        rows.append(r)
    if not rows:
        return base.clear()
    t = pl.DataFrame(rows)
    # Flat $50 economics via the canonical money function (constant stakes:
    # ROI attribution is pure selection). Never hand-roll payouts here.
    payout = [bet_pnl(UNIT, float(r["price"]), won=bool(r["won"]))
              for r in t.iter_rows(named=True)]
    return t.with_columns(pl.Series("pnl", payout), pl.lit(UNIT).alias("stake"))


def lcb_roi(t: pl.DataFrame, n_boot: int = N_BOOT, seed: int = SEED) -> float | None:
    """2.5th percentile of slate-clustered bootstrap ROI."""
    if len(t) == 0:
        return None
    rng = np.random.default_rng(seed)
    slates = t["gd"].unique().to_list()
    pnl = t["pnl"].to_numpy()
    gd = t["gd"].to_numpy()
    idx = {g: np.where(gd == g)[0] for g in slates}
    k = len(slates)
    boot = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, k, k)
        sel = np.concatenate([idx[slates[i]] for i in pick])
        n = sel.size
        boot[b] = pnl[sel].sum() / (UNIT * n) if n else 0.0
    return float(np.percentile(boot, 2.5))


def cell_concentration(t: pl.DataFrame) -> float:
    """Max line x side share of total PnL (inf if total <= 0)."""
    total = float(t["pnl"].sum())
    if total <= 0:
        return float("inf")
    cells = t.group_by(["line", "side"]).agg(pl.col("pnl").sum().alias("p"))
    return float(cells["p"].max() / total)


CONFIGS = [(fl, cap, side, book) for fl in FLOORS for cap in CAPS
           for side in SIDES for book in BOOKS]


def run_stress(df: pl.DataFrame, champ: dict,
               n_boot: int = N_BOOT, seed: int = SEED + 1) -> dict:
    """Stress battery on the selection slice (all $0, in-memory).

    1. White-lite: slate-clustered resamples, best-of-36 ROI per resample =
       the luck-max distribution; p = P(luck-max >= champion ROI).
    2. Cell exclusion: champion ROI dropping each line x side cell.
    3. Month exclusion: champion ROI dropping each gd month.
    4. September slice: champion on gd >= September (remainder analog).
    """
    out: dict = {}
    c = (float(champ["floor"]), float(champ["cap"]),
         str(champ["side"]), str(champ["book"]))
    ct = apply_config(df, *c)
    stop = {"n": len(ct)}
    if len(ct) == 0:
        return {"empty": True}
    obs_roi = float(ct["pnl"].sum() / ct["stake"].sum())
    stop["obs_roi"] = round(obs_roi, 4)

    fam = []
    for cfg in CONFIGS:
        t = apply_config(df, *cfg)
        if len(t):
            # Impose the null config-by-config: demean ticket pnl so every
            # config has exactly zero edge; resampling then measures what
            # best-of-36 luck alone can print. Without this the test is
            # biased to fail (resamples carry the real edge).
            p = np.asarray(t["pnl"], dtype=float)
            fam.append((t["gd"].to_numpy(), p - p.mean()))
    slates = sorted(set(df["gd"].unique().to_list()))
    rng = np.random.default_rng(seed)
    k = len(slates)
    luck_max = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, k, k)
        best = -np.inf
        for gds, pnl0 in fam:
            sel = np.isin(gds, [slates[i] for i in pick])
            n = int(sel.sum())
            if n:
                r = pnl0[sel].sum() / (UNIT * n)
                if r > best:
                    best = r
        luck_max[b] = best
    out["white_lite"] = {
        "n_boot": n_boot,
        "luck_max_p50": round(float(np.percentile(luck_max, 50)), 4),
        "luck_max_p95": round(float(np.percentile(luck_max, 95)), 4),
        "p_value": round(float((luck_max >= obs_roi).mean()), 4),
    }

    cells = ct.group_by(["line", "side"]).agg(pl.len().alias("n")).sort("n", descending=True)
    excl = []
    for cell in cells.iter_rows(named=True):
        rest = ct.filter(~((pl.col("line") == cell["line"]) & (pl.col("side") == cell["side"])))
        if len(rest):
            excl.append({
                "line": cell["line"], "side": cell["side"], "dropped_n": cell["n"],
                "roi": round(float(rest["pnl"].sum() / rest["stake"].sum()), 4),
                "n": len(rest),
            })
    out["cell_exclusion"] = excl
    months = sorted({str(g)[:7] for g in ct["gd"].unique().to_list()})
    mex = []
    for m in months:
        rest = ct.filter(pl.col("gd").str.slice(0, 7) != m)
        if len(rest):
            mex.append({"dropped_month": m,
                        "roi": round(float(rest["pnl"].sum() / rest["stake"].sum()), 4),
                        "n": len(rest)})
    out["month_exclusion"] = mex
    sept = ct.filter(pl.col("gd") >= "2025-09-01")
    out["september"] = {"n": len(sept)}
    if len(sept):
        out["september"].update({
            "roi": round(float(sept["pnl"].sum() / sept["stake"].sum()), 4),
            "wr": round(float(sept["won"].mean()), 4),
        })
    out["taken"] = stop
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--select-year", default="2025")
    ap.add_argument("--judge-year", default=None,
                    help="if given, score the champion once on this year "
                         "(disclosed peek -- labeled, never clean)")
    ap.add_argument("--stress", action="store_true",
                    help="run the White-lite + exclusion + September battery "
                         "on the selection slice")
    args = ap.parse_args()

    df = pl.read_parquet(CANDIDATES).filter(pl.col("yr") == args.select_year)
    print(f"{args.select_year} candidate rows: {len(df)}")
    results = []
    for fl in FLOORS:
        for cap in CAPS:
            for side in SIDES:
                for book in BOOKS:
                    t = apply_config(df, fl, cap, side, book)
                    n = len(t)
                    if n < MIN_N:
                        results.append({"floor": fl, "cap": cap, "side": side,
                                        "book": book, "n": n, "eligible": False})
                        continue
                    roi = float(t["pnl"].sum() / t["stake"].sum())
                    wr = float(t["won"].mean())
                    clvs = [v for v in t["clv_pp"].to_list() if v is not None]
                    mean_clv = float(np.mean(clvs)) if clvs else None
                    conc = cell_concentration(t)
                    dk = t.filter(pl.col("book").is_in(["draftkings", "fanduel"]))
                    dk_roi = (float(dk["pnl"].sum() / dk["stake"].sum())
                              if len(dk) else None)
                    results.append({
                        "floor": fl, "cap": cap, "side": side, "book": book,
                        "n": n, "roi": round(roi, 4), "wr": round(wr, 4),
                        "mean_clv_pp": round(mean_clv, 3) if mean_clv is not None else None,
                        "cell_conc": round(conc, 3) if conc != float("inf") else None,
                        "dkfd_n": len(dk),
                        "dkfd_roi": round(dk_roi, 4) if dk_roi is not None else None,
                        "lcb95": round(lcb_roi(t, args.n_boot), 4),
                        "eligible": True,
                    })
    for r in results:
        if not r["eligible"]:
            continue
        ok = (r["mean_clv_pp"] is not None and r["mean_clv_pp"] >= 0
              and r["cell_conc"] is not None and r["cell_conc"] <= 0.40
              and r["dkfd_roi"] is not None and (r["dkfd_roi"] > 0) == (r["roi"] > 0))
        r["passes_constraints"] = bool(ok)
    elig = [r for r in results if r.get("eligible")]
    passing = [r for r in elig if r.get("passes_constraints")]
    pool = passing if passing else []
    champ = max(pool, key=lambda r: r["lcb95"]) if pool else None
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contract": "2025-select per prereg 2026-09-11; veto+probation on; "
                    "flat $50; slate-clustered LCB; constraints CLV>=0, "
                    "cell<=0.40, dkfd-sign, n>=200",
        "n_configs": len(results),
        "n_eligible": len(elig),
        "n_passing": len(pool),
        "results": sorted(elig, key=lambda r: r["lcb95"], reverse=True),
        "ineligible": [r for r in results if not r.get("eligible")],
        "champion": champ,
    }
    print(f"configs={len(results)} eligible={len(elig)} passing={len(pool)}")
    for r in report["results"][:12]:
        print(f"fl={r['floor']} cap={r['cap']} side={r['side']} book={r['book']} "
              f"n={r['n']} roi={r['roi']} wr={r['wr']} lcb={r['lcb95']} "
              f"clv={r['mean_clv_pp']} conc={r['cell_conc']} dkfd={r['dkfd_roi']} "
              f"pass={r.get('passes_constraints')}")
    print("CHAMPION:", json.dumps(champ))
    if args.stress and champ is not None:
        report["stress"] = run_stress(df, champ, args.n_boot)
        s = report["stress"]
        print("STRESS white:", json.dumps(s.get("white_lite")))
        print("STRESS september:", json.dumps(s.get("september")))
        print("STRESS worst-cell-drop:",
              json.dumps(min(s.get("cell_exclusion", [{"roi": None}]),
                             key=lambda e: e["roi"] if e["roi"] is not None else 9)))
        print("STRESS worst-month-drop:",
              json.dumps(min(s.get("month_exclusion", [{"roi": None}]),
                             key=lambda e: e["roi"] if e["roi"] is not None else 9)))
    if args.judge_year and champ is not None:
        jdf = pl.read_parquet(CANDIDATES).filter(pl.col("yr") == args.judge_year)
        jt = apply_config(jdf, champ["floor"], champ["cap"],
                          champ["side"], champ["book"])
        jn = len(jt)
        judge = {"n": jn}
        if jn:
            judge.update({
                "roi": round(float(jt["pnl"].sum() / jt["stake"].sum()), 4),
                "wr": round(float(jt["won"].mean()), 4),
                "lcb95": round(lcb_roi(jt, args.n_boot), 4),
                "note": "DISCLOSED PEEK (blindness broken pre-run) -- not a clean judge",
            })
            clvs = [v for v in jt["clv_pp"].to_list() if v is not None]
            judge["mean_clv_pp"] = round(float(np.mean(clvs)), 3) if clvs else None
        report["judge"] = {"year": args.judge_year, **judge}
        print("JUDGE:", json.dumps(report["judge"]))
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
