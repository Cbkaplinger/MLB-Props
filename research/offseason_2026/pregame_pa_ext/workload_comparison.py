"""Workload personalization comparison (W0 pooled vs W1 pitcher-specific
BF), thin wrapper around the REGISTERED machinery.

SYNTHETIC-TESTED ONLY until separately authorized; write-once outputs.
Reuses: m0_multiclass (labels, fit_multinomial, apply_multinomial),
adapter (projected_long, attach_prior_features, start_count_pmfs,
validate_bf37_by_start, bf_pmf_from_37), statcast_event_bridge
(terminal-event labels), baseline_ladder.paired_contrast (slate-date
bootstrap), kc.count_rps. Adds NO statistical machinery.

Primary contrast: delta = RPS(W1) - RPS(W0) per start on identical
assessment keys. W0 computes a per-cutoff pooled empirical BF37 from
ALL first-pitcher-of-record starter outings strictly before each
forecast cutoff (expanding, 2023-01-01 onward, opener-inclusive).
W1 uses the registered bf-workload-v1 pitcher-specific PMFs unchanged.
Both arms share the same keyed PA probabilities (from the multinomial
model), the same assessment cohort, and the same count aggregation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import baseline_ladder as bl  # noqa: E402
from pregame_pa_ext import forecast_states_v2 as fv  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402
from pregame_pa_ext import statcast_event_bridge as seb  # noqa: E402
import kcount_combiner as kc  # noqa: E402

EXECUTION_ACK_TOKEN = "EXECUTE-WORKLOAD-PERSONALIZATION-V1"
EXPERIMENT_ID = "workload_personalization_w0v1"
K_CLASS = m0.K_CLASS
FEATURES = list(m0.FEATURES)
REQ_KEYS = ["game_pk", "side", "pitcher"]
RECON_TOLERANCE = 1e-12
RECON_REF_COLUMN = "rps_ref1_multinomial"
ASSESS_COLUMNS = ["game_pk", "side", "pitcher", "at_bat_number", "batter",
                  "class_label"]
LINEUP_COLUMNS = REQ_KEYS + ["game_date", "nine_distinct"] + [
    f"u_slot_{i}" for i in range(1, 10)]


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cohort_hash(keys: list) -> str:
    """Sorted-key SHA-256 hash. Each key is a (game_pk, side, pitcher)
    tuple. Uses explicit f-string formatting to avoid %-tuple ambiguity."""
    lines = sorted(f"{k[0]}|{k[1]}|{k[2]}" for k in keys)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _require_columns(frame, required, name):
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(f"{name}: missing column(s) {missing}")


def _pooled_bf37_at(pa: pl.DataFrame, cutoff) -> np.ndarray:
    """Pooled BF37 from first-pitcher-of-record outings strictly before
    the cutoff. Add-one smoothing. Registered tail convention.

    Derives one observation per (game_pk, inning_topbot) game-half by
    finding the first pitcher of record (minimum at_bat_number in that
    half), then counting ALL PAs by that pitcher in that half as the
    outing BF. This matches the registered bf-workload-v1 construction
    (opener-inclusive, no starter filter)."""
    pre = pa.filter(
        (pl.col("game_date") >= pl.date(2023, 1, 1))
        & (pl.col("game_date") < cutoff)
    )
    if pre.height == 0:
        return np.full(37, 1.0 / 37.0)
    # first pitcher per (game_pk, inning_topbot): min at_bat_number
    first = (pre.sort("at_bat_number")
             .group_by("game_pk", "inning_topbot", maintain_order=True)
             .first()
             .select("game_pk", "inning_topbot", "pitcher"))
    # count ALL PAs by that pitcher in that game-half = outing BF
    outings = (pre.join(first, on=["game_pk", "inning_topbot", "pitcher"],
                        how="semi")
               .group_by("game_pk", "inning_topbot", "pitcher")
               .agg(realized_bf=pl.len()))
    v = outings["realized_bf"].to_numpy()
    counts = np.zeros(37)
    for b in v:
        counts[min(int(b), 37) - 1] += 1.0
    return (counts + 1.0) / (counts.sum() + 37.0)


def _observed_bf_by_start(pa: pl.DataFrame, keys: list) -> dict:
    """Realized BF per start from the PA source, using the identical
    first-pitcher-of-record construction as the pooled W0 history
    (opener-inclusive): for each (game_pk, side) game-half, the first
    pitcher of record is the pitcher on the minimum-at_bat_number row;
    observed BF is ALL PAs by that pitcher in that half. A start whose
    lineup pitcher is not the first pitcher of record has NO observed
    BF (recorded as null, excluded from BF diagnostics) -- a missing
    source never produces an invented replacement."""
    out = {}
    for key in keys:
        gk, side, p = key
        rows = pa.filter((pl.col("game_pk") == gk)
                         & (pl.col("inning_topbot") == side))
        if rows.height == 0:
            out[key] = None
            continue
        first_pitcher = rows.sort("at_bat_number")["pitcher"][0]
        if int(first_pitcher) != int(p):
            out[key] = None
            continue
        out[key] = int(rows.filter(pl.col("pitcher") == p).height)
    return out


def _bf_diagnostics(pmf37: np.ndarray, observed_bf: int) -> dict:
    """The four registered direct BF diagnostics for one start.

    - bf_rps: discrete RPS over the 37-category BF support, observed BF
      mapped to its category index (overflow bucket absorbs BF >= 37,
      NOT scored as exactly 37).
    - point_mae / mean_bf_error: |E[BF] - obs| and E[BF] - obs, where
      E[BF] uses the EXTENDED distribution (bf_pmf_from_37, cap 60,
      geometric tail), not the truncated 37-category vector.
    - coverage: observed BF within the predicted 50% / 90% central
      intervals of the extended distribution.
    """
    pmf37 = np.asarray(pmf37, dtype=np.float64)
    ext = ad.bf_pmf_from_37(pmf37, cap=60)
    support = np.arange(1, 61)
    mean_bf = float((support * ext).sum())
    cdf = np.cumsum(ext)

    def _central(level):
        lo_q = (1.0 - level) / 2.0
        hi_q = 1.0 - lo_q
        lo = int(support[int(np.searchsorted(cdf, lo_q, side="left"))])
        hi = int(support[min(np.searchsorted(cdf, hi_q, side="left"),
                             len(support) - 1)])
        return lo, hi

    lo50, hi50 = _central(0.5)
    lo90, hi90 = _central(0.9)
    obs = int(observed_bf)
    return {
        "bf_rps": kc.count_rps(pmf37, min(obs, 37) - 1),
        "point_mae": abs(mean_bf - obs),
        "mean_bf_error": mean_bf - obs,
        "in_50": int(lo50 <= obs <= hi50),
        "in_90": int(lo90 <= obs <= hi90),
    }


def _aggregate_bf_diag(per_start_diag: list) -> dict:
    if not per_start_diag:
        return {"n_scored": 0}
    return {
        "n_scored": len(per_start_diag),
        "bf_distribution_rps_mean": float(np.mean(
            [d["bf_rps"] for d in per_start_diag])),
        "point_mae_mean": float(np.mean(
            [d["point_mae"] for d in per_start_diag])),
        "mean_bf_error": float(np.mean(
            [d["mean_bf_error"] for d in per_start_diag])),
        "coverage_50": float(np.mean(
            [d["in_50"] for d in per_start_diag])),
        "coverage_90": float(np.mean(
            [d["in_90"] for d in per_start_diag])),
    }


def run_workload_comparison(
        pa: pl.DataFrame, lineups: pl.DataFrame,
        assessment: pl.DataFrame,
        bf_w1: pl.DataFrame,
        out_dir, *,
        train_start: str, train_end: str,
        execution_ack: str,
        raw_events: list | None = None,
        cohort_keys: pl.DataFrame | None = None,
        expected_cohort_hash: str | None = None,
        reconstruction_reference: pl.DataFrame | None = None,
        reconstruction_reference_sha256: str | None = None,
        input_identities: dict | None = None,
        ack_route: str = "direct-call") -> dict:
    """Execute the workload personalization comparison.

    reconstruction_reference: REQUIRED pinned per-start reference from
    the accepted baseline (multiclass_baseline_per_start_v1.parquet
    schema: REQ_KEYS + rps_ref1_multinomial). The gate fails if it is
    missing, its keys differ from the scored starts, or W1's per-start
    RPS differs by more than RECON_TOLERANCE (1e-12)."""
    if execution_ack != EXECUTION_ACK_TOKEN:
        raise ValueError(
            "execution acknowledgement missing or invalid; refusing "
            "(technical gate only)")
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)
    failure_path = out_dir / "failure_record.json"
    initial_path = out_dir / "receipt_initial.json"

    code_identity = {
        "runner_sha256": _sha_file(Path(__file__)),
        "adapter_sha256": _sha_file(Path(ad.__file__)),
        "m0_multiclass_sha256": _sha_file(Path(m0.__file__)),
        "kcount_combiner_sha256": _sha_file(Path(kc.__file__)),
    }
    config = {
        "experiment_identity": EXPERIMENT_ID,
        "train_window": [train_start, train_end],
        "primary_pair": ["W1_pitcher_specific", "W0_pooled_league"],
        "primary_contrast": "RPS(W1) - RPS(W0) per start",
        "n_boot": 2000, "seed": 20261001,
        "interpretation": ("delta < 0: pitcher-specific workload improves "
                           "count forecasts; CI overlapping zero is "
                           "inconclusive"),
    }
    initial = {"execution_acknowledgement": {"route": ack_route,
               "token": execution_ack},
               "code_identity": code_identity, "config": config,
               "counts": None}
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)

    try:
        # ---- labels: bridge over the ACTUAL schema -------------------
        _require_columns(pa, ["game_date", "game_pk", "at_bat_number",
                              "inning_topbot", "pitcher", "batter", "y"],
                         "PA source")
        if not raw_events:
            raise ValueError("raw_events required")
        pa_labeled, label_acc = seb.attach_terminal_event_labels(
            pa, raw_events, out_dir=out_dir)

        # ---- training split (labeled subset, frozen coefficients) ----
        train = pa_labeled.filter(
            (pl.col("game_date") >= pl.date(
                *map(int, train_start.split("-"))))
            & (pl.col("game_date") <= pl.date(
                *map(int, train_end.split("-"))))
            & (pl.col("class_label") >= 0))
        if train.height == 0:
            raise ValueError("empty training population")
        train_cutoffs = train["game_date"].unique().to_list()

        # ---- requests through projected_long ------------------------
        _require_columns(lineups, LINEUP_COLUMNS, "projected lineups")
        long, n_uncovered = ad.projected_long(lineups)
        if long.height == 0:
            raise ValueError("empty projection request population")
        request_cutoffs = long["game_date"].unique().to_list()

        # ---- cohort restriction BEFORE feature construction ----------
        n_requests_before = long.height
        cohort_identity = {"restriction_applied": False, "n_keys": None,
                           "computed_hash": None, "expected_hash": None,
                           "hash_match": None}
        if cohort_keys is not None:
            cohort_unique = cohort_keys.select(*REQ_KEYS).unique()
            if cohort_unique.height != cohort_keys.height:
                raise ValueError(
                    "duplicate (game_pk, side, pitcher) keys in the "
                    "cohort-key input")
            null_mask = pl.any_horizontal(
                [pl.col(c).is_null() for c in REQ_KEYS])
            if cohort_keys.filter(null_mask).height > 0:
                raise ValueError("null cohort keys present")
            cohort_hash_val = _cohort_hash(
                [tuple(r) for r in cohort_unique.iter_rows()])
            if expected_cohort_hash is not None and \
                    cohort_hash_val != expected_cohort_hash:
                raise ValueError(
                    f"cohort identity mismatch: actual={cohort_hash_val} "
                    f"expected={expected_cohort_hash}")
            long = long.join(cohort_unique, on=REQ_KEYS, how="semi")
            if long.height == 0:
                raise ValueError(
                    "empty request population after cohort restriction")
            assessment = assessment.join(
                cohort_unique, on=REQ_KEYS, how="semi")
            cohort_identity = {
                "restriction_applied": True,
                "n_keys": cohort_unique.height,
                "computed_hash": cohort_hash_val,
                "expected_hash": expected_cohort_hash,
                "hash_match": (cohort_hash_val == expected_cohort_hash
                               if expected_cohort_hash is not None
                               else None)}
        n_requests_after = long.height
        request_cutoffs = long["game_date"].unique().to_list()
        request_dates = {(int(r["game_pk"]), str(r["side"]),
                          int(r["pitcher"])): r["game_date"]
                         for r in long.select(*REQ_KEYS, "game_date")
                         .unique().iter_rows(named=True)}

        # ---- states + features (v2 cutoff, full y-based population) --
        # states consume the FULL y-based history population
        p_v2, b_v2, lg_v2, _ = fv.build_v2_states(
            pa, train_cutoffs + request_cutoffs)
        feat_train = ad.attach_prior_features(
            train.select("game_date", "pitcher", "batter", "class_label"),
            p_v2, b_v2, lg_v2)
        feat_req = ad.attach_prior_features(
            long.select("game_date", "pitcher", "batter", "game_pk",
                        "side", "slot"),
            p_v2, b_v2, lg_v2)
        for fname, fframe in (("training", feat_train),
                              ("request", feat_req)):
            bad = {c: fframe[c].null_count() for c in FEATURES
                   if c in fframe.columns and fframe[c].null_count() > 0}
            if bad:
                raise ValueError(
                    f"{fname} features contain nulls {bad}: history "
                    "window does not precede the earliest cutoff")

        # ---- multinomial fit (shared PA model) ----------------------
        model = m0.fit_multinomial(feat_train)
        probs = m0.apply_multinomial(feat_req, model)
        n_cls = len(model["classes"])
        if probs.shape[1] == n_cls:
            probs_full = probs
        elif n_cls == 2 and probs.shape[1] == 1:
            # sklearn binary convention: one coef row, one column =
            # P(classes[1]); expand to the full class-probability vector
            col = probs[:, 0]
            probs_full = np.column_stack([1.0 - col, col])
        else:
            raise ValueError(
                f"model/probability class-count mismatch: "
                f"probs={probs.shape[1]} classes={n_cls}")
        # keyed PA probability table (full class-probability vector,
        # serialized output; p_k is the K column of the same vector)
        forecast_table = feat_req.select(
            "game_pk", "side", "pitcher", "slot", "batter",
        ).with_columns(
            pl.Series("p_k", probs_full[:, list(
                model["classes"]).index(K_CLASS)]),
        )
        for j, cls in enumerate(model["classes"]):
            forecast_table = forecast_table.with_columns(
                pl.Series(f"p_class_{cls}", probs_full[:, j]))
        keyed_path = out_dir / "keyed_pa_probabilities.parquet"
        forecast_table.write_parquet(keyed_path)

        # ---- W1: registered BF workload ------------------------------
        bf_val, bf_meta = ad.validate_bf37_by_start(
            bf_w1, long.select(*REQ_KEYS, "game_date").unique()
            .sort(*REQ_KEYS))
        bf_w1_lookup = {}
        for r in bf_val.select(
                "game_pk", "side", "pitcher",
                *[f"pmf37_{j}" for j in range(37)]).iter_rows(named=True):
            bf_w1_lookup[(int(r["game_pk"]), str(r["side"]),
                          int(r["pitcher"]))] = np.asarray(
                [r[f"pmf37_{j}"] for j in range(37)], dtype=np.float64)

        # ---- assessment outcomes (enter ONLY here) -------------------
        _require_columns(assessment, ASSESS_COLUMNS, "assessment outcomes")
        if assessment.height == 0:
            raise ValueError("empty assessment outcome population")
        actual = assessment.select(
            "game_pk", "side", "pitcher", "at_bat_number", "batter",
            "class_label").with_columns(
            (pl.col("class_label") == K_CLASS).cast(pl.Int64)
            .alias("is_k"))
        if actual.select("game_pk", "side", "pitcher", "at_bat_number",
                         "batter").n_unique() != actual.height:
            raise ValueError("duplicate actual-PA identity rows")
        k_real_df = actual.group_by(*REQ_KEYS).agg(
            realized_k=pl.col("is_k").sum())
        realized = {(int(r["game_pk"]), str(r["side"]),
                     int(r["pitcher"])): int(r["realized_k"])
                    for r in k_real_df.iter_rows(named=True)}
        # dates from validated request keys (lineups), not assessment
        dates = request_dates

        # ---- W0: per-cutoff pooled BF37 (expanding history) ----------
        # for each distinct assessment cutoff date, compute the pooled
        # BF37 from ALL first-pitcher-of-record outings before that date
        pooled_bf37_by_date = {}
        for t in sorted(set(request_cutoffs)):
            pooled_bf37_by_date[t] = _pooled_bf37_at(pa, t)

        # ---- build W0 and W1 count PMFs ------------------------------
        fc_by_start = {}
        for r in forecast_table.iter_rows(named=True):
            key = (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
            fc_by_start.setdefault(key, {})[int(r["slot"])] = r["p_k"]

        pmf_w0 = {}
        pmf_w1 = {}
        for key in sorted(realized):
            slots = fc_by_start.get(key, {})
            if len(slots) != 9 or min(slots) != 1 or max(slots) != 9:
                raise ValueError(
                    f"start {key} does not have 9 usable slots "
                    f"({len(slots)}); count aggregation requires the "
                    "full key")
            p9 = np.asarray([slots[i] for i in range(1, 10)])
            # W1: pitcher-specific workload
            pmf_w1[key] = ad.start_count_pmfs(
                p9, p9, bf_w1_lookup[key])["pmf_h3_raw"]
            # W0: pooled league workload per this start's cutoff
            cutoff_date = dates[key]
            pooled = _pooled_bf37_at(pa, cutoff_date)
            pmf_w0[key] = ad.start_count_pmfs(
                p9, p9, pooled)["pmf_h3_raw"]

        # ---- scores ---------------------------------------------------
        rps_w0 = {k: kc.count_rps(pmf_w0[k], realized[k])
                  for k in sorted(realized)}
        rps_w1 = {k: kc.count_rps(pmf_w1[k], realized[k])
                  for k in sorted(realized)}
        blocks = {k: "block_2025H1" for k in realized}
        paired_raw = bl.paired_contrast(rps_w1, rps_w0, dates, blocks,
                                        n_boot=2000, seed=20261001)
        paired = dict(paired_raw)
        paired["primary_pair"] = "W1_pitcher_specific_vs_W0_pooled_league"
        paired["contrast"] = "RPS(W1) - RPS(W0) per start"
        paired["helper_label_note"] = (
            "paired_contrast() labels its delta 'S_vs_F' by legacy "
            "convention; here delta_a_minus_b = RPS(W1) - RPS(W0)")

        # ---- observed BF (diagnostic outcome, enters only here) ------
        observed_bf = _observed_bf_by_start(pa, sorted(realized))

        # ---- per-start BF diagnostics for both arms ------------------
        bf_diag_w0 = {}
        bf_diag_w1 = {}
        for key in sorted(realized):
            obs = observed_bf[key]
            if obs is None:
                continue
            bf_diag_w0[key] = _bf_diagnostics(
                pooled_bf37_by_date[dates[key]], obs)
            bf_diag_w1[key] = _bf_diagnostics(bf_w1_lookup[key], obs)
        bf_diag_summary = {
            "w0_pooled": _aggregate_bf_diag(list(bf_diag_w0.values())),
            "w1_registered": _aggregate_bf_diag(list(bf_diag_w1.values())),
            "definition_note": ("BF distribution score: discrete RPS over "
                                "the 37-category support with bucketed "
                                "observed BF; point MAE / mean error use "
                                "the extended distribution (cap 60, "
                                "geometric tail); coverage uses extended "
                                "50% / 90% central intervals"),
        }

        # ---- W1 reconstruction gate (pinned external reference) ------
        # per-start evidence is written BEFORE the gate so a mismatch is
        # diagnosable; the gate still aborts the report and receipt.
        per_start = pl.DataFrame({
            "game_pk": [k[0] for k in sorted(realized)],
            "side": [k[1] for k in sorted(realized)],
            "pitcher": [k[2] for k in sorted(realized)],
            "game_date": [dates[k] for k in sorted(realized)],
            "realized_k": [realized[k] for k in sorted(realized)],
            "realized_bf": [observed_bf[k] for k in sorted(realized)],
            "rps_w0_pooled": [rps_w0[k] for k in sorted(realized)],
            "rps_w1_pitcher": [rps_w1[k] for k in sorted(realized)],
            "rps_diff": [rps_w1[k] - rps_w0[k] for k in sorted(realized)],
            "bf_rps_w0": [bf_diag_w0[k]["bf_rps"] if k in bf_diag_w0
                          else None for k in sorted(realized)],
            "bf_rps_w1": [bf_diag_w1[k]["bf_rps"] if k in bf_diag_w1
                          else None for k in sorted(realized)],
            "bf_point_mae_w0": [bf_diag_w0[k]["point_mae"] if k in bf_diag_w0
                                else None for k in sorted(realized)],
            "bf_point_mae_w1": [bf_diag_w1[k]["point_mae"] if k in bf_diag_w1
                                else None for k in sorted(realized)],
            "bf_mean_err_w0": [bf_diag_w0[k]["mean_bf_error"]
                               if k in bf_diag_w0 else None
                               for k in sorted(realized)],
            "bf_mean_err_w1": [bf_diag_w1[k]["mean_bf_error"]
                               if k in bf_diag_w1 else None
                               for k in sorted(realized)],
        })
        per_start_path = out_dir / "workload_per_start_v1.parquet"
        per_start.write_parquet(per_start_path)

        if reconstruction_reference is None:
            raise ValueError(
                "reconstruction reference required: pin the accepted "
                "baseline per-start reference "
                "(multiclass_baseline_per_start_v1.parquet schema) "
                "before running")
        _require_columns(reconstruction_reference,
                         REQ_KEYS + [RECON_REF_COLUMN],
                         "reconstruction reference")
        ref_map = {}
        for r in reconstruction_reference.iter_rows(named=True):
            ref_map[(int(r["game_pk"]), str(r["side"]),
                     int(r["pitcher"]))] = float(r[RECON_REF_COLUMN])
        if sorted(ref_map) != sorted(realized):
            raise ValueError(
                "reconstruction reference keys differ from scored "
                f"starts: reference={len(ref_map)} "
                f"scored={len(realized)}")
        recon_diffs = [abs(rps_w1[k] - ref_map[k]) for k in sorted(realized)]
        recon_max_abs = float(max(recon_diffs))
        if recon_max_abs > RECON_TOLERANCE:
            raise ValueError(
                f"reconstruction gate FAILED: max per-start absolute "
                f"RPS difference {recon_max_abs!r} exceeds tolerance "
                f"{RECON_TOLERANCE!r}; diagnose before proceeding, do "
                "not tune away")
        reconstruction = {
            "verified": True,
            "n_keys": len(ref_map),
            "max_abs_rps_diff": recon_max_abs,
            "tolerance": RECON_TOLERANCE,
            "reference_sha256": reconstruction_reference_sha256,
            "note": ("W1 (registered bf-workload-v1 BF forecasts over "
                     "the shared keyed PA model) reproduces the pinned "
                     "accepted-baseline per-start count-RPS within "
                     "tolerance"),
        }

        # ---- outputs ---------------------------------------------------

        # save model artifact (reloadable for class-probability verification)
        model_path = out_dir / "model_artifact.json"
        model_path.write_text(json.dumps(model, indent=1, sort_keys=True,
                                         default=str), encoding="utf-8")

        # save keyed PA probabilities
        keyed_path = out_dir / "keyed_pa_probabilities.parquet"
        forecast_table.write_parquet(keyed_path)

        # save per-start K PMFs for both arms
        k_pmf_rows = []
        for key in sorted(realized):
            for bucket in range(24):
                k_pmf_rows.append({
                    "game_pk": key[0], "side": key[1], "pitcher": key[2],
                    "bucket": bucket,
                    "pmf_w0": float(pmf_w0[key][bucket]),
                    "pmf_w1": float(pmf_w1[key][bucket]),
                })
        k_pmf_path = out_dir / "k_pmf_per_start_v1.parquet"
        pl.DataFrame(k_pmf_rows).write_parquet(k_pmf_path)

        # save per-start BF37 for BOTH arms in one keyed file
        # (deduplicated lossless layout)
        bf37_rows = []
        for key in sorted(realized):
            row = {"game_pk": key[0], "side": key[1], "pitcher": key[2],
                   "game_date": dates[key]}
            for j in range(37):
                row[f"pmf37_w0_{j}"] = float(pooled_bf37_by_date[
                    dates[key]][j])
                row[f"pmf37_w1_{j}"] = float(bf_w1_lookup[key][j])
            bf37_rows.append(row)
        bf37_path = out_dir / "bf37_by_start_v1.parquet"
        pl.DataFrame(bf37_rows).write_parquet(bf37_path)

        # save W0 pooled BF37 once per cutoff date
        bf_rows = []
        for t in sorted(pooled_bf37_by_date):
            for j in range(37):
                bf_rows.append({
                    "cutoff_date": str(t), "bf_category": j,
                    "bf37_w0_pooled": float(pooled_bf37_by_date[t][j]),
                })
        bf_path = out_dir / "bf37_pooled_by_date_v1.parquet"
        pl.DataFrame(bf_rows).write_parquet(bf_path)

        # validate the start-to-date mapping is complete and 1:1 with
        # the pooled-by-date artifact (W0 BF37 recoverable per start)
        scored_dates = {dates[k] for k in realized}
        if not sorted(pooled_bf37_by_date) == sorted(set(
                pooled_bf37_by_date) & scored_dates) or \
                not scored_dates.issubset(pooled_bf37_by_date):
            raise ValueError(
                "W0 start-to-date mapping incomplete: scored cutoff "
                "dates missing from pooled BF37 population")
        bf_dates_saved = set(pl.read_parquet(bf_path)[
            "cutoff_date"].unique().to_list())
        if bf_dates_saved != {str(t) for t in pooled_bf37_by_date}:
            raise ValueError("pooled-by-date artifact does not cover "
                             "every computed cutoff")

        report = {
            "experiment_identity": EXPERIMENT_ID,
            "primary_contrast": "RPS(W1) - RPS(W0) per start",
            "n_starts": len(realized),
            "mean_rps_w0": float(np.mean(list(rps_w0.values()))),
            "mean_rps_w1": float(np.mean(list(rps_w1.values()))),
            "paired_contrast": paired,
            "reconstruction": reconstruction,
            "bf_diagnostics": bf_diag_summary,
        }
        report_path = out_dir / "workload_comparison_report.json"
        report_path.write_text(json.dumps(report, indent=1,
                                           sort_keys=True, default=str),
                                encoding="utf-8")
        outputs = {
            "workload_per_start_v1.parquet": ad.sha256_file(per_start_path),
            "workload_comparison_report.json": ad.sha256_file(report_path),
            "keyed_pa_probabilities.parquet": ad.sha256_file(keyed_path),
            "model_artifact.json": ad.sha256_file(model_path),
            "k_pmf_per_start_v1.parquet": ad.sha256_file(k_pmf_path),
            "bf37_by_start_v1.parquet": ad.sha256_file(bf37_path),
            "bf37_pooled_by_date_v1.parquet": ad.sha256_file(bf_path),
        }
        final = dict(initial)
        final["counts"] = {
            "n_starts": len(realized),
            "n_requests_before_cohort": n_requests_before,
            "n_requests_after_cohort": n_requests_after,
            "n_starts_with_observed_bf": len(bf_diag_w1),
        }
        final["cohort_identity"] = cohort_identity
        final["reconstruction"] = reconstruction
        final["consumed_input_identities"] = input_identities or {}
        final["outputs"] = outputs
        final["primary_contrast"] = paired
        final["model_artifact"] = {
            "mean": model["mean"], "scale": model["scale"],
            "features": model["features"], "classes": model["classes"],
            "note": ("reloadable: apply_multinomial on the same feature "
                     "rows reproduces saved class probabilities"),
        }
        final["acceptance"] = {"receipt_chain": initial_sha,
                               "status": "COMPLETED"}
        (out_dir / "receipt_final.json").write_text(
            json.dumps(final, indent=1, sort_keys=True, default=str),
            encoding="utf-8")
        if ad.sha256_file(initial_path) != initial_sha:
            raise ValueError("IMMUTABLE initial receipt modified")
    except Exception as exc:
        failure = {"stage": "workload_personalization", "failure": True,
                   "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        raise
    return {"out_dir": str(out_dir),
            "experiment_identity": EXPERIMENT_ID,
            "primary_contrast": paired,
            "mean_rps_w0": report["mean_rps_w0"],
            "mean_rps_w1": report["mean_rps_w1"],
            "reconstruction": reconstruction,
            "outputs": outputs,
            "receipt_initial_sha256": initial_sha}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Workload personalization comparison (W0 vs W1). "
                    "Technical ack gate only. Identity/cohort pins are "
                    "REQUIRED: omitting one refuses execution rather "
                    "than silently running an unrestricted experiment.")
    p.add_argument("--pa-source", required=True)
    p.add_argument("--lineups", required=True)
    p.add_argument("--assessment", required=True)
    p.add_argument("--bf-source", required=True,
                   help="registered bf-workload-v1 per-start BF PMF artifact")
    p.add_argument("--raw-events", required=True,
                   help="comma-separated explicit raw Statcast parquet "
                        "paths; NOTE: the terminal-event preflight over "
                        "these files is procedural (bridge accounting), "
                        "the CLI records their hashes but does not "
                        "enforce event-level identity")
    p.add_argument("--train-start", required=True)
    p.add_argument("--train-end", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--execution-ack", required=True)
    p.add_argument("--cohort-keys", required=True,
                   help="REQUIRED parquet with (game_pk, side, pitcher) "
                        "keys restricting the experiment")
    p.add_argument("--expected-cohort-hash", required=True,
                   help="REQUIRED sha256 of the sorted cohort-key "
                        "identity lines")
    p.add_argument("--reconstruction-reference", required=True,
                   help="REQUIRED pinned accepted-baseline per-start "
                        "reference parquet (rps_ref1_multinomial)")
    p.add_argument("--expected-pa-sha256", required=True)
    p.add_argument("--expected-lineups-sha256", required=True)
    p.add_argument("--expected-assessment-sha256", required=True)
    p.add_argument("--expected-bf-sha256", required=True)
    args = p.parse_args(argv)
    if args.execution_ack != EXECUTION_ACK_TOKEN:
        print("EXECUTION REFUSED: invalid acknowledgement; no input "
              "read, nothing created.", file=sys.stderr)
        return 2
    # verify input file hashes before any decode
    file_checks = [("PA source", args.pa_source,
                    args.expected_pa_sha256),
                   ("projected lineups", args.lineups,
                    args.expected_lineups_sha256),
                   ("assessment outcomes", args.assessment,
                    args.expected_assessment_sha256),
                   ("BF workload", args.bf_source,
                    args.expected_bf_sha256)]
    for name, path, exp in file_checks:
        actual = _sha_file(Path(path))
        if actual != exp:
            print(f"INPUT IDENTITY MISMATCH for {name}: "
                  f"actual={actual} expected={exp}",
                  file=sys.stderr)
            return 1
    input_identities = {
        "pa_source": args.expected_pa_sha256,
        "lineups": args.expected_lineups_sha256,
        "assessment": args.expected_assessment_sha256,
        "bf_source": args.expected_bf_sha256,
        "reconstruction_reference": _sha_file(
            Path(args.reconstruction_reference)),
        "raw_events": {p: _sha_file(Path(p))
                       for p in args.raw_events.split(",") if p},
    }
    pa = pl.read_parquet(args.pa_source)
    lineups = pl.read_parquet(args.lineups)
    assessment = pl.read_parquet(args.assessment)
    bf_w1 = pl.read_parquet(args.bf_source)
    recon_ref = pl.read_parquet(args.reconstruction_reference)
    raw_events = [s for s in args.raw_events.split(",") if s]
    cohort_keys = pl.read_parquet(args.cohort_keys)
    res = run_workload_comparison(
        pa, lineups, assessment, bf_w1, args.out_dir,
        train_start=args.train_start, train_end=args.train_end,
        execution_ack=args.execution_ack, raw_events=raw_events,
        cohort_keys=cohort_keys, expected_cohort_hash=args.expected_cohort_hash,
        reconstruction_reference=recon_ref,
        reconstruction_reference_sha256=(
            input_identities["reconstruction_reference"]),
        input_identities=input_identities,
        ack_route="cli")
    print(json.dumps({"experiment": res["experiment_identity"],
                      "primary_contrast": res["primary_contrast"],
                      "mean_rps_w0": res["mean_rps_w0"],
                      "mean_rps_w1": res["mean_rps_w1"],
                      "out_dir": res["out_dir"]},
                     indent=1, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
