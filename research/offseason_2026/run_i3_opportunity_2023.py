"""I3 ordered starter-only opportunity scored runner (ONE run, 2023).

Implements `research/offseason_2026/pregame-opportunity-contract.md`
(frozen 2026-10-08, sha recorded in the manifest). LABELED: a
CHRONOLOGICAL FALLBACK DIAGNOSTIC - not a verified 8am pregame
forecast; not production evidence.

Opportunity model: B1 FIRST-NINE-OBSERVED-BATTER PROXY - the first
nine DISTINCT batters observed (first-PA order) in the opposing
team's most recent game STRICTLY BEFORE the game's calendar date.
NOT verified starting slots; substitute contamination possible.

Arms on identical rows (the 4,446 training-policy eval pitcher-games):
  I1   saved frozen benchmark (reused PMFs from the scored K-count
       run; reproduction asserted)
  I3a  ordered Poisson-binomial mixture over the B1 proxy card
  I3b  homogeneous p* mixture (latent expected-K parity with I3a,
       asserted 1e-12)
  C2   unchanged combined oracle (saved PMFs; NON-deployable)

Primary: paired count-RPS I3a - I1, date-clustered bootstrap 2000 /
seed 20261001, 95% CI entirely below 0. Secondary: I3a - I3b,
per-origin scores, milestone diagnostics, log-floor counts,
prespecified cap-120 sensitivity. PIT/dispersion descriptive only.

No BF refit. No market inputs, no 2024+ access, no tuning, no
calibration fitting, no production changes. 2023 DEVELOPMENTAL.
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
import lineup_opportunity as lo  # noqa: E402
import pa_k_baseline as pak  # noqa: E402
import run_corrected_history_2023 as rch  # noqa: E402
import run_kcount_integration_2023 as rkc  # noqa: E402
import run_pa_k_baseline_2023 as rpt  # noqa: E402

K_MAX = 24
SEED = 20261001
N_BOOT = 2000
ORIGINS = (date(2023, 4, 15), date(2023, 7, 1), date(2023, 8, 1),
           date(2023, 9, 1))
FINAL = date(2023, 10, 1)
MILESTONES = (6, 7, 8, 9, 10, 12)
LADDER_SENS = (6, 8, 10, 12)
SENS_CAP = 120
SENS_EN_FLAG = 0.1
SENS_ARMS = ("I1", "I3a", "I3b")
ARMS = ("I1", "I3a", "I3b", "C2")
PARITY_TOL = 1e-12
PIT_BINS = 10
PIT_RNG_SEED = 20261001
ALIGN_TOL = 1e-8


class RunFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def build_cards(raw) -> tuple[pl.DataFrame, pl.DataFrame]:
    """FIRST-NINE-OBSERVED-BATTER PROXY per (game_pk, batting team),
    plus the (game_pk, team, date) schedule. Terminal PAs only (no
    truncated_pa), any pitcher; first-PA order = at_bat_number order."""
    bat = (raw.select(["game_pk", "game_date", "batter", "inning_topbot",
                       "at_bat_number", "events", "home_team", "away_team"])
           .filter(pl.col("events").is_not_null()
                   & ~pl.col("events").is_in(["truncated_pa"]))
           .with_columns(
               pl.when(pl.col("inning_topbot") == "Top")
               .then(pl.col("away_team")).otherwise(pl.col("home_team"))
               .alias("team"),
               pl.col("game_date").cast(pl.Date).alias("d")))
    cards = (bat.sort(["game_pk", "at_bat_number"])
             .group_by(["game_pk", "team"])
             .agg(pl.col("batter").unique(maintain_order=True)
                  .alias("order"))
             .with_columns(pl.col("order").list.head(9).alias("card"),
                           pl.col("order").list.len().alias("n_distinct")))
    sched = pl.concat([
        bat.select(["game_pk", "team", "d"]).unique(),
    ], how="vertical").unique(subset=["game_pk", "team"])
    return cards, sched


def _prior_card(card_game: pl.DataFrame, sched: pl.DataFrame,
                team: str, gd) -> tuple[list[int], any, int]:
    """Most recent proxy card with >=9 distinct observed batters for
    `team` strictly before date `gd`. Calendar-date strict (same-day
    doubleheaders never used). No eligible prior game -> B2 fallback
    (flagged by the caller)."""
    prior = (sched.join(card_game.select(["game_pk", "team", "card",
                                          "n_distinct"]),
                        on=["game_pk", "team"], how="inner")
             .filter((pl.col("team") == team) & (pl.col("d") < gd)
                     & (pl.col("n_distinct") >= 9))
             .sort(["d", "game_pk"], descending=True).head(1))
    if prior.height == 0:
        return [], None, -1
    r = prior.row(0, named=True)
    ids = r["card"]
    if len(ids) != 9:
        raise RunFailure("proxy card slot count != 9")
    return list(ids), r["d"], int((gd - r["d"]).days)


def randomized_pit(pmf: np.ndarray, k: np.ndarray, seed: int,
                   bins: int = PIT_BINS) -> dict:
    """U = F(K-1) + V * P(K), V ~ Uniform(0,1); 10-bin histogram.
    Descriptive only (frozen definition, contract item 16)."""
    rng = np.random.default_rng(seed)
    v = rng.uniform(0.0, 1.0, size=len(k))
    u = np.empty(len(k))
    for i in range(len(k)):
        kk = int(k[i])
        f_km1 = float(pmf[i, :max(kk, 0)].sum())
        u[i] = f_km1 + v[i] * float(pmf[i, min(kk, K_MAX - 1)])
    hist, _ = np.histogram(u, bins=bins, range=(0.0, 1.0))
    return {"seed": seed, "bins": bins,
            "hist": [int(h) for h in hist],
            "mean_u": float(u.mean()),
            "status": "descriptive only; never a gate"}


def run_diagnostic(pa23, pa22, keys23, raw23, raw22,
                   kc_preds_path: Path, kc_pmfs_path: Path,
                   bf_preds_path: Path, bf_pmfs_path: Path,
                   out_dir: Path, contract_path: Path) -> dict:
    out_dir = Path(out_dir)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        # ---- frozen inputs -----------------------------------------
        kpreds = pl.read_csv(kc_preds_path)
        kpk = pl.read_parquet(kc_pmfs_path)
        kpreds = kpreds.with_row_index("kc_row")
        n = kpreds.height
        pkI1 = kpk.select(["pkI1_%02d" % i for i in range(K_MAX)]).to_numpy()
        pkC2 = kpk.select(["pkC2_%02d" % i for i in range(K_MAX)]).to_numpy()
        if pkI1.shape != (n, K_MAX) or pkC2.shape != (n, K_MAX):
            raise RunFailure("saved K-count PMF shape mismatch")
        # BF 37-category PMFs aligned by pred_row_idx (provenance chain
        # from the K-count run's verified alignment)
        bf_pmfs = pl.read_parquet(bf_pmfs_path).to_numpy()
        pmB37 = bf_pmfs[:, 37:][kpreds["pred_row_idx"].to_numpy()]
        # sanity: K-count rps_I1 must reproduce from pkI1 on every row
        rps_rep = np.array([kc.count_rps(pkI1[i], int(kpreds["K"][i]))
                            for i in range(n)])
        d_i1 = float(np.abs(rps_rep
                            - kpreds["rps_I1"].to_numpy()).max())
        if d_i1 > ALIGN_TOL:
            raise RunFailure("saved I1 PMF reproduction failed: %g" % d_i1)

        # spine join + identity (fail-loud)
        joined = kpreds.join(
            keys23.select([pl.col("game_pk"),
                           pl.col("forecast_pitcher").alias("pitcher"),
                           pl.col("game_date").alias("spine_date"),
                           "is_home"]),
            on=["game_pk", "pitcher"], how="left")
        if joined["is_home"].null_count() > 0:
            raise RunFailure("eval keys missing from 2023 spine")
        if (joined["game_date"].cast(pl.Utf8)
                != joined["spine_date"].cast(pl.Utf8)).any():
            raise RunFailure("saved game_date does not match spine")
        pa_counts = pa23.group_by(["game_pk", "pitcher"]).agg(
            pl.len().alias("n_pa"), pl.col("y").sum().alias("k_actual"))
        joined = joined.join(pa_counts, on=["game_pk", "pitcher"],
                             how="left")
        if not (joined["PA"] == joined["n_pa"]).all():
            raise RunFailure("BF identity failed")
        if not (joined["K"] == joined["k_actual"]).all():
            raise RunFailure("saved K identity failed vs 2023 table")

        cards, sched = build_cards(raw23)
        pool = pl.concat([pa22, pa23], how="vertical")

        per_origin = []
        row_frames = []
        pk_store = {"I1": [], "I3a": [], "I3b": [], "C2": []}
        parity_max = 0.0
        for origin in ORIGINS:
            ev = joined.filter(pl.col("origin") == str(origin))
            if ev.height == 0:
                raise RunFailure("no eval rows for %s" % origin)
            as_of = pd.Timestamp(origin)
            pr_rates, lg, _ = pak.prior_rates(pool, as_of, "pitcher",
                                              pak.W_SHRINK)
            br_rates, _, _ = pak.prior_rates(pool, as_of, "batter",
                                             pak.W_SHRINK)
            lg_safe = lg if lg == lg else 0.2

            cards_l, dates_l, stale_l, newer_l = [], [], [], []
            slot_p_all = np.empty((ev.height, lo.SLOT_COUNT))
            for r_i, row in enumerate(ev.iter_rows(named=True)):
                ids, cd, gap = _prior_card(cards, sched,
                                           row["batting_team"],
                                           row["spine_date"])
                if not ids:  # B2 league fallback (flagged; 0 in audit)
                    ids = [None] * 9
                    p_bar_slots = np.full(9, lg_safe)
                else:
                    p_bar_slots = lo.slot_probs(
                        ids, pr_rates.get(row["pitcher"], (lg_safe, 0))[0],
                        br_rates, lg, pak.W_SHRINK)
                slot_p_all[r_i] = p_bar_slots
                cards_l.append(";".join(str(x) for x in ids))
                dates_l.append(str(cd) if cd is not None else "B2_FALLBACK")
                stale_l.append(gap)
                newer_l.append(bool(cd is not None and cd > as_of.date()))

            pmf37 = pmB37[[r["pred_row_idx"]
                           for r in ev.iter_rows(named=True)]]
            ext60 = np.array([kc.bf_pmf_from_37(pmf37[i])
                              for i in range(ev.height)])
            ext120 = np.array([kc.bf_pmf_from_37(pmf37[i], cap=SENS_CAP)
                               for i in range(ev.height)])
            en60 = np.array([kc.expected_bf(ext60[i])
                             for i in range(ev.height)])
            en120 = np.array([kc.expected_bf(ext120[i])
                              for i in range(ev.height)])
            p_bar_l1 = ev["p_bar_l1"].to_numpy()
            k_obs = ev["K"].to_numpy()

            pk = {"I1": pkI1[[r["kc_row"]
                              for r in ev.iter_rows(named=True)]],
                  "I3a": np.array([lo.mixture_ordered(ext60[i],
                                                      slot_p_all[i])
                                   for i in range(ev.height)]),
                  "C2": pkC2[[r["kc_row"]
                              for r in ev.iter_rows(named=True)]]}
            # I3b: homogeneous p* comparator (latent expected-K parity)
            p_star = np.array([lo.p_star(ext60[i], slot_p_all[i])
                               for i in range(ev.height)])
            ek_i3a = np.array([lo.expected_k_ordered(ext60[i],
                                                     slot_p_all[i])
                               for i in range(ev.height)])
            par = np.abs(p_star * en60 - ek_i3a)
            parity_max = max(parity_max, float(par.max()))
            if float(par.max()) > PARITY_TOL:
                raise RunFailure("latent expected-K parity failed: %g"
                                 % float(par.max()))
            pk["I3b"] = np.array([kc.combine_count(ext60[i], p_star[i])
                                  for i in range(ev.height)])
            for a in ARMS:
                pk_store[a].append(pk[a])

            e_k = {"I1": p_bar_l1 * en60,
                   "I3a": ek_i3a,
                   "I3b": p_star * en60,
                   "C2": ev["PA"].to_numpy() * ev["p_bar_c2"]
                         .cast(pl.Float64).to_numpy()}
            sc = {a: rkc._row_scores(pk[a], k_obs, e_k[a]) for a in ARMS}

            # cap-120 sensitivity (matched: I1/I3a/I3b recomputed)
            slot120 = np.array([lo.opportunity_sequence(slot_p_all[i],
                                                        SENS_CAP)
                                for i in range(ev.height)])
            pk120 = {
                "I1": np.array([kc.combine_count(ext120[i], p_bar_l1[i])
                                for i in range(ev.height)]),
                "I3a": np.array([lo.mixture_ordered(ext120[i],
                                                    slot_p_all[i])
                                 for i in range(ev.height)]),
            }
            p_star120 = np.array([
                lo.p_star(ext120[i], slot_p_all[i])
                for i in range(ev.height)])
            pk120["I3b"] = np.array([
                kc.combine_count(ext120[i], p_star120[i])
                for i in range(ev.height)])
            sc120 = {a: rkc._row_scores(pk120[a], k_obs, e_k[a])
                     for a in SENS_ARMS}
            d_en = float(en120.mean() - en60.mean())

            rows = pd.DataFrame({
                "origin": str(origin),
                "kc_row": ev["kc_row"].to_numpy(),
                "game_pk": ev["game_pk"].to_numpy(),
                "pitcher": ev["pitcher"].to_numpy(),
                "game_date": ev["game_date"].to_numpy().astype(str),
                "batting_team": ev["batting_team"].to_numpy(),
                "is_home": ev["is_home"].to_numpy(),
                "PA": ev["PA"].to_numpy(),
                "K": k_obs,
                "proxy_card": cards_l,
                "card_date": dates_l,
                "card_staleness_days": stale_l,
                "card_newer_than_rate_origin": newer_l,
                "p_star": p_star,
                "p_bar_l1": p_bar_l1,
                "EN60": en60,
                "EN120": en120,
                "parity_absdiff": par,
            })
            for a in ARMS:
                rows["rps_" + a] = sc[a]["rps"]
                rows["logscore_" + a] = sc[a]["logscore"]
                rows["floorhit_" + a] = sc[a]["floor_hit"].astype(int)
                rows["mae_" + a] = sc[a]["mae"]
                rows["mean_" + a] = e_k[a]
                for m in MILESTONES:
                    rows["mb%d_" % m + a] = np.array(
                        [kc.milestone_brier(pk[a][i], int(k_obs[i]),
                                            MILESTONES)["ge%d" % m]
                         for i in range(ev.height)])
            for a in SENS_ARMS:
                rows["rps120_" + a] = sc120[a]["rps"]
                rows["logscore120_" + a] = sc120[a]["logscore"]
                for m in LADDER_SENS:
                    rows["ge%d_60_" % m + a] = np.array(
                        [kc.exceedance(pk[a][i], m)
                         for i in range(ev.height)])
                    rows["ge%d_120_" % m + a] = np.array(
                        [kc.exceedance(pk120[a][i], m)
                         for i in range(ev.height)])
            # per-row PMF variance for the descriptive dispersion
            # diagnostic (bucket 23 valued at 23: documented slight
            # tail-variance underestimate)
            ks_cat = np.arange(K_MAX)
            for a in ("I1", "I3a"):
                ek_c = (pk[a] * ks_cat).sum(axis=1)
                ek2_c = (pk[a] * ks_cat ** 2).sum(axis=1)
                rows["pvar_" + a] = ek2_c - ek_c ** 2
            row_frames.append(rows)
            per_origin.append({
                "origin": str(origin),
                "n_eval": int(ev.height),
                "card_after_rate_origin": int(sum(newer_l)),
                "card_b2_fallbacks": int(sum(
                    1 for d in dates_l if d == "B2_FALLBACK")),
                "card_staleness_mean_days": float(np.mean(
                    [g for g in stale_l if g >= 0])) if any(
                    g >= 0 for g in stale_l) else None,
                "mean_EN60": float(en60.mean()),
                "mean_EN120": float(en120.mean()),
                "delta_EN": d_en,
                "sensitivity_flag_EN_gt_0p1": bool(
                    abs(d_en) > SENS_EN_FLAG),
                "arm_means": {a: {
                    "mean_rps": float(sc[a]["rps"].mean()),
                    "mean_logscore": float(sc[a]["logscore"].mean()),
                    "floor_hit_rows": int(sc[a]["floor_hit"].sum()),
                    "mean_mae_of_mean": float(sc[a]["mae"].mean()),
                    "mean_milestone_brier": {
                        m: float(np.mean([kc.milestone_brier(
                            pk[a][i], int(k_obs[i]),
                            MILESTONES)["ge%d" % m]
                            for i in range(ev.height)]))
                        for m in MILESTONES}} for a in ARMS},
            })

        all_rows = pd.concat(row_frames, ignore_index=True)
        k_all = all_rows["K"].to_numpy()
        dates = all_rows["game_date"].to_numpy().astype(str)
        pk_all = {a: np.vstack(pk_store[a]) for a in ARMS}
        pooled = {"n": int(len(all_rows)),
                  "label": "chronological fallback diagnostic; NOT a "
                           "verified 8am pregame forecast",
                  "opportunity_model": "FIRST-NINE-OBSERVED-BATTER "
                                       "PROXY (substitute "
                                       "contamination possible)",
                  "parity_max_absdiff": parity_max,
                  "parity_tolerance": PARITY_TOL}
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
                "mean_ladder": {m: float(np.mean(
                    [kc.exceedance(pk_all[a][i], m)
                     for i in range(len(all_rows))]))
                    for m in LADDER_SENS},
            }
        paired = {}
        for comp, (a1, a2) in {
                "I3a_vs_I1_PRIMARY": ("I3a", "I1"),
                "I3a_vs_I3b": ("I3a", "I3b"),
                "I3b_vs_I1_EXPLORATORY": ("I3b", "I1")}.items():
            d = (all_rows["rps_" + a1].to_numpy()
                 - all_rows["rps_" + a2].to_numpy())
            paired[comp] = {
                "comparison_id": "i3_%s__vs__i3_%s" % (a1, a2),
                "slate_date_primary": rch.cluster_bootstrap(
                    d, dates, n_boot=N_BOOT, seed=SEED),
                "mean_rps_%s" % a1: pooled[a1]["mean_rps"],
                "mean_rps_%s" % a2: pooled[a2]["mean_rps"],
            }
        gate = paired["I3a_vs_I1_PRIMARY"]["slate_date_primary"]
        pooled["gate1"] = {
            "definition": "pooled paired count-RPS (I3a - I1) 95% CI "
                          "entirely below 0",
            "estimate": gate["estimate"], "lo95": gate["lo95"],
            "hi95": gate["hi95"], "pass": bool(gate["hi95"] < 0.0)}
        pooled["paired"] = paired
        # descriptive diagnostics (frozen definitions; never a gate)
        pooled["descriptive_pit"] = {
            "I1": randomized_pit(pk_all["I1"], k_all, PIT_RNG_SEED),
            "I3a": randomized_pit(pk_all["I3a"], k_all, PIT_RNG_SEED)}
        pooled["descriptive_dispersion"] = {
            "definition": "observed Var(K) vs mean per-row predicted "
                          "PMF variance (bucket 23 valued at 23; "
                          "slight tail-variance underestimate); "
                          "descriptive only, never a gate",
            "pooled": {a: {
                "obs_var": float(np.var(k_all.astype(float))),
                "mean_pred_var": float(all_rows["pvar_" + a].mean()),
                "ratio": float(np.var(k_all.astype(float))
                               / all_rows["pvar_" + a].mean())}
                for a in ("I1", "I3a")},
            "per_origin": {}}
        for origin in ORIGINS:
            m = (all_rows["origin"].to_numpy() == str(origin))
            obs = float(np.var(k_all[m].astype(float)))
            pooled["descriptive_dispersion"]["per_origin"][str(origin)] = {
                a: {"obs_var": obs,
                    "mean_pred_var": float(all_rows["pvar_" + a][m].mean()),
                    "ratio": obs / float(all_rows["pvar_" + a][m].mean())}
                for a in ("I1", "I3a")}
        pooled["sensitivity_pooled"] = {
            "delta_EN": float(all_rows["EN120"].mean()
                              - all_rows["EN60"].mean()),
            "flag_EN_gt_0p1_any_origin": bool(any(
                po["sensitivity_flag_EN_gt_0p1"] for po in per_origin)),
            "mean_rps_cap60": {a: float(all_rows["rps_" + a].mean())
                               for a in SENS_ARMS},
            "mean_rps_cap120": {a: float(all_rows["rps120_" + a].mean())
                                for a in SENS_ARMS},
            "ladder": {m: {
                "mean_ge_cap60": {a: float(
                    all_rows["ge%d_60_" % m + a].mean())
                    for a in SENS_ARMS},
                "mean_ge_cap120": {a: float(
                    all_rows["ge%d_120_" % m + a].mean())
                    for a in SENS_ARMS},
            } for m in LADDER_SENS},
            "status": "prespecified sensitivity; never a cap selector"}

        # ---- artifacts ----------------------------------------------
        keep = list(all_rows.columns)
        all_rows[keep].to_csv(out_dir / "predictions.csv", index=False)
        pmf_cols = []
        pmf_data = []
        for a in ("I1", "I3a", "I3b", "C2"):
            pmf_cols += ["pk%s_%02d" % (a, i) for i in range(K_MAX)]
            pmf_data.append(pk_all[a])
        pmf_data.append(all_rows["EN60"].to_numpy().reshape(-1, 1))
        pmf_cols.append("EN60")
        pl.DataFrame(np.hstack(pmf_data),
                     schema=pmf_cols).write_parquet(out_dir
                                                    / "pmfs.parquet")
        key_hash = hashlib.sha256(";".join(sorted(
            "%s:%s" % (g, p) for g, p in zip(
                all_rows["game_pk"].astype(str),
                all_rows["pitcher"].astype(str)))).encode()).hexdigest()
        provenance = {
            "opportunity_contract": sha256_file(Path(contract_path)),
            "code_run_i3_opportunity_2023": sha256_file(
                HERE / "run_i3_opportunity_2023.py"),
            "code_lineup_opportunity": sha256_file(
                HERE / "lineup_opportunity.py"),
            "code_kcount_integration_runner": sha256_file(
                HERE / "run_kcount_integration_2023.py"),
            "code_kcount_combiner": sha256_file(
                HERE / "kcount_combiner.py"),
            "code_lineup_prereg_draft": sha256_file(
                HERE / "pregame-opportunity-contract-draft.md"),
            "kc_artifact_predictions_csv": sha256_file(
                Path(kc_preds_path)),
            "kc_artifact_pmfs_parquet": sha256_file(Path(kc_pmfs_path)),
            "bf_artifact_predictions_csv": sha256_file(
                Path(bf_preds_path)),
            "bf_artifact_pmfs_parquet": sha256_file(Path(bf_pmfs_path)),
        }
        kc.validate_provenance(provenance)
        manifest = {
            "lane": "i3_opportunity_2023",
            "status": "COMPLETE",
            "label": "chronological fallback diagnostic; NOT a verified "
                     "8am pregame forecast",
            "opportunity_model": "FIRST-NINE-OBSERVED-BATTER PROXY "
                                 "(substitute contamination possible; "
                                 "prior-date completion unverified)",
            "opportunity_contract": str(contract_path),
            "opportunity_contract_sha256":
                provenance["opportunity_contract"],
            "rate_policy": "strict pre-ORIGIN PA pools (w=150), "
                           "unchanged; card identities may be newer "
                           "than the rate origin (disclosed per row)",
            "origins": [str(o) for o in ORIGINS],
            "row_identity_hash_sha256": key_hash,
            "population": {"n_eval_total": pooled["n"]},
            "per_origin": per_origin,
            "pooled": pooled,
            "provenance": provenance,
            "notes": ("2023 DEVELOPMENTAL; diagnostic only; no BF "
                      "refit; C2 NON-deployable; a failed gate would "
                      "not prove lineups useless - only that this "
                      "stale, possibly contaminated proxy did not "
                      "demonstrate improvement under the tested "
                      "recipe"),
        }
        (out_dir / "i3_opportunity_manifest.json").write_text(
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
    ap.add_argument("--contract", required=True)
    ap.add_argument("--kc-preds", required=True)
    ap.add_argument("--kc-pmfs", required=True)
    ap.add_argument("--bf-preds", required=True)
    ap.add_argument("--bf-pmfs", required=True)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--season-sha", action="append", default=[])
    args = ap.parse_args(argv)

    from run_corrected_history_2023 import (MechanicalFailure,
                                            default_sources,
                                            verify_and_load)
    out_dir = Path(args.out)
    try:
        rch._require_temp_out(out_dir)
        contract = Path(args.contract)
        if not contract.is_file():
            raise RunFailure("missing frozen opportunity contract")
        for p in (args.kc_preds, args.kc_pmfs, args.bf_preds,
                  args.bf_pmfs):
            if not Path(p).is_file():
                raise RunFailure("missing saved artifact: %s" % p)
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
        keys23, _ = rch.audit_identity(unified23)
        keys22, _ = rch.audit_identity(unified22)
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
            pa23, pa22, keys23, raw23, raw22,
            Path(args.kc_preds), Path(args.kc_pmfs),
            Path(args.bf_preds), Path(args.bf_pmfs),
            out_dir, contract)
        manifest["inputs"] = {
            name: {"path": str(Path(s["path"]).resolve()),
                   "sha256": s["sha256"]}
            for name, s in sources.items()}
        kc.validate_provenance(
            {k: v["sha256"] for k, v in manifest["inputs"].items()})
        (out_dir / "i3_opportunity_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="ascii")
        print(json.dumps({"status": manifest["status"],
                          "gate1": manifest["pooled"]["gate1"],
                          "parity_max_absdiff":
                              manifest["pooled"]["parity_max_absdiff"],
                          "n": manifest["pooled"]["n"]}))
        return 0
    except (RunFailure, MechanicalFailure) as exc:
        print("RUN %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
