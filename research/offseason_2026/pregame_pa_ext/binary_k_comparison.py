"""Binary-K vs multinomial-K comparison (thin wrapper around the
REGISTERED machinery).

SYNTHETIC-TESTED ONLY until separately authorized; write-once outputs.
Reuses: m0_multiclass (labels contract, fit_multinomial for the control
arm, K_CLASS, FEATURES), adapter (projected_long, attach_prior_features,
start_count_pmfs, sha256_file), statcast_event_bridge (terminal-event
labels), forecast_states_v2 (cutoff-correct states),
baseline_ladder.paired_contrast (slate-date bootstrap), kc.count_rps, and
the reviewed workload runner's pooled-BF37 construction (imported, not
re-implemented, so the W0 control reconstruction is exact by identity).
Adds exactly ONE new statistical object: the binary K-vs-non-K logistic
(same estimator family and hyperparameters as the registered multinomial;
sigmoid head).

Primary contrast: delta = RPS(binary-K) - RPS(multinomial-K control) per
start on identical assessment keys, both arms consuming the SAME p9
layout, the SAME pooled BF37 per cutoff, and the SAME registered count
aggregation. The ONLY difference is the source of the per-PA K
probability (sigmoid vs softmax K marginal).

A reconstruction gate MUST verify the multinomial arm reproduces the
pinned accepted-W0 per-start count-RPS (workload_personalization_w0v1
per-start artifact, column rps_w0_pooled) within 1e-12 before any
contrast is reported.
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
from pregame_pa_ext import workload_comparison as wcmod  # noqa: E402
import kcount_combiner as kc  # noqa: E402

EXECUTION_ACK_TOKEN = "EXECUTE-BINARY-K-VS-MULTINOMIAL-V1"
EXPERIMENT_ID = "binary_k_vs_multinomial_v1"
K_CLASS = m0.K_CLASS
FEATURES = list(m0.FEATURES)
REQ_KEYS = ["game_pk", "side", "pitcher"]
RECON_TOLERANCE = 1e-12
RECON_REF_COLUMN = "rps_w0_pooled"
ASSESS_COLUMNS = ["game_pk", "side", "pitcher", "at_bat_number", "batter",
                  "class_label"]
LINEUP_COLUMNS = REQ_KEYS + ["game_date", "nine_distinct"] + [
    f"u_slot_{i}" for i in range(1, 10)]
BINARY_LABEL_COL = "is_k"
PRACTICAL_THRESHOLD = 0.005


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cohort_hash(keys: list) -> str:
    """Sorted-key SHA-256 hash (registered recipe, shared with the
    reviewed runners)."""
    lines = sorted(f"{k[0]}|{k[1]}|{k[2]}" for k in keys)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _require_columns(frame, required, name):
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(f"{name}: missing column(s) {missing}")


# ------------------------------------------------------------- binary model
def fit_binary(train: pl.DataFrame) -> dict:
    """Binary K-vs-non-K logistic, SAME estimator family and
    hyperparameters as the registered multinomial (StandardScaler +
    LogisticRegression C=1.0 lbfgs max_iter=1000). Label derived ONLY
    from the bridged class_label column."""
    y = (train["class_label"] == K_CLASS).cast(pl.Int64).to_numpy()
    if y.min() < 0 or y.max() > 1:
        raise ValueError("binary label derivation produced non-binary y")
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    X = train.select(FEATURES).to_numpy()
    scaler = StandardScaler().fit(X)
    lr = LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs")
    lr.fit(scaler.transform(X), y)
    if lr.coef_.shape[0] != 1:
        raise ValueError(
            f"binary model expected a single coefficient row, got "
            f"{lr.coef_.shape[0]}")
    return {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
            "coef": lr.coef_.tolist(), "intercept": lr.intercept_.tolist(),
            "features": list(FEATURES), "classes": [0, 1],
            "label_definition": f"is_k = 1[class_label == {K_CLASS}]",
            "n_train_rows": int(train.height),
            "n_train_positive": int(y.sum())}


def _sigmoid(logits: np.ndarray) -> np.ndarray:
    logits = np.asarray(logits, dtype=np.float64)
    out = np.empty_like(logits)
    pos = logits >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-logits[pos]))
    ex = np.exp(logits[~pos])
    out[~pos] = ex / (1.0 + ex)
    return out


def apply_binary(features: pl.DataFrame, model: dict) -> np.ndarray:
    """Per-PA P(K) from the binary model. Returns an (n,) vector; the
    multinomial's apply (softmax) is NOT reused because its manual
    softmax is undefined for a single-logit binary model."""
    X = features.select(FEATURES).to_numpy()
    mean = np.asarray(model["mean"], dtype=np.float64)
    scale = np.asarray(model["scale"], dtype=np.float64)
    coef = np.asarray(model["coef"], dtype=np.float64)
    intercept = np.asarray(model["intercept"], dtype=np.float64)
    z = (X - mean) / scale
    logits = (z @ coef[0]) + intercept[0]
    p = _sigmoid(logits)
    if not np.all(np.isfinite(p)):
        raise ValueError("non-finite binary probability")
    if p.min() < 0.0 or p.max() > 1.0:
        raise ValueError("binary probability out of [0,1]")
    return p


def reload_models(path: Path) -> dict:
    """Reload serialized model artifacts (fresh read; parity is asserted
    by tests against freshly applied probabilities)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: data[k] for k in ("multinomial_control", "binary_k")}


