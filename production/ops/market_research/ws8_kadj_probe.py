"""WS8 kAdj probe v1 — usage-weighted per-pitch CSW residual (post hoc, research).

KSplit homework, first cut: for each start G (strictly prior dates only),
  kadj = sum_pt usage_prior5_pt * (pitcher_roll20_csw_pt - league_prior_csw_pt)

- League prior: expanding pitch-weighted CSW per pitch_type over dates < G.
- Pitcher roll: pitch-weighted CSW per pitch_type over prior 20 starts (< G).
- Usage weights: pitch shares over prior 5 starts (< G).
- Gate: >=5 prior starts AND >=300 prior pitches, else null (hard shrink).

Tests (SOP: single-feature, chrono CUT=2026-05-23, live-equivalent baseline):
  1. Coverage + stability gate (pitcher-season-mean YoY r, needs >=0.7).
  2. Berkson: corr(kadj,resid_K) raw / stuff-conditioned / within-pitcher.
  3. Challenger: OLS resid_K ~ kadj_tbf (=kadj*projected_tbf) through origin on
     TRAIN; apply to TEST; Poisson + WS1c-Platt probs; Brier vs recomputed
     live-equivalent baseline on the SAME universe-joined subset.
Kill: TEST Brier gain vs baseline < 0.0005.

Writes artifacts/odds_log/ws8_kadj_report.json. No live change.
"""
from __future__ import annotations

import argparse
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
PITCH = ROOT / "data" / "processed" / "pitch_type_games.parquet"
PANEL = ROOT / "artifacts" / "odds_log" / "universe_panel.parquet"
CALIB = ROOT / "artifacts" / "models" / "prob_calibration_ws1c_platt_20260910_012559.joblib"
ODDS_DIR = ROOT / "artifacts" / "odds_log"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
CUT = "2026-05-23"
MIN_PRIOR_STARTS = 5
MIN_PRIOR_PITCHES = 300
ROLL_N = 20
USAGE_N = 5


def build_league_prior(pt: pl.DataFrame) -> dict[tuple[str, str], float]:
    """(pitch_type, gd_str) -> expanding prior-date pitch-weighted CSW mean."""
    daily = (
        pt.group_by(["pitch_type", "game_date"])
        .agg(pl.col("CSW").sum().alias("csw"), pl.col("Pitches").sum().alias("pit"))
        .sort(["pitch_type", "game_date"])
        .with_columns(
            pl.col("csw").cum_sum().shift(1).over("pitch_type").alias("pcsw"),
            pl.col("pit").cum_sum().shift(1).over("pitch_type").alias("ppit"),
        )
        .with_columns(
            pl.when(pl.col("ppit") > 0)
            .then(pl.col("pcsw") / pl.col("ppit"))
            .otherwise(None)
            .alias("prior_mean")
        )
    )
    out: dict[tuple[str, str], float] = {}
    for r in daily.select(["pitch_type", "game_date", "prior_mean"]).to_dicts():
        if r["prior_mean"] is not None:
            out[(r["pitch_type"], str(r["game_date"]))] = float(r["prior_mean"])
    return out


