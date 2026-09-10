"""WS9 family-vulnerability probe v1 — batter whiff-vs-pitch-family (post hoc).

The unexplored shelf: how vulnerable is TODAY's lineup to THIS arsenal?
Per start G (strictly prior dates only):
  famVuln = sum_pt usage_prior5_pt *
            mean_slots( shrunk_whiff(batter,pt,stand) - league(pt,stand) )

- Pitch-level Savant regular 2015+ (8.2M pitches): whiff = swinging_strike /
  swinging_strike_blocked / missed_bunt; swings = whiffs + foul + foul_tip +
  foul_bunt + bunt_foul_tip + hit_into_play. Main-8 families only.
- League: expanding prior-date whiff per (pitch_type, stand).
- Batter: expanding prior-date sums per (batter, pitch_type, stand) + EB
  shrink toward league (strength 200 swings). No history -> league -> 0.
- Lineup: first-9 initial slots from batter_games (ws5b pattern, no names).
- Usage: pitcher prior-5 shares from pitch_type_games (kadj pattern).

Tests (SOP: CUT=2026-05-23, live-equivalent Poisson+WS1c baseline):
  1. Coverage + min-n (>=50-pitch share) + stability (pitcher-season YoY).
  2. Berkson: corr(famVuln,resid_K) raw / stuff-conditioned / within-pitcher.
  3. Challenger: OLS resid_K ~ famVuln*TBF through origin on TRAIN; TEST
     Brier gain vs baseline. Kill: gain < 0.0005.

Writes artifacts/odds_log/ws9_famvuln_report.json. No live change.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.count_layer import p_strikeouts_ge  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.prob_calibration import ProbCalibrationBundle  # noqa: E402

SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
BATG = ROOT / "data" / "processed" / "batter_games.parquet"
PITCH = ROOT / "data" / "processed" / "pitch_type_games.parquet"
PANEL = ROOT / "artifacts" / "odds_log" / "universe_panel.parquet"
CALIB = ROOT / "artifacts" / "models" / "prob_calibration_ws1c_platt_20260910_012559.joblib"
ODDS_DIR = ROOT / "artifacts" / "odds_log"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
CUT = "2026-05-23"
MAIN8 = ["FF", "SI", "FC", "SL", "CU", "CH", "FS", "ST"]
WHIFFS = {"swinging_strike", "swinging_strike_blocked", "missed_bunt"}
SWINGS = WHIFFS | {"foul", "foul_tip", "foul_bunt", "bunt_foul_tip", "hit_into_play"}
EB_PITCHES = 200.0


class CumTable:
    """Expanding prior-date sums queried by exact date (all ints/dates sorted)."""

    def __init__(self, dates: np.ndarray, cum_w: np.ndarray, cum_s: np.ndarray):
        self.dates = dates
        self.cum_w = cum_w
        self.cum_s = cum_s

    def prior(self, gdate: int):
        i = int(np.searchsorted(self.dates, gdate, side="left")) - 1
        if i < 0:
            return 0, 0
        return int(self.cum_w[i]), int(self.cum_s[i])


def build_tables(sav: pl.DataFrame):
    sav = sav.with_columns(
        pl.col("description").is_in(WHIFFS).cast(pl.Int32).alias("w"),
        pl.col("description").is_in(SWINGS).cast(pl.Int32).alias("s"),
        pl.col("game_date").cast(pl.Date),
    ).filter(pl.col("s") == 1)
    league: dict[tuple[str, str], CumTable] = {}
    for (pt, st), sub in sav.group_by(["pitch_type", "stand"]):
        d = sub.group_by("game_date").agg(
            pl.col("w").sum().alias("w"), pl.col("s").sum().alias("s")
        ).sort("game_date")
        arr = d["game_date"].to_numpy().astype("datetime64[D]").astype(int)
        league[(pt, st)] = CumTable(arr, d["w"].cum_sum().to_numpy(),
                                    d["s"].cum_sum().to_numpy())
    bat: dict[tuple[int, str, str], CumTable] = {}
    for (b, pt, st), sub in sav.group_by(["batter", "pitch_type", "stand"]):
        d = sub.group_by("game_date").agg(
            pl.col("w").sum().alias("w"), pl.col("s").sum().alias("s")
        ).sort("game_date")
        arr = d["game_date"].to_numpy().astype("datetime64[D]").astype(int)
        bat[(int(b), pt, st)] = CumTable(arr, d["w"].cum_sum().to_numpy(),
                                         d["s"].cum_sum().to_numpy())
    return league, bat


def league_rate(league, pt, st, gdate) -> float:
    t = league.get((pt, st))
    if t is None:
        return 0.0
    w, s = t.prior(gdate)
    return w / s if s > 0 else 0.0


def shrunk_resid(league, bat, b, pt, st, gdate) -> tuple[float, int]:
    lg = league_rate(league, pt, st, gdate)
    t = bat.get((int(b), pt, st))
    w, s = t.prior(gdate) if t is not None else (0, 0)
    return (w + EB_PITCHES * lg) / (s + EB_PITCHES) - lg, s


def corr(a: np.ndarray, b: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 10 or a[m].std() == 0 or b[m].std() == 0:
        return float("nan")
    return float(np.corrcoef(a[m], b[m])[0, 1])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    files = sorted(glob.glob(str(ROOT / "data" / "Savant-Data" / "regular" / "*" / "*.parquet")))
    print(f"savant files: {len(files)}")
    frames = []
    for fp in files:
        frames.append(pl.scan_parquet(fp).select(
            ["game_date", "batter", "stand", "pitch_type", "description"]).collect()
            .with_columns(pl.col("game_date").cast(pl.Date)))
    sav = pl.concat(frames, how="diagonal").filter(
        pl.col("pitch_type").is_in(MAIN8)
        & pl.col("stand").is_in(["L", "R"])
        & pl.col("batter").is_not_null())
    print(f"pitches: {sav.height}")
    league, bat = build_tables(sav)
    print(f"league cells: {len(league)}, batter cells: {len(bat)}")

    sc = (pl.scan_parquet(SCORED).select(
        ["gd", "game_pk", "pitcher", "p_throws", "K", "expected_K", "k_rate_pred",
         "projected_tbf", "is_home", "home_team", "away_team",
         "whiff_rate_P20", "ff_velo_P1"]).collect().filter(
        pl.col("K").is_not_null() & pl.col("expected_K").is_not_null()
        & pl.col("k_rate_pred").is_not_null() & pl.col("projected_tbf").is_not_null()))
    slots = (pl.scan_parquet(BATG).select(
        ["game_pk", "bat_team", "batter", "stand", "lineup_slot",
         "is_initial_lineup"]).collect().filter(pl.col("is_initial_lineup")))
    pt = (pl.scan_parquet(PITCH).select(
        ["game_pk", "pitcher", "pitch_type", "game_date", "Pitches"]).collect()
        .with_columns(pl.col("game_date").cast(pl.Date)))
    pt_by_p: dict[int, list] = {}
    for r in pt.sort(["game_date", "game_pk"]).to_dicts():
        pt_by_p.setdefault(int(r["pitcher"]), []).append(r)

    def usage(pid: int, gdate) -> dict[str, float]:
        hist = [h for h in pt_by_p.get(pid, []) if h["game_date"] < gdate]
        starts = sorted({(h["game_date"], int(h["game_pk"])) for h in hist})
        last5 = set(starts[-5:])
        tot: dict[str, int] = {}
        # NOTE: pitch_type_games codes lowercase (ff/si), Savant uppercase.
        for h in hist:
            ptype = str(h["pitch_type"]).upper()
            if (h["game_date"], int(h["game_pk"])) in last5 and ptype in MAIN8:
                tot[ptype] = tot.get(ptype, 0) + int(h["Pitches"])
        s = sum(tot.values())
        return {k: v / s for k, v in tot.items()} if s else {}

    import datetime as _dt
    rows, n_noslot, n_nousage, pitch_n = [], 0, 0, []
    for r in sc.sort(["gd", "game_pk"]).to_dicts():
        opp = r["away_team"] if r["is_home"] else r["home_team"]
        sl = slots.filter((pl.col("game_pk") == r["game_pk"])
                          & (pl.col("bat_team") == opp)).sort("lineup_slot").head(9)
        if sl.height < 9:
            n_noslot += 1
            continue
        u = usage(int(r["pitcher"]), _dt.date.fromisoformat(r["gd"]))
        if not u:
            n_nousage += 1
            continue
        gnum = _dt.date.fromisoformat(r["gd"]).toordinal()
        v, npt = 0.0, 0
        for ptype, w in u.items():
            cell = [shrunk_resid(league, bat, s["batter"], ptype, s["stand"], gnum)
                    for s in sl.to_dicts()]
            pitch_n.extend([c[1] for c in cell])
            v += w * float(np.mean([c[0] for c in cell]))
            npt += 1
        rows.append({"game_pk": r["game_pk"], "pitcher": int(r["pitcher"]),
                     "gd": r["gd"], "famvuln": v, "n_pt": npt})
    print(f"starts scored: {len(rows)} (noslot={n_noslot} nousage={n_nousage})")
    if not rows:
        raise ValueError(f"zero coverage (noslot={n_noslot} nousage={n_nousage}) — join keys broken")
    fv = pl.DataFrame(rows)
    cov = len(rows) / sc.height
    pitch_n = np.array(pitch_n)
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "cut": CUT,
                 "n_scored": sc.height, "n_famvuln": len(rows), "coverage": float(cov),
                 "min50_share": float(np.mean(pitch_n >= 50)) if len(pitch_n) else None}

    df = sc.join(fv, on=["game_pk", "pitcher"], how="left").with_columns(
        (pl.col("K").cast(pl.Float64) - pl.col("expected_K").cast(pl.Float64)).alias("resid_K"),
        (pl.col("famvuln").cast(pl.Float64) * pl.col("projected_tbf").cast(pl.Float64)).alias("fv_tbf"))
    d = df.filter(pl.col("famvuln").is_not_null()).with_columns(
        pl.col("gd").str.slice(0, 4).alias("season"))
    res = d["resid_K"].to_numpy().astype(float)
    f = d["famvuln"].to_numpy().astype(float)
    rep["assoc"] = {"n": int(d.height), "corr_raw": corr(f, res)}
    w = d["whiff_rate_P20"].to_numpy().astype(float)
    v = d["ff_velo_P1"].to_numpy().astype(float)
    m = np.isfinite(f) & np.isfinite(res) & np.isfinite(w) & np.isfinite(v)
    if m.sum() > 50:
        X = np.column_stack([np.ones(m.sum()), w[m], v[m]])
        rep["assoc"]["corr_stuff_conditioned"] = corr(
            f[m] - X @ np.linalg.lstsq(X, f[m], rcond=None)[0],
            res[m] - X @ np.linalg.lstsq(X, res[m], rcond=None)[0])
        rep["assoc"]["n_conditioned"] = int(m.sum())
    dfm = d.with_columns(pl.col("famvuln").mean().over("pitcher").alias("mf"),
                         pl.col("resid_K").mean().over("pitcher").alias("mr"))
    rep["assoc"]["corr_within_pitcher"] = corr(
        (dfm["famvuln"] - dfm["mf"]).to_numpy().astype(float),
        (dfm["resid_K"] - dfm["mr"]).to_numpy().astype(float))
    print(f"assoc: {rep['assoc']}")

    seas = (d.group_by(["pitcher", "season"])
            .agg(pl.col("famvuln").mean().alias("mk"), pl.len().alias("n"))
            .filter(pl.col("n") >= 10))
    piv = seas.pivot(on="season", index="pitcher", values="mk")
    if "2025" in piv.columns and "2026" in piv.columns:
        sub = piv.filter(pl.col("2025").is_not_null() & pl.col("2026").is_not_null())
        r = corr(sub["2025"].to_numpy().astype(float), sub["2026"].to_numpy().astype(float))
        rep["stability"] = {"n_both": int(sub.height), "yoy_r": r,
                            "gate": "PASS" if r >= 0.7 else "FAIL"}
    else:
        rep["stability"] = {"n_both": 0, "yoy_r": None, "gate": "FAIL"}
    print(f"stability: {rep['stability']}")

    tr = d.filter(pl.col("gd") <= CUT)
    te = d.filter(pl.col("gd") > CUT)
    kf = tr["fv_tbf"].to_numpy().astype(float)
    rf = tr["resid_K"].to_numpy().astype(float)
    mt = np.isfinite(kf) & np.isfinite(rf)
    beta = float((kf[mt] @ rf[mt]) / max(kf[mt] @ kf[mt], 1e-12))
    rep["fit"] = {"beta": beta, "n_train": int(mt.sum()), "n_test": int(te.height)}
    bundle: ProbCalibrationBundle = joblib.load(CALIB)
    maps = {ln: bundle.line_maps[k] for k, ln in
            [("2_5", 2.5), ("3_5", 3.5), ("4_5", 4.5), ("5_5", 5.5),
             ("6_5", 6.5), ("7_5", 7.5), ("8_5", 8.5), ("9_5", 9.5)]}

    def probs(kr: np.ndarray, tbf: np.ndarray, ln: float) -> np.ndarray:
        raw = np.array([float(p_strikeouts_ge(ln, k_rate=np.array([k]),
                              projected_tbf=np.array([t]), family="poisson")[0])
                        for k, t in zip(kr, tbf)])
        return maps[ln].transform(raw)

    te = te.with_columns(
        (pl.col("expected_K").cast(pl.Float64)
         + beta * pl.col("fv_tbf").cast(pl.Float64)).alias("xK_adj"))
    te = te.with_columns(
        (pl.col("xK_adj") / pl.col("projected_tbf").cast(pl.Float64)).clip(0.05, 0.45).alias("kr_adj"))
    kr0 = te["k_rate_pred"].to_numpy().astype(float)
    kra = te["kr_adj"].to_numpy().astype(float)
    tbf = te["projected_tbf"].to_numpy().astype(float)
    ks = pl.scan_parquet(SCORED).select(["game_pk", "key_sorted"]).collect()
    kmap = dict(zip(ks["game_pk"].to_list(), ks["key_sorted"].to_list()))
    rec = []
    rb, ra = [], []
    for i, r in enumerate(te.to_dicts()):
        if not (np.isfinite(kr0[i]) and np.isfinite(kra[i]) and np.isfinite(tbf[i])):
            continue
        for ln in LINES:
            rec.append({"gd": r["gd"], "key": kmap.get(r["game_pk"]), "line": float(ln)})
            rb.append(probs(np.array([kr0[i]]), np.array([tbf[i]]), ln)[0])
            ra.append(probs(np.array([kra[i]]), np.array([tbf[i]]), ln)[0])
    cand = pl.DataFrame(rec).with_columns(pl.Series("p_base", np.array(rb)),
                                          pl.Series("p_adj", np.array(ra)))
    panel = pl.read_parquet(PANEL).select(["gd", "key", "line", "y", "p_book_close"])
    cmpf = cand.join(panel, on=["gd", "key", "line"], how="inner").filter(
        pl.col("p_book_close").is_not_null())
    y = cmpf["y"].to_numpy().astype(float)
    pb, pa, pk = (cmpf[c].to_numpy().astype(float) for c in ("p_base", "p_adj", "p_book_close"))
    rep["brier"] = {"n": int(cmpf.height),
                    "base": float(np.mean((pb - y) ** 2)),
                    "adj": float(np.mean((pa - y) ** 2)),
                    "book": float(np.mean((pk - y) ** 2))}
    rep["brier"]["gain"] = rep["brier"]["base"] - rep["brier"]["adj"]
    karr = te["K"].cast(pl.Float64).to_numpy().astype(float)
    xa = te["xK_adj"].to_numpy().astype(float)
    x0 = te["expected_K"].cast(pl.Float64).to_numpy().astype(float)
    mf = np.isfinite(karr) & np.isfinite(xa) & np.isfinite(x0)
    rep["mae"] = {"mae_base": float(np.mean(np.abs(x0[mf] - karr[mf]))),
                  "mae_adj": float(np.mean(np.abs(xa[mf] - karr[mf])))}
    print(f"beta={beta:.4f} MAE {rep['mae']['mae_base']:.4f}->{rep['mae']['mae_adj']:.4f} "
          f"Brier n={rep['brier']['n']} base={rep['brier']['base']:.4f} "
          f"adj={rep['brier']['adj']:.4f} book={rep['brier']['book']:.4f} "
          f"gain={rep['brier']['gain']:+.5f}")
    rep["kill"] = "SURVIVE" if rep["brier"]["gain"] >= 0.0005 else "KILL"
    out = ODDS_DIR / "ws9_famvuln_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
