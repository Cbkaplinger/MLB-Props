"""2024 transfer validation of frozen I3b (ONE canonical run).

Implements `research/offseason_2026/i3b-transfer-freeze-2024.md`
(frozen BEFORE any 2024 outcome read) and the owner work packet
"publication checkpoint + one bounded 2024 transfer-validation run".

Recipe (frozen): BF expanding hazard (CHALLENGER_FEATURES, L2 C=1.0)
-> ext60 overflow extension; shrunk log5 rates (w=150 FIXED by
prereg, cold start = league); B1 previous-game proxy card / B2
league-rate-slot fallback; p* = sum_t S(t) p_t / sum_t S(t);
K|N=n ~ Binomial(n, p*); xBF = E[N], xK = p* E[N].

Pre-registered 2024 translation (freeze doc section 1): hazard-fit
rows = 2022 + 2023 + 2024-to-origin eligible first-pitcher rows;
rate pool = 2022 + 2023 + 2024-to-origin; card pool = 2024 season
only (same-season structure as the 2023 lane). No tuning, no
calibration, no September challenger, no I5 revision, no 2025+.
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

import kcount_combiner as kc  # noqa: E402
import lineup_opportunity as lo  # noqa: E402
import pa_k_baseline as pak  # noqa: E402
import run_corrected_history_2023 as rch  # noqa: E402
import run_i3_opportunity_2023 as r3  # noqa: E402
import run_kcount_integration_2023 as rkc  # noqa: E402
import run_pa_k_baseline_2023 as rpt  # noqa: E402
import run_training_policy_2023 as rtp  # noqa: E402
import workload_spine as ws  # noqa: E402

ORIGINS = (date(2024, 4, 15), date(2024, 7, 1), date(2024, 8, 1),
           date(2024, 9, 1))
NEXT_ORIGIN = {date(2024, 4, 15): date(2024, 7, 1),
               date(2024, 7, 1): date(2024, 8, 1),
               date(2024, 8, 1): date(2024, 9, 1),
               date(2024, 9, 1): date(2024, 10, 1)}
FINAL = date(2024, 10, 1)
COVERAGE_START = date(2022, 1, 1)
K_MAX = 24
W_SHRINK = pak.W_SHRINK
GATE_SEED = 20261001
GATE_BOOT = 2000
FEATURES = rch.CHALLENGER_FEATURES
PA_COLUMNS = rpt.PA_COLUMNS
SPARSE_PRIOR_N = 50
SAVANT_2024_SHA = ("de78a1893aa21e305153f5594987f85b40e4bc0cf5724"
                   "84e995a1416b3c49b33")
GE12_CRITERION = -0.0058  # benchmark 2023 reliability -0.0008 - 0.005
BF_BIAS_CRITERION = 0.35
PIT_BIN_CAP = 1.5


class RunFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _appearances(raw_frames: list[pl.DataFrame]) -> tuple[
        pl.DataFrame, list[dict]]:
    parts: list[pl.DataFrame] = []
    quarantine: list[dict] = []
    for raw in raw_frames:
        pitches = rch._unified_pitches([raw])
        keys, quar = rch.audit_identity(pitches)
        quarantine.extend(quar)
        good = set(keys["game_pk"].to_list())
        key_flag = keys.select(
            "game_pk",
            pl.col("forecast_pitcher").alias("pitcher"),
            pl.lit(True).alias("is_start"))
        game_dates = (pitches.filter(pl.col("game_pk").is_in(good))
                      .select("game_pk", "game_date")
                      .unique(subset=["game_pk"]))
        parts.append(
            rch.bf_proxy_table(pitches.filter(
                pl.col("game_pk").is_in(good)))
            .join(key_flag, on=["game_pk", "pitcher"], how="left")
            .with_columns(pl.col("is_start").fill_null(False))
            .join(game_dates, on="game_pk", how="left")
            .rename({"bf_proxy": "bf"})
            .with_columns(pl.col("bf").alias("pitches"),
                          pl.lit(0, dtype=pl.Int64).alias("outs"))
            .select("game_pk", "pitcher", "game_date", "is_start",
                    "pitches", "outs", "bf"))
    return pl.concat(parts, how="vertical"), quarantine


def _season_frame(raw: pl.DataFrame, appearances: pl.DataFrame,
                  batting_current: pl.DataFrame,
                  batting_prior: pl.DataFrame | None,
                  cur_year: int, prior_year: int,
                  fallback_mean: float) -> pl.DataFrame:
    pitches = rch._unified_pitches([raw])
    keys, _quar = rch.audit_identity(pitches)
    bf, _ex = rch.bf_table_canonical(raw)
    keyed = keys.select(
        "game_pk", pl.col("forecast_pitcher").alias("pitcher"),
        "game_date").join(bf, on=["game_pk", "pitcher"], how="left")
    starts = keyed.filter(pl.col("PA").is_not_null()
                          & (pl.col("PA") >= 1))
    hist = ws.build_appearance_history(
        appearances, keyed, fallback_mean, COVERAGE_START,
        date(cur_year, 12, 31))
    game_meta = (raw.select("game_pk", "home_team", "away_team")
                 .unique(subset=["game_pk"]))
    hand = (raw.select("game_pk", "pitcher", "p_throws")
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
    rated = rch.build_team_rate_features(
        lineup_free, batting_current, batting_prior,
        cur_year=cur_year, prior_year=prior_year)
    frame = (starts.select("game_pk", "pitcher", "game_date", "PA")
             .join(lineup_free.select("game_pk", "pitcher",
                                      "batting_team"),
                   on=["game_pk", "pitcher"], how="left")
             .join(hist.drop("game_date"), on=["game_pk", "pitcher"],
                   how="left")
             .join(rated.select(
                 ["game_pk", "pitcher"] + FEATURES[-2:]
                 + ["rate_std_source", "rate_hand_source",
                    "rate_std_used_fallback", "rate_hand_unknown"]),
                 on=["game_pk", "pitcher"], how="left"))
    if frame.height != starts.height:
        raise RunFailure("feature join dropped rows (%s)" % cur_year)
    return frame


def build_frames_2024(raw22, raw23, raw24, fallback_mean: float):
    appearances, hist_quar = _appearances([raw22, raw23, raw24])
    b22 = rch.build_batting_rows(raw22)
    b23 = rch.build_batting_rows(raw23)
    b24 = rch.build_batting_rows(raw24)
    frame24 = _season_frame(raw24, appearances, b24, b23, 2024, 2023,
                            fallback_mean)
    frame23 = _season_frame(raw23, appearances, b23, b22, 2023, 2022,
                            fallback_mean)
    # 2022 hazard-fit rows are NOT constructible: the frozen
    # prior-year team-rate chain requires 2021 batting rows (absent)
    # and exhausts fail-loud (= BLOCKED per the frozen feature
    # manifest). Documented deviation from the pre-registered
    # "2022+2023+2024" pool: hazard-fit rows = 2023 + 2024-to-origin;
    # 2022 remains available through appearance histories only.
    return frame23, frame24, appearances, hist_quar


def _pa_pool(raw22, raw23, raw24) -> pl.DataFrame:
    out = []
    for raw in (raw22, raw23, raw24):
        pitches = rch._unified_pitches([raw])
        keys, _q = rch.audit_identity(pitches)
        out.append(pak.build_pa_table(
            raw.select(PA_COLUMNS),
            keys.select(["game_pk", pl.col("forecast_pitcher")
                         .alias("pitcher")])))
    return pl.concat(out, how="vertical")


def run_canonical(raw22, raw23, raw24, fallback_mean: float,
                  out_dir: Path, contract_path: Path,
                  gate0_metrics: dict) -> dict:
    out_dir = Path(out_dir)
    rch._require_temp_out(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        frame23, frame24, _apps, hist_quar = \
            build_frames_2024(raw22, raw23, raw24, fallback_mean)
        pdf23 = frame23.to_pandas()
        pdf24 = frame24.to_pandas()
        pdf24["game_date"] = pd.to_datetime(pdf24["game_date"])
        assigned = rch.assign_origins(
            pdf24, tuple(str(o) for o in ORIGINS), str(FINAL))
        pa_pool = _pa_pool(raw22, raw23, raw24)
        k_map = (pa_pool.group_by(["game_pk", "pitcher"])
                 .agg(pl.col("y").sum().alias("K"))
                 .to_pandas().set_index(["game_pk", "pitcher"])["K"])
        cards, sched = r3.build_cards(raw24)

        row_frames = []
        pk_store = []
        per_origin = []
        pit_all = []
        parity_note = []
        for origin in ORIGINS:
            origin_ts = pd.Timestamp(origin)
            nxt_ts = pd.Timestamp(NEXT_ORIGIN[origin])
            train24 = assigned[assigned["game_date"] < origin_ts]
            train = pd.concat([pdf23, train24],
                              ignore_index=True)
            bundle = rtp.fit_arm(train)
            ev = assigned[(assigned["origin"] == str(origin))
                          & (assigned["role"] == "eval")]
            if ev.empty:
                raise RunFailure("no eval rows for %s" % origin)
            pmf37 = rtp.batch_predict(bundle,
                                      ev[FEATURES].to_numpy(float))
            ext60 = np.array([kc.bf_pmf_from_37(pmf37[i])
                              for i in range(len(ev))])
            en60 = np.array([kc.expected_bf(ext60[i])
                             for i in range(len(ev))])
            pr_rates, lg, _n = pak.prior_rates(pa_pool, origin,
                                               "pitcher", W_SHRINK)
            br_rates, _, _ = pak.prior_rates(pa_pool, origin,
                                             "batter", W_SHRINK)
            lg_safe = lg if lg == lg else 0.2
            p_star = np.empty(len(ev))
            prior_n = np.empty(len(ev))
            cards_l, stale_l, fallback_l, newer_l = [], [], [], []
            slot_all = np.empty((len(ev), lo.SLOT_COUNT))
            for i in range(len(ev)):
                row = ev.iloc[i]
                ids, cd, gap = r3._prior_card(cards, sched,
                                              row["batting_team"],
                                              row["game_date"].date())
                if not ids:
                    ids = [None] * 9
                    slot_p = np.full(lo.SLOT_COUNT, lg_safe)
                else:
                    pr_e = pr_rates.get(row["pitcher"], (lg_safe, 0))
                    prior_n[i] = pr_e[1]
                    slot_p = lo.slot_probs(ids, pr_e[0], br_rates,
                                           lg_safe, W_SHRINK)
                slot_all[i] = slot_p
                p_star[i] = lo.p_star(ext60[i], slot_p)
                cards_l.append(";".join("NA" if x is None else str(x)
                                        for x in ids))
                stale_l.append(int(gap) if gap is not None else -1)
                fallback_l.append(0 if cd is not None else 1)
                newer_l.append(bool(cd is not None
                                    and cd > origin))
            pk = np.array([kc.combine_count(ext60[i], p_star[i])
                           for i in range(len(ev))])
            pk_store.append(pk)
            e_k = p_star * en60
            k_obs = np.array([k_map.get((int(r["game_pk"]),
                                         int(r["pitcher"])), np.nan)
                              for _, r in ev.iterrows()])
            if np.isnan(k_obs).any():
                raise RunFailure("missing actual K for %d eval rows"
                                 % int(np.isnan(k_obs).sum()))
            k_i = k_obs.astype(int)
            sc = rkc._row_scores(pk, k_i, e_k)
            pit = r3.randomized_pit(pk, k_i, GATE_SEED)
            pit_all.append(pit)
            rows = pd.DataFrame({
                "origin": str(origin),
                "game_pk": ev["game_pk"].to_numpy(int),
                "pitcher": ev["pitcher"].to_numpy(int),
                "game_date": ev["game_date"].dt.strftime("%Y-%m-%d"),
                "PA": ev["PA"].to_numpy(int),
                "K": k_i,
                "prior_n_pitcher": prior_n.astype(int),
                "card": cards_l,
                "card_stale_days": stale_l,
                "card_b2_fallback": fallback_l,
                "card_newer_than_origin": newer_l,
                "rps_I3b24": sc["rps"],
                "logscore_I3b24": sc["logscore"],
                "floorhit_I3b24": sc["floor_hit"].astype(int),
                "mae_I3b24": sc["mae"],
                "mean_I3b24": e_k,
                "EN60": en60,
                "p_star": p_star,
            })
            for m in (6, 8, 10, 12):
                rows["mb%d" % m] = [
                    kc.milestone_brier(pk[i], int(k_i[i]),
                                       (6, 8, 10, 12))["ge%d" % m]
                    for i in range(len(ev))]
                rows["ge%d" % m] = [kc.exceedance(pk[i], m)
                                    for i in range(len(ev))]
            row_frames.append(rows)
            n_ev = len(ev)
            obs_ge12 = float((k_i >= 12).mean())
            per_origin.append({
                "origin": str(origin),
                "n_train_hazard_2024": int(len(train24)),
                "n_train_hazard_total": int(len(train)),
                "n_eval": n_ev,
                "b2_fallback_rows": int(sum(fallback_l)),
                "card_newer_than_origin_rows": int(sum(newer_l)),
                "debut_rows": int((prior_n == 0).sum()),
                "sparse_rows": int(((prior_n > 0)
                                    & (prior_n < SPARSE_PRIOR_N))
                                   .sum()),
                "mean_rps": float(sc["rps"].mean()),
                "mean_logscore": float(sc["logscore"].mean()),
                "floor_rows": int(sc["floor_hit"].sum()),
                "bf_mean_bias": float(en60.mean() - ev["PA"].mean()),
                "k_mean_bias": float(e_k.mean() - k_i.mean()),
                "ge12_pred": float(rows["ge12"].mean()),
                "ge12_obs": obs_ge12,
                "ge12_events": int((k_i >= 12).sum()),
                "pit_hist": pit["hist"],
            })

        all_rows = pd.concat(row_frames, ignore_index=True)
        n = len(all_rows)
        d_rps = all_rows["rps_I3b24"].to_numpy()
        bias_bf = (all_rows["EN60"].to_numpy()
                   - all_rows["PA"].to_numpy(float))
        bias_k = (all_rows["mean_I3b24"].to_numpy()
                  - all_rows["K"].to_numpy(float))
        dates = all_rows["game_date"].to_numpy()
        ci_rps = rch.cluster_bootstrap(d_rps - d_rps.mean(), dates,
                                       n_boot=GATE_BOOT,
                                       seed=GATE_SEED)
        ci_bfbias = rch.cluster_bootstrap(bias_bf - bias_bf.mean(),
                                          dates, n_boot=GATE_BOOT,
                                          seed=GATE_SEED)
        ci_kbias = rch.cluster_bootstrap(bias_k - bias_k.mean(),
                                         dates, n_boot=GATE_BOOT,
                                         seed=GATE_SEED)
        ge12_pred = float(all_rows["ge12"].mean())
        ge12_obs = float((all_rows["K"].to_numpy() >= 12).mean())
        ge12_rel = ge12_pred - ge12_obs
        pit = {"seed": GATE_SEED,
               "hist": list(np.sum([np.array(p["hist"])
                                    for p in pit_all], axis=0))}
        exp_bin = n / len(pit["hist"])
        pit_tail_ok = (max(pit["hist"][0], pit["hist"][-1])
                       <= PIT_BIN_CAP * exp_bin)
        criteria = {
            "bf_bias_within_0p35": bool(
                abs(float(bias_bf.mean())) <= BF_BIAS_CRITERION),
            "ge12_reliability_not_worse_than_-0p0058": bool(
                ge12_rel >= GE12_CRITERION),
            "pit_tail_bins_within_1p5x": bool(pit_tail_ok),
        }
        pooled = {
            "n": n,
            "label": "2024 transfer validation of frozen I3b "
                     "(chronological fallback diagnostic)",
            "mean_rps": float(d_rps.mean()),
            "mean_rps_ci95": [float(ci_rps["lo95"]
                                    + d_rps.mean()),
                              float(ci_rps["hi95"]
                                    + d_rps.mean())],
            "mean_logscore": float(all_rows["logscore_I3b24"]
                                   .mean()),
            "logscore_floor_rows": int(all_rows["floorhit_I3b24"]
                                       .sum()),
            "mean_mae": float(all_rows["mae_I3b24"].mean()),
            "bf_mean_bias": float(bias_bf.mean()),
            "bf_mean_bias_ci95": [float(ci_bfbias["lo95"]
                                        + bias_bf.mean()),
                                  float(ci_bfbias["hi95"]
                                        + bias_bf.mean())],
            "k_mean_bias": float(bias_k.mean()),
            "k_mean_bias_ci95": [float(ci_kbias["lo95"]
                                       + bias_k.mean()),
                                 float(ci_kbias["hi95"]
                                       + bias_k.mean())],
            "ge12_pred": ge12_pred, "ge12_obs": ge12_obs,
            "ge12_reliability": float(ge12_rel),
            "ge12_events": int((all_rows["K"].to_numpy()
                                >= 12).sum()),
            "b2_fallback_rows": int(all_rows["card_b2_fallback"]
                                    .sum()),
            "debut_rows": int((all_rows["prior_n_pitcher"]
                               == 0).sum()),
            "sparse_rows": int(((all_rows["prior_n_pitcher"] > 0)
                                & (all_rows["prior_n_pitcher"]
                                   < SPARSE_PRIOR_N)).sum()),
            "pit": pit,
            "criteria": criteria,
            "per_origin": per_origin,
        }
        all_rows.to_csv(out_dir / "predictions.csv", index=False)
        pmf_cols = ["pkI3b24_%02d" % i for i in range(K_MAX)]
        pk_all = np.vstack(pk_store)
        pl.DataFrame(pk_all, schema=pmf_cols).write_parquet(
            out_dir / "pmfs.parquet")
        provenance = {
            "i3b_transfer_freeze_2024": sha256_file(
                Path(contract_path)),
            "code_run_i3_transfer_2024": sha256_file(
                HERE / "run_i3_transfer_2024.py"),
            "savant_2024_sha256": SAVANT_2024_SHA,
        }
        kc.validate_provenance(provenance)
        manifest = {
            "lane": "i3b_transfer_2024",
            "status": "COMPLETE",
            "contract": str(contract_path),
            "gate0": gate0_metrics,
            "population": {"n_eval_total": n,
                           "n_hazard_fit_2022": 0,
                           "hazard_pool_deviation":
                               "2022 rows excluded: frozen "
                               "prior-year team-rate chain requires "
                               "2021 (absent); exhaustion = BLOCKED "
                               "per frozen feature manifest; pool = "
                               "2023 + 2024-to-origin",
                           "n_hazard_fit_2023": int(len(pdf23)),
                           "n_history_quarantined":
                               len(hist_quar)},
            "pooled": pooled,
            "provenance": provenance,
            "notes": ("frozen I3b recipe; p* recomputed per row "
                      "(part of the recipe); w=150 fixed by prereg; "
                      "card pool = 2024 season only; rate + hazard "
                      "pool = 2022+2023+2024-prior (pre-registered "
                      "expansion); proxy-card limitation: validates "
                      "the research chain, not a deployable pregame "
                      "forecast"),
        }
        (out_dir / "transfer_2024_manifest.json").write_text(
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
    ap.add_argument("--out", required=True)
    ap.add_argument("--contract", required=True)
    ap.add_argument("--gate0-json", required=True)
    ap.add_argument("--fallback-mean", type=float, required=True)
    args = ap.parse_args(argv)
    data = Path(r"C:\Users\ckaplinger\Downloads\Personal-Projects"
                r"\MLB-Props\data")
    raw22 = pl.read_parquet(data / "Savant-Data" / "regular" / "2022"
                            / "statcast_2022_regular.parquet")
    raw23 = pl.read_parquet(data / "Savant-Data" / "regular" / "2023"
                            / "statcast_2023_regular.parquet")
    raw24 = pl.read_parquet(data / "Savant-Data" / "regular" / "2024"
                            / "statcast_2024_regular.parquet")
    got = sha256_file(data / "Savant-Data" / "regular" / "2024"
                      / "statcast_2024_regular.parquet")
    if got != SAVANT_2024_SHA:
        raise RunFailure("2024 Savant sha mismatch: %s" % got)
    gate0 = json.loads(Path(args.gate0_json).read_text())
    if not gate0.get("bf_agreement_rate", 0) >= 0.99:
        raise RunFailure("Gate 0 not passed - refusing to score")
    manifest = run_canonical(raw22, raw23, raw24,
                             args.fallback_mean, Path(args.out),
                             Path(args.contract), gate0)
    print(json.dumps({"status": manifest["status"],
                      "criteria": manifest["pooled"]["criteria"],
                      "mean_rps": manifest["pooled"]["mean_rps"],
                      "bf_bias": manifest["pooled"]["bf_mean_bias"],
                      "n": manifest["pooled"]["n"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