def build_kadj(sc: pl.DataFrame, pt: pl.DataFrame, league: dict) -> pl.DataFrame:
    # Per-pitcher start history, strictly-prior lookups by date.
    pt_by_pitcher: dict[int, list[dict]] = {}
    for r in pt.sort(["game_date", "game_pk"]).to_dicts():
        pt_by_pitcher.setdefault(int(r["pitcher"]), []).append(r)
    # Index starts per pitcher sorted by (date, game_pk)
    rows = []
    for r in sc.sort(["game_date", "game_pk"]).to_dicts():
        pid = int(r["pitcher"])
        gdate = str(r["game_date"])
        hist = [h for h in pt_by_pitcher.get(pid, []) if str(h["game_date"]) < gdate]
        starts = sorted({(str(h["game_date"]), int(h["game_pk"])) for h in hist})
        n_prior = len(starts)
        tot_pit = sum(int(h["Pitches"]) for h in hist)
        if n_prior < MIN_PRIOR_STARTS or tot_pit < MIN_PRIOR_PITCHES:
            rows.append({"game_pk": r["game_pk"], "pitcher": pid,
                         "kadj": None, "n_prior": n_prior, "prior_pitches": tot_pit})
            continue
        last20 = set(starts[-ROLL_N:])
        last5 = set(starts[-USAGE_N:])
        roll_csw: dict[str, list[int]] = {}
        roll_pit: dict[str, int] = {}
        use_pit: dict[str, int] = {}
        use_tot = 0
        for h in hist:
            key = (str(h["game_date"]), int(h["game_pk"]))
            if key in last20:
                roll_csw.setdefault(h["pitch_type"], [0, 0])
                roll_csw[h["pitch_type"]][0] += int(h["CSW"])
                roll_csw[h["pitch_type"]][1] += int(h["Pitches"])
            if key in last5:
                use_pit[h["pitch_type"]] = use_pit.get(h["pitch_type"], 0) + int(h["Pitches"])
                use_tot += int(h["Pitches"])
        kadj = 0.0
        wsum = 0.0
        for ptype, pcount in use_pit.items():
            w = pcount / use_tot if use_tot else 0.0
            csw, pit = roll_csw.get(ptype, (0, 0))
            if pit <= 0:
                continue
            base = league.get((ptype, gdate))
            if base is None:
                continue
            kadj += w * (csw / pit - base)
            wsum += w
        rows.append({"game_pk": r["game_pk"], "pitcher": pid,
                     "kadj": (kadj / wsum * wsum) if wsum else None,
                     "n_prior": n_prior, "prior_pitches": tot_pit})
    return pl.DataFrame(rows, strict=False)


