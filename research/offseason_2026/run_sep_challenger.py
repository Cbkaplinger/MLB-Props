"""September hazard challenger: 2023 dev, 2024 confirm (frozen).

Implements `research/offseason_2026/sep-challenger-contract.md`
(frozen BEFORE any scoring). One mechanism: logit h_t =
logit h_0,t + beta_Sep * I(September), I(September) appended as an
11th feature inside the unchanged `bf_distribution.fit_hazard`
(L2 C=1.0, identical risk-set construction/preprocessing).
p* HELD FIXED per row (reference p*); challenger changes only the
BF PMF. History pools follow the canonized one-prior-season rule.
Within-run reference arm shares the challenger's pools exactly.
"""

from __future__ import annotations

import argparse
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
import run_i3_opportunity_2023 as r3  # noqa: E402
import run_i3_transfer_2024 as rt  # noqa: E402
import run_kcount_integration_2023 as rkc  # noqa: E402
import run_training_policy_2023 as rtp  # noqa: E402
import workload_spine as ws  # noqa: E402

RunFailure = rt.RunFailure
FEATURES = rch.CHALLENGER_FEATURES
CHAL_FEATURES = FEATURES + ["is_september"]
W_SHRINK = pak.W_SHRINK
GATE_SEED = 20261001
GATE_BOOT = 2000
SPARSE_PRIOR_N = 50
COVERAGE_START = date(2022, 1, 1)
SEASON_SHAS = {
    2022: "63d40a4955da73ab8f9b01d87d90dd676acdf8b7447c574a5edf807897724ce4",
    2023: "b9f9db9923badca17e551cf23be8429bfba984361732a8911bf0d68a40d5285f",
    2024: "de78a1893aa21e305153f5594987f85b40e4bc0cf572484e995a1416b3c49b33",
}
SEASONS = {
    2023: {"prior": 2022, "cur": 2023,
           "origins": (date(2023, 4, 15), date(2023, 7, 1),
                       date(2023, 8, 1), date(2023, 9, 1)),
           "final": date(2023, 10, 1), "is_dev": True},
    2024: {"prior": 2023, "cur": 2024,
           "origins": (date(2024, 4, 15), date(2024, 7, 1),
                       date(2024, 8, 1), date(2024, 9, 1)),
           "final": date(2024, 10, 1), "is_dev": False},
}


def _fit_arm(train_pdf: pd.DataFrame, feats: list[str]) -> dict:
    n = len(train_pdf)
    short = int((train_pdf["PA"].to_numpy(dtype=int) < 9).sum())
    if n < rtp.MIN_TRAIN_ROWS or short < rtp.MIN_TRAIN_SHORT_EVENTS:
        raise RunFailure(
            "training gate failed: n=%d short_events=%d (min %d/%d)"
            % (n, short, rtp.MIN_TRAIN_ROWS,
               rtp.MIN_TRAIN_SHORT_EVENTS))
    return bfd.fit_hazard(train_pdf[feats].to_numpy(dtype=float),
                          train_pdf["PA"].to_numpy(dtype=int),
                          list(feats))


