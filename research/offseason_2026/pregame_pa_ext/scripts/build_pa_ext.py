"""pregame-pa-ext-v1 BUILD: frozen per-PA projected-batter probability
payload for the 7,194-start bf-workload-v1 cohort.

Registered spec: scripts/preregistration.json (frozen before this build).

Order of operations (freeze protocol):
  G1  daily-state machinery reproduces overnight-p2 features_v3 on every
      eligible realized row (pregame-state-v1 gate, verbatim);
  G2  frozen overnight-p2 checkpoint coefficients reconstructed
      deterministically and verified bit-compatibly (<=1e-8) against the
      stored preds checkpoints (H3_raw/H3_cal/LOG5_raw/LOG5_cal) BEFORE any
      projected-row inference; ABORTS on mismatch;
  G3  cohort integrity: 7,194 unique starts, accepted unique-batter v2
      lineups join without loss, nine distinct projected batters;
  payload computed from PRIOR-ONLY state (explicit per-start forecast
  cutoff; league-rate fill fallback for uncovered slots; both arms share
  the identical per-start BF PMF; P(K=k) = sum_n P(N=n)*Binom(k; n,
  pbar_n)), written and sha256-hashed BEFORE any label join. Realized K is
  never read in this script (preds files are touched only inside G2 as a
  verification oracle; bf_forecasts realized_bf is never selected).

Outputs: data/predictor_payload.parquet, artifacts/h3_models_<block>.joblib,
report.json, manifest.json, reports/build_summary.txt.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import joblib
import numpy as np
import polars as pl

import paext_core as core

WORK = core.WORK
OUT_PAYLOAD = core.PAYLOAD
OUT_REPORT = core.REPORT
OUT_MANIFEST = core.MANIFEST


def load_prereg() -> dict:
    return json.loads(
        (WORK / "scripts" / "preregistration.json").read_text(encoding="ascii"))


def main() -> None:
    prereg = load_prereg()
    pa = pl.read_parquet(core.P2_DATA / "pa_table.parquet")
    feat = pl.read_parquet(core.P2_DATA / "features_v3.parquet")
    fc = (
        pl.read_parquet(core.BFW / "bf_forecasts.parquet")
        .filter(
            (pl.col("game_date") >= core.WINDOW[0])
            & (pl.col("game_date") <= core.WINDOW[1])
        )
        .select(
            "game_pk", "side", "pitcher", "game_date",
            "prior_n", "cold_start", *core.PMF37_COLS,
        )
    )
    proj_u = pl.read_parquet(
        core.PREGAME_STATE / "data" / "projected_lineups_variant_v2.parquet")

    # ---------------- G3 cohort integrity (before anything else)
    assert fc.height == core.EXPECTED_N_STARTS, f"cohort size {fc.height}"
    dup_fc = fc.group_by("game_pk", "side", "pitcher").agg(
        n=pl.len()).filter(pl.col("n") > 1).height
    assert dup_fc == 0, "bf_forecasts cohort keys not unique"
    pairs = proj_u.join(
        fc.select("game_pk", "side", "pitcher", "prior_n", "cold_start",
                  *core.PMF37_COLS),
        on=["game_pk", "side", "pitcher"], how="inner",
    )
    assert pairs.height == core.EXPECTED_N_STARTS, \
        f"projected/cohort join lost rows: {pairs.height}"
    assert (proj_u["nine_distinct"] == 1).all(), \
        "accepted unique-batter v2 must have nine distinct ids per start"

    # ---------------- G1 state machinery (verbatim v1 gate)
    p_daily = core.v1.entity_daily_state(pa, "pitcher")
    b_daily = core.v1.entity_daily_state(pa, "batter")
    lg = core.v1.league_daily_state(pa)
    g1 = core.v1.gate1_state_verification(p_daily, b_daily, lg, feat)
    print("G1 PASS")

    # ---------------- G2 frozen-coefficient reconstruction + verification
    models, g2 = core.fit_models_verified(feat, pa)
    print("G2 PASS: frozen checkpoint verified (<=1e-8) for all blocks")
    for block in core.BLOCKS:
        scaler, lr, (a_h3, b_h3), (a_l5, b_l5) = models[block]
        joblib.dump(
            {"block": block, "scaler": scaler, "logistic": lr,
             "h3_calibrator": (a_h3, b_h3), "l5_calibrator": (a_l5, b_l5)},
            WORK / "artifacts" / f"h3_models_{block}.joblib",
        )

    # ---------------- projected per-PA probabilities (prior-only path)
    long = core.projected_long(pairs)
    pf = core.attach_prior_features(long, p_daily, b_daily, lg)
    pf = core.add_block(pf)
    cutoff_stats = core.assert_cutoff(pf)
    pf = core.arm_probs(pf, models)

    # ---------------- payload assembly (no realized fields anywhere)
    key_cols = ["game_pk", "side", "pitcher", "game_date"]
    wide = pf.pivot(
        on="slot", index=key_cols,
        values=["p_h3_raw", "p_h3_cal", "p_l5_raw", "p_l5_cal"],
        sort_columns=True,
    )
    prov = pf.group_by(key_cols).agg(
        n_fallback_slots=pl.col("slot_uncovered").sum(),
        n_cold_slots=pl.col("cold_start").sum(),
        mean_n_prior_batter=pl.col("n_prior_batter").mean(),
        max_src_date=pl.max_horizontal(core.SRC_DATE_COLS).max(),
    )
    st_raw = pf.pivot(
        on="slot", index=key_cols, values=["src_type_batter"],
        sort_columns=True,
    )
    slot_types = st_raw.rename({
        c: f"slot_src_type_{c}" for c in st_raw.columns if c not in key_cols
    })

    payload = (
        wide.join(prov, on=key_cols, how="inner")
        .join(slot_types, on=key_cols, how="inner")
        .join(
            fc.select("game_pk", "side", "pitcher", "prior_n", "cold_start",
                      *core.PMF37_COLS),
            on=["game_pk", "side", "pitcher"], how="inner",
        )
        .join(
            proj_u.select(
                "game_pk", "side",
                pl.col("nine_distinct"),
                *[pl.col(f"u_slot_{i}").alias(f"batter_slot_{i}")
                  for i in range(1, 10)],
                pl.col("n_fallback_slots").alias("n_fallback_slots_lineup"),
            ),
            on=["game_pk", "side"], how="inner",
        )
        .with_columns(pl.col("game_date").alias("forecast_cutoff"))
        .sort(key_cols)
    )
    # block name per start (fixed date bounds, identical to add_block)
    payload = payload.with_columns(
        pl.when(pl.col("game_date") <= pl.date(2024, 12, 31))
        .then(pl.lit("block_2024H2"))
        .when(pl.col("game_date") <= pl.date(2025, 6, 30))
        .then(pl.lit("block_2025H1"))
        .otherwise(pl.lit("confirm_2025H2"))
        .alias("block")
    )
    assert payload.height == core.EXPECTED_N_STARTS, \
        f"payload rows {payload.height}"

    # per-start count PMFs for the two REGISTERED RAW arms (shared BF PMF)
    n_fb = int(payload["n_fallback_slots"].sum())
    n_fb_lineup = int(payload["n_fallback_slots_lineup"].sum())
    pmf_h3 = np.zeros((payload.height, core.K_MAX))
    pmf_l5 = np.zeros((payload.height, core.K_MAX))
    mean_h3 = np.zeros(payload.height)
    mean_l5 = np.zeros(payload.height)
    p9_h3 = payload.select(
        [f"p_h3_raw_{i}" for i in range(1, 10)]).to_numpy()
    p9_l5 = payload.select(
        [f"p_l5_raw_{i}" for i in range(1, 10)]).to_numpy()
    bf37 = payload.select(core.PMF37_COLS).to_numpy()
    for r in range(payload.height):
        pk, mean_k, _, _ = core.start_count_pmf(p9_h3[r], bf37[r])
        pmf_h3[r] = pk
        mean_h3[r] = mean_k
        pk, mean_k, _, _ = core.start_count_pmf(p9_l5[r], bf37[r])
        pmf_l5[r] = pk
        mean_l5[r] = mean_k
    payload = pl.concat(
        [payload,
         pl.DataFrame(pmf_h3, schema=core.PMF_COLS["h3_raw"]),
         pl.DataFrame(pmf_l5, schema=core.PMF_COLS["l5_raw"]),
         pl.DataFrame({"mean_k_h3_raw": mean_h3, "mean_k_l5_raw": mean_l5}),
         ],
        how="horizontal",
    )
    assert payload.height == core.EXPECTED_N_STARTS

    # freeze: write payload, then hash (BEFORE any label join anywhere)
    payload.write_parquet(OUT_PAYLOAD)
    payload_sha = core.sha256_file(OUT_PAYLOAD)

    # ---------------- coverage stats
    bcols = [f"u_slot_{i}" for i in range(1, 10)]
    nd = np.array([
        len(set(r)) for r in
        proj_u.select(bcols).to_numpy()])
    nine_distinct_ok = bool((nd == 9).all())
    coverage = {
        "n_starts": int(payload.height),
        "n_slate_dates": int(payload["game_date"].n_unique()),
        "window": ["2024-07-01", "2025-12-31"],
        "starts_all9_slots_assigned": int(
            (payload["n_fallback_slots_lineup"] == 0).sum()),
        "total_uncovered_slots": n_fb,
        "total_uncovered_slots_lineup": n_fb_lineup,
        "mean_fallback_slots_per_start": float(
            payload["n_fallback_slots_lineup"].mean()),
        "total_cold_start_slots": int(payload["n_cold_slots"].sum()),
        "mean_n_prior_batter_per_projected_pa": float(
            payload["mean_n_prior_batter"].mean()),
        "nine_distinct_validation_all_starts": nine_distinct_ok,
        "mean_prior_n_pitcher": float(payload["prior_n"].mean()),
        "starts_pitcher_cold_start": int((payload["cold_start"] == 1).sum()),
        "fallback_source_type": core.SOURCE_TYPE_FALLBACK,
        "fallback_occurrences": n_fb,
        "feature_cutoff": {
            **cutoff_stats,
            "rule": "all feature source dates strictly < the start's "
                    "forecast cutoff (scheduled game_date)",
        },
    }

    # ---------------- per-arm mean-K summaries
    def _summ(vals: np.ndarray) -> dict:
        return {
            "mean": float(vals.mean()), "median": float(np.median(vals)),
            "p05": float(np.percentile(vals, 5)),
            "p95": float(np.percentile(vals, 95)),
            "min": float(vals.min()), "max": float(vals.max()),
        }

    mean_k_summary = {
        "h3_raw": _summ(mean_h3),
        "l5_raw": _summ(mean_l5),
        "mean_abs_diff_h3_minus_l5": float(np.abs(mean_h3 - mean_l5).mean()),
        "mean_per_pa_prob_h3_raw": float(p9_h3.mean()),
        "mean_per_pa_prob_l5_raw": float(p9_l5.mean()),
    }

    # ---------------- hashes + gates + notes
    inputs_sha = {}
    for name, path in [
        ("scripts/preregistration.json",
         WORK / "scripts" / "preregistration.json"),
        ("scripts/paext_core.py", WORK / "scripts" / "paext_core.py"),
        ("scripts/build_pa_ext.py", Path(__file__).resolve()),
        ("pregame-state-v1/data/projected_lineups_variant_v2.parquet",
         core.PREGAME_STATE / "data" / "projected_lineups_variant_v2.parquet"),
        ("pregame-state-v1/scripts/preregistration_variant_v2.json",
         core.PREGAME_STATE / "scripts" / "preregistration_variant_v2.json"),
        ("pregame-state-v1/scripts/run_pregame_state_comparison.py",
         core.PREGAME_STATE / "scripts" / "run_pregame_state_comparison.py"),
        ("pregame-state-v1/scripts/run_pregame_state_v3.py",
         core.PREGAME_STATE / "scripts" / "run_pregame_state_v3.py"),
        ("bf-workload-v1/data/bf_forecasts.parquet",
         core.BFW / "bf_forecasts.parquet"),
        ("overnight-p2/data/pa_table.parquet", core.P2_DATA / "pa_table.parquet"),
        ("overnight-p2/data/features_v3.parquet",
         core.P2_DATA / "features_v3.parquet"),
        *[("overnight-p2/" + f, core.P2_DATA / f)
          for f in core.PREDS.values()],
        ("helpers/kcount_combiner.py", core.HELPERS / "kcount_combiner.py"),
    ]:
        inputs_sha[name] = core.sha256_file(path)

    artifact_hashes = {
        f"artifacts/h3_models_{b}.joblib": core.sha256_file(
            WORK / "artifacts" / f"h3_models_{b}.joblib")
        for b in core.BLOCKS
    }

    report = {
        "card": "pregame-pa-ext-v1",
        "created": "2026-10-14",
        "registration": prereg,
        "status": (
            "REGISTERED EXTENSION - payload FROZEN and hashed BEFORE any "
            "label join; the scoring step (scripts/score_pa_ext.py) is NOT "
            "executed in this card. 2026 closed; window 2024-07-01.."
            "2025-12-31 only."),
        "population": {
            "source": "bf-workload-v1 bf_forecasts assessment rows",
            "grain": "(game_pk, side, pitcher) first pitcher of record, "
                     "opener-inclusive; inherited unchanged",
            "n_starts": int(payload.height),
        },
        "projected_state": (
            "accepted pregame-state-v1 unique-batter v2 lineups "
            "(projected_lineups_variant_v2.parquet), slot order unchanged; "
            "no realized batting order, no realized PA sequence, no "
            "current-game outcomes anywhere in the payload path"),
        "arms": {
            "h3_raw": "frozen H3 feature machinery (w=150 priors, 90d EW, "
                      "league cold fallbacks) -> block StandardScaler + "
                      "LogisticRegression(C=1.0) -> RAW output",
            "l5_raw": "corrected league-aware log5 on the same projected "
                      "prior rates (RAW)",
            "calibrated_variants_stored_per_pa": [
                "p_h3_cal_slot_1..9", "p_l5_cal_slot_1..9"],
            "registered_count_pmf_arms": ["h3_raw", "l5_raw"],
        },
        "coefficient_application": {
            "checkpoint": (
                "overnight-p2 stores per-PA preds checkpoints + fit recipe, "
                "NOT serialized coefficients"),
            "applied_by": (
                "deterministic reconstruction of the SAME frozen fit "
                "(identical blocks/windows/features/sklearn settings; no "
                "new information, no tuning), verified bit-compatibly "
                "(<=1e-8) against stored pred_H3_raw/pred_H3_cal/"
                "pred_LOG5_raw/pred_LOG5_cal BEFORE any projected-row "
                "inference - the accepted pregame-state-v1 G2 mechanism"),
            "stop_condition": (
                "if the checkpoints were missing or verification failed, "
                "the build aborts and reports what is missing; on this "
                "lineage verification passed for all three blocks"),
            "verification": g2,
        },
        "gates": {
            "G1_state": g1,
            "G2_checkpoint": g2,
            "G3_cohort": {
                "n_starts": int(payload.height),
                "cohort_keys_unique": True,
                "projected_join_losses": 0,
                "nine_distinct_all_starts": nine_distinct_ok,
            },
            "cutoff_enforcement": cutoff_stats,
        },
        "coverage": coverage,
        "mean_k_summary": mean_k_summary,
        "freeze_protocol": {
            "payload": "data/predictor_payload.parquet",
            "payload_sha256": payload_sha,
            "payload_rows": int(payload.height),
            "payload_columns": int(len(payload.columns)),
            "hashed_before_label_join": True,
            "label_sources_read_during_build": [],
            "note": (
                "realized K is never read in the build. The overnight-p2 "
                "preds files are read ONLY inside G2 as a verification "
                "oracle for the frozen coefficients (their y values "
                "reproduce the stored checkpoint; no y enters any "
                "probability). bf_forecasts realized_bf is never selected. "
                "The label join happens only in scripts/score_pa_ext.py, "
                "which re-verifies the payload hash before reading labels."),
        },
        "tests": {
            "command": "python -m pytest tests/test_pa_ext.py -v",
            "status": "PENDING (recorded post-build in "
                      "reports/test_results.txt)",
        },
        "scoring_command": {
            "script": "scripts/score_pa_ext.py",
            "command": "python scripts/score_pa_ext.py",
            "executed": False,
            "does": (
                "verify payload sha256; label join (realized K from preds, "
                "BF-count checked); per-start count-RPS/logscore/mean-K "
                "RMSE/milestone Briers (PMF-tail exceedance) for h3_raw and "
                "l5_raw; paired comparisons H3-raw vs LOG5-raw with "
                "slate-date bootstrap (2000, seed 20261001); secondary "
                "descriptive comparison vs the accepted v3 uniq calibrated "
                "arms with a <=1e-12 machinery bit-identity gate"),
        },
        "inputs_sha256": inputs_sha,
        "artifact_sha256": artifact_hashes,
        "outputs_sha256": {},
    }
    report["outputs_sha256"]["data/predictor_payload.parquet"] = payload_sha

    summary = [
        "pregame-pa-ext-v1 BUILD summary",
        "=" * 60,
        f"starts: {coverage['n_starts']} (window 2024-07-01..2025-12-31); "
        f"slate dates: {coverage['n_slate_dates']}",
        f"uncovered slots: {n_fb} (fallback inert, as expected); "
        f"cold-start slots: {coverage['total_cold_start_slots']}",
        f"nine distinct projected batters on every start: {nine_distinct_ok}",
        f"cutoff: mean feature-source lag {cutoff_stats['mean_source_lag_days']:.2f} d "
        f"(min {cutoff_stats['min_source_lag_days']} d, all strictly < cutoff)",
        "",
        "per-arm mean-K (E[K] over the shared BF PMF):",
        f"  h3_raw: mean {mean_k_summary['h3_raw']['mean']:.4f} "
        f"median {mean_k_summary['h3_raw']['median']:.4f} "
        f"[p05 {mean_k_summary['h3_raw']['p05']:.3f}, "
        f"p95 {mean_k_summary['h3_raw']['p95']:.3f}]",
        f"  l5_raw: mean {mean_k_summary['l5_raw']['mean']:.4f} "
        f"median {mean_k_summary['l5_raw']['median']:.4f} "
        f"[p05 {mean_k_summary['l5_raw']['p05']:.3f}, "
        f"p95 {mean_k_summary['l5_raw']['p95']:.3f}]",
        f"  mean per-PA prob: h3_raw {mean_k_summary['mean_per_pa_prob_h3_raw']:.6f}"
        f"  l5_raw {mean_k_summary['mean_per_pa_prob_l5_raw']:.6f}",
        "",
        f"payload FROZEN: {OUT_PAYLOAD.name} rows={payload.height} "
        f"cols={len(payload.columns)}",
        f"payload sha256: {payload_sha}",
        "scoring step NOT executed (separate label join; command in report).",
    ]
    (WORK / "reports" / "build_summary.txt").write_text(
        "\n".join(summary) + "\n", encoding="ascii")
    OUT_REPORT.write_text(json.dumps(report, indent=1), encoding="ascii")
    OUT_MANIFEST.write_text(json.dumps(
        {"card": "pregame-pa-ext-v1",
         "created": "2026-10-14",
         "payload": {"path": "data/predictor_payload.parquet",
                     "sha256": payload_sha,
                     "rows": int(payload.height),
                     "columns": int(len(payload.columns)),
                     "frozen_before_label_join": True},
         "inputs_sha256": inputs_sha,
         "artifact_sha256": artifact_hashes,
         "scoring_command": report["scoring_command"],
         "tests": report["tests"]},
        indent=1), encoding="ascii")
    print("\n".join(summary))


if __name__ == "__main__":
    main()
