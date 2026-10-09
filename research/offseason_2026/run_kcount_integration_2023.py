"""K-count integration scored runner (ONE diagnostic run, 2023).

Implements `research/offseason_2026/kcount-integration-prereg.md`
(frozen 2026-10-08). Combination: P(K=k) = sum_n P(N=n) * Binom(k; n,
p_bar). BF distributions are REUSED from the frozen training-policy
artifacts (no BF refit; positional alignment is proven from the saved
artifact pair before use). PA-K p_bar uses the shrunk log5 benchmark
(w=150) over strictly-prior first-pitcher PA pools (2022 + 2023
pre-origin).

Arms on identical rows (the 4,446 training-policy eval pitcher-games):
  I1      full expanding BF distribution x L1 p_bar (league-average)
  I2      full expanding BF distribution x L2 p_bar (team aggregate)
  C1(L1)  point exposure n_C1 x I1's p_bar      (comparator, per-arm)
  C1(L2)  point exposure n_C1 x I2's p_bar      (comparator, per-arm)
  C2      realized BF x realized-lineup p_bar   (NON-deployable oracle)

Primary gate: pooled paired count-RPS (I1 - C1(L1)), date-clustered
bootstrap 2000 / seed 20261001, CI entirely below 0. Prespecified
cap-120 sensitivity (matched comparator recomputation) is diagnostic
and never a cap selector.

No market inputs, no 2024+ access, no tuning, no calibration fitting,
no production changes. 2023 DEVELOPMENTAL; diagnostic only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import bf_distribution as bfd  # noqa: E402
import kcount_combiner as kc  # noqa: E402
import pa_k_baseline as pak  # noqa: E402
import run_corrected_history_2023 as rch  # noqa: E402
import run_pa_k_baseline_2023 as rpt  # noqa: E402

K_MAX = 24
SEED = 20261001
N_BOOT = 2000
ORIGINS = (date(2023, 4, 15), date(2023, 7, 1), date(2023, 8, 1),
           date(2023, 9, 1))
FINAL = date(2023, 10, 1)
ALIGN_TOL = 1e-8
LOG_FLOOR = 1e-12
MILESTONES = (6, 7, 8, 9, 10, 12)
LADDER_SENS = (6, 8, 10, 12)
RELIABILITY_BANDS = ((0.0, 0.05), (0.05, 0.10), (0.10, 0.20),
                     (0.20, 0.30), (0.30, 1.01))
PBAR_BANDS = ((0.0, 0.18), (0.18, 0.21), (0.21, 0.24), (0.24, 0.28),
              (0.28, 1.01))
SENS_CAP = 120
SENS_EN_FLAG = 0.1
SENS_ARMS = ("I1", "I2", "C1L1", "C1L2")
ARMS = ("I1", "I2", "C1L1", "C1L2", "C2")


class RunFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def point_exposure_pmf(n: int, p: float, k_max: int = K_MAX) -> np.ndarray:
    """Binomial(n, p) over k=0..k_max-1 with the absorbing >=k_max-1
    bucket (same structural convention as kc.combine_count)."""
    ks = np.arange(0, k_max)
    out = kc.binom_pmf(ks, int(n), float(p))
    tail = max(0.0, 1.0 - out.sum())
    out[k_max - 1] += tail
    return out


def verify_saved_alignment(preds: pl.DataFrame, pmfs: np.ndarray) -> None:
    """Prove positional alignment of the saved artifact PAIR from the
    artifacts alone (prereg convention 12): rps_B and q_B must
    reproduce from the saved arm-B PMFs on every row."""
    if preds.height != pmfs.shape[0]:
        raise RunFailure("saved artifact row mismatch: %d vs %d"
                         % (preds.height, pmfs.shape[0]))
    if pmfs.shape[1] != 74:
        raise RunFailure("saved pmfs must have 74 columns (A+B x 37)")
    pmB = pmfs[:, 37:]
    pa = preds["PA"].to_numpy()
    reps = np.array([bfd.rps_score(pmB[i], int(pa[i]))
                     for i in range(preds.height)])
    d_rps = float(np.abs(reps - preds["rps_B"].to_numpy()).max())
    d_q = float(np.abs(pmB[:, :8].sum(axis=1)
                       - preds["q_B"].to_numpy()).max())
    if d_rps > ALIGN_TOL or d_q > ALIGN_TOL:
        raise RunFailure(
            "saved-artifact alignment FAILED: rps_B diff %g, q_B diff %g"
            % (d_rps, d_q))
    if not np.isclose(pmfs[:, :37].sum(axis=1), 1.0, atol=1e-9).all() \
            or not np.isclose(pmB.sum(axis=1), 1.0, atol=1e-9).all():
        raise RunFailure("saved PMFs do not sum to 1")


def _batting_team_map(raw, keys) -> pl.DataFrame:
    """(game_pk, pitcher) -> batting team facing that first pitcher."""
    gm = raw.select("game_pk", "home_team", "away_team").unique(
        subset=["game_pk"])
    return (keys.select([pl.col("game_pk"),
                         pl.col("forecast_pitcher").alias("pitcher"),
                         "is_home"])
            .join(gm, on="game_pk", how="left")
            .with_columns(
                pl.when(pl.col("is_home")).then(pl.col("away_team"))
                .otherwise(pl.col("home_team")).alias("batting_team"))
            .select(["game_pk", "pitcher", "batting_team"]))


def _team_rates(pa_pool: pl.DataFrame, team_map_all: pl.DataFrame,
                as_of, w: float) -> tuple[dict, float]:
    """Shrunk K rates by BATTING team over the strictly-prior pool;
    the league rate is the same one pak.prior_rates computes."""
    prior = (pa_pool.filter(pl.col("game_date") < as_of)
             .join(team_map_all, on=["game_pk", "pitcher"], how="left"))
    if prior["batting_team"].null_count() > 0:
        raise RunFailure("prior-pool rows missing batting team")
    _, lg, _ = pak.prior_rates(pa_pool, as_of, "pitcher", w)
    lg_safe = lg if lg == lg else 0.2
    g = prior.group_by("batting_team").agg(
        pl.col("y").sum().alias("k"), pl.len().alias("n"))
    rates = {r[0]: ((r[1] + w * lg_safe) / (r[2] + w), int(r[2]))
             for r in g.iter_rows()}
    return rates, lg


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def _map_rates(frame: pl.DataFrame, rates: dict, entity: str,
               lg: float) -> tuple[np.ndarray, np.ndarray]:
    lg_safe = lg if lg == lg else 0.2
    vals, ns = [], []
    for v in frame[entity].to_list():
        r, n = rates.get(v, (lg_safe, 0))
        vals.append(r)
        ns.append(n)
    return np.asarray(vals, dtype=float), np.asarray(ns, dtype=int)


def _row_scores(pk: np.ndarray, k: np.ndarray, e_k: np.ndarray
                ) -> dict[str, np.ndarray]:
    """Per-row scores for one arm's count PMFs (summed-RPS convention)."""
    n = len(k)
    rps = np.array([kc.count_rps(pk[i], int(k[i])) for i in range(n)])
    ls = np.array([kc.count_logscore(pk[i], int(k[i])) for i in range(n)])
    floor_hit = np.array(
        [pk[i, min(int(k[i]), K_MAX - 1)] < LOG_FLOOR for i in range(n)])
    mae = np.abs(e_k - k)
    return {"rps": rps, "logscore": ls, "floor_hit": floor_hit,
            "mae": mae}