def _multinomial_pk(features: pl.DataFrame, model: dict) -> np.ndarray:
    """K marginal of the multinomial model, correct for ANY observed
    class count.

    m0.apply_multinomial applies a manual softmax over z @ coef.T. For
    a 2-class model sklearn stores ONE coefficient row (logit of
    classes[1]), so that softmax degenerates to a constant and the K
    marginal is undefined there. This helper applies the IDENTICAL
    softmax definition explicitly: >=3 classes via m0 unchanged;
    exactly 2 classes via the equivalent two-class softmax
    ([sigmoid(-logit), sigmoid(logit)]). The real registered cohort has
    4 observed classes (m0 path unchanged); this keeps the control arm
    mathematically correct on any synthetic fixture with fewer
    observed classes."""
    classes = list(model["classes"])
    n_cls = len(classes)
    if n_cls >= 3:
        probs = m0.apply_multinomial(features, model)
        return probs[:, classes.index(K_CLASS)]
    if n_cls != 2:
        raise ValueError(
            f"multinomial model has unsupported class count {n_cls}")
    X = features.select(FEATURES).to_numpy()
    mean = np.asarray(model["mean"], dtype=np.float64)
    scale = np.asarray(model["scale"], dtype=np.float64)
    coef = np.asarray(model["coef"], dtype=np.float64)
    intercept = np.asarray(model["intercept"], dtype=np.float64)
    if coef.shape[0] != 1:
        raise ValueError(
            f"2-class multinomial expected one coefficient row, got "
            f"{coef.shape[0]}")
    logits = ((X - mean) / scale) @ coef[0] + intercept[0]
    p_last = _sigmoid(logits)
    p = np.column_stack([1.0 - p_last, p_last])
    if not np.all(np.isfinite(p)):
        raise ValueError("non-finite multinomial probability")
    return p[:, classes.index(K_CLASS)]


def _pa_descriptive_metrics(p_k: np.ndarray, is_k: np.ndarray) -> dict:
    eps = 1e-15
    p = np.clip(np.asarray(p_k, dtype=np.float64), eps, 1.0 - eps)
    y = np.asarray(is_k, dtype=np.float64)
    return {
        "n_pas": int(len(y)),
        "log_loss": float(-(y * np.log(p)
                            + (1.0 - y) * np.log(1.0 - p)).mean()),
        "brier": float(((p - y) ** 2).mean()),
    }


