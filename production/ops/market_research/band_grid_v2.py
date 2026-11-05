"""Band-grid v2 executor (prereg 2026-09-17, owner order: Execute).

80 configs: floor {uniform 0.08/0.10/0.12/0.14, file-map} x cap
{0.18/0.20/0.24/none} x side {both/lean} x books {next/dkfd}. Selection rule
is the 2025-lock contract (min-n, CLV>=0, cell<=40%, dkfd-sign, max LCB_95,
White-lite p<0.05). See docs/reference/reports/band_grid_v2_prereg_2026-09-17.md.

BLINDNESS (mechanical): selection runs on gd >= SELECT_FROM (2026-09-28)
only. An earlier --select-from without --allow-peeked refuses (exit 2).
Peeked runs are labeled and can never promote. Before the slice exists the
run yields a valid empty selection: plumbing proof, no peek.

Usage:
  python production/ops/market_research/band_grid_v2.py [--select-from YYYY-MM-DD]
      [--allow-peeked] [--n-boot N] [--out FILE]
Writes artifacts/odds_log/band_grid_v2_report.json (ignored, regenerable).
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
sys.path.insert(0, str(ROOT / "production" / "ops" / "market_research"))

from Python.market import bet_pnl  # noqa: E402
from select_2025_champion import (  # noqa: E402
    UNIT, cell_concentration, floor_for, lcb_roi, take_mask,
)

CANDIDATES = ROOT / "artifacts" / "odds_log" / "juiced_replay_candidates.parquet"
OUT_JSON = ROOT / "artifacts" / "odds_log" / "band_grid_v2_report.json"
FILE_FLOORS = ROOT / "production" / "ops" / "market_research" / "line_floor_policy.json"

SELECT_FROM = "2026-09-28"
N_BOOT = 2000
SEED = 20260917
MIN_N = 200
NO_CAP = 9.0

FLOOR_OPTS: list[tuple[str, float | None]] = (
    [("uniform", v) for v in (0.08, 0.10, 0.12, 0.14)] + [("file", None)]
)
CAPS: list[float | None] = [0.18, 0.20, 0.24, None]
SIDES = ("both", "lean")
BOOKS = ("next", "dkfd")


class PeekRefused(RuntimeError):
    """Raised when selection is requested on peeked-era data without the flag."""


def file_floors() -> dict[float, float]:
    raw = json.loads(FILE_FLOORS.read_text(encoding="utf-8"))
    return {float(k): float(v) for k, v in raw.get("line_edge_floors", {}).items()}


def take_v2(df: pl.DataFrame, floor_mode: str, floor_val: float | None,
            cap: float | None, side_rule: str,
            book_universe: str) -> pl.DataFrame:
    """Taken set under a v2 config; flat-$50 economics via canonical bet_pnl."""
    base = df.filter(take_mask(df, 0.0, NO_CAP, "both", book_universe))
    if base.is_empty():
        return base.head(0)
    fmap = file_floors() if floor_mode == "file" else {}
    prem = 0.04 if side_rule == "lean" else 0.0
    cap_v = float(cap) if cap is not None else NO_CAP
    rows = []
    for r in base.iter_rows(named=True):
        if floor_mode == "file":
            fl = float(fmap.get(round(float(r["line"]), 1), 0.12))
        else:
            fl = floor_for(float(r["line"]), str(r["side"]), float(floor_val))
        if str(r["side"]) == "over":
            fl += prem
        if float(r["edge"]) < fl:
            continue
        if float(r["edge"]) >= cap_v:
            continue
        rows.append(r)
    if not rows:
        return base.head(0)
    t = pl.DataFrame(rows)
    payout = [bet_pnl(UNIT, float(r["price"]), won=bool(r["won"]))
              for r in t.iter_rows(named=True)]
    return t.with_columns(pl.Series("pnl", payout), pl.lit(UNIT).alias("stake"))


def white_lite(fam: dict[str, pl.DataFrame], slates: list[str],
               obs_roi: float, n_boot: int = N_BOOT,
               seed: int = SEED + 1) -> dict:
    """Demeaned best-of-N luck p-value over slate-clustered resamples."""
    parts = []
    for t in fam.values():
        if len(t) == 0:
            continue
        p = np.asarray(t["pnl"], dtype=float)
        parts.append((np.asarray(t["gd"].to_list()), p - p.mean()))
    if not parts:
        return {"empty": True}
    rng = np.random.default_rng(seed)
    k = len(slates)
    luck = np.empty(n_boot)
    for b in range(n_boot):
        pick = [slates[i] for i in rng.integers(0, k, k)]
        best = -np.inf
        for gds, p0 in parts:
            sel = np.isin(gds, pick)
            n = int(sel.sum())
            if n:
                r = p0[sel].sum() / (UNIT * n)
                if r > best:
                    best = r
        luck[b] = best
    return {"n_boot": n_boot, "n_configs": len(parts),
            "luck_max_p50": round(float(np.percentile(luck, 50)), 4),
            "luck_max_p95": round(float(np.percentile(luck, 95)), 4),
            "p_value": round(float((luck >= obs_roi).mean()), 4)}


def cfg_name(floor_mode: str, floor_val: float | None, cap: float | None,
             side: str, books: str) -> str:
    fl = "file" if floor_mode == "file" else f"{floor_val:.2f}"
    cp = "none" if cap is None else f"{cap:.2f}"
    return f"fl_{fl}/cap_{cp}/{side}/{books}"


def run(select_from: str = SELECT_FROM, allow_peeked: bool = False,
        n_boot: int = N_BOOT) -> dict:
    """Run the grid; returns the report dict (pure orchestration, testable)."""
    if select_from < SELECT_FROM and not allow_peeked:
        raise PeekRefused(
            f"--select-from {select_from} predates the blindness boundary "
            f"{SELECT_FROM}; pass --allow-peeked for a labeled non-promotable run.")
    peeked = select_from < SELECT_FROM
    cand = pl.read_parquet(CANDIDATES)
    dates = cand.select(pl.col("gd").cast(pl.String)).to_series().to_list()
    sl = cand.filter(pl.col("gd").cast(pl.String) >= select_from)
    slates = sorted(sl["gd"].unique().to_list()) if not sl.is_empty() else []
    rep: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contract": "band-grid-v2 prereg 2026-09-17; 80 configs; min-n 200; "
                    "CLV>=0, cell<=0.40, dkfd-sign; max LCB_95; White-lite",
        "select_from": select_from,
        "peeked": peeked,
        "promotable": (not peeked),
        "data_max_gd": max(dates) if dates else None,
        "n_configs": 0, "legs": {}, "champion": None, "white": None,
    }
    if sl.is_empty():
        rep["note"] = "selection slice empty (fresh data not yet closed out)"
        return rep
    fam: dict[str, pl.DataFrame] = {}
    for fmode, fval in FLOOR_OPTS:
        for cap in CAPS:
            for side in SIDES:
                for books in BOOKS:
                    name = cfg_name(fmode, fval, cap, side, books)
                    t = take_v2(sl, fmode, fval, cap, side, books)
                    fam[name] = t
    rep["n_configs"] = len(fam)
    scored = []
    for name, t in fam.items():
        n = len(t)
        if n < MIN_N:
            rep["legs"][name] = {"n": n, "eligible": False}
            continue
        roi = float(t["pnl"].sum() / t["stake"].sum())
        clvs = [v for v in t["clv_pp"].to_list() if v is not None]
        mean_clv = float(np.mean(clvs)) if clvs else None
        conc = cell_concentration(t)
        dk = t.filter(pl.col("book").is_in(["draftkings", "fanduel"]))
        dk_roi = float(dk["pnl"].sum() / dk["stake"].sum()) if len(dk) else None
        leg = {"n": n, "roi": round(roi, 4),
               "wr": round(float(t["won"].mean()), 4),
               "mean_clv_pp": round(mean_clv, 3) if mean_clv is not None else None,
               "cell_conc": round(conc, 3) if conc != float("inf") else None,
               "lcb95": round(lcb_roi(t, n_boot), 4),
               "eligible": True}
        ok = (leg["mean_clv_pp"] is not None and leg["mean_clv_pp"] >= 0
              and leg["cell_conc"] is not None and leg["cell_conc"] <= 0.40
              and dk_roi is not None and (dk_roi > 0) == (roi > 0))
        leg["passes_constraints"] = bool(ok)
        rep["legs"][name] = leg
        if ok:
            scored.append((name, leg))
    if scored:
        name, leg = max(scored, key=lambda kv: kv[1]["lcb95"])
        rep["champion"] = {"config": name, **leg}
        rep["white"] = white_lite(fam, slates, leg["roi"], n_boot)
    return rep


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--select-from", default=SELECT_FROM)
    ap.add_argument("--allow-peeked", action="store_true")
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--out", default=str(OUT_JSON))
    args = ap.parse_args()
    rep = run(args.select_from, args.allow_peeked, args.n_boot)
    Path(args.out).write_text(json.dumps(rep, indent=2, default=str))
    ch = rep.get("champion")
    print(f"configs={rep['n_configs']} peeked={rep['peeked']} "
          f"promotable={rep['promotable']}")
    if ch:
        print("CHAMPION:", json.dumps(ch), "WHITE:", json.dumps(rep.get("white")))
    else:
        print(rep.get("note", "no champion (no passing leg)"))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
