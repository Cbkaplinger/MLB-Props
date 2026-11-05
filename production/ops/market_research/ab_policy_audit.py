"""A/B policy audit on the identical 2026 opportunity set (measurement only).

Legs (all flat $50, same candidates, same selector machinery):
  status_quo  floor 0.12, no cap, no lean, all books  (pre-champion live rule)
  cap_only    status_quo + edge cap 0.24
  lean_only   status_quo + under-lean premium 0.04
  dkfd_only   status_quo + DK+FD-only books
  champion    floor 0.12 / cap 0.24 / lean / DK+FD (the promoted rule)

The A/B is bundled by design: champion vs status_quo tests the package;
single-factor legs attribute it. Cap=9.0 encodes "no cap" through the exact
same refuse path (nothing reaches it) — no selector change, no new machinery.

Stats: slate-clustered bootstrap ROI 95% CI (resample gd, 2000 draws, fixed
seeds — same method as the LCB selector). Monthly CIs reuse the same helper
on each month's slates; thin months print wide intervals, never point claims.

Usage:
  python production/ops/market_research/ab_policy_audit.py [--out FILE]
Writes artifacts/odds_log/ab_policy_report.json + prints markdown tables.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "production" / "ops" / "market_research"))

from Python.market import bet_pnl  # noqa: E402  (imported for parity; economics via selector)

ODDS_DIR = ROOT / "artifacts" / "odds_log"
UNIT = 50.0
N_BOOT = 2000
SEED = 20260917
NO_CAP = 9.0

LEGS: list[tuple[str, float, float, str, str]] = [
    ("status_quo", 0.12, NO_CAP, "both", "next"),
    ("cap_only", 0.12, 0.24, "both", "next"),
    ("lean_only", 0.12, NO_CAP, "lean", "next"),
    ("dkfd_only", 0.12, NO_CAP, "both", "dkfd"),
    ("champion", 0.12, 0.24, "lean", "dkfd"),
]


def boot_roi_ci(gd: list, pnl: list, n_boot: int = N_BOOT,
                seed: int = SEED) -> dict:
    """Slate-clustered bootstrap ROI percentiles (pure, testable)."""
    n = len(pnl)
    if n == 0:
        return {"n": 0, "roi": None, "ci_lo": None, "ci_hi": None}
    rng = np.random.default_rng(seed)
    slates = sorted(set(gd))
    idx = {g: np.array([i for i, x in enumerate(gd) if x == g]) for g in slates}
    k = len(slates)
    parr = np.array(pnl, dtype=float)
    boot = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, k, k)
        sel = np.concatenate([idx[slates[i]] for i in pick])
        m = sel.size
        boot[b] = parr[sel].sum() / (UNIT * m) if m else 0.0
    roi = float(parr.sum() / (UNIT * n))
    return {"n": n, "slates": k, "roi": round(roi, 4),
            "ci_lo": round(float(np.percentile(boot, 2.5)), 4),
            "ci_hi": round(float(np.percentile(boot, 97.5)), 4)}


def leg_stats(t: pl.DataFrame, seed: int) -> dict:
    """Economics + CI for one taken set (pure over rows)."""
    rows = t.to_dicts()
    pnl = [float(r["pnl"]) for r in rows]
    gd = [str(r["gd"]) for r in rows]
    out = boot_roi_ci(gd, pnl, seed=seed)
    out["pnl"] = round(sum(pnl), 2)
    out["wr"] = round(sum(1 for r in rows if r["won"]) / len(rows), 4) if rows else None
    clv = [float(r["clv_pp"]) for r in rows if r.get("clv_pp") is not None]
    out["clv_n"] = len(clv)
    out["clv_mean_pp"] = round(sum(clv) / len(clv), 2) if clv else None
    out["clv_beat"] = round(sum(1 for c in clv if c > 0) / len(clv), 4) if clv else None
    out["days"] = len(set(gd))
    out["bets_per_day"] = round(len(rows) / out["days"], 2) if out["days"] else None
    return out


def load_selector():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "select_2025_champion",
        ROOT / "production" / "ops" / "market_research" / "select_2025_champion.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["select_2025_champion"] = mod
    spec.loader.exec_module(mod)
    return mod


def md_ab(rep: dict) -> str:
    lines = ["### A/B legs, identical 2026 set, flat $50",
             "| Leg | n | PnL | ROI | 95% CI | WR | CLV | beat |",
             "|---|---:|---:|---:|---|---|---:|---:|---:|"]
    for name, b in rep["legs"].items():
        lines.append(
            f"| {name} | {b['n']} | ${b['pnl']:+.0f} | {b['roi']:+.1%} | "
            f"[{b['ci_lo']:+.1%}, {b['ci_hi']:+.1%}] | {b['wr']:.0%} | "
            f"{b['clv_mean_pp']:+.2f}pp | {b['clv_beat']:.0%} |")
    return "\n".join(lines)


def md_monthly(rep: dict) -> str:
    lines = ["### Champion monthly ROI with 95% CI",
             "| Month | n | ROI | 95% CI | Clears 0? |",
             "|---|---:|---:|---|---|"]
    for m, b in rep["monthly_ci"].items():
        clears = "yes" if b["ci_lo"] > 0 else ("no (red)" if b["ci_hi"] < 0 else "no")
        lines.append(
            f"| {m} | {b['n']} | {b['roi']:+.1%} | "
            f"[{b['ci_lo']:+.1%}, {b['ci_hi']:+.1%}] | {clears} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ODDS_DIR / "ab_policy_report.json"))
    args = ap.parse_args()

    sel = load_selector()
    cand = pl.read_parquet(ODDS_DIR / "juiced_replay_candidates.parquet")
    c26 = cand.filter(pl.col("yr").cast(pl.String) == "2026")

    rep: dict = {"legs": {}, "monthly_ci": {},
                 "note": "identical 2026 opportunity set, flat $50, slate-clustered CIs"}
    taken: dict[str, pl.DataFrame] = {}
    for i, (name, fl, cap, side, book) in enumerate(LEGS):
        t = sel.apply_config(c26, fl, cap, side, book)
        taken[name] = t
        rep["legs"][name] = {"config": {"floor": fl, "cap": None if cap == NO_CAP else cap,
                                        "side": side, "books": book},
                             **leg_stats(t, SEED + i)}

    champ = taken["champion"].with_columns(
        pl.col("gd").cast(pl.String).str.slice(0, 7).alias("_m"))
    for m in sorted(champ["_m"].drop_nulls().unique().to_list()):
        sub = champ.filter(pl.col("_m") == m)
        rep["monthly_ci"][m] = boot_roi_ci(
            [str(x) for x in sub["gd"].to_list()],
            [float(x) for x in sub["pnl"].to_list()], seed=SEED + 100)

    Path(args.out).write_text(json.dumps(rep, indent=2, default=str))
    print(md_ab(rep))
    print()
    print(md_monthly(rep))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