def _exceed_all(pk: np.ndarray, m: int) -> np.ndarray:
    return np.array([kc.exceedance(pk[i], m) for i in range(len(pk))])


def _reliability(p_ge: np.ndarray, y_ge: np.ndarray) -> list[dict]:
    rows = []
    for lo, hi in RELIABILITY_BANDS:
        m = (p_ge >= lo) & (p_ge < hi)
        n = int(m.sum())
        rows.append({
            "band": "[%g,%g%s" % (lo, hi, ")" if hi <= 1 else "]"),
            "n": n,
            "mean_pred": float(p_ge[m].mean()) if n else None,
            "obs_freq": float(y_ge[m].mean()) if n else None})
    return rows


def _dispersion(k: np.ndarray, n_c1: np.ndarray, p_bar: np.ndarray
                ) -> list[dict]:
    out = []
    for lo, hi in PBAR_BANDS:
        m = (p_bar >= lo) & (p_bar < hi)
        n_b = int(m.sum())
        label = "[%g,%g%s" % (lo, hi, ")" if hi <= 1 else "]")
        if n_b == 0:
            out.append({"band": label, "n": 0, "obs_var": None,
                        "binom_var": None, "ratio": None})
            continue
        var_obs = float(np.var(k[m].astype(float)))
        var_bin = float(np.mean(n_c1[m] * p_bar[m] * (1.0 - p_bar[m])))
        out.append({"band": label, "n": n_b, "obs_var": var_obs,
                    "binom_var": var_bin,
                    "ratio": var_obs / var_bin if var_bin > 0 else None})
    return out


