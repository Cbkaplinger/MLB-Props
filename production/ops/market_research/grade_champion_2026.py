"""Grade a 2025-lock family config beyond PnL (owner 2026-09-16).

Reuses the SELECTOR's exact taken set (`select_2025_champion.apply_config` on
the canonical frozen candidates — the same rows the White/LCB judge graded),
scopes to one year, and prints the full grading surface the live ledger
tracks: ROI (realized), xROI (mean taken edge, flat + stake-weighted), CLV
mean + beat_rate, WR, side/snap splits, and monthly splits. CLV here is
PERCENT scale (juiced convention); beat_rate is scale-invariant.

Why the selector, not a ledger sidecar: the ledger `--floor/--cap/--lean`
flags implement a different (more permissive) take rule — a sidecar run took
844 vs the judge's 485 on 2026. Only the selector reproduces the judged set.

Usage:
  python production/ops/market_research/grade_champion_2026.py [--year 2026]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from Python.odds_ledger import atomic_write_text  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"
RESEARCH_DIR = ROOT / "production" / "ops" / "market_research"
sys.path.insert(0, str(RESEARCH_DIR))


def load_selector():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "select_2025_champion",
        RESEARCH_DIR / "select_2025_champion.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["select_2025_champion"] = mod
    spec.loader.exec_module(mod)
    return mod


def build_ensemble_close() -> pl.DataFrame:
    """Devigged-median consensus close per (gd, key, line), 2+ books required.

    Mirrors the manuscript consensus doctrine (per-book multiplicative devig,
    median across books) and the paid-closeout `read_consensus_cache`
    methodology. Returns (gd, key, line, ens_over, ens_under, n_books).
    """
    from join_keys import load_event_date_map, sorted_key  # noqa: E402

    hist = (ROOT / "data" / "Odds-Historical" / "theoddsapi"
            / "book_lines_pitcher.parquet")
    bk = pl.scan_parquet(hist).filter(
        (pl.col("market") == "pitcher_strikeouts")
        & (pl.col("snapshot") == "close")
    ).collect()
    ev = pl.DataFrame({"event_id": list(load_event_date_map().keys()),
                       "gd": list(load_event_date_map().values())})
    bk = bk.join(ev, on="event_id", how="left").filter(
        pl.col("gd").is_not_null() & (pl.col("gd") != ""))
    bk = bk.with_columns(
        pl.col("player_norm").map_elements(sorted_key, return_dtype=pl.Utf8).alias("key"))
    over = bk.filter(pl.col("side") == "over").select(
        ["gd", "key", "line", "book", "price"]).rename({"price": "o"})
    under = bk.filter(pl.col("side") == "under").select(
        ["gd", "key", "line", "book", "price"]).rename({"price": "u"})
    pairs = over.join(under, on=["gd", "key", "line", "book"])
    raw_o = pl.when(pl.col("o") > 0).then(100.0 / (pl.col("o") + 100.0)) \
        .otherwise(-pl.col("o") / (-pl.col("o") + 100.0))
    raw_u = pl.when(pl.col("u") > 0).then(100.0 / (pl.col("u") + 100.0)) \
        .otherwise(-pl.col("u") / (-pl.col("u") + 100.0))
    pairs = pairs.with_columns(
        (raw_o / (raw_o + raw_u)).alias("p_over"),
        (raw_u / (raw_o + raw_u)).alias("p_under"),
    )
    return (
        pairs.group_by(["gd", "key", "line"])
        .agg(pl.col("p_over").median().alias("ens_over"),
             pl.col("p_under").median().alias("ens_under"),
             pl.col("book").n_unique().alias("n_books"))
        .filter(pl.col("n_books") >= 2)
    )


def attach_ensemble(taken: pl.DataFrame, ens: pl.DataFrame) -> pl.DataFrame:
    """Ensemble-consensus CLV (percent scale) on the taken side."""
    out = taken.join(ens, on=["gd", "key", "line"], how="left")
    ens_side = pl.when(pl.col("side") == "over").then(pl.col("ens_over")) \
        .otherwise(pl.col("ens_under"))
    return out.with_columns(
        ((ens_side - pl.col("p_mkt")) * 100.0).alias("ens_clv_pp"))


def grade_frame(taken: pl.DataFrame, pnl_col: str, stake_col: str,
                _depth: int = 0) -> dict:
    """Full grading surface for one taken set (pure, testable)."""
    n = taken.height
    if n == 0:
        return {"n": 0}
    stake = taken[stake_col].cast(pl.Float64).sum()
    pnl = taken[pnl_col].cast(pl.Float64).sum()
    edge = taken["edge"].cast(pl.Float64)
    out: dict = {
        "n": n,
        "stake": float(stake),
        "pnl": float(pnl),
        "roi": float(pnl / stake) if stake else None,
        "wr": float(taken["won"].cast(pl.Float64).mean()),
        "xroi_edge": float(edge.mean()),
        "xroi_stake_wtd": float((edge * taken[stake_col].cast(pl.Float64)).sum() / stake)
        if stake else None,
    }
    clv = taken.filter(pl.col("clv_pp").is_not_null())
    out["n_clv"] = clv.height
    if clv.height:
        c = clv["clv_pp"].cast(pl.Float64)
        out["mean_clv_pp"] = float(c.mean())
        out["beat_rate"] = float((c > 0).mean())
    else:
        out["mean_clv_pp"] = None
        out["beat_rate"] = None
    if out["roi"] is not None:
        out["xroi_roi_gap"] = float(out["xroi_edge"] - out["roi"])
    # Taken-set calibration (E1): ECE/Brier of taken-side probs vs outcomes.
    # p_ours_cal is P(over); flip for unders. Guards keep unit tests (which
    # lack prob columns) green.
    if {"p_ours_cal", "side", "won"} <= set(taken.columns):
        from bettable_calibration import ece_mce  # noqa: E402

        pairs = [(float(r["p_ours_cal"]) if r["side"] == "over"
                  else 1.0 - float(r["p_ours_cal"]), float(bool(r["won"])))
                 for r in taken.to_dicts()]
        if pairs:
            out["calib"] = ece_mce(pairs)
            out["calib"]["brier"] = round(
                sum((p - y) ** 2 for p, y in pairs) / len(pairs), 4)
    if _depth > 0:
        return out
    for dim in ("side", "snap"):
        if dim not in taken.columns:
            continue
        splits = {}
        for val in sorted(taken[dim].drop_nulls().unique().to_list()):
            splits[str(val)] = grade_frame(
                taken.filter(pl.col(dim) == val), pnl_col, stake_col,
                _depth=_depth + 1)
        out[f"by_{dim}"] = splits
    if "gd" in taken.columns:
        monthly = {}
        months = sorted({str(g)[:7] for g in taken["gd"].drop_nulls().to_list()})
        for m in months:
            monthly[m] = grade_frame(
                taken.filter(pl.col("gd").cast(pl.String).str.slice(0, 7) == m),
                pnl_col, stake_col, _depth=_depth + 1)
        out["monthly"] = monthly
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--floor", type=float, default=0.12)
    ap.add_argument("--cap", type=float, default=0.24)
    ap.add_argument("--side", default="lean", choices=("both", "lean"))
    ap.add_argument("--book", default="dkfd", choices=("next", "dkfd"))
    args = ap.parse_args()

    sel = load_selector()
    cand = pl.read_parquet(ODDS_DIR / "juiced_replay_candidates.parquet")
    df = cand.filter(pl.col("yr").cast(pl.String) == str(args.year))
    taken = sel.apply_config(df, args.floor, args.cap, args.side, args.book)
    rep = grade_frame(taken, "pnl", "stake")
    # Ensemble-consensus CLV: same taken set, graded against the multi-book
    # median close (owner: opens on DK/FD, grading vs the ensemble).
    ens = build_ensemble_close()
    te = attach_ensemble(taken, ens).filter(pl.col("ens_clv_pp").is_not_null())
    rep["n_ens"] = te.height
    if te.height:
        ec = te["ens_clv_pp"].cast(pl.Float64)
        rep["ens_clv_pp"] = round(float(ec.mean()), 2)
        rep["ens_beat"] = round(float((ec > 0).mean()), 4)
    else:
        rep["ens_clv_pp"] = None
        rep["ens_beat"] = None
    cfg = f"{args.floor:g}_{args.cap:g}_{args.side}_{args.book}"
    rep["contract"] = {
        "config": cfg, "year": args.year,
        "taken_by": "select_2025_champion.apply_config (judge-identical rows)",
        "clv_scale": "percent (juiced convention)",
        "note": "banked friend-open/paid-morning quotes, frozen model, $0",
    }
    out = ODDS_DIR / f"champion_{args.year}_grade.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    show = {k: (round(v, 4) if isinstance(v, float) else v)
            for k, v in rep.items()
            if k not in ("by_side", "by_snap", "monthly", "contract")}
    if isinstance(show.get("calib"), dict):
        show["calib"] = {k: v for k, v in show["calib"].items() if k != "bins"}
    print(json.dumps(show, indent=1))
    for s in ("open", "morning"):
        b = rep.get("by_snap", {}).get(s, {})
        cc = b.get("calib", {}) if isinstance(b, dict) else {}
        print(f"{s}: n={b.get('n')} roi={b.get('roi'):+.3f} "
              f"ECE={cc.get('ece')} Brier={cc.get('brier')} "
              f"CLV={b.get('mean_clv_pp'):+.2f} beat={b.get('beat_rate'):.2f}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