def corr(a: np.ndarray, b: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 10 or a[m].std() == 0 or b[m].std() == 0:
        return float("nan")
    return float(np.corrcoef(a[m], b[m])[0, 1])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()

    sc = (
        pl.scan_parquet(SCORED)
        .select(["gd", "game_date", "game_pk", "pitcher", "key_sorted", "K",
                 "expected_K", "k_rate_pred", "projected_tbf",
                 "whiff_rate_P20", "ff_velo_P1"])
        .collect()
        .filter(pl.col("K").is_not_null() & pl.col("expected_K").is_not_null()
                & pl.col("k_rate_pred").is_not_null()
                & pl.col("projected_tbf").is_not_null())
        .with_columns(pl.col("game_date").cast(pl.Date))
    )
    pt = (
        pl.scan_parquet(PITCH)
        .select(["game_date", "game_pk", "pitcher", "pitch_type", "Pitches", "CSW"])
        .collect()
        .with_columns(pl.col("game_date").cast(pl.Date))
        .filter(pl.col("Pitches") > 0)
    )
    print(f"scored starts: {sc.height}, pitch rows: {pt.height}")
    league = build_league_prior(pt)
    kj = build_kadj(sc, pt, league)
    cov = kj.filter(pl.col("kadj").is_not_null())
    print(f"kadj coverage: {cov.height}/{kj.height} = {cov.height / max(kj.height, 1):.3f}")

    df = sc.join(kj, on=["game_pk", "pitcher"], how="left").with_columns(
        (pl.col("K").cast(pl.Float64) - pl.col("expected_K").cast(pl.Float64)).alias("resid_K"),
        (pl.col("kadj").cast(pl.Float64) * pl.col("projected_tbf").cast(pl.Float64)).alias("kadj_tbf"),
    )
    d = df.filter(pl.col("kadj").is_not_null()).with_columns(
        pl.col("gd").str.slice(0, 4).alias("season")
    )
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "cut": CUT,
                 "n_scored": sc.height, "n_kadj": int(d.height),
                 "coverage": float(cov.height / max(kj.height, 1))}

    # 1. Stability gate: pitcher-season mean kadj YoY (min 10 starts each season).
    seas = (d.group_by(["pitcher", "season"])
            .agg(pl.col("kadj").mean().alias("mk"), pl.len().alias("n"))
            .filter(pl.col("n") >= 10))
    piv = seas.pivot(on="season", index="pitcher", values="mk")
    rep["stability"] = {"n_pitchers_total": int(seas["pitcher"].n_unique())}
    cols = [c for c in piv.columns if c != "pitcher"]
    if "2025" in cols and "2026" in cols:
        sub = piv.filter(pl.col("2025").is_not_null() & pl.col("2026").is_not_null())
        r = corr(sub["2025"].to_numpy().astype(float), sub["2026"].to_numpy().astype(float))
        rep["stability"].update({"n_both": int(sub.height), "yoy_r": r,
                                 "gate": "PASS" if r >= 0.7 else "FAIL"})
    else:
        rep["stability"].update({"n_both": 0, "yoy_r": None, "gate": "FAIL"})
    print(f"stability: {rep['stability']}")

    # 2. Berkson: raw / stuff-conditioned / within-pitcher.
    res = d["resid_K"].to_numpy().astype(float)
    k = d["kadj"].to_numpy().astype(float)
    rep["assoc"] = {"n": int(d.height), "corr_raw": corr(k, res)}
    w = d["whiff_rate_P20"].to_numpy().astype(float)
    v = d["ff_velo_P1"].to_numpy().astype(float)
    m = np.isfinite(k) & np.isfinite(res) & np.isfinite(w) & np.isfinite(v)
    if m.sum() > 50:
        X = np.column_stack([np.ones(m.sum()), w[m], v[m]])
        rk = k[m] - X @ np.linalg.lstsq(X, k[m], rcond=None)[0]
        rr = res[m] - X @ np.linalg.lstsq(X, res[m], rcond=None)[0]
        rep["assoc"]["corr_stuff_conditioned"] = corr(rk, rr)
        rep["assoc"]["n_conditioned"] = int(m.sum())
    dfm = d.with_columns(
        pl.col("kadj").mean().over("pitcher").alias("mk_p"),
        pl.col("resid_K").mean().over("pitcher").alias("mr_p"))
    rep["assoc"]["corr_within_pitcher"] = corr(
        (dfm["kadj"] - dfm["mk_p"]).to_numpy().astype(float),
        (dfm["resid_K"] - dfm["mr_p"]).to_numpy().astype(float))
    print(f"assoc: {rep['assoc']}")

    # 3. Challenger: OLS resid_K ~ kadj_tbf through origin on TRAIN.
    tr = d.filter(pl.col("gd") <= CUT)
    te = d.filter(pl.col("gd") > CUT)
    ktr = tr["kadj_tbf"].to_numpy().astype(float)
    rtr = tr["resid_K"].to_numpy().astype(float)
    mt = np.isfinite(ktr) & np.isfinite(rtr)
    beta = float((ktr[mt] @ rtr[mt]) / max(ktr[mt] @ ktr[mt], 1e-12))
    rep["fit"] = {"beta": beta, "n_train": int(mt.sum()), "n_test": int(te.height)}
    print(f"beta={beta:.4f} train_n={mt.sum()} test_n={te.height}")

    bundle: ProbCalibrationBundle = joblib.load(CALIB)
    maps = {float(ln): bundle.line_maps[k] for k, ln in
            [("2_5", 2.5), ("3_5", 3.5), ("4_5", 4.5), ("5_5", 5.5),
             ("6_5", 6.5), ("7_5", 7.5), ("8_5", 8.5), ("9_5", 9.5)]}

    def probs(kr: np.ndarray, tbf: np.ndarray, ln: float) -> np.ndarray:
        raw = np.array([float(p_strikeouts_ge(ln, k_rate=np.array([k]),
                              projected_tbf=np.array([t]), family="poisson")[0])
                        for k, t in zip(kr, tbf)])
        return maps[ln].transform(raw)

    te = te.with_columns(
        (pl.col("expected_K").cast(pl.Float64)
         + beta * pl.col("kadj_tbf").cast(pl.Float64)).alias("xK_adj"))
    te = te.with_columns(
        (pl.col("xK_adj") / pl.col("projected_tbf").cast(pl.Float64))
        .clip(0.05, 0.45).alias("kr_adj"))
    panel = pl.read_parquet(PANEL).select(["gd", "key", "line", "y", "p_book_close"])
    # MAE delta on test starts first (no join needed).
    karr = te["K"].cast(pl.Float64).to_numpy()
    xa = te["xK_adj"].to_numpy().astype(float)
    x0 = te["expected_K"].cast(pl.Float64).to_numpy()
    mf = np.isfinite(karr) & np.isfinite(xa) & np.isfinite(x0)
    rep["mae"] = {"n": int(mf.sum()),
                  "mae_base": float(np.mean(np.abs(x0[mf] - karr[mf]))),
                  "mae_adj": float(np.mean(np.abs(xa[mf] - karr[mf])))}
    print(f"MAE base={rep['mae']['mae_base']:.4f} adj={rep['mae']['mae_adj']:.4f}")

    # Brier on the universe-joined TEST subset (same n for base + challenger).
    kr0 = te["k_rate_pred"].to_numpy().astype(float)
    kra = te["kr_adj"].to_numpy().astype(float)
    tbf = te["projected_tbf"].to_numpy().astype(float)
    gd = te["gd"].to_list()
    key = te["key_sorted"].to_list()
    rows_p, rows_b, ys, lns, gds, kys = [], [], [], [], [], []
    for i in range(te.height):
        if not (np.isfinite(kr0[i]) and np.isfinite(kra[i]) and np.isfinite(tbf[i])):
            continue
        for ln in LINES:
            rows_b.append(probs(np.array([kr0[i]]), np.array([tbf[i]]), ln)[0])
            rows_p.append(probs(np.array([kra[i]]), np.array([tbf[i]]), ln)[0])
    # Rebuild frame aligned with (gd,key,line) order used above.
    rec = []
    for i in range(te.height):
        if not (np.isfinite(kr0[i]) and np.isfinite(kra[i]) and np.isfinite(tbf[i])):
            continue
        for ln in LINES:
            rec.append({"gd": gd[i], "key": key[i], "line": float(ln)})
    cand = pl.DataFrame(rec)
    cand = cand.with_columns(pl.Series("p_base", np.array(rows_b)),
                             pl.Series("p_adj", np.array(rows_p)))
    cmpf = cand.join(panel, on=["gd", "key", "line"], how="inner").filter(
        pl.col("p_book_close").is_not_null())
    y = cmpf["y"].to_numpy().astype(float)
    pb = cmpf["p_base"].to_numpy().astype(float)
    pa = cmpf["p_adj"].to_numpy().astype(float)
    pk = cmpf["p_book_close"].to_numpy().astype(float)
    rep["brier"] = {"n": int(cmpf.height),
                    "base": float(np.mean((pb - y) ** 2)),
                    "adj": float(np.mean((pa - y) ** 2)),
                    "book": float(np.mean((pk - y) ** 2))}
    rep["brier"]["gain"] = rep["brier"]["base"] - rep["brier"]["adj"]
    rep["brier"]["skill_adj_vs_book"] = float(np.mean((pk - y) ** 2) - np.mean((pa - y) ** 2))
    print(f"Brier n={rep['brier']['n']} base={rep['brier']['base']:.4f} "
          f"adj={rep['brier']['adj']:.4f} book={rep['brier']['book']:.4f} "
          f"gain={rep['brier']['gain']:+.5f}")
    rep["per_line"] = []
    for ln in LINES:
        s = cmpf.filter(pl.col("line") == ln)
        if s.height < 50:
            continue
        yy = s["y"].to_numpy().astype(float)
        rep["per_line"].append({"line": ln, "n": int(s.height),
            "brier_base": float(np.mean((s["p_base"].to_numpy().astype(float) - yy) ** 2)),
            "brier_adj": float(np.mean((s["p_adj"].to_numpy().astype(float) - yy) ** 2)),
            "brier_book": float(np.mean((s["p_book_close"].to_numpy().astype(float) - yy) ** 2))})
    rep["kill"] = "SURVIVE" if rep["brier"]["gain"] >= 0.0005 else "KILL"
    out = ODDS_DIR / "ws8_kadj_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