def run_diagnostic(pa23, pa22, keys23, raw23, keys22, raw22,
                   bf_preds_path: Path, bf_pmfs_path: Path,
                   out_dir: Path, prereg_path: Path,
                   bf_manifest_path: Path | None = None) -> dict:
    """Full scored diagnostic on injected frames. Returns manifest."""
    out_dir = Path(out_dir)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        # ---- saved BF artifacts (no refit) -------------------------
        preds = pl.read_csv(bf_preds_path)
        pmfs_np = pl.read_parquet(bf_pmfs_path).to_numpy()
        verify_saved_alignment(preds, pmfs_np)
        pmB37 = pmfs_np[:, 37:]
        preds = preds.with_row_index("pred_row_idx")

        # ---- spine join + identity ---------------------------------
        joined = preds.join(
            keys23.select([pl.col("game_pk"),
                           pl.col("forecast_pitcher").alias("pitcher"),
                           pl.col("game_date").alias("spine_date"),
                           "is_home"]),
            on=["game_pk", "pitcher"], how="left")
        if joined["is_home"].null_count() > 0:
            raise RunFailure("saved eval keys missing from 2023 spine")
        if (joined["game_date"].cast(pl.Utf8)
                != joined["spine_date"].cast(pl.Utf8)).any():
            raise RunFailure("saved game_date does not match spine")
        gm23 = raw23.select("game_pk", "home_team", "away_team").unique(
            subset=["game_pk"])
        gm22 = raw22.select("game_pk", "home_team", "away_team").unique(
            subset=["game_pk"])
        joined = (joined.join(gm23, on="game_pk", how="left")
                  .with_columns(
                      pl.when(pl.col("is_home")).then(pl.col("away_team"))
                      .otherwise(pl.col("home_team"))
                      .alias("batting_team")))
        if joined["batting_team"].null_count() > 0:
            raise RunFailure("eval rows missing opposing team")

        # actual K counts + BF identity (fail-loud)
        pa_counts = pa23.group_by(["game_pk", "pitcher"]).agg(
            pl.len().alias("n_pa"), pl.col("y").sum().alias("k_actual"))
        joined = joined.join(pa_counts, on=["game_pk", "pitcher"],
                             how="left")
        if joined["n_pa"].null_count() > 0:
            raise RunFailure("eval rows missing terminal-PA counts")
        if not (joined["PA"] == joined["n_pa"]).all():
            n_bad = int((joined["PA"] != joined["n_pa"]).sum())
            raise RunFailure("BF identity failed for %d rows" % n_bad)
        if not (joined["k_actual"] <= joined["PA"]).all():
            raise RunFailure("K count exceeds BF for some rows")

        team_map_all = pl.concat(
            [_batting_team_map(raw22, keys22),
             _batting_team_map(raw23, keys23)], how="vertical").unique(
            subset=["game_pk", "pitcher"])
        pool = pl.concat([pa22, pa23], how="vertical")

        per_origin = []
        row_frames = []
        pk_store = {a: [] for a in ARMS}
        for origin in ORIGINS:
            ev = joined.filter(pl.col("origin") == str(origin))
            if ev.height == 0:
                raise RunFailure("no eval rows for %s" % origin)
            as_of = pd.Timestamp(origin)
            prior_rows = int(pool.filter(
                pl.col("game_date") < as_of).height)
            pr_rates, lg, _ = pak.prior_rates(pool, as_of, "pitcher",
                                              pak.W_SHRINK)
            br_rates, _, _ = pak.prior_rates(pool, as_of, "batter",
                                             pak.W_SHRINK)
            tr_rates, _ = _team_rates(pool, team_map_all, as_of,
                                      pak.W_SHRINK)
            lg_safe = lg if lg == lg else 0.2

            p_p, n_p = _map_rates(ev, pr_rates, "pitcher", lg)
            p_t, n_t = _map_rates(ev, tr_rates, "batting_team", lg)
            # L1: league-average batter -> log5 collapses to the shrunk
            # pitcher rate (declared identity, computed via log5 form)
            p_bar_l1 = np.clip(
                _sigmoid(_logit(p_p) + _logit(lg_safe)
                         - _logit(lg_safe)), pak.CLIP_LO, pak.CLIP_HI)
            # L2: opposing-team aggregate batter rate
            p_bar_l2 = np.clip(
                _sigmoid(_logit(p_p) + _logit(p_t) - _logit(lg_safe)),
                pak.CLIP_LO, pak.CLIP_HI)
            # C2: realized-lineup p_bar (NON-deployable oracle)
            ev_pa = pa23.join(ev.select(["game_pk", "pitcher"]),
                              on=["game_pk", "pitcher"], how="inner")
            pb_pa, _ = _map_rates(ev_pa, br_rates, "batter", lg)
            pp_pa, _ = _map_rates(ev_pa, pr_rates, "pitcher", lg)
            z_pa = _logit(pp_pa) + _logit(pb_pa) - _logit(lg_safe)
            lineup = (ev_pa.with_columns(
                        pl.Series("p_pa",
                                  np.clip(_sigmoid(z_pa), pak.CLIP_LO,
                                          pak.CLIP_HI)))
                      .group_by(["game_pk", "pitcher"])
                      .agg(pl.col("p_pa").mean().alias("p_bar_c2"),
                           pl.len().alias("n_lineup")))
            ev = ev.join(lineup, on=["game_pk", "pitcher"], how="left")
            if ev["p_bar_c2"].null_count() > 0:
                raise RunFailure(
                    "realized-lineup p_bar missing for some eval rows")

            # ---- combine (no BF refit) ------------------------------
            pmf37 = pmB37[ev["pred_row_idx"].to_numpy()]
            ext60 = np.array([kc.bf_pmf_from_37(pmf37[i])
                              for i in range(ev.height)])
            ext120 = np.array([kc.bf_pmf_from_37(pmf37[i], cap=SENS_CAP)
                               for i in range(ev.height)])
            en60 = np.array([kc.expected_bf(ext60[i])
                             for i in range(ev.height)])
            en120 = np.array([kc.expected_bf(ext120[i])
                              for i in range(ev.height)])
            n_c1 = np.array([kc.point_exposure_n(pmf37[i])
                             for i in range(ev.height)])
            n_c1_sens = np.array([max(1, int(np.floor(en120[i] + 0.5)))
                                  for i in range(ev.height)])
            k_obs = ev["k_actual"].to_numpy()
            pa_real = ev["PA"].to_numpy()
            p_c2 = ev["p_bar_c2"].to_numpy()
            pk = {
                "I1": np.array([kc.combine_count(ext60[i], p_bar_l1[i])
                                for i in range(ev.height)]),
                "I2": np.array([kc.combine_count(ext60[i], p_bar_l2[i])
                                for i in range(ev.height)]),
                "C1L1": np.array([point_exposure_pmf(n_c1[i], p_bar_l1[i])
                                  for i in range(ev.height)]),
                "C1L2": np.array([point_exposure_pmf(n_c1[i], p_bar_l2[i])
                                  for i in range(ev.height)]),
                "C2": np.array([point_exposure_pmf(int(pa_real[i]),
                                                   p_c2[i])
                                for i in range(ev.height)]),
            }
            e_k = {
                "I1": p_bar_l1 * en60,
                "I2": p_bar_l2 * en60,
                "C1L1": n_c1 * p_bar_l1,
                "C1L2": n_c1 * p_bar_l2,
                "C2": pa_real * p_c2,
            }
            for a in ARMS:
                pk_store[a].append(pk[a])
            sc = {a: _row_scores(pk[a], k_obs, e_k[a]) for a in ARMS}

            # cap-120 sensitivity (matched comparator recomputation)
            pk_sens = {
                "I1": np.array([kc.combine_count(ext120[i], p_bar_l1[i])
                                for i in range(ev.height)]),
                "I2": np.array([kc.combine_count(ext120[i], p_bar_l2[i])
                                for i in range(ev.height)]),
                "C1L1": np.array([point_exposure_pmf(n_c1_sens[i],
                                                     p_bar_l1[i])
                                  for i in range(ev.height)]),
                "C1L2": np.array([point_exposure_pmf(n_c1_sens[i],
                                                     p_bar_l2[i])
                                  for i in range(ev.height)]),
            }
            sc_sens = {a: _row_scores(pk_sens[a], k_obs, e_k[a])
                       for a in SENS_ARMS}
            d_en = float(en120.mean() - en60.mean())
            sens = {
                "cap": SENS_CAP,
                "mean_EN60": float(en60.mean()),
                "mean_EN120": float(en120.mean()),
                "delta_EN": d_en,
                "flag_EN_gt_0p1": bool(abs(d_en) > SENS_EN_FLAG),
                "mean_rps_cap60": {a: float(sc[a]["rps"].mean())
                                   for a in SENS_ARMS},
                "mean_rps_cap120": {a: float(sc_sens[a]["rps"].mean())
                                    for a in SENS_ARMS},
                "mean_logscore_cap60": {
                    a: float(sc[a]["logscore"].mean()) for a in SENS_ARMS},
                "mean_logscore_cap120": {
                    a: float(sc_sens[a]["logscore"].mean())
                    for a in SENS_ARMS},
                "ladder": {m: {
                    "mean_ge_cap60": {a: float(
                        _exceed_all(pk[a], m).mean()) for a in SENS_ARMS},
                    "mean_ge_cap120": {a: float(
                        _exceed_all(pk_sens[a], m).mean())
                        for a in SENS_ARMS},
                } for m in LADDER_SENS},
                "status": "prespecified sensitivity diagnostic; never a "
                          "cap selector",
            }

            rows = pd.DataFrame({
                "origin": str(origin),
                "pred_row_idx": ev["pred_row_idx"].to_numpy(),
                "game_pk": ev["game_pk"].to_numpy(),
                "pitcher": ev["pitcher"].to_numpy(),
                "game_date": ev["game_date"].to_numpy().astype(str),
                "batting_team": ev["batting_team"].to_numpy(),
                "is_home": ev["is_home"].to_numpy(),
                "PA": pa_real,
                "K": k_obs,
                "EN60": en60,
                "EN120": en120,
                "n_c1": n_c1,
                "n_c1_sens": n_c1_sens,
                "p_bar_l1": p_bar_l1,
                "p_bar_l2": p_bar_l2,
                "p_bar_c2": p_c2,
                "n_lineup": ev["n_lineup"].to_numpy(),
                "pitcher_prior_pa": n_p,
                "team_prior_pa": n_t,
            })
            for a in ARMS:
                rows["rps_" + a] = sc[a]["rps"]
                rows["logscore_" + a] = sc[a]["logscore"]
                rows["floorhit_" + a] = sc[a]["floor_hit"].astype(int)
                rows["mae_" + a] = sc[a]["mae"]
                for m in MILESTONES:
                    rows["mb%d_" % m + a] = np.array(
                        [kc.milestone_brier(pk[a][i], int(k_obs[i]),
                                            MILESTONES)["ge%d" % m]
                         for i in range(ev.height)])
                rows["mean_" + a] = e_k[a]
            for a in SENS_ARMS:
                rows["rps120_" + a] = sc_sens[a]["rps"]
                rows["logscore120_" + a] = sc_sens[a]["logscore"]
                for m in LADDER_SENS:
                    rows["ge%d_60_" % m + a] = _exceed_all(pk[a], m)
                    rows["ge%d_120_" % m + a] = _exceed_all(pk_sens[a], m)
            row_frames.append(rows)
            per_origin.append({
                "origin": str(origin),
                "n_eval": int(ev.height),
                "prior_pool_rows": prior_rows,
                "prior_pitchers": len(pr_rates),
                "prior_teams": len(tr_rates),
                "cold_start_pitchers": int((n_p == 0).sum()),
                "cold_start_teams": int((n_t == 0).sum()),
                "league_rate": lg_safe,
                "mean_EN60": float(en60.mean()),
                "mean_EN120": float(en120.mean()),
                "delta_EN": d_en,
                "sensitivity_flag_EN_gt_0p1": bool(
                    abs(d_en) > SENS_EN_FLAG),
                "mean_p_bar_L1": float(p_bar_l1.mean()),
                "mean_p_bar_L2": float(p_bar_l2.mean()),
                "mean_p_bar_C2": float(p_c2.mean()),
            })

        # ---- pooled scoring ----------------------------------------
        all_rows = pd.concat(row_frames, ignore_index=True)
        k_all = all_rows["K"].to_numpy()
        dates = all_rows["game_date"].to_numpy().astype(str)
        pk_all = {a: np.vstack(pk_store[a]) for a in ARMS}
        pooled = {
            "n": int(len(all_rows)),
            "n_unique_dates": int(all_rows["game_date"].nunique()),
            "n_unique_pitchers": int(all_rows["pitcher"].nunique()),
        }
        for a in ARMS:
            pooled[a] = {
                "mean_rps": float(all_rows["rps_" + a].mean()),
                "mean_logscore": float(all_rows["logscore_" + a].mean()),
                "logscore_floor_hit_rows": int(
                    all_rows["floorhit_" + a].sum()),
                "mean_mae_of_mean": float(all_rows["mae_" + a].mean()),
                "mean_milestone_brier": {
                    m: float(all_rows["mb%d_" % m + a].mean())
                    for m in MILESTONES},
                "mean_ladder": {m: float(_exceed_all(pk_all[a], m).mean())
                                for m in LADDER_SENS},
            }
        paired = {}
        for comp, (a1, a2) in {
                "I1_vs_C1L1_PRIMARY": ("I1", "C1L1"),
                "I2_vs_C1L2": ("I2", "C1L2"),
                "I2_vs_I1": ("I2", "I1"),
                "I1_vs_C2_oracle_diagnostic": ("I1", "C2")}.items():
            d = (all_rows["rps_" + a1].to_numpy()
                 - all_rows["rps_" + a2].to_numpy())
            paired[comp] = {
                "comparison_id": "kcount_%s__vs__kcount_%s" % (a1, a2),
                "slate_date_primary": rch.cluster_bootstrap(
                    d, dates, n_boot=N_BOOT, seed=SEED),
                "mean_rps_%s" % a1: pooled[a1]["mean_rps"],
                "mean_rps_%s" % a2: pooled[a2]["mean_rps"],
            }
        gate = paired["I1_vs_C1L1_PRIMARY"]["slate_date_primary"]
        pooled["gate1"] = {
            "definition": "pooled paired count-RPS (I1 - C1L1) 95% CI "
                          "entirely below 0",
            "estimate": gate["estimate"], "lo95": gate["lo95"],
            "hi95": gate["hi95"], "pass": bool(gate["hi95"] < 0.0)}
        pooled["paired"] = paired
        pooled["dispersion_by_p_bar_band"] = _dispersion(
            k_all, all_rows["n_c1"].to_numpy(),
            all_rows["p_bar_l1"].to_numpy())
        pooled["milestone_reliability"] = {
            a: {m: _reliability(_exceed_all(pk_all[a], m),
                                (k_all >= m).astype(float))
                for m in (6, 8, 10, 12)} for a in ("I1", "I2", "C1L1")}
        pooled["sensitivity_pooled"] = {
            "delta_EN": float(all_rows["EN120"].mean()
                              - all_rows["EN60"].mean()),
            "flag_EN_gt_0p1_any_origin": bool(any(
                po["sensitivity_flag_EN_gt_0p1"] for po in per_origin)),
            "mean_rps_cap60": {a: float(all_rows["rps_" + a].mean())
                               for a in SENS_ARMS},
            "mean_rps_cap120": {a: float(all_rows["rps120_" + a].mean())
                                for a in SENS_ARMS},
            "mean_logscore_cap60": {
                a: float(all_rows["logscore_" + a].mean())
                for a in SENS_ARMS},
            "mean_logscore_cap120": {
                a: float(all_rows["logscore120_" + a].mean())
                for a in SENS_ARMS},
            "ladder": {m: {
                "mean_ge_cap60": {a: float(
                    all_rows["ge%d_60_" % m + a].mean())
                    for a in SENS_ARMS},
                "mean_ge_cap120": {a: float(
                    all_rows["ge%d_120_" % m + a].mean())
                    for a in SENS_ARMS},
            } for m in LADDER_SENS},
            "status": "prespecified sensitivity diagnostic; never a cap "
                      "selector",
        }

        # ---- artifacts ----------------------------------------------
        keep = ["origin", "pred_row_idx", "game_pk", "pitcher",
                "game_date", "batting_team", "is_home", "PA", "K",
                "EN60", "EN120", "n_c1", "n_c1_sens", "p_bar_l1",
                "p_bar_l2", "p_bar_c2", "n_lineup", "pitcher_prior_pa",
                "team_prior_pa"]
        for a in ARMS:
            keep += ["rps_" + a, "logscore_" + a, "floorhit_" + a,
                     "mae_" + a, "mean_" + a]
            keep += ["mb%d_" % m + a for m in MILESTONES]
        for a in SENS_ARMS:
            keep += ["rps120_" + a, "logscore120_" + a]
            keep += ["ge%d_60_" % m + a for m in LADDER_SENS]
            keep += ["ge%d_120_" % m + a for m in LADDER_SENS]
        all_rows[keep].to_csv(out_dir / "predictions.csv", index=False)
        pmf_cols = []
        pmf_data = []
        for a in ARMS:
            pmf_cols += ["pk%s_%02d" % (a, i) for i in range(K_MAX)]
            pmf_data.append(pk_all[a])
        pmf_data.append(all_rows["EN60"].to_numpy().reshape(-1, 1))
        pmf_cols.append("EN60")
        pl.DataFrame(np.hstack(pmf_data), schema=pmf_cols).write_parquet(
            out_dir / "pmfs.parquet")

        key_hash = hashlib.sha256(";".join(sorted(
            "%s:%s" % (g, p) for g, p in zip(
                all_rows["game_pk"].astype(str),
                all_rows["pitcher"].astype(str)))).encode()).hexdigest()
        provenance = {
            "preregistration": sha256_file(Path(prereg_path)),
            "code_run_kcount_integration_2023": sha256_file(
                HERE / "run_kcount_integration_2023.py"),
            "code_kcount_combiner": sha256_file(
                HERE / "kcount_combiner.py"),
            "code_pa_k_baseline": sha256_file(HERE / "pa_k_baseline.py"),
            "code_run_pa_k_baseline_2023": sha256_file(
                HERE / "run_pa_k_baseline_2023.py"),
            "code_run_corrected_history_2023": sha256_file(
                HERE / "run_corrected_history_2023.py"),
            "code_run_reconstruction_audit_2023": sha256_file(
                HERE / "run_reconstruction_audit_2023.py"),
            "code_workload_spine": sha256_file(
                HERE / "workload_spine.py"),
            "code_bf_distribution": sha256_file(
                HERE / "bf_distribution.py"),
            "bf_artifact_predictions_csv": sha256_file(
                Path(bf_preds_path)),
            "bf_artifact_pmfs_parquet": sha256_file(Path(bf_pmfs_path)),
        }
        if bf_manifest_path is not None:
            provenance["bf_artifact_manifest"] = sha256_file(
                Path(bf_manifest_path))
        kc.validate_provenance(provenance)  # blocks marker/garbage
        manifest = {
            "lane": "kcount_integration_2023",
            "status": "COMPLETE",
            "preregistration": str(prereg_path),
            "preregistration_sha256": provenance["preregistration"],
            "origins": [str(o) for o in ORIGINS],
            "final_date": str(FINAL),
            "k_support": {"k_max": K_MAX,
                          "absorbing_bucket": ">=23",
                          "bf_support_assumption": "BF>60 has zero "
                          "model support (support/truncation "
                          "assumption, not a factual impossibility)"},
            "logscore_floor": LOG_FLOOR,
            "row_identity_hash_sha256": key_hash,
            "population": {
                "n_eval_total": pooled["n"],
                "pa_2023_first_pitcher": int(pa23.height),
                "pa_2022_first_pitcher": int(pa22.height)},
            "per_origin": per_origin,
            "pooled": pooled,
            "provenance": provenance,
            "notes": ("2023 DEVELOPMENTAL; diagnostic only; no market "
                      "inputs; BF PMFs reused from the frozen "
                      "training-policy artifacts (no refit); C2 is a "
                      "NON-deployable realized-lineup oracle"),
        }
        (out_dir / "kcount_integration_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="ascii")
        return manifest
    except RunFailure:
        raise
    except Exception as exc:  # noqa: BLE001 - receipt then re-raise
        import traceback as _tb
        receipt = {"status": "MECHANICAL_FAILURE",
                   "stage": "run_diagnostic",
                   "error": "%s: %s" % (type(exc).__name__, exc),
                   "traceback": _tb.format_exc()}
        (out_dir / "failure_receipt.json").write_text(
            json.dumps(receipt, indent=2, default=str), encoding="ascii")
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--prereg", required=True)
    ap.add_argument("--bf-preds", required=True)
    ap.add_argument("--bf-pmfs", required=True)
    ap.add_argument("--bf-manifest", default=None)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--season-sha", action="append", default=[])
    args = ap.parse_args(argv)

    from run_corrected_history_2023 import (MechanicalFailure,
                                            default_sources,
                                            verify_and_load)

    out_dir = Path(args.out)
    try:
        rch._require_temp_out(out_dir)
        prereg = Path(args.prereg)
        if not prereg.is_file():
            raise RunFailure("missing preregistration file")
        for p in (args.bf_preds, args.bf_pmfs):
            if not Path(p).is_file():
                raise RunFailure("missing saved BF artifact: %s" % p)
        root = Path(args.data_root) if args.data_root else rch.REPO / "data"
        shas = {}
        for item in args.season_sha or []:
            y, d = item.split(":", 1)
            shas[int(y)] = d.lower()
        sources = default_sources(root, 2023, (2022,), shas)
        raw23 = verify_and_load(sources["savant_2023"])
        raw22 = verify_and_load(sources["savant_2022"])
        if sorted(rch.frame_years(raw23)) != [2023] \
                or sorted(rch.frame_years(raw22)) != [2022]:
            raise RunFailure("period violation")
        unified23 = rch._unified_pitches([raw23])
        unified22 = rch._unified_pitches([raw22])
        keys23, _q23 = rch.audit_identity(unified23)
        keys22, _q22 = rch.audit_identity(unified22)
        PA_COLUMNS = ["game_pk", "game_date", "pitcher", "batter",
                      "stand", "p_throws", "events", "at_bat_number"]
        pa23 = pak.build_pa_table(
            raw23.select(PA_COLUMNS),
            keys23.select(["game_pk",
                           pl.col("forecast_pitcher").alias("pitcher")]))
        pa22 = pak.build_pa_table(
            raw22.select(PA_COLUMNS),
            keys22.select(["game_pk",
                           pl.col("forecast_pitcher").alias("pitcher")]))
        manifest = run_diagnostic(
            pa23, pa22, keys23, raw23, keys22, raw22,
            Path(args.bf_preds), Path(args.bf_pmfs), out_dir, prereg,
            Path(args.bf_manifest) if args.bf_manifest else None)
        manifest["inputs"] = {
            name: {"path": str(Path(s["path"]).resolve()),
                   "sha256": s["sha256"]}
            for name, s in sources.items()}
        kc.validate_provenance(
            {k: v["sha256"] for k, v in manifest["inputs"].items()})
        (out_dir / "kcount_integration_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="ascii")
        print(json.dumps({"status": manifest["status"],
                          "gate1": manifest["pooled"]["gate1"],
                          "n": manifest["pooled"]["n"]}))
        return 0
    except (RunFailure, MechanicalFailure) as exc:
        print("RUN %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