def _season_frame_2022(raw22: pl.DataFrame,
                       appearances: pl.DataFrame,
                       b22: pl.DataFrame,
                       fallback_mean: float) -> tuple[pl.DataFrame, int]:
    """2022 hazard-fit frame: pre-filter rows whose opponent team has
    no strictly-prior 2022 game (the frozen prior-year team-rate
    chain has no 2021 source and exhausts fail-loud on those rows).
    Returns (frame, n_excluded)."""
    pitches = rch._unified_pitches([raw22])
    keys, _quar = rch.audit_identity(pitches)
    bf, _ex = rch.bf_table_canonical(raw22)
    keyed = keys.select(
        "game_pk", pl.col("forecast_pitcher").alias("pitcher"),
        "game_date").join(bf, on=["game_pk", "pitcher"], how="left")
    starts = keyed.filter(pl.col("PA").is_not_null()
                          & (pl.col("PA") >= 1))
    hist = ws.build_appearance_history(
        appearances, keyed, fallback_mean, COVERAGE_START,
        date(2022, 12, 31))
    game_meta = (raw22.select("game_pk", "home_team", "away_team")
                 .unique(subset=["game_pk"]))
    hand = (raw22.select("game_pk", "pitcher", "p_throws")
            .unique(subset=["game_pk", "pitcher"]))
    lineup_free = (keyed.join(game_meta, on="game_pk", how="left")
                   .join(hand, on=["game_pk", "pitcher"], how="left")
                   .join(keys.select("game_pk",
                                     pl.col("forecast_pitcher")
                                     .alias("pitcher"), "is_home"),
                         on=["game_pk", "pitcher"], how="left")
                   .with_columns(
                       pl.when(pl.col("is_home"))
                       .then(pl.col("away_team"))
                       .otherwise(pl.col("home_team"))
                       .alias("batting_team"))
                   .with_columns(
                       pl.col("batting_team").alias("opponent_team"),
                       pl.col("p_throws").alias("pitcher_hand")))
    first_game = (b22.group_by("team")
                  .agg(pl.col("game_date").min().alias("first_game")))
    keep = (lineup_free.join(first_game, left_on="batting_team",
                             right_on="team", how="left")
            .filter(pl.col("game_date") > pl.col("first_game"))
            .select(["game_pk", "pitcher"]))
    n_excluded = int(lineup_free.height - keep.height)
    lineup_ok = lineup_free.join(keep, on=["game_pk", "pitcher"],
                                 how="inner")
    starts_ok = starts.join(keep, on=["game_pk", "pitcher"],
                            how="inner")
    rated = rch.build_team_rate_features(
        lineup_ok, b22, None, cur_year=2022, prior_year=2021)
    frame = (starts_ok.select("game_pk", "pitcher", "game_date",
                              "PA")
             .join(lineup_ok.select("game_pk", "pitcher",
                                    "batting_team"),
                   on=["game_pk", "pitcher"], how="left")
             .join(hist.drop("game_date"), on=["game_pk", "pitcher"],
                   how="left")
             .join(rated.select(
                 ["game_pk", "pitcher"] + FEATURES[-2:]
                 + ["rate_std_source", "rate_hand_source",
                    "rate_std_used_fallback", "rate_hand_unknown"]),
                 on=["game_pk", "pitcher"], how="left"))
    if frame.height != starts_ok.height:
        raise RunFailure("feature join dropped rows (2022)")
    return frame, n_excluded


def _pa_pool2(raw_prior: pl.DataFrame, raw_cur: pl.DataFrame,
              pa_cols: list[str]) -> pl.DataFrame:
    out = []
    for raw in (raw_prior, raw_cur):
        pitches = rch._unified_pitches([raw])
        keys, _q = rch.audit_identity(pitches)
        out.append(pak.build_pa_table(
            raw.select(pa_cols),
            keys.select(["game_pk", pl.col("forecast_pitcher")
                         .alias("pitcher")])))
    return pl.concat(out, how="vertical")


def _pit_tail_ok(hist: list[int], n: int, cap: float = 1.5) -> bool:
    exp = n / len(hist)
    return max(hist[0], hist[-1]) <= cap * exp


def _milestone_brier(pk: np.ndarray, k: np.ndarray,
                     milestones=(6, 8, 10, 12)) -> dict:
    out = {}
    for m in milestones:
        ge = np.array([kc.exceedance(pk[i], m) for i in range(len(k))])
        y = (k >= m).astype(float)
        out["ge%d" % m] = float(((ge - y) ** 2).mean())
    return out


