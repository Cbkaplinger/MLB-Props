"""Temporal-robustness evaluation of the retained candidate
(temporal_robustness_v1) - thin wrapper around the REGISTERED machinery.

SYNTHETIC-TESTED ONLY until separately authorized; write-once outputs.
Card: PROPOSED-temporal-robustness-evaluation.md (specification resolved
2026-11-04). Evaluates the RETAINED candidate (12-feature
multinomial-plus-platoon) against the 8-feature multinomial-plus-W0
control across two chronological periods, reusing the current harness.

STRUCTURAL ACCESS LIMITS (hard constants): the score windows end
2025-06-30; the runner refuses any scored date on/after 2025-07-01 (the
R3 confirm partition) and any date in 2026. R3 and 2026 are inaccessible
to this evaluation path by construction.

Periods (hardcoded constants):
- R1: fit 2023-03-30..2024-06-30 -> score 2024-07-01..2024-09-30
  (scored actual PAs derive from the labeled PA source).
- R2: fit 2023-03-30..2024-12-31 -> score 2025-01-01..2025-06-30
  (scored actual PAs come from the pinned registered 2025H1 assessment
  artifact).

Per period, BOTH arms are fit on the SAME fit rows and scored on the
SAME matched-PA population. Feasibility (observed date clusters, nonempty
populations, strict chronology, score-class compatibility) is verified
BEFORE any model fit. Machinery-identity anchor: the registered
8-feature multinomial-plus-W0 recipe refit on 2024-05-01..2024-12-31 and
scored on the registered 2025H1 cohort MUST reproduce the accepted
per-start reference (`ae971758...`, rps_w0_pooled) within 1e-12 before
any period contrast is reported.

Primary metric per period: per-PA multiclass log loss (per-start means;
each start equally weighted, PAs equally weighted within a start; paired
slate-date bootstrap 2000/20261001). K-count non-degradation guard per
period: 0.002 point-estimate margin (NOT a noninferiority claim).
Practical log-loss threshold 0.0005 nats. Secondary: classwise metrics,
K RPS means, K PMFs. No tuning, no new features, no calibration, no
additional learner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import baseline_ladder as bl  # noqa: E402
from pregame_pa_ext import binary_k_comparison as bk  # noqa: E402
from pregame_pa_ext import forecast_states_v2 as fv  # noqa: E402
from pregame_pa_ext import lgbm_multiclass_comparison as lc  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402
from pregame_pa_ext import platoon_comparison as pc  # noqa: E402
from pregame_pa_ext import platoon_features as pf  # noqa: E402
from pregame_pa_ext import statcast_event_bridge as seb  # noqa: E402
from pregame_pa_ext import workload_comparison as wcmod  # noqa: E402
import kcount_combiner as kc  # noqa: E402

EXECUTION_ACK_TOKEN = "EXECUTE-TEMPORAL-ROBUSTNESS-V1"
EXPERIMENT_ID = "temporal_robustness_v1"
K_CLASS = m0.K_CLASS
FEATURES = list(m0.FEATURES)
PLATOON_COLS = list(pf.PLATOON_COLS)
CHALLENGE_FEATURES = FEATURES + PLATOON_COLS
REQ_KEYS = ["game_pk", "side", "pitcher"]
RECON_TOLERANCE = 1e-12
# ---- STRUCTURAL ACCESS LIMITS (hard constants; never widened) --------
R3_START = date(2025, 7, 1)          # confirm partition begins here
HARD_MAX_SCORE_DATE = date(2025, 6, 30)  # last permitted scored date
PERIODS = [
    {"id": "R1", "fit_start": date(2023, 3, 30),
     "fit_end": date(2024, 6, 30),
     "score_start": date(2024, 7, 1), "score_end": date(2024, 9, 30)},
    {"id": "R2", "fit_start": date(2023, 3, 30),
     "fit_end": date(2024, 12, 31),
     "score_start": date(2025, 1, 1), "score_end": HARD_MAX_SCORE_DATE},
]
ANCHOR_FIT_WINDOW = (date(2024, 5, 1), date(2024, 12, 31))
RECON_REF_COLUMN = "rps_w0_pooled"
ASSESS_COLUMNS = ["game_pk", "side", "pitcher", "at_bat_number", "batter",
                  "class_label"]
LINEUP_COLUMNS = REQ_KEYS + ["game_date", "nine_distinct"] + [
    f"u_slot_{i}" for i in range(1, 10)]
LOGLOSS_PRACTICAL_THRESHOLD = 0.0005
COUNT_RPS_NONDEG_MARGIN = 0.002
MIN_FIT_DATE_CLUSTERS = 60


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_columns(frame, required, name):
    bk._require_columns(frame, required, name)


def _cohort_hash(keys: list) -> str:
    return bk._cohort_hash(keys)


def _log_loss_multiclass(probs: np.ndarray, classes: list,
                         y: np.ndarray) -> float:
    return lc._log_loss_multiclass(probs, classes, y)


def _classwise_multiclass(probs: np.ndarray, classes: list,
                          y: np.ndarray) -> dict:
    return lc._classwise_multiclass(probs, classes, y)


def check_structural_limits():
    """The period constants themselves must respect the structural
    access limits - verified at entry, independent of any data."""
    for p in PERIODS:
        if p["score_end"] >= R3_START or p["fit_end"] >= R3_START:
            raise ValueError(
                f"period {p['id']} reaches the R3 confirm partition "
                "(2025-07-01+); R3 and 2026 are inaccessible to this "
                "evaluation path")
        if p["score_end"] > HARD_MAX_SCORE_DATE:
            raise ValueError(
                f"period {p['id']} exceeds the hard scored-date limit "
                f"{HARD_MAX_SCORE_DATE}")
        if not (p["fit_start"] < p["fit_end"] < p["score_start"]
                <= p["score_end"]):
            raise ValueError(
                f"period {p['id']} is not strictly chronological")


def period_feasibility(pa_labeled: pl.DataFrame, lineups: pl.DataFrame,
                       period: dict, min_clusters: int) -> dict:
    """Per-period feasibility BEFORE any model fit: observed date
    clusters in fit and score windows, nonempty populations, strict
    chronology, score-class compatibility."""
    pid = period["id"]
    fit_dates = sorted(
        pa_labeled.filter(
            (pl.col("game_date") >= pl.lit(period["fit_start"]))
            & (pl.col("game_date") <= pl.lit(period["fit_end"])))
        ["game_date"].unique().to_list())
    score_dates = sorted(
        lineups.filter(
            (pl.col("game_date") >= pl.lit(period["score_start"]))
            & (pl.col("game_date") <= pl.lit(period["score_end"])))
        ["game_date"].unique().to_list())
    if len(fit_dates) < min_clusters:
        raise ValueError(
            f"period {pid}: only {len(fit_dates)} distinct fit-window "
            f"date clusters (minimum {min_clusters})")
    if not score_dates:
        raise ValueError(
            f"period {pid}: no projected-lineup dates in the score "
            "window")
    if max(fit_dates) >= min(score_dates):
        raise ValueError(
            f"period {pid}: fit does not strictly precede the score "
            "window")
    return {"id": pid, "n_fit_dates": len(fit_dates),
            "fit_first": str(fit_dates[0]), "fit_last": str(fit_dates[-1]),
            "n_score_dates": len(score_dates),
            "score_first": str(score_dates[0]),
            "score_last": str(score_dates[-1])}


def run_temporal_robustness(
        pa: pl.DataFrame, lineups: pl.DataFrame,
        assessment: pl.DataFrame,
        out_dir, *,
        execution_ack: str,
        raw_events: list | None = None,
        cohort_keys: pl.DataFrame | None = None,
        expected_cohort_hash: str | None = None,
        reconstruction_reference: pl.DataFrame | None = None,
        reconstruction_reference_sha256: str | None = None,
        input_identities: dict | None = None,
        ack_route: str = "direct-call",
        min_fit_date_clusters: int = MIN_FIT_DATE_CLUSTERS) -> dict:
    if execution_ack != EXECUTION_ACK_TOKEN:
        raise ValueError(
            "execution acknowledgement missing or invalid; refusing "
            "(technical gate only)")
    check_structural_limits()
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)
    failure_path = out_dir / "failure_record.json"
    initial_path = out_dir / "receipt_initial.json"

    code_identity = {
        "runner_sha256": _sha_file(Path(__file__)),
        "platoon_features_sha256": _sha_file(Path(pf.__file__)),
        "platoon_comparison_sha256": _sha_file(Path(pc.__file__)),
        "adapter_sha256": _sha_file(Path(ad.__file__)),
        "m0_multiclass_sha256": _sha_file(Path(m0.__file__)),
        "workload_comparison_sha256": _sha_file(Path(wcmod.__file__)),
        "kcount_combiner_sha256": _sha_file(Path(kc.__file__)),
    }
    config = {
        "experiment_identity": EXPERIMENT_ID,
        "periods": [{"id": p["id"], "fit": [str(p["fit_start"]),
                                            str(p["fit_end"])],
                     "score": [str(p["score_start"]),
                               str(p["score_end"])]} for p in PERIODS],
        "structural_limits": {"r3_start": str(R3_START),
                              "hard_max_score_date":
                              str(HARD_MAX_SCORE_DATE)},
        "primary_contrast": ("per-PA multiclass log loss (per-start "
                             "means, paired): retained candidate - "
                             "8-feature multinomial-plus-W0 control"),
        "n_boot": 2000, "seed": 20261001,
        "logloss_practical_threshold": lc.LOGLOSS_PRACTICAL_THRESHOLD,
        "count_rps_nondegradation_margin": lc.COUNT_RPS_NONDEG_MARGIN,
        "interpretation": (
            "per-period statistical direction reported separately; a "
            "mean log-loss improvement below the declared practical "
            "threshold (0.0005 nats) does not justify the added feature "
            "family regardless of CI direction; the K-count acceptance "
            "guard is a POINT-ESTIMATE criterion (0.002 margin), not a "
            "statistical noninferiority claim; promotion is never "
            "automatic"),
    }
    initial = {"execution_acknowledgement": {"route": ack_route,
               "token": execution_ack},
               "code_identity": code_identity, "config": config,
               "counts": None}
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)

    try:
        # ---- structural limits + labels ------------------------------
        check_structural_limits()
        _require_columns(pa, ["game_date", "game_pk", "at_bat_number",
                              "inning_topbot", "pitcher", "batter", "y",
                              "stand", "p_throws"],
                         "PA source")
        if not raw_events:
            raise ValueError("raw_events required")
        pa_labeled, label_acc = seb.attach_terminal_event_labels(
            pa, raw_events, out_dir=out_dir)

        # ---- requests + cohort restriction ---------------------------
        _require_columns(lineups, LINEUP_COLUMNS, "projected lineups")
        long_all, n_uncovered = ad.projected_long(lineups)
        if long_all.height == 0:
            raise ValueError("empty projection request population")
        # ---- cohort: supplied 2025H1 keys apply to anchor/R2 ONLY ----
        # (R1 scores 2024H2; a global 2025H1 filter would remove R1. R1
        # gets its own explicitly defined, outcome-independent eligible
        # key set derived from the pinned lineups input, with its
        # identity recorded.)
        cohort_identity = {
            "supplied_cohort_applied_to": ["anchor", "R2"],
            "restriction_applied": False}
        cohort_unique = None
        if cohort_keys is not None:
            cohort_unique = cohort_keys.select(*REQ_KEYS).unique()
            if cohort_unique.height != cohort_keys.height:
                raise ValueError(
                    "duplicate (game_pk, side, pitcher) keys in the "
                    "cohort-key input")
            if cohort_keys.filter(pl.any_horizontal(
                    [pl.col(c).is_null() for c in REQ_KEYS])).height > 0:
                raise ValueError("null cohort keys present")
            cohort_hash_val = _cohort_hash(
                [tuple(r) for r in cohort_unique.iter_rows()])
            if expected_cohort_hash is not None and \
                    cohort_hash_val != expected_cohort_hash:
                raise ValueError(
                    f"cohort identity mismatch: actual={cohort_hash_val} "
                    f"expected={expected_cohort_hash}")
            cohort_identity = {
                "supplied_cohort_applied_to": ["anchor", "R2"],
                "restriction_applied": True,
                "n_keys": cohort_unique.height,
                "computed_hash": cohort_hash_val,
                "expected_hash": expected_cohort_hash,
                "hash_match": True}
        if long_all.height == 0:
            raise ValueError(
                "empty projection request population after cohort "
                "validation")

        # ---- fold feasibility for EVERY period BEFORE any fit --------
        feasibilities = [period_feasibility(pa_labeled, lineups, p,
                                            min_fit_date_clusters)
                         for p in PERIODS]

        # ---- training-label coverage by year (BEFORE any fit) --------
        # the declared fit windows begin 2023-03-30; the bridge can only
        # label rows whose raw-event year is supplied. A fit-window year
        # with raw observations but ZERO eligible labels refuses here
        # rather than silently shortening the effective training history.
        label_years = []
        union_fit = sorted({d for p in PERIODS
                            for d in [p["fit_start"], p["fit_end"]]})
        fit_lo, fit_hi = min(union_fit), max(union_fit)
        in_fit = pa_labeled.filter(
            (pl.col("game_date") >= pl.lit(fit_lo))
            & (pl.col("game_date") <= pl.lit(fit_hi)))
        for y in sorted({x.year for x in
                         in_fit["game_date"].unique().to_list()}):
            yr = in_fit.filter(pl.col("game_date").dt.year() == y)
            n_raw = yr.height
            n_lab = int(yr.filter(pl.col("class_label") >= 0).height)
            label_years.append({"year": y, "n_rows": n_raw,
                                "n_labeled": n_lab})
            if n_raw > 0 and n_lab == 0:
                raise ValueError(
                    f"training-label feasibility: fit-window year {y} "
                    f"has {n_raw} raw observations but ZERO eligible "
                    "labels (raw-event source unavailable for that "
                    "year); the declared training history would be "
                    "silently shortened - pin the missing source or "
                    "revise the fit window")

        # ---- machinery-identity anchor (before period contrasts) -----
        # the registered 8-feature recipe, refit on the declared
        # 2024-05-01..2024-12-31 window and scored on the registered
        # 2025H1 cohort, MUST reproduce the accepted per-start reference
        if reconstruction_reference is None:
            raise ValueError(
                "reconstruction reference required: pin the accepted "
                "multinomial-plus-W0 per-start reference "
                "(workload_per_start_v1.parquet schema, column "
                "rps_w0_pooled) before running")
        _require_columns(reconstruction_reference,
                         REQ_KEYS + ["rps_w0_pooled"],
                         "reconstruction reference")
        anchor_train = pa_labeled.filter(
            (pl.col("game_date") >= pl.lit(ANCHOR_FIT_WINDOW[0]))
            & (pl.col("game_date") <= pl.lit(ANCHOR_FIT_WINDOW[1]))
            & (pl.col("class_label") >= 0))
        if anchor_train.height == 0:
            raise ValueError("empty anchor training population")
        anchor_cutoffs = anchor_train["game_date"].unique().to_list()
        anchor_requests = long_all.filter(
            (pl.col("game_date") >= pl.lit(date(2025, 1, 1)))
            & (pl.col("game_date") <= pl.lit(HARD_MAX_SCORE_DATE)))
        if cohort_unique is not None:
            anchor_requests = anchor_requests.join(
                cohort_unique, on=REQ_KEYS, how="semi")
        if anchor_requests.height == 0:
            raise ValueError("empty anchor request population")
        anchor_req_dates = sorted(
            anchor_requests["game_date"].unique().to_list())
        p_v2, b_v2, lg_v2, _ = fv.build_v2_states(
            pa, anchor_cutoffs + anchor_req_dates)
        anchor_feat_req = ad.attach_prior_features(
            anchor_requests.select("game_date", "pitcher", "batter",
                                   "game_pk", "side", "slot"),
            p_v2, b_v2, lg_v2)
        bad = {c: anchor_feat_req[c].null_count() for c in FEATURES
               if c in anchor_feat_req.columns
               and anchor_feat_req[c].null_count() > 0}
        if bad:
            raise ValueError(f"anchor features contain nulls {bad}")
        anchor_feat_fit = ad.attach_prior_features(
            anchor_train.select("game_date", "pitcher", "batter",
                                "class_label"),
            p_v2, b_v2, lg_v2)
        abad = {c: anchor_feat_fit[c].null_count() for c in FEATURES
                if c in anchor_feat_fit.columns
                and anchor_feat_fit[c].null_count() > 0}
        if abad:
            raise ValueError(f"anchor fit features contain nulls {abad}")
        anchor_model = m0.fit_multinomial(anchor_feat_fit)
        anchor_probs = pc._softmax_full(anchor_feat_req, anchor_model,
                                        FEATURES)
        anchor_cls = list(anchor_model["classes"])
        anchor_keyed = anchor_feat_req.select(
            "game_pk", "side", "pitcher", "slot", "batter").with_columns(
            pl.Series(f"p_class_{c}_anchor", anchor_probs[:, j])
            for j, c in enumerate(anchor_cls))
        anchor_scored = anchor_requests.select(*REQ_KEYS).unique()
        anchor_pooled = {}
        for t in sorted(anchor_req_dates):
            anchor_pooled[t] = wcmod._pooled_bf37_at(pa, t)
        fc_anchor = {}
        for r in anchor_keyed.iter_rows(named=True):
            fc_anchor.setdefault(
                (int(r["game_pk"]), str(r["side"]), int(r["pitcher"])),
                {})[int(r["slot"])] = r[f"p_class_{K_CLASS}_anchor"]
        # anchor realized K from the labeled PA source (2025H1 rows);
        # side attached from the uniqueness-validated (game_pk, pitcher)
        # request mapping (registered D1 repair pattern - the PA source
        # is side-less)
        anchor_actual = pa_labeled.filter(
            (pl.col("game_date") >= pl.lit(date(2025, 1, 1)))
            & (pl.col("game_date") <= pl.lit(HARD_MAX_SCORE_DATE)))
        side_map = anchor_requests.select("game_pk", "pitcher", "side") \
            .unique()
        if side_map.group_by("game_pk", "pitcher").agg(
                n=pl.len()).filter(pl.col("n") > 1).height > 0:
            raise ValueError(
                "ambiguous side mapping for the anchor population")
        anchor_actual = anchor_actual.join(
            side_map, on=["game_pk", "pitcher"], how="inner")
        anchor_realized = {
            (int(r["game_pk"]), str(r["side"]), int(r["pitcher"])):
                int(r["realized_k"])
            for r in anchor_actual.group_by(*REQ_KEYS).agg(
                realized_k=(pl.col("class_label") == K_CLASS)
                .cast(pl.Int64).sum()).iter_rows(named=True)}
        anchor_dates = {
            (int(r["game_pk"]), str(r["side"]), int(r["pitcher"])): r[
                "game_date"]
            for r in anchor_requests.select(*REQ_KEYS, "game_date")
            .unique().iter_rows(named=True)}
        if sorted(anchor_realized) != sorted(
                k for k in anchor_dates
                if k in {tuple(x) for x in anchor_scored.iter_rows()}):
            raise ValueError(
                "anchor realized-K population differs from the scored "
                "request population")
        rps_anchor = {}
        for key in sorted(anchor_realized):
            slots = fc_anchor.get(key, {})
            if len(slots) != 9 or min(slots) != 1 or max(slots) != 9:
                raise ValueError(
                    f"anchor start {key} does not have 9 usable slots")
            p9 = np.asarray([slots[i] for i in range(1, 10)])
            pmf = ad.start_count_pmfs(
                p9, p9, anchor_pooled[anchor_dates[key]])["pmf_h3_raw"]
            rps_anchor[key] = kc.count_rps(pmf, anchor_realized[key])
        anchor_per_start = pl.DataFrame({
            "game_pk": [k[0] for k in sorted(rps_anchor)],
            "side": [k[1] for k in sorted(rps_anchor)],
            "pitcher": [k[2] for k in sorted(rps_anchor)],
            "realized_k": [anchor_realized[k] for k in sorted(rps_anchor)],
            "rps_anchor": [rps_anchor[k] for k in sorted(rps_anchor)],
        })
        anchor_ps_path = out_dir / "anchor_per_start.parquet"
        anchor_per_start.write_parquet(anchor_ps_path)
        ref_map = {}
        for r in reconstruction_reference.iter_rows(named=True):
            ref_map[(int(r["game_pk"]), str(r["side"]),
                     int(r["pitcher"]))] = float(r["rps_w0_pooled"])
        if sorted(ref_map) != sorted(rps_anchor):
            raise ValueError(
                "anchor reference keys differ from the scored "
                f"population: reference={len(ref_map)} "
                f"anchor={len(rps_anchor)}")
        recon_max = float(max(abs(rps_anchor[k] - ref_map[k])
                              for k in sorted(ref_map)))
        if recon_max > RECON_TOLERANCE:
            raise ValueError(
                f"ANCHOR reconstruction gate FAILED: max per-start "
                f"absolute RPS difference {recon_max!r} exceeds "
                f"tolerance {RECON_TOLERANCE!r}; diagnose before "
                "proceeding, do not tune away")
        reconstruction = {
            "verified": True, "n_keys": len(ref_map),
            "max_abs_rps_diff": recon_max, "tolerance": RECON_TOLERANCE,
            "reference_sha256": reconstruction_reference_sha256,
            "reference_column": "rps_w0_pooled",
            "note": ("the registered 8-feature recipe refit on "
                     "2024-05-01..2024-12-31 reproduces the accepted "
                     "per-start reference within tolerance, anchoring "
                     "the shared machinery for the temporal refits"),
        }

        # ---- per-period evaluation ------------------------------------
        periods_out = []
        per_start_frames = {}
        for period in PERIODS:
            pid = period["id"]
            fit = pa_labeled.filter(
                (pl.col("game_date") >= pl.lit(period["fit_start"]))
                & (pl.col("game_date") <= pl.lit(period["fit_end"]))
                & (pl.col("class_label") >= 0))
            # warm-up/fit boundary: the FIRST distinct date in the fit
            # window has zero strictly-prior labeled history (opening
            # day); its rows are retained as history for states/rates
            # but EXCLUDED from fitting. The resolved fit start = the
            # second distinct date.
            fit_all_dates = sorted(
                fit["game_date"].unique().to_list())
            if len(fit_all_dates) < 2:
                raise ValueError(
                    f"period {pid}: only {len(fit_all_dates)} distinct "
                    "fit-window dates; need at least 2 (warm-up + "
                    "eligible)")
            warmup_dates = fit_all_dates[:1]
            eligible_fit_dates = fit_all_dates[1:]
            excluded_warmup_rows = int(
                fit.filter(pl.col("game_date")
                           == fit_all_dates[0]).height)
            fit = fit.filter(pl.col("game_date") > fit_all_dates[0])
            if fit.height == 0:
                raise ValueError(
                    f"period {pid}: no eligible fit rows after warm-up "
                    "exclusion")
            resolved_fit_start = str(fit_all_dates[1])
            requests = long_all.filter(
                (pl.col("game_date") >= pl.lit(period["score_start"]))
                & (pl.col("game_date") <= pl.lit(period["score_end"])))
            if pid == "R2" and cohort_unique is not None:
                requests = requests.join(cohort_unique, on=REQ_KEYS,
                                         how="semi")
            # R1 eligible key set: explicitly defined, outcome-
            # independent - the cohort-restricted score-window request
            # keys themselves; identity recorded (hash + count)
            r1_cohort_keys = sorted(
                (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
                for r in requests.select(*REQ_KEYS).unique()
                .iter_rows(named=True))
            r1_cohort_identity = {
                "definition": ("score-window request keys from the "
                               "pinned lineups input (outcome-"
                               "independent)"),
                "n_keys": len(r1_cohort_keys),
                "keys_sha256": _cohort_hash(r1_cohort_keys)}
            req_dates = sorted(
                requests["game_date"].unique().to_list())
            # structural guard: nothing scored reaches the R3 partition
            if req_dates and max(req_dates) >= R3_START:
                raise ValueError(
                    f"period {pid}: scored dates reach the R3 confirm "
                    "partition; structurally inaccessible")
            cutoffs = fit["game_date"].unique().to_list() + req_dates
            p2, b2, l2, _ = fv.build_v2_states(pa, cutoffs)
            feat_fit = ad.attach_prior_features(
                fit.select("game_date", "pitcher", "batter",
                           "class_label", "stand", "p_throws"),
                p2, b2, l2)
            feat_req = ad.attach_prior_features(
                requests.select("game_date", "pitcher", "batter",
                                "game_pk", "side", "slot"),
                p2, b2, l2)
            for fname, fframe in (("fit", feat_fit),
                                  ("request", feat_req)):
                bad = {c: fframe[c].null_count() for c in FEATURES
                       if c in fframe.columns
                       and fframe[c].null_count() > 0}
                if bad:
                    raise ValueError(
                        f"period {pid} {fname} features contain nulls "
                        f"{bad}")
            rates = pf.build_split_class_rates(
                pa_labeled, fit["game_date"].unique().to_list()
                + req_dates, alpha=pc.ALPHA, n_classes=4)
            feat_fit = feat_fit.with_columns(
                pl.col("game_date").alias("cutoff"))
            feat_fit = pf.attach_platoon_features(feat_fit, rates,
                                                  n_classes=4)
            hands = pf.forecast_matchup_hands(
                pa_labeled,
                requests.select(pl.col("batter"), pl.col("pitcher"),
                                pl.col("game_date").alias("cutoff")))
            feat_req = (feat_req
                        .join(hands.select("batter", "pitcher", "cutoff",
                                           "f_stand", "f_hand"),
                              left_on=["batter", "pitcher", "game_date"],
                              right_on=["batter", "pitcher", "cutoff"],
                              how="left")
                        .with_columns(
                            pl.col("game_date").alias("cutoff"),
                            pl.col("f_stand").alias("stand"),
                            pl.col("f_hand").alias("p_throws"))
                        .drop(["f_stand", "f_hand"]))
            feat_req = pf.attach_platoon_features(feat_req, rates,
                                                  n_classes=4)

            # identical-arm fits: SAME fit rows, SAME populations
            model_ctrl = m0.fit_multinomial(feat_fit)
            model_cand = pc.fit_challenger(feat_fit)
            probs_ctrl = pc._softmax_full(feat_req, model_ctrl, FEATURES)
            cls_ctrl = list(model_ctrl["classes"])
            probs_cand = pc._softmax_full(feat_req, model_cand,
                                          pc.CHALLENGE_FEATURES)
            cls_cand = list(model_cand["classes"])
            if sorted(cls_ctrl) != sorted(cls_cand):
                raise ValueError(
                    f"period {pid}: control and candidate class sets "
                    "differ")

            keyed = feat_req.select(
                "game_pk", "side", "pitcher", "slot", "batter")
            for j, c in enumerate(cls_ctrl):
                keyed = keyed.with_columns(pl.Series(
                    f"p_class_{c}_control", probs_ctrl[:, j]))
            for j, c in enumerate(cls_cand):
                keyed = keyed.with_columns(pl.Series(
                    f"p_class_{c}_platoon", probs_cand[:, j]))
            keyed_path = out_dir / f"keyed_pa_probabilities_{pid}.parquet"
            keyed.write_parquet(keyed_path)

            # scored actual PAs: R1 from the labeled PA source, R2 from
            # the pinned registered assessment artifact
            if pid == "R1":
                # scored actual PAs derive from the labeled PA source
                # (side-less); side attached from the uniqueness-
                # validated (game_pk, pitcher) request mapping
                # (registered D1 repair pattern)
                actual = pa_labeled.filter(
                    (pl.col("game_date") >= pl.lit(period["score_start"]))
                    & (pl.col("game_date") <= pl.lit(period["score_end"]))
                ).select("game_pk", "pitcher", "at_bat_number", "batter",
                         "class_label")
                side_map = requests.select("game_pk", "pitcher", "side") \
                    .unique()
                if side_map.group_by("game_pk", "pitcher").agg(
                        n=pl.len()).filter(pl.col("n") > 1).height > 0:
                    raise ValueError(
                        f"period {pid}: ambiguous side mapping")
                actual = actual.join(side_map, on=["game_pk", "pitcher"],
                                     how="inner")
            else:
                _require_columns(assessment, ASSESS_COLUMNS,
                                 "assessment outcomes")
                actual = assessment.select(
                    "game_pk", "side", "pitcher", "at_bat_number",
                    "batter", "class_label").join(
                    requests.select(*REQ_KEYS).unique(), on=REQ_KEYS,
                    how="semi")
                actual = actual.filter(
                    (pl.col("game_pk").is_in(
                        requests["game_pk"].unique().to_list())))
            if actual.height == 0:
                raise ValueError(f"period {pid}: empty scored population")
            k_real = {
                (int(r["game_pk"]), str(r["side"]), int(r["pitcher"])):
                    int(r["realized_k"])
                for r in actual.group_by(*REQ_KEYS).agg(
                    realized_k=(pl.col("class_label") == K_CLASS)
                    .cast(pl.Int64).sum()).iter_rows(named=True)}
            # ---- coverage reconciliation BEFORE rows are filtered ----
            # mutually exclusive start-level buckets + accounting
            # invariant; PA counts kept separate from start counts
            requested_keys = sorted(set(fc_by_start_of(keyed)))
            keys_with_outcomes = set(k_real)
            missing_outcome_keys = sorted(
                k for k in requested_keys
                if k not in keys_with_outcomes)
            scored_keys = sorted(
                k for k in requested_keys if k in keys_with_outcomes)
            if not scored_keys:
                raise ValueError(
                    f"period {pid}: no scored starts with complete "
                    "outcomes")
            # actual PAs not joined to any projected matchup (PA-level;
            # the keyed table is read here and reused for scoring)
            keyed_read = pl.read_parquet(keyed_path)
            matched_pa_keys = keyed_read.select(
                "game_pk", "side", "pitcher", "batter").unique()
            unmatched_pas = actual.join(
                matched_pa_keys, on=["game_pk", "side", "pitcher",
                                     "batter"], how="anti")
            projected_without_actual = keyed_read.join(
                actual.select("game_pk", "side", "pitcher", "batter")
                .unique(), on=["game_pk", "side", "pitcher", "batter"],
                how="anti")
            coverage = {
                "requested_starts_before_exclusions":
                    len(requested_keys),
                "excluded_missing_outcomes": len(missing_outcome_keys),
                "missing_outcome_keys": [
                    list(k) for k in missing_outcome_keys],
                "scored_starts": len(scored_keys),
                "scored_keys_identity_sha256": _cohort_hash(scored_keys),
                "accounting_invariant": (
                    "scored + excluded_missing_outcomes == requested"),
                "pooled_bf_coverage": (
                    "constructed for every scored cutoff directly from "
                    "the pinned PA source (no registered BF rows "
                    "consumed on this path)"),
                "pa_accounting": {
                    "unmatched_pas": int(unmatched_pas.height),
                    "projected_matchups_without_actual_pas":
                        int(projected_without_actual.height),
                    "note": ("PA counts are separate from start counts; "
                             "matched_pas added after the per-PA join"),
                },
            }
            assert len(scored_keys) + len(missing_outcome_keys) == \
                len(requested_keys), (
                f"period {pid}: coverage accounting invariant violated")
            dates_p = {k: dates for k, dates in
                       request_date_map(requests).items()
                       if k in set(scored_keys)}

            pmf_ctrl, pmf_cand = {}, {}
            fc = fc_table(keyed_read, cls_ctrl, cls_cand, K_CLASS)
            for key in scored_keys:
                slots = fc.get(key, {})
                if len(slots) != 9 or min(slots) != 1 or max(slots) != 9:
                    raise ValueError(
                        f"period {pid} start {key} does not have 9 "
                        "usable slots")
                p9c = np.asarray([slots[i][0] for i in range(1, 10)])
                p9p = np.asarray([slots[i][1] for i in range(1, 10)])
                bf37 = pooled_bf37_by_date(pa, dates_p[key])
                pmf_ctrl[key] = ad.start_count_pmfs(
                    p9c, p9c, bf37)["pmf_h3_raw"]
                pmf_cand[key] = ad.start_count_pmfs(
                    p9p, p9p, bf37)["pmf_h3_raw"]
            rps_ctrl = {k: kc.count_rps(pmf_ctrl[k], k_real[k])
                        for k in scored_keys}
            rps_cand = {k: kc.count_rps(pmf_cand[k], k_real[k])
                        for k in scored_keys}
            # per-PA coverage accounting (PA counts, separate from start
            # counts): matched, unmatched actual PAs, projected matchups
            # without actual PAs
            n_unique = keyed_read.select(
                "game_pk", "side", "pitcher", "batter").n_unique()
            if keyed_read.height != n_unique:
                raise ValueError(
                    f"period {pid}: keyed table not unique per matchup")
            matched = actual.join(
                keyed_read, on=["game_pk", "side", "pitcher", "batter"],
                how="inner")
            if matched.height == 0:
                raise ValueError(
                    f"period {pid}: empty matched per-PA population")
            unmatched_pas = actual.join(
                keyed_read.select("game_pk", "side", "pitcher", "batter")
                .unique(), on=["game_pk", "side", "pitcher", "batter"],
                how="anti")
            projected_without_actual = keyed_read.join(
                actual.select("game_pk", "side", "pitcher", "batter")
                .unique(), on=["game_pk", "side", "pitcher", "batter"],
                how="anti")
            pa_accounting = {
                "matched_pas": int(matched.height),
                "unmatched_pas": int(unmatched_pas.height),
                "projected_matchups_without_actual_pas":
                    int(projected_without_actual.height),
                "note": "PA counts are separate from start counts",
            }
            coverage["pa_accounting"] = pa_accounting
            unl = matched.filter(~pl.col("class_label").is_in(cls_ctrl))
            if unl.height > 0:
                raise ValueError(
                    f"period {pid}: {unl.height} matched PA(s) carry "
                    "labels outside the fitted class set")
            yv = matched["class_label"].to_numpy().astype(int)
            idx_c = {c: j for j, c in enumerate(cls_ctrl)}
            idx_p = {c: j for j, c in enumerate(cls_cand)}
            mat_c = np.column_stack(
                [matched[f"p_class_{c}_control"].to_numpy()
                 for c in cls_ctrl])
            mat_p = np.column_stack(
                [matched[f"p_class_{c}_platoon"].to_numpy()
                 for c in cls_cand])
            ll_ctrl = _log_loss_multiclass(mat_c, cls_ctrl, yv)
            ll_cand = _log_loss_multiclass(mat_p, cls_cand, yv)
            ll_ctrl_start, ll_cand_start = {}, {}
            for r in matched.with_row_index(
                    "__i__").iter_rows(named=True):
                key = (int(r["game_pk"]), str(r["side"]),
                       int(r["pitcher"]))
                yv_i = int(r["class_label"])
                ll_ctrl_start.setdefault(key, []).append(
                    -np.log(max(mat_c[int(r["__i__"]), idx_c[yv_i]],
                                1e-15)))
                ll_cand_start.setdefault(key, []).append(
                    -np.log(max(mat_p[int(r["__i__"]), idx_p[yv_i]],
                                1e-15)))
            ll_ctrl_m = {k: float(np.mean(v))
                         for k, v in ll_ctrl_start.items()}
            ll_cand_m = {k: float(np.mean(v))
                         for k, v in ll_cand_start.items()}
            dts = {k: request_date_map(requests)[k]
                   for k in ll_ctrl_m}
            blks = {k: f"block_{pid}" for k in ll_ctrl_m}
            paired = dict(bl.paired_contrast(
                ll_cand_m, ll_ctrl_m, dts, blks, n_boot=2000,
                seed=20261001))
            paired["contrast"] = ("per-start mean multiclass log loss: "
                                  "retained candidate - control")
            paired["helper_label_note"] = (
                "paired_contrast() labels its delta 'S_vs_F' by legacy "
                "convention; delta_a_minus_b = candidate - control")
            rps_paired = dict(bl.paired_contrast(
                rps_cand, rps_ctrl, dates_p,
                {k: f"block_{pid}" for k in rps_ctrl}, n_boot=2000,
                seed=20261001))
            nondeg = {
                "margin": lc.COUNT_RPS_NONDEG_MARGIN,
                "point_estimate": float(np.mean(
                    [rps_cand[k] - rps_ctrl[k] for k in scored_keys])),
                "ci95": rps_paired.get("ci95"),
                "within_margin": bool(np.mean(
                    [rps_cand[k] - rps_ctrl[k] for k in scored_keys])
                    <= lc.COUNT_RPS_NONDEG_MARGIN),
                "note": ("POINT-ESTIMATE ACCEPTANCE GUARD; NOT a "
                         "statistical noninferiority claim"),
            }
            per_start = pl.DataFrame({
                "game_pk": [k[0] for k in scored_keys],
                "side": [k[1] for k in scored_keys],
                "pitcher": [k[2] for k in scored_keys],
                "game_date": [dates_p[k] for k in scored_keys],
                "realized_k": [k_real[k] for k in scored_keys],
                "rps_control": [rps_ctrl[k] for k in scored_keys],
                "rps_platoon": [rps_cand[k] for k in scored_keys],
                "rps_diff": [rps_cand[k] - rps_ctrl[k]
                             for k in scored_keys],
                "logloss_control": [ll_ctrl_m.get(k)
                                    for k in scored_keys],
                "logloss_platoon": [ll_cand_m.get(k)
                                    for k in scored_keys],
            })
            ps_path = out_dir / f"temporal_per_start_{pid}.parquet"
            per_start.write_parquet(ps_path)
            per_start_frames[pid] = ps_path
            k_pmf_rows = []
            for key in scored_keys:
                for bucket in range(24):
                    k_pmf_rows.append({
                        "game_pk": key[0], "side": key[1],
                        "pitcher": key[2], "bucket": bucket,
                        "pmf_control": float(pmf_ctrl[key][bucket]),
                        "pmf_platoon": float(pmf_cand[key][bucket]),
                    })
            k_pmf_path = out_dir / f"k_pmf_per_start_{pid}.parquet"
            pl.DataFrame(k_pmf_rows).write_parquet(k_pmf_path)
            per_start_frames[pid + "_kpmf"] = k_pmf_path
            periods_out.append({
                "id": pid,
                "resolved_fit_start": resolved_fit_start,
                "excluded_warmup_dates": [str(d) for d in warmup_dates],
                "excluded_warmup_rows": excluded_warmup_rows,
                "n_starts": len(scored_keys),
                "n_matched_pas": int(matched.height),
                "mean_logloss_control": ll_ctrl,
                "mean_logloss_platoon": ll_cand,
                "paired": paired,
                "coverage": coverage,
                "r1_cohort_identity": (r1_cohort_identity
                                       if pid == "R1" else None),
                "k_count": {
                    "mean_rps_control": float(np.mean(
                        list(rps_ctrl.values()))),
                    "mean_rps_platoon": float(np.mean(
                        list(rps_cand.values()))),
                    "non_degradation": nondeg,
                },
                "classwise": {
                    "control": _classwise_multiclass(
                        mat_c, cls_ctrl, yv),
                    "platoon": _classwise_multiclass(
                        mat_p, cls_cand, yv),
                },
            })

        # ---- report + receipts ----------------------------------------
        report = {
            "experiment_identity": EXPERIMENT_ID,
            "reconstruction": reconstruction,
            "feasibility": feasibilities,
            "training_label_coverage_by_year": label_years,
            "periods": periods_out,
            "structural_limits": config["structural_limits"],
        }
        report_path = out_dir / "temporal_robustness_report.json"
        report_path.write_text(json.dumps(
            report, indent=1, sort_keys=True, default=str),
            encoding="utf-8")
        outputs = {"temporal_robustness_report.json":
                   ad.sha256_file(report_path),
                   "anchor_per_start.parquet":
                   ad.sha256_file(anchor_ps_path)}
        for pid, path in per_start_frames.items():
            if pid.endswith("_kpmf"):
                outputs[f"k_pmf_per_start_{pid[:-5]}.parquet"] = \
                    ad.sha256_file(path)
            else:
                outputs[f"temporal_per_start_{pid}.parquet"] = \
                    ad.sha256_file(path)
        for p in Path(out_dir).glob("keyed_pa_probabilities_*.parquet"):
            outputs[p.name] = ad.sha256_file(p)
        final = dict(initial)
        final["counts"] = {
            "periods": [
                {"id": po["id"], "n_starts": po["n_starts"],
                 "n_matched_pas": po["n_matched_pas"]}
                for po in periods_out],
            "n_train_rows": [
                {"id": p["id"]} for p in PERIODS],
        }
        final["cohort_identity"] = cohort_identity
        final["reconstruction"] = reconstruction
        final["consumed_input_identities"] = input_identities or {}
        final["outputs"] = outputs
        final["acceptance"] = {"receipt_chain": initial_sha,
                               "status": "COMPLETED"}
        (out_dir / "receipt_final.json").write_text(
            json.dumps(final, indent=1, sort_keys=True, default=str),
            encoding="utf-8")
        if ad.sha256_file(initial_path) != initial_sha:
            raise ValueError("IMMUTABLE initial receipt modified")
    except Exception as exc:
        failure = {"stage": "temporal_robustness", "failure": True,
                   "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                            sort_keys=True),
                                encoding="utf-8")
        raise
    return {"out_dir": str(out_dir),
            "experiment_identity": EXPERIMENT_ID,
            "reconstruction": reconstruction,
            "periods": periods_out,
            "outputs": outputs,
            "receipt_initial_sha256": initial_sha}


def fc_table(keyed: pl.DataFrame, cls_ctrl: list, cls_cand: list,
             k_class: int) -> dict:
    table = {}
    for r in keyed.iter_rows(named=True):
        key = (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
        table.setdefault(key, {})[int(r["slot"])] = (
            r[f"p_class_{k_class}_control"], r[f"p_class_{k_class}_platoon"])
    return table


def fc_by_start_of(keyed: pl.DataFrame) -> set:
    return {(int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
            for r in keyed.iter_rows(named=True)}


def request_date_map(requests: pl.DataFrame) -> dict:
    return {(int(r["game_pk"]), str(r["side"]), int(r["pitcher"])):
            r["game_date"]
            for r in requests.select(*REQ_KEYS, "game_date")
            .unique().iter_rows(named=True)}


def pooled_bf37_by_date(pa: pl.DataFrame, cutoff) -> np.ndarray:
    return wcmod._pooled_bf37_at(pa, cutoff)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Temporal-robustness evaluation of the retained "
                    "candidate. Technical ack gate only. Cohort and "
                    "reconstruction pins are REQUIRED.")
    p.add_argument("--pa-source", required=True)
    p.add_argument("--lineups", required=True)
    p.add_argument("--assessment", required=True)
    p.add_argument("--raw-events", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--execution-ack", required=True)
    p.add_argument("--cohort-keys", required=True)
    p.add_argument("--expected-cohort-hash", required=True)
    p.add_argument("--reconstruction-reference", required=True)
    p.add_argument("--expected-reconstruction-sha256", required=True)
    p.add_argument("--expected-pa-sha256", required=True)
    p.add_argument("--expected-lineups-sha256", required=True)
    p.add_argument("--expected-assessment-sha256", required=True)
    p.add_argument("--min-fit-date-clusters", type=int,
                   default=MIN_FIT_DATE_CLUSTERS,
                   help="minimum distinct fit-window date clusters per "
                        "period (packet-pinned; default 60)")
    args = p.parse_args(argv)
    if args.execution_ack != EXECUTION_ACK_TOKEN:
        print("EXECUTION REFUSED: invalid acknowledgement; no input "
              "read, nothing created.", file=sys.stderr)
        return 2
    file_checks = [("PA source", args.pa_source,
                    args.expected_pa_sha256),
                   ("projected lineups", args.lineups,
                    args.expected_lineups_sha256),
                   ("assessment outcomes", args.assessment,
                    args.expected_assessment_sha256),
                   ("reconstruction reference",
                    args.reconstruction_reference,
                    args.expected_reconstruction_sha256)]
    for name, path, exp in file_checks:
        if _sha_file(Path(path)) != exp:
            print(f"INPUT IDENTITY MISMATCH for {name}", file=sys.stderr)
            return 1
    input_identities = {
        "pa_source": args.expected_pa_sha256,
        "lineups": args.expected_lineups_sha256,
        "assessment": args.expected_assessment_sha256,
        "reconstruction_reference": _sha_file(
            Path(args.reconstruction_reference)),
        "raw_events": {q: _sha_file(Path(q))
                       for q in args.raw_events.split(",") if q},
    }
    res = run_temporal_robustness(
        pl.read_parquet(args.pa_source),
        pl.read_parquet(args.lineups),
        pl.read_parquet(args.assessment), args.out_dir,
        execution_ack=args.execution_ack,
        raw_events=[s for s in args.raw_events.split(",") if s],
        cohort_keys=pl.read_parquet(args.cohort_keys),
        expected_cohort_hash=args.expected_cohort_hash,
        reconstruction_reference=pl.read_parquet(
            args.reconstruction_reference),
        reconstruction_reference_sha256=input_identities[
            "reconstruction_reference"],
        input_identities=input_identities, ack_route="cli",
        min_fit_date_clusters=args.min_fit_date_clusters)
    print(json.dumps({"experiment": res["experiment_identity"],
                      "reconstruction": res["reconstruction"],
                      "out_dir": res["out_dir"]},
                     indent=1, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