def run_binary_k_comparison(
        pa: pl.DataFrame, lineups: pl.DataFrame,
        assessment: pl.DataFrame,
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
    """Execute the binary-K vs multinomial-K comparison (synthetic or
    authorized-real; identical code path)."""
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
        "workload_comparison_sha256": _sha_file(Path(wcmod.__file__)),
        "kcount_combiner_sha256": _sha_file(Path(kc.__file__)),
    }
    config = {
        "experiment_identity": EXPERIMENT_ID,
        "train_window": [train_start, train_end],
        "primary_pair": ["binary_k", "multinomial_plus_w0_control"],
        "primary_contrast": "RPS(binary-K) - RPS(multinomial-K) per start",
        "pooled_workload_source": "workload_comparison._pooled_bf37_at",
        "n_boot": 2000, "seed": 20261001,
        "practical_threshold": PRACTICAL_THRESHOLD,
        "interpretation": (
            "statistical direction reported separately: delta < 0 "
            "favors binary-K, delta > 0 favors the multinomial "
            "control, CI overlapping zero is inconclusive; a "
            "magnitude below the declared practical threshold "
            "(0.005 count-RPS) does not justify added complexity "
            "regardless of CI direction; promotion is never "
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
        # ---- labels: bridge over the ACTUAL schema -------------------
        _require_columns(pa, ["game_date", "game_pk", "at_bat_number",
                              "inning_topbot", "pitcher", "batter", "y"],
                         "PA source")
        if not raw_events:
            raise ValueError("raw_events required")
        pa_labeled, label_acc = seb.attach_terminal_event_labels(
            pa, raw_events, out_dir=out_dir)

        # ---- shared training split (ONE frame, two fits) -------------
        train = pa_labeled.filter(
            (pl.col("game_date") >= pl.date(
                *map(int, train_start.split("-"))))
            & (pl.col("game_date") <= pl.date(
                *map(int, train_end.split("-"))))
            & (pl.col("class_label") >= 0))
        if train.height == 0:
            raise ValueError("empty training population")
        # binary-label derivation from the SAME class_label column
        train = train.with_columns(
            (pl.col("class_label") == K_CLASS).cast(pl.Int64)
            .alias(BINARY_LABEL_COL))
        n_pos = int(train[BINARY_LABEL_COL].sum())
        n_neg = int(train.height - n_pos)
        if n_pos == 0 or n_neg == 0:
            raise ValueError(
                f"single-class training population refuses: "
                f"n_pos={n_pos} n_neg={n_neg}")
        train_cutoffs = train["game_date"].unique().to_list()

        # ---- requests through projected_long ------------------------
        _require_columns(lineups, LINEUP_COLUMNS, "projected lineups")
        long, n_uncovered = ad.projected_long(lineups)
        if long.height == 0:
            raise ValueError("empty projection request population")

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

        # ---- states + features (v2 cutoff, ONE construction) ---------
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

        # ---- both fits on the SAME rows ------------------------------
        model_mn = m0.fit_multinomial(feat_train)
        model_bin = fit_binary(feat_train)
        if model_bin["n_train_rows"] != int(train.height):
            raise ValueError(
                "binary training row count differs from the shared "
                "training frame")
        p_k_multinomial = _multinomial_pk(feat_req, model_mn)
        p_k_binary = apply_binary(feat_req, model_bin)

        # ---- keyed PA probability table (both arms, one table) -------
        # built directly from the shared feature rows; NO positional
        # transfer across frames
        keyed_path = out_dir / "keyed_pa_probabilities.parquet"
        feat_req.select(
            "game_pk", "side", "pitcher", "slot", "batter",
        ).with_columns(
            pl.Series("p_k_multinomial", p_k_multinomial),
            pl.Series("p_k_binary", p_k_binary),
        ).write_parquet(keyed_path)

        # ---- pooled BF37 per cutoff (reviewed construction, imported)
        pooled_bf37_by_date = {}
        for t in sorted(set(request_cutoffs)):
            pooled_bf37_by_date[t] = wcmod._pooled_bf37_at(pa, t)

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
        dates = request_dates

        # ---- keyed counts for BOTH arms (ONE population, ONE loop) ---
        fc_by_start = {}
        for r in pl.read_parquet(keyed_path).iter_rows(named=True):
            key = (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
            fc_by_start.setdefault(key, {})[int(r["slot"])] = (
                r["p_k_multinomial"], r["p_k_binary"])

        pmf_mn = {}
        pmf_bin = {}
        for key in sorted(realized):
            slots = fc_by_start.get(key, {})
            if len(slots) != 9 or min(slots) != 1 or max(slots) != 9:
                raise ValueError(
                    f"start {key} does not have 9 usable slots "
                    f"({len(slots)}); count aggregation requires the "
                    "full key")
            p9_mn = np.asarray([slots[i][0] for i in range(1, 10)])
            p9_bin = np.asarray([slots[i][1] for i in range(1, 10)])
            bf37 = pooled_bf37_by_date[dates[key]]
            # SAME registered aggregation, SAME BF37; only p9 differs
            pmf_mn[key] = ad.start_count_pmfs(
                p9_mn, p9_mn, bf37)["pmf_h3_raw"]
            pmf_bin[key] = ad.start_count_pmfs(
                p9_bin, p9_bin, bf37)["pmf_h3_raw"]

        # ---- scores ---------------------------------------------------
        rps_mn = {k: kc.count_rps(pmf_mn[k], realized[k])
                  for k in sorted(realized)}
        rps_bin = {k: kc.count_rps(pmf_bin[k], realized[k])
                   for k in sorted(realized)}
        blocks = {k: "block_2025H1" for k in realized}
        paired_raw = bl.paired_contrast(rps_bin, rps_mn, dates, blocks,
                                        n_boot=2000, seed=20261001)
        paired = dict(paired_raw)
        paired["primary_pair"] = "binary_k_vs_multinomial_plus_w0_control"
        paired["contrast"] = "RPS(binary-K) - RPS(multinomial-K) per start"
        paired["helper_label_note"] = (
            "paired_contrast() labels its delta 'S_vs_F' by legacy "
            "convention; here delta_a_minus_b = RPS(binary-K) - "
            "RPS(multinomial-K)")

        # ---- observed BF (diagnostic outcome, enters only here) ------
        observed_bf = wcmod._observed_bf_by_start(pa, sorted(realized))

        # ---- per-start parquet ----------------------------------------
        per_start = pl.DataFrame({
            "game_pk": [k[0] for k in sorted(realized)],
            "side": [k[1] for k in sorted(realized)],
            "pitcher": [k[2] for k in sorted(realized)],
            "game_date": [dates[k] for k in sorted(realized)],
            "realized_k": [realized[k] for k in sorted(realized)],
            "realized_bf": [observed_bf[k] for k in sorted(realized)],
            "rps_multinomial_control": [rps_mn[k]
                                        for k in sorted(realized)],
            "rps_binary_k": [rps_bin[k] for k in sorted(realized)],
            "rps_diff": [rps_bin[k] - rps_mn[k]
                         for k in sorted(realized)],
        })
        per_start_path = out_dir / "binary_k_per_start_v1.parquet"
        per_start.write_parquet(per_start_path)

        # ---- reconstruction gate (pinned accepted-W0 reference) -------
        # per-start evidence is written BEFORE the gate so a mismatch is
        # diagnosable; the gate still aborts the report and receipt.
        if reconstruction_reference is None:
            raise ValueError(
                "reconstruction reference required: pin the accepted "
                "W0 per-start reference (workload_personalization_w0v1 "
                "workload_per_start_v1.parquet schema, column "
                "rps_w0_pooled) before running")
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
        recon_diffs = [abs(rps_mn[k] - ref_map[k]) for k in sorted(realized)]
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
            "reference_column": RECON_REF_COLUMN,
            "note": ("the multinomial arm (registered multinomial K "
                     "marginal + W0 pooled BF37) reproduces the pinned "
                     "accepted-W0 per-start count-RPS within tolerance"),
        }

        # ---- per-PA descriptive metrics (identical population) -------
        keyed = pl.read_parquet(keyed_path)
        # matchup join must be many-to-one onto the keyed table
        n_unique_matchups = keyed.select(
            "game_pk", "side", "pitcher", "batter").n_unique()
        if keyed.height != n_unique_matchups:
            raise ValueError("keyed table is not unique per matchup key")
        matched = actual.join(
            keyed, on=["game_pk", "side", "pitcher", "batter"],
            how="inner")
        if matched.height == 0:
            raise ValueError("empty matched per-PA population")
        is_k_vec = matched["is_k"].to_numpy()
        met_mn = _pa_descriptive_metrics(
            matched["p_k_multinomial"].to_numpy(), is_k_vec)
        met_bin = _pa_descriptive_metrics(
            matched["p_k_binary"].to_numpy(), is_k_vec)
        if met_mn["n_pas"] != met_bin["n_pas"]:
            raise ValueError(
                "per-PA descriptive populations differ between arms")

        # ---- outputs ---------------------------------------------------
        model_path = out_dir / "model_artifacts.json"
        model_path.write_text(json.dumps(
            {"multinomial_control": model_mn, "binary_k": model_bin},
            indent=1, sort_keys=True, default=str), encoding="utf-8")

        k_pmf_rows = []
        for key in sorted(realized):
            for bucket in range(24):
                k_pmf_rows.append({
                    "game_pk": key[0], "side": key[1], "pitcher": key[2],
                    "bucket": bucket,
                    "pmf_multinomial_control": float(pmf_mn[key][bucket]),
                    "pmf_binary_k": float(pmf_bin[key][bucket]),
                })
        k_pmf_path = out_dir / "k_pmf_per_start_v1.parquet"
        pl.DataFrame(k_pmf_rows).write_parquet(k_pmf_path)

        bf_rows = []
        for t in sorted(pooled_bf37_by_date):
            for j in range(37):
                bf_rows.append({
                    "cutoff_date": str(t), "bf_category": j,
                    "bf37_w0_pooled": float(pooled_bf37_by_date[t][j]),
                })
        bf_path = out_dir / "bf37_pooled_by_date_v1.parquet"
        pl.DataFrame(bf_rows).write_parquet(bf_path)

        scored_dates = {dates[k] for k in realized}
        if not scored_dates.issubset(pooled_bf37_by_date):
            raise ValueError(
                "pooled BF37 population does not cover every scored "
                "cutoff date")
        bf_dates_saved = set(pl.read_parquet(bf_path)[
            "cutoff_date"].unique().to_list())
        if bf_dates_saved != {str(t) for t in pooled_bf37_by_date}:
            raise ValueError("pooled-by-date artifact does not cover "
                             "every computed cutoff")

        report = {
            "experiment_identity": EXPERIMENT_ID,
            "primary_contrast": "RPS(binary-K) - RPS(multinomial-K) "
                                "per start",
            "n_starts": len(realized),
            "mean_rps_multinomial_control": float(
                np.mean(list(rps_mn.values()))),
            "mean_rps_binary_k": float(np.mean(list(rps_bin.values()))),
            "paired_contrast": paired,
            "reconstruction": reconstruction,
            "per_pa_descriptive": {
                "multinomial_control": met_mn,
                "binary_k": met_bin,
                "note": "descriptive only, not decisive",
            },
            "binary_label_accounting": {
                "n_train_rows": int(train.height),
                "n_train_positive": n_pos,
                "n_train_negative": n_neg,
                "derivation": f"is_k = 1[class_label == {K_CLASS}]",
            },
        }
        report_path = out_dir / "binary_k_comparison_report.json"
        report_path.write_text(json.dumps(report, indent=1,
                                           sort_keys=True, default=str),
                                encoding="utf-8")
        outputs = {
            "binary_k_per_start_v1.parquet": ad.sha256_file(
                per_start_path),
            "binary_k_comparison_report.json": ad.sha256_file(
                report_path),
            "keyed_pa_probabilities.parquet": ad.sha256_file(keyed_path),
            "model_artifacts.json": ad.sha256_file(model_path),
            "k_pmf_per_start_v1.parquet": ad.sha256_file(k_pmf_path),
            "bf37_pooled_by_date_v1.parquet": ad.sha256_file(bf_path),
        }
        final = dict(initial)
        final["counts"] = {
            "n_starts": len(realized),
            "n_requests_before_cohort": n_requests_before,
            "n_requests_after_cohort": n_requests_after,
            "n_train_rows": int(train.height),
            "n_train_positive": n_pos,
        }
        final["cohort_identity"] = cohort_identity
        final["reconstruction"] = reconstruction
        final["consumed_input_identities"] = input_identities or {}
        final["outputs"] = outputs
        final["primary_contrast"] = paired
        final["model_artifacts"] = {
            "multinomial_control": {
                "mean": model_mn["mean"], "scale": model_mn["scale"],
                "features": model_mn["features"],
                "classes": model_mn["classes"]},
            "binary_k": {
                "mean": model_bin["mean"], "scale": model_bin["scale"],
                "features": model_bin["features"],
                "classes": model_bin["classes"]},
            "note": ("reloadable: re-applying the reloaded models on the "
                     "same feature rows reproduces the saved per-key "
                     "probabilities"),
        }
        final["acceptance"] = {"receipt_chain": initial_sha,
                               "status": "COMPLETED"}
        (out_dir / "receipt_final.json").write_text(
            json.dumps(final, indent=1, sort_keys=True, default=str),
            encoding="utf-8")
        if ad.sha256_file(initial_path) != initial_sha:
            raise ValueError("IMMUTABLE initial receipt modified")
    except Exception as exc:
        failure = {"stage": "binary_k_vs_multinomial", "failure": True,
                   "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                            sort_keys=True),
                                encoding="utf-8")
        raise
    return {"out_dir": str(out_dir),
            "experiment_identity": EXPERIMENT_ID,
            "primary_contrast": paired,
            "mean_rps_multinomial_control": report[
                "mean_rps_multinomial_control"],
            "mean_rps_binary_k": report["mean_rps_binary_k"],
            "reconstruction": reconstruction,
            "outputs": outputs,
            "receipt_initial_sha256": initial_sha}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Binary-K vs multinomial-K comparison. Technical ack "
                    "gate only. Cohort and reconstruction pins are "
                    "REQUIRED: omitting one refuses execution rather than "
                    "silently running an unrestricted experiment.")
    p.add_argument("--pa-source", required=True)
    p.add_argument("--lineups", required=True)
    p.add_argument("--assessment", required=True)
    p.add_argument("--raw-events", required=True,
                   help="comma-separated explicit raw Statcast parquet "
                        "paths")
    p.add_argument("--train-start", required=True)
    p.add_argument("--train-end", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--execution-ack", required=True)
    p.add_argument("--cohort-keys", required=True,
                   help="REQUIRED parquet with (game_pk, side, pitcher) "
                        "keys restricting the experiment")
    p.add_argument("--expected-cohort-hash", required=True)
    p.add_argument("--reconstruction-reference", required=True,
                   help="REQUIRED pinned accepted-W0 per-start reference "
                        "parquet (workload_per_start_v1.parquet schema, "
                        "column rps_w0_pooled)")
    p.add_argument("--expected-reconstruction-sha256", required=True,
                   help="REQUIRED sha256 of the reconstruction-reference "
                        "file; verified BEFORE any decode and recorded in "
                        "the receipt - recording alone is not identity "
                        "enforcement")
    p.add_argument("--expected-pa-sha256", required=True)
    p.add_argument("--expected-lineups-sha256", required=True)
    p.add_argument("--expected-assessment-sha256", required=True)
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
        "reconstruction_reference": _sha_file(
            Path(args.reconstruction_reference)),
        "raw_events": {p: _sha_file(Path(p))
                       for p in args.raw_events.split(",") if p},
    }
    pa = pl.read_parquet(args.pa_source)
    lineups = pl.read_parquet(args.lineups)
    assessment = pl.read_parquet(args.assessment)
    recon_ref = pl.read_parquet(args.reconstruction_reference)
    raw_events = [s for s in args.raw_events.split(",") if s]
    cohort_keys = pl.read_parquet(args.cohort_keys)
    res = run_binary_k_comparison(
        pa, lineups, assessment, args.out_dir,
        train_start=args.train_start, train_end=args.train_end,
        execution_ack=args.execution_ack, raw_events=raw_events,
        cohort_keys=cohort_keys, expected_cohort_hash=args.expected_cohort_hash,
        reconstruction_reference=recon_ref,
        reconstruction_reference_sha256=(
            input_identities["reconstruction_reference"]),
        input_identities=input_identities,
        ack_route="cli")
    print(json.dumps({
        "experiment": res["experiment_identity"],
        "primary_contrast": res["primary_contrast"],
        "mean_rps_multinomial_control": res[
            "mean_rps_multinomial_control"],
        "mean_rps_binary_k": res["mean_rps_binary_k"],
        "out_dir": res["out_dir"]},
        indent=1, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