def run_season(season: int, raws: dict[int, pl.DataFrame],
               fallback_mean: float, out_dir: Path,
               contract_path: Path) -> dict:
    cfg = SEASONS[season]
    prior, cur = cfg["prior"], cfg["cur"]
    origins, final = cfg["origins"], cfg["final"]
    out_dir = Path(out_dir)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        raw_prior, raw_cur = raws[prior], raws[cur]
        appearances, hist_quar = rt._appearances(
            [raw_prior, raw_cur])
        b_prior = rch.build_batting_rows(raw_prior)
        b_cur = rch.build_batting_rows(raw_cur)
        frame_cur = rt._season_frame(
            raw_cur, appearances, b_cur, b_prior, cur, prior,
            fallback_mean)
        if prior == 2022:
            frame_prior, n_prior_excluded = _season_frame_2022(
                raw_prior, appearances, b_prior, fallback_mean)
        else:
            b_prior_prior = rch.build_batting_rows(raws[prior - 1])
            frame_prior = rt._season_frame(
                raw_prior, appearances, b_prior, b_prior_prior,
                prior, prior - 1, fallback_mean)
            n_prior_excluded = 0
        pdf_prior = frame_prior.to_pandas()
        pdf_cur = frame_cur.to_pandas()
        for pdf in (pdf_prior, pdf_cur):
            pdf["game_date"] = pd.to_datetime(pdf["game_date"])
            pdf["is_september"] = (
                pdf["game_date"].dt.month == 9).astype(int)
        assigned = rch.assign_origins(
            pdf_cur, tuple(str(o) for o in origins), str(final))
        pa_pool = _pa_pool2(raw_prior, raw_cur, rt.PA_COLUMNS)
        k_map = (pa_pool.group_by(["game_pk", "pitcher"])
                 .agg(pl.col("y").sum().alias("K"))
                 .to_pandas().set_index(["game_pk", "pitcher"])["K"])
        cards, sched = r3.build_cards(raw_cur)

        row_frames, pk_ref_store, pk_chal_store = [], [], []
        ext_ref_store, ext_chal_store = [], []
        per_origin = []
        for origin in origins:
            origin_ts = pd.Timestamp(origin)
            train_cur = assigned[assigned["game_date"] < origin_ts]
            train = pd.concat([pdf_prior, train_cur],
                              ignore_index=True)
            ref_bundle = _fit_arm(train, FEATURES)
            chal_bundle = _fit_arm(train, CHAL_FEATURES)
            coef = chal_bundle["model"].coef_[0]
            scale = chal_bundle["preprocess"]["scales"]
            beta_sep = {"standardized": float(coef[-1]),
                        "raw_scale": float(coef[-1] / scale[-1])}
            ev = assigned[(assigned["origin"] == str(origin))
                          & (assigned["role"] == "eval")]
            if ev.empty:
                raise RunFailure("no eval rows for %s" % origin)
            ev = ev.copy()
            ev["is_september"] = (
                ev["game_date"].dt.month == 9).astype(int)
            pmf37_ref = rtp.batch_predict(
                ref_bundle, ev[FEATURES].to_numpy(float))
            pmf37_chal = rtp.batch_predict(
                chal_bundle, ev[CHAL_FEATURES].to_numpy(float))
            ext_ref = np.array([kc.bf_pmf_from_37(pmf37_ref[i])
                                for i in range(len(ev))])
            ext_chal = np.array([kc.bf_pmf_from_37(pmf37_chal[i])
                                 for i in range(len(ev))])
            en_ref = np.array([kc.expected_bf(ext_ref[i])
                               for i in range(len(ev))])
            en_chal = np.array([kc.expected_bf(ext_chal[i])
                                for i in range(len(ev))])
            pr_rates, lg, _n = pak.prior_rates(
                pa_pool, origin, "pitcher", rt.W_SHRINK)
            br_rates, _, _ = pak.prior_rates(
                pa_pool, origin, "batter", rt.W_SHRINK)
            lg_safe = lg if lg == lg else 0.2
            p_star = np.empty(len(ev))
            prior_n = np.empty(len(ev))
            cards_l, stale_l, fallback_l = [], [], []
            slot_all = np.empty((len(ev), lo.SLOT_COUNT))
            for i in range(len(ev)):
                row = ev.iloc[i]
                ids, cd, gap = r3._prior_card(
                    cards, sched, row["batting_team"],
                    row["game_date"].date())
                if not ids:
                    ids = [None] * 9
                    slot_p = np.full(lo.SLOT_COUNT, lg_safe)
                else:
                    pr_e = pr_rates.get(row["pitcher"], (lg_safe, 0))
                    prior_n[i] = pr_e[1]
                    slot_p = lo.slot_probs(ids, pr_e[0], br_rates,
                                           lg_safe, rt.W_SHRINK)
                slot_all[i] = slot_p
                # canonical reference p* (frozen per row; challenger
                # changes only the BF PMF)
                p_star[i] = lo.p_star(ext_ref[i], slot_p)
                cards_l.append(";".join(
                    "NA" if x is None else str(x) for x in ids))
                stale_l.append(int(gap) if gap is not None else -1)
                fallback_l.append(0 if cd is not None else 1)
            pk_ref = np.array([kc.combine_count(ext_ref[i], p_star[i])
                               for i in range(len(ev))])
            pk_chal = np.array([kc.combine_count(ext_chal[i],
                                                 p_star[i])
                                for i in range(len(ev))])
            pk_ref_store.append(pk_ref)
            pk_chal_store.append(pk_chal)
            ext_ref_store.append(ext_ref)
            ext_chal_store.append(ext_chal)
            e_k_ref = p_star * en_ref
            e_k_chal = p_star * en_chal
            k_obs = np.array([k_map.get((int(r["game_pk"]),
                                         int(r["pitcher"])), np.nan)
                              for _, r in ev.iterrows()])
            if np.isnan(k_obs).any():
                raise RunFailure("missing actual K for %d eval rows"
                                 % int(np.isnan(k_obs).sum()))
            k_i = k_obs.astype(int)
            sc_ref = rkc._row_scores(pk_ref, k_i, e_k_ref)
            sc_chal = rkc._row_scores(pk_chal, k_i, e_k_chal)
            pit_ref = r3.randomized_pit(pk_ref, k_i, GATE_SEED)
            pit_chal = r3.randomized_pit(pk_chal, k_i, GATE_SEED)
            rows = pd.DataFrame({
                "origin": str(origin),
                "game_pk": ev["game_pk"].to_numpy(int),
                "pitcher": ev["pitcher"].to_numpy(int),
                "game_date": ev["game_date"].dt.strftime("%Y-%m-%d"),
                "PA": ev["PA"].to_numpy(int),
                "K": k_i,
                "is_september_row": ev["is_september"].to_numpy(int),
                "prior_n_pitcher": prior_n.astype(int),
                "card": cards_l,
                "card_stale_days": stale_l,
                "card_b2_fallback": fallback_l,
                "p_star": p_star,
                "rps_REF": sc_ref["rps"],
                "logscore_REF": sc_ref["logscore"],
                "floorhit_REF": sc_ref["floor_hit"].astype(int),
                "mae_REF": sc_ref["mae"],
                "mean_REF": e_k_ref,
                "EN60_REF": en_ref,
                "rps_CHAL": sc_chal["rps"],
                "logscore_CHAL": sc_chal["logscore"],
                "floorhit_CHAL": sc_chal["floor_hit"].astype(int),
                "mae_CHAL": sc_chal["mae"],
                "mean_CHAL": e_k_chal,
                "EN60_CHAL": en_chal,
            })
            row_frames.append(rows)
            sep_m = ev["is_september"].to_numpy() == 1
            per_origin.append({
                "origin": str(origin),
                "n_train_prior": int(len(pdf_prior)),
                "n_train_cur": int(len(train_cur)),
                "n_eval": int(len(ev)),
                "n_eval_september": int(sep_m.sum()),
                "beta_sep": beta_sep,
                "b2_fallback_rows": int(sum(fallback_l)),
                "mean_rps_REF": float(sc_ref["rps"].mean()),
                "mean_rps_CHAL": float(sc_chal["rps"].mean()),
                "floor_REF": int(sc_ref["floor_hit"].sum()),
                "floor_CHAL": int(sc_chal["floor_hit"].sum()),
                "bf_bias_REF": float(en_ref.mean()
                                     - ev["PA"].mean()),
                "bf_bias_CHAL": float(en_chal.mean()
                                      - ev["PA"].mean()),
                "k_bias_REF": float(e_k_ref.mean() - k_i.mean()),
                "k_bias_CHAL": float(e_k_chal.mean() - k_i.mean()),
                "bf_mae_REF": float(np.abs(
                    en_ref - ev["PA"].to_numpy(float)).mean()),
                "bf_mae_CHAL": float(np.abs(
                    en_chal - ev["PA"].to_numpy(float)).mean()),
                "k_mae_REF": float(np.abs(e_k_ref - k_i).mean()),
                "k_mae_CHAL": float(np.abs(e_k_chal - k_i).mean()),
                "sept_bf_bias_REF": (
                    float(en_ref[sep_m].mean()
                          - ev["PA"].to_numpy(float)[sep_m].mean())
                    if sep_m.sum() else None),
                "sept_bf_bias_CHAL": (
                    float(en_chal[sep_m].mean()
                          - ev["PA"].to_numpy(float)[sep_m].mean())
                    if sep_m.sum() else None),
                "sept_k_bias_REF": (
                    float(e_k_ref[sep_m].mean() - k_i[sep_m].mean())
                    if sep_m.sum() else None),
                "sept_k_bias_CHAL": (
                    float(e_k_chal[sep_m].mean() - k_i[sep_m].mean())
                    if sep_m.sum() else None),
                "pit_hist_REF": pit_ref["hist"],
                "pit_hist_CHAL": pit_chal["hist"],
                "short_p_lt9_REF": float(
                    ext_ref[:, :8].sum(axis=1).mean()),
                "short_p_lt9_CHAL": float(
                    ext_chal[:, :8].sum(axis=1).mean()),
                "short_obs_lt9": float(
                    (ev["PA"].to_numpy(int) < 9).mean()),
            })

        all_rows = pd.concat(row_frames, ignore_index=True)
        n = len(all_rows)
        dates = all_rows["game_date"].to_numpy()
        k_all = all_rows["K"].to_numpy()
        pa_all = all_rows["PA"].to_numpy(float)
        pk_ref_all = np.vstack(pk_ref_store)
        pk_chal_all = np.vstack(pk_chal_store)
        rps_ref = all_rows["rps_REF"].to_numpy()
        rps_chal = all_rows["rps_CHAL"].to_numpy()
        d_full = rps_chal - rps_ref
        ci_full = rch.cluster_bootstrap(d_full, dates,
                                        n_boot=GATE_BOOT,
                                        seed=GATE_SEED)
        sep = all_rows["is_september_row"].to_numpy() == 1
        d_sep = (rps_chal - rps_ref)[sep]
        ci_sep = rch.cluster_bootstrap(
            d_sep, dates[sep], n_boot=GATE_BOOT, seed=GATE_SEED)
        en_ref_all = all_rows["EN60_REF"].to_numpy()
        en_chal_all = all_rows["EN60_CHAL"].to_numpy()
        ek_ref_all = all_rows["mean_REF"].to_numpy()
        ek_chal_all = all_rows["mean_CHAL"].to_numpy()
        sept_bias_bf_ref = float(en_ref_all[sep].mean()
                                 - pa_all[sep].mean())
        sept_bias_bf_chal = float(en_chal_all[sep].mean()
                                  - pa_all[sep].mean())
        sept_bias_k_ref = float(ek_ref_all[sep].mean()
                                - k_all[sep].mean())
        sept_bias_k_chal = float(ek_chal_all[sep].mean()
                                 - k_all[sep].mean())
        pit_sep_ref = r3.randomized_pit(pk_ref_all[sep], k_all[sep],
                                        GATE_SEED)
        pit_sep_chal = r3.randomized_pit(pk_chal_all[sep],
                                         k_all[sep], GATE_SEED)
        ext_ref_all = np.vstack(ext_ref_store)
        ext_chal_all = np.vstack(ext_chal_store)
        short_obs_sep = float((pa_all[sep] < 9).mean())
        err_ref = abs(float(ext_ref_all[sep][:, :8].sum(axis=1)
                            .mean()) - short_obs_sep)
        err_chal = abs(float(ext_chal_all[sep][:, :8].sum(axis=1)
                             .mean()) - short_obs_sep)
        mb_ref = _milestone_brier(pk_ref_all, k_all)
        mb_chal = _milestone_brier(pk_chal_all, k_all)
        apr = all_rows["game_date"].str.slice(5, 7) == "04"
        apr_bf_ref = float(en_ref_all[apr].mean() - pa_all[apr].mean())
        apr_bf_chal = float(en_chal_all[apr].mean()
                            - pa_all[apr].mean())
        floor_ref = int(all_rows["floorhit_REF"].sum())
        floor_chal = int(all_rows["floorhit_CHAL"].sum())
        primary = {
            "sept_bf_absbias_improve_ge_0p15": bool(
                abs(sept_bias_bf_ref) - abs(sept_bias_bf_chal)
                >= 0.15),
            "sept_bf_absbias_ref": sept_bias_bf_ref,
            "sept_bf_absbias_chal": sept_bias_bf_chal,
            "sept_k_worsen_le_0p02": bool(
                abs(sept_bias_k_chal) - abs(sept_bias_k_ref)
                <= 0.02),
            "sept_k_bias_ref": sept_bias_k_ref,
            "sept_k_bias_chal": sept_bias_k_chal,
            "sept_rps_ci": [float(ci_sep["lo95"]),
                            float(ci_sep["hi95"])],
            "sept_rps_not_above_0p0005": bool(ci_sep["hi95"]
                                              <= 0.0005),
            "sept_pit_tails_ok_both": bool(
                _pit_tail_ok(pit_sep_ref["hist"], int(sep.sum()))
                and _pit_tail_ok(pit_sep_chal["hist"],
                                 int(sep.sum()))),
            "sept_short_err_ref": err_ref,
            "sept_short_err_chal": err_chal,
            "sept_short_neutral_or_better": bool(
                err_chal - err_ref < 0.002),
        }
        safety = {
            "full_rps_ci": [float(ci_full["lo95"]),
                            float(ci_full["hi95"])],
            "full_rps_not_below_minus_0p0005": bool(
                ci_full["lo95"] >= -0.0005),
            "bf_mae_ref": float(np.abs(en_ref_all - pa_all).mean()),
            "bf_mae_chal": float(np.abs(en_chal_all - pa_all).mean()),
            "k_mae_ref": float(np.abs(ek_ref_all - k_all).mean()),
            "k_mae_chal": float(np.abs(ek_chal_all - k_all).mean()),
            "bf_mae_worsen_le_0p02": bool(
                float(np.abs(en_chal_all - pa_all).mean())
                - float(np.abs(en_ref_all - pa_all).mean()) <= 0.02),
            "k_mae_worsen_le_0p02": bool(
                float(np.abs(ek_chal_all - k_all).mean())
                - float(np.abs(ek_ref_all - k_all).mean()) <= 0.02),
            "milestone_brier_ref": mb_ref,
            "milestone_brier_chal": mb_chal,
            "milestone_max_increase_le_0p0002": bool(
                max(mb_chal[m] - mb_ref[m] for m in mb_ref)
                <= 0.0002),
            "floor_REF": floor_ref,
            "floor_CHAL": floor_chal,
            "floor_no_increase": bool(floor_chal <= floor_ref),
            "april_bf_bias_ref": apr_bf_ref,
            "april_bf_bias_chal": apr_bf_chal,
            "april_bf_worsen_le_0p10": bool(
                abs(apr_bf_chal) - abs(apr_bf_ref) <= 0.10),
        }
        primary_pass = all([
            primary["sept_bf_absbias_improve_ge_0p15"],
            primary["sept_k_worsen_le_0p02"],
            primary["sept_rps_not_above_0p0005"],
            primary["sept_pit_tails_ok_both"],
            primary["sept_short_neutral_or_better"]])
        safety_pass = all([
            safety["full_rps_not_below_minus_0p0005"],
            safety["bf_mae_worsen_le_0p02"],
            safety["k_mae_worsen_le_0p02"],
            safety["milestone_max_increase_le_0p0002"],
            safety["floor_no_increase"],
            safety["april_bf_worsen_le_0p10"]])
        pooled = {
            "n": n, "n_september": int(sep.sum()),
            "sept_rps_REF": float(rps_ref[sep].mean()),
            "sept_rps_CHAL": float(rps_chal[sep].mean()),
            "full_rps_REF": float(rps_ref.mean()),
            "full_rps_CHAL": float(rps_chal.mean()),
            "primary": primary, "safety": safety,
            "primary_pass": bool(primary_pass),
            "safety_pass": bool(safety_pass),
            "per_origin": per_origin,
        }
        all_rows.to_csv(out_dir / "predictions.csv", index=False)
        cols = (["pkREF_%02d" % i for i in range(24)]
                + ["pkCHAL_%02d" % i for i in range(24)])
        pl.DataFrame(np.hstack([pk_ref_all, pk_chal_all]),
                     schema=cols).write_parquet(out_dir
                                                / "pmfs.parquet")
        provenance = {
            "sep_challenger_contract": rt.sha256_file(
                Path(contract_path)),
            "code_run_sep_challenger": rt.sha256_file(
                HERE / "run_sep_challenger.py"),
        }
        for yr in sorted({prior, cur}):
            provenance["savant_%d_sha256" % yr] = SEASON_SHAS[yr]
        kc.validate_provenance(provenance)
        manifest = {
            "lane": "sep_challenger_%d" % season,
            "status": "COMPLETE",
            "season": season,
            "season_is_dev": bool(cfg["is_dev"]),
            "contract": str(contract_path),
            "population": {
                "n_eval_total": n,
                "n_eval_september": int(sep.sum()),
                "n_hazard_fit_prior": int(len(pdf_prior)),
                "n_prior_excluded_teamrate": (
                    int(n_prior_excluded)
                    if prior == 2022 else 0),
                "n_history_quarantined": len(hist_quar)},
            "pooled": pooled,
            "provenance": provenance,
            "notes": ("reference vs challenger share canonical pools; "
                      "p* frozen per row (reference p*); beta_Sep "
                      "estimated per origin via refit; confirmation "
                      "season evaluated under prior endpoint "
                      "awareness, not pristine-holdout status"),
        }
        (out_dir / ("sep_%d_manifest.json" % season)).write_text(
            json.dumps(manifest, indent=2, default=str),
            encoding="ascii")
        return manifest
    except RunFailure:
        raise
    except Exception as exc:  # noqa: BLE001
        import traceback as _tb
        (out_dir / "failure_receipt.json").write_text(
            json.dumps({"status": "MECHANICAL_FAILURE",
                        "error": "%s: %s" % (type(exc).__name__, exc),
                        "traceback": _tb.format_exc()},
                       indent=2, default=str), encoding="ascii")
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, choices=(2023, 2024),
                    required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--contract", required=True)
    ap.add_argument("--fallback-mean", type=float, required=True)
    args = ap.parse_args(argv)
    season = args.season
    cfg = SEASONS[season]
    prior, cur = cfg["prior"], cfg["cur"]
    data = rt.DATA if hasattr(rt, "DATA") else Path(
        r"C:\Users\ckaplinger\Downloads\Personal-Projects"
        r"\MLB-Props\data")

    def load(year: int) -> pl.DataFrame:
        p = (data / "Savant-Data" / "regular" / str(year)
             / ("statcast_%d_regular.parquet" % year))
        got = rt.sha256_file(p)
        if got != SEASON_SHAS[year]:
            raise RunFailure("Savant %d sha mismatch: %s" % (year,
                                                             got))
        return pl.read_parquet(p)

    raws = {prior: load(prior), cur: load(cur)}
    if prior - 1 not in raws and prior > 2022:
        # prior season's own prior-year chain (e.g. 2022 rows for a
        # 2023 hazard pool in the 2024 confirmation)
        raws[prior - 1] = load(prior - 1)
    manifest = run_season(season, raws, args.fallback_mean,
                          Path(args.out), Path(args.contract))
    print(json.dumps({"status": manifest["status"],
                      "primary_pass": manifest["pooled"][
                          "primary_pass"],
                      "safety_pass": manifest["pooled"][
                          "safety_pass"],
                      "n": manifest["pooled"]["n"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
