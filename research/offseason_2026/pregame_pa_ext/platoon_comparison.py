"""Platoon-information value comparison (thin wrapper around the
REGISTERED machinery).

SYNTHETIC-TESTED ONLY until separately authorized; write-once outputs.
Reuses: m0_multiclass (labels contract, fit_multinomial, K_CLASS,
FEATURES), adapter (projected_long, attach_prior_features,
start_count_pmfs, sha256_file), statcast_event_bridge (terminal-event
labels), forecast_states_v2 (cutoff-correct states),
baseline_ladder.paired_contrast, kc.count_rps, the reviewed workload
runner's pooled-BF37 construction (imported, not re-implemented), and the
binary runner's softmax helpers (imported for identity). Adds exactly ONE
new feature family: platoon-features-v1 (platoon_features.py) - four
handedness-conditioned strictly-prior shrunk class-rate columns.

Control arm: the existing eight-feature multinomial-plus-W0 pipeline
(registered recipe, unchanged). Challenger arm: the SAME pipeline plus the
4 platoon columns (12-feature fit, same estimator family/hyperparameters).
The ONLY difference is the added feature family.

Primary endpoint: per-PA multiclass log loss on the identical matched-PA
population (per-start means, registered paired slate-date bootstrap).
K-count non-degradation: mean per-start count-RPS challenger - control
must not exceed the declared margin (0.002). Secondary (declared,
non-decisive): classwise log loss / Brier, K-count RPS means, per-start K
PMFs. A reconstruction gate requires the control arm to reproduce the
pinned accepted multinomial-plus-W0 per-start count-RPS (rps_w0_pooled)
within 1e-12 before any contrast is reported.
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
from pregame_pa_ext import binary_k_comparison as bk  # noqa: E402
from pregame_pa_ext import forecast_states_v2 as fv  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402
from pregame_pa_ext import platoon_features as pf  # noqa: E402
from pregame_pa_ext import statcast_event_bridge as seb  # noqa: E402
from pregame_pa_ext import workload_comparison as wcmod  # noqa: E402
import kcount_combiner as kc  # noqa: E402

EXECUTION_ACK_TOKEN = "EXECUTE-PLATOON-INFORMATION-V1"
EXPERIMENT_ID = "platoon_information_v1"
K_CLASS = m0.K_CLASS
FEATURES = list(m0.FEATURES)
PLATOON_COLS = list(pf.PLATOON_COLS)
CHALLENGE_FEATURES = FEATURES + PLATOON_COLS
REQ_KEYS = ["game_pk", "side", "pitcher"]
RECON_TOLERANCE = 1e-12
RECON_REF_COLUMN = "rps_w0_pooled"
ASSESS_COLUMNS = ["game_pk", "side", "pitcher", "at_bat_number", "batter",
                  "class_label"]
LINEUP_COLUMNS = REQ_KEYS + ["game_date", "nine_distinct"] + [
    f"u_slot_{i}" for i in range(1, 10)]
LOGLOSS_PRACTICAL_THRESHOLD = 0.0005
COUNT_RPS_NONDEG_MARGIN = 0.002
ALPHA = pf.DEFAULT_ALPHA


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_columns(frame, required, name):
    bk._require_columns(frame, required, name)


def _cohort_hash(keys: list) -> str:
    return bk._cohort_hash(keys)


def _softmax_full(features: pl.DataFrame, model: dict,
                  feature_cols: list) -> np.ndarray:
    """Full class-probability vector, identical softmax definition for
    any observed class count (>=3 via m0.apply_multinomial semantics;
    exactly 2 via the equivalent two-class softmax)."""
    classes = list(model["classes"])
    n_cls = len(classes)
    X = features.select(feature_cols).to_numpy()
    mean = np.asarray(model["mean"], dtype=np.float64)
    scale = np.asarray(model["scale"], dtype=np.float64)
    coef = np.asarray(model["coef"], dtype=np.float64)
    intercept = np.asarray(model["intercept"], dtype=np.float64)
    z = (X - mean) / scale
    if n_cls >= 3:
        logits = z @ coef.T + intercept
    elif n_cls == 2:
        if coef.shape[0] != 1:
            raise ValueError(
                f"2-class model expected one coefficient row, got "
                f"{coef.shape[0]}")
        logits = np.column_stack([np.zeros(len(z)),
                                  (z @ coef[0]) + intercept[0]])
    else:
        raise ValueError(
            f"model has unsupported class count {n_cls}")
    exp_l = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs = exp_l / exp_l.sum(axis=1, keepdims=True)
    if not np.all(np.isfinite(probs)):
        raise ValueError("non-finite class probability")
    return probs


def fit_challenger(train: pl.DataFrame) -> dict:
    """Multinomial fit on the 8 registered features + the 4 platoon
    columns; same estimator family and hyperparameters as the registered
    recipe; NO tuning."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    X = train.select(CHALLENGE_FEATURES).to_numpy()
    scaler = StandardScaler().fit(X)
    lr = LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs")
    lr.fit(scaler.transform(X),
           train["class_label"].to_numpy().astype(int))
    return {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
            "coef": lr.coef_.tolist(), "intercept": lr.intercept_.tolist(),
            "features": list(CHALLENGE_FEATURES),
            "classes": lr.classes_.tolist(),
            "n_train_rows": int(train.height)}


def _log_loss(probs: np.ndarray, classes: list, y: np.ndarray) -> float:
    idx = {c: j for j, c in enumerate(classes)}
    eps = 1e-15
    p = np.clip(probs[np.arange(len(y)),
                      [idx[int(v)] for v in y]], eps, 1.0)
    return float(-np.log(p).mean())


def _classwise(probs: np.ndarray, classes: list, y: np.ndarray) -> dict:
    out = {}
    eps = 1e-15
    for j, c in enumerate(classes):
        yb = (y == int(c)).astype(np.float64)
        pc = np.clip(probs[:, j], eps, 1.0 - eps)
        out[str(int(c))] = {
            "n": int(yb.sum()),
            "log_loss": float(-(yb * np.log(pc)
                                + (1.0 - yb) * np.log(1.0 - pc)).mean()),
            "brier": float(((pc - yb) ** 2).mean()),
        }
    return out


def run_platoon_comparison(
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
        "platoon_features_sha256": _sha_file(Path(pf.__file__)),
        "adapter_sha256": _sha_file(Path(ad.__file__)),
        "m0_multiclass_sha256": _sha_file(Path(m0.__file__)),
        "workload_comparison_sha256": _sha_file(Path(wcmod.__file__)),
        "kcount_combiner_sha256": _sha_file(Path(kc.__file__)),
    }
    config = {
        "experiment_identity": EXPERIMENT_ID,
        "train_window": [train_start, train_end],
        "primary_pair": ["platoon_challenger", "multinomial_plus_w0_control"],
        "primary_contrast": "per-PA multiclass log loss (per-start means, "
                            "paired): challenger - control",
        "feature_family": pf.VERSION,
        "alpha": ALPHA,
        "n_boot": 2000, "seed": 20261001,
        "logloss_practical_threshold": LOGLOSS_PRACTICAL_THRESHOLD,
        "count_rps_nondegradation_margin": COUNT_RPS_NONDEG_MARGIN,
        "interpretation": (
            "statistical direction reported separately; a mean log-loss "
            "improvement below the declared practical threshold "
            "(0.0005 nats) does not justify the added feature family "
            "regardless of CI direction; the K-count non-degradation "
            "margin is 0.002 count-RPS; promotion is never automatic"),
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
                              "inning_topbot", "pitcher", "batter", "y",
                              "stand", "p_throws"],
                         "PA source")
        if not raw_events:
            raise ValueError("raw_events required")
        pa_labeled, label_acc = seb.attach_terminal_event_labels(
            pa, raw_events, out_dir=out_dir)
        _require_columns(pa_labeled, ["stand", "p_throws"],
                         "labeled PA source")

        # ---- shared training split (ONE frame, two fits) -------------
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

        # ---- states + base features (v2 cutoff, ONE construction) ----
        all_cutoffs = train_cutoffs + request_cutoffs
        p_v2, b_v2, lg_v2, _ = fv.build_v2_states(pa, all_cutoffs)
        feat_train = ad.attach_prior_features(
            train.select("game_date", "pitcher", "batter", "class_label",
                         "stand", "p_throws"),
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

        # ---- platoon features (platoon-features-v1) ------------------
        rates = pf.build_split_class_rates(pa_labeled, all_cutoffs,
                                           alpha=ALPHA,
                                           n_classes=len(
                                               m0.CLASS_NAMES))
        rates.write_parquet(out_dir / "platoon_split_rates_v1.parquet")
        feat_train = feat_train.with_columns(
            pl.col("game_date").alias("cutoff"))
        feat_train = pf.attach_platoon_features(
            feat_train, rates, n_classes=len(m0.CLASS_NAMES))
        hands = pf.forecast_matchup_hands(
            pa_labeled,
            long.select(pl.col("batter"), pl.col("pitcher"),
                        pl.col("game_date").alias("cutoff")))
        feat_req = (feat_req
                    .join(hands.select("batter", "pitcher", "cutoff",
                                       "f_stand", "f_hand"),
                          left_on=["batter", "pitcher", "game_date"],
                          right_on=["batter", "pitcher", "cutoff"],
                          how="left")
                    .with_columns(pl.col("game_date").alias("cutoff"),
                                  pl.col("f_stand").alias("stand"),
                                  pl.col("f_hand").alias("p_throws"))
                    .drop(["f_stand", "f_hand"]))
        feat_req = pf.attach_platoon_features(
            feat_req, rates, n_classes=len(m0.CLASS_NAMES))

        # ---- both fits on the SAME rows ------------------------------
        model_ctrl = m0.fit_multinomial(feat_train)
        model_chat = fit_challenger(feat_train)
        probs_ctrl = _softmax_full(feat_req, model_ctrl, FEATURES)
        probs_chat = _softmax_full(feat_req, model_chat,
                                   CHALLENGE_FEATURES)
        cls_ctrl = list(model_ctrl["classes"])
        cls_chat = list(model_chat["classes"])
        if sorted(cls_ctrl) != sorted(cls_chat):
            raise ValueError(
                "control and challenger observed class sets differ")

        # ---- keyed PA probability table (both arms, full vectors) ----
        keyed_path = out_dir / "keyed_pa_probabilities.parquet"
        keyed = feat_req.select(
            "game_pk", "side", "pitcher", "slot", "batter")
        for j, c in enumerate(cls_ctrl):
            keyed = keyed.with_columns(
                pl.Series(f"p_class_{c}_control", probs_ctrl[:, j]))
        for j, c in enumerate(cls_chat):
            keyed = keyed.with_columns(
                pl.Series(f"p_class_{c}_platoon", probs_chat[:, j]))
        keyed.write_parquet(keyed_path)

        # ---- pooled BF37 per cutoff (reviewed construction) ----------
        pooled_bf37_by_date = {}
        for t in sorted(set(request_cutoffs)):
            pooled_bf37_by_date[t] = wcmod._pooled_bf37_at(pa, t)

        # ---- assessment outcomes (enter ONLY here) -------------------
        _require_columns(assessment, ASSESS_COLUMNS, "assessment outcomes")
        if assessment.height == 0:
            raise ValueError("empty assessment outcome population")
        actual = assessment.select(
            "game_pk", "side", "pitcher", "at_bat_number", "batter",
            "class_label")
        if actual.select("game_pk", "side", "pitcher", "at_bat_number",
                         "batter").n_unique() != actual.height:
            raise ValueError("duplicate actual-PA identity rows")
        k_real_df = actual.group_by(*REQ_KEYS).agg(
            realized_k=(pl.col("class_label") == K_CLASS)
            .cast(pl.Int64).sum())
        realized = {(int(r["game_pk"]), str(r["side"]),
                     int(r["pitcher"])): int(r["realized_k"])
                    for r in k_real_df.iter_rows(named=True)}
        dates = request_dates

        # ---- keyed counts for BOTH arms (ONE population, ONE loop) ---
        keyed_read = pl.read_parquet(keyed_path)
        fc_by_start = {}
        for r in keyed_read.iter_rows(named=True):
            key = (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
            fc_by_start.setdefault(key, {})[int(r["slot"])] = (
                r[f"p_class_{K_CLASS}_control"],
                r[f"p_class_{K_CLASS}_platoon"])

        pmf_ctrl = {}
        pmf_chat = {}
        for key in sorted(realized):
            slots = fc_by_start.get(key, {})
            if len(slots) != 9 or min(slots) != 1 or max(slots) != 9:
                raise ValueError(
                    f"start {key} does not have 9 usable slots "
                    f"({len(slots)}); count aggregation requires the "
                    "full key")
            p9_ctrl = np.asarray([slots[i][0] for i in range(1, 10)])
            p9_chat = np.asarray([slots[i][1] for i in range(1, 10)])
            bf37 = pooled_bf37_by_date[dates[key]]
            pmf_ctrl[key] = ad.start_count_pmfs(
                p9_ctrl, p9_ctrl, bf37)["pmf_h3_raw"]
            pmf_chat[key] = ad.start_count_pmfs(
                p9_chat, p9_chat, bf37)["pmf_h3_raw"]

        rps_ctrl = {k: kc.count_rps(pmf_ctrl[k], realized[k])
                    for k in sorted(realized)}
        rps_chat = {k: kc.count_rps(pmf_chat[k], realized[k])
                    for k in sorted(realized)}
        blocks = {k: "block_2025H1" for k in realized}

        # ---- per-PA primary metrics (identical population) -----------
        n_unique_matchups = keyed_read.select(
            "game_pk", "side", "pitcher", "batter").n_unique()
        if keyed_read.height != n_unique_matchups:
            raise ValueError("keyed table is not unique per matchup key")
        matched = actual.join(
            keyed_read, on=["game_pk", "side", "pitcher", "batter"],
            how="inner")
        if matched.height == 0:
            raise ValueError("empty matched per-PA population")
        unknown_labels = matched.filter(
            ~pl.col("class_label").is_in(cls_ctrl))
        if unknown_labels.height > 0:
            raise ValueError(
                f"{unknown_labels.height} matched PA(s) carry class "
                "labels outside the fitted class set; refusing rather "
                "than scoring an undefined class")
        y_vec = matched["class_label"].to_numpy().astype(int)
        prob_ctrl_mat = np.column_stack(
            [matched[f"p_class_{c}_control"].to_numpy()
             for c in cls_ctrl])
        prob_chat_mat = np.column_stack(
            [matched[f"p_class_{c}_platoon"].to_numpy()
             for c in cls_chat])
        ll_ctrl_pa = _log_loss(prob_ctrl_mat, cls_ctrl, y_vec)
        ll_chat_pa = _log_loss(prob_chat_mat, cls_chat, y_vec)
        # per-start means for the paired contrast
        start_of = {(int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
                    for r in matched.select("game_pk", "side",
                                            "pitcher").unique()
                    .iter_rows(named=True)}
        ll_ctrl_start = {}
        ll_chat_start = {}
        for r in matched.with_row_index("__i__").iter_rows(named=True):
            key = (int(r["game_pk"]), str(r["side"]), int(r["pitcher"]))
            ll_ctrl_start.setdefault(key, []).append(
                -np.log(max(prob_ctrl_mat[int(r["__i__"]),
                                          cls_ctrl.index(
                                              int(r["class_label"]))],
                            1e-15)))
            ll_chat_start.setdefault(key, []).append(
                -np.log(max(prob_chat_mat[int(r["__i__"]),
                                          cls_chat.index(
                                              int(r["class_label"]))],
                            1e-15)))
        ll_ctrl_mean = {k: float(np.mean(v))
                        for k, v in ll_ctrl_start.items()}
        ll_chat_mean = {k: float(np.mean(v))
                        for k, v in ll_chat_start.items()}
        blocks_ll = {k: "block_2025H1" for k in ll_ctrl_mean}
        dates_ll = {k: dates[k] for k in ll_ctrl_mean}
        paired_ll = dict(bl.paired_contrast(
            ll_chat_mean, ll_ctrl_mean, dates_ll, blocks_ll,
            n_boot=2000, seed=20261001))
        paired_ll["primary_pair"] = \
            "platoon_challenger_vs_multinomial_plus_w0_control"
        paired_ll["contrast"] = ("per-start mean multiclass log loss: "
                                 "challenger - control")
        paired_ll["helper_label_note"] = (
            "paired_contrast() labels its delta 'S_vs_F' by legacy "
            "convention; here delta_a_minus_b = challenger - control")

        # ---- K-count non-degradation contrast (secondary) ------------
        paired_rps = dict(bl.paired_contrast(
            rps_chat, rps_ctrl, dates, blocks, n_boot=2000,
            seed=20261001))
        paired_rps["contrast"] = ("RPS(platoon challenger) - RPS(control) "
                                  "per start")
        nondeg = {
            "margin": COUNT_RPS_NONDEG_MARGIN,
            "point_estimate": float(np.mean(
                [rps_chat[k] - rps_ctrl[k] for k in sorted(realized)])),
            "ci95": paired_rps.get("ci95"),
            "within_margin": bool(np.mean(
                [rps_chat[k] - rps_ctrl[k] for k in sorted(realized)])
                <= COUNT_RPS_NONDEG_MARGIN),
        }

        # ---- per-start parquet ---------------------------------------
        observed_bf = wcmod._observed_bf_by_start(pa, sorted(realized))
        per_start = pl.DataFrame({
            "game_pk": [k[0] for k in sorted(realized)],
            "side": [k[1] for k in sorted(realized)],
            "pitcher": [k[2] for k in sorted(realized)],
            "game_date": [dates[k] for k in sorted(realized)],
            "realized_k": [realized[k] for k in sorted(realized)],
            "realized_bf": [observed_bf[k] for k in sorted(realized)],
            "rps_multinomial_control": [rps_ctrl[k]
                                        for k in sorted(realized)],
            "rps_platoon": [rps_chat[k] for k in sorted(realized)],
            "rps_diff": [rps_chat[k] - rps_ctrl[k]
                         for k in sorted(realized)],
            "logloss_multinomial_control": [ll_ctrl_mean.get(k)
                                            for k in sorted(realized)],
            "logloss_platoon": [ll_chat_mean.get(k)
                                for k in sorted(realized)],
        })
        per_start_path = out_dir / "platoon_per_start_v1.parquet"
        per_start.write_parquet(per_start_path)

        # ---- reconstruction gate (pinned accepted-W0 reference) ------
        if reconstruction_reference is None:
            raise ValueError(
                "reconstruction reference required: pin the accepted "
                "multinomial-plus-W0 per-start reference "
                "(workload_per_start_v1.parquet schema, column "
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
        recon_diffs = [abs(rps_ctrl[k] - ref_map[k])
                       for k in sorted(realized)]
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
            "note": ("the control arm (registered eight-feature "
                     "multinomial + W0 pooled BF37) reproduces the "
                     "pinned accepted per-start count-RPS within "
                     "tolerance"),
        }

        # ---- outputs ---------------------------------------------------
        model_path = out_dir / "model_artifacts.json"
        model_path.write_text(json.dumps(
            {"multinomial_control": model_ctrl, "platoon_challenger":
             model_chat},
            indent=1, sort_keys=True, default=str), encoding="utf-8")

        k_pmf_rows = []
        for key in sorted(realized):
            for bucket in range(24):
                k_pmf_rows.append({
                    "game_pk": key[0], "side": key[1], "pitcher": key[2],
                    "bucket": bucket,
                    "pmf_multinomial_control": float(
                        pmf_ctrl[key][bucket]),
                    "pmf_platoon": float(pmf_chat[key][bucket]),
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

        report = {
            "experiment_identity": EXPERIMENT_ID,
            "primary_contrast": paired_ll,
            "n_starts": len(realized),
            "n_matched_pas": int(matched.height),
            "mean_multiclass_logloss_control": ll_ctrl_pa,
            "mean_multiclass_logloss_platoon": ll_chat_pa,
            "classwise": {
                "control": _classwise(prob_ctrl_mat, cls_ctrl, y_vec),
                "platoon": _classwise(prob_chat_mat, cls_chat, y_vec),
                "note": "declared secondary evidence, not decisive",
            },
            "k_count": {
                "mean_rps_control": float(np.mean(
                    list(rps_ctrl.values()))),
                "mean_rps_platoon": float(np.mean(
                    list(rps_chat.values()))),
                "non_degradation": nondeg,
                "paired_contrast": paired_rps,
            },
            "reconstruction": reconstruction,
            "platoon_feature_accounting": {
                "family": pf.VERSION,
                "alpha": ALPHA,
                "n_rate_rows": int(rates.height),
            },
        }
        report_path = out_dir / "platoon_comparison_report.json"
        report_path.write_text(json.dumps(report, indent=1,
                                           sort_keys=True, default=str),
                                encoding="utf-8")
        outputs = {
            "platoon_per_start_v1.parquet": ad.sha256_file(
                per_start_path),
            "platoon_comparison_report.json": ad.sha256_file(
                report_path),
            "keyed_pa_probabilities.parquet": ad.sha256_file(keyed_path),
            "model_artifacts.json": ad.sha256_file(model_path),
            "k_pmf_per_start_v1.parquet": ad.sha256_file(k_pmf_path),
            "bf37_pooled_by_date_v1.parquet": ad.sha256_file(bf_path),
            "platoon_split_rates_v1.parquet": ad.sha256_file(
                out_dir / "platoon_split_rates_v1.parquet"),
        }
        final = dict(initial)
        final["counts"] = {
            "n_starts": len(realized),
            "n_requests_before_cohort": n_requests_before,
            "n_requests_after_cohort": n_requests_after,
            "n_train_rows": int(train.height),
            "n_matched_pas": int(matched.height),
            "n_starts_with_logloss": len(ll_ctrl_mean),
        }
        final["cohort_identity"] = cohort_identity
        final["reconstruction"] = reconstruction
        final["consumed_input_identities"] = input_identities or {}
        final["outputs"] = outputs
        final["primary_contrast"] = paired_ll
        final["model_artifacts"] = {
            "multinomial_control": {
                "mean": model_ctrl["mean"], "scale": model_ctrl["scale"],
                "features": model_ctrl["features"],
                "classes": model_ctrl["classes"]},
            "platoon_challenger": {
                "mean": model_chat["mean"], "scale": model_chat["scale"],
                "features": model_chat["features"],
                "classes": model_chat["classes"]},
            "note": ("reloadable: re-applying the reloaded models on the "
                     "same feature rows reproduces the saved per-key "
                     "class probabilities"),
        }
        final["acceptance"] = {"receipt_chain": initial_sha,
                               "status": "COMPLETED"}
        (out_dir / "receipt_final.json").write_text(
            json.dumps(final, indent=1, sort_keys=True, default=str),
            encoding="utf-8")
        if ad.sha256_file(initial_path) != initial_sha:
            raise ValueError("IMMUTABLE initial receipt modified")
    except Exception as exc:
        failure = {"stage": "platoon_information", "failure": True,
                   "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                            sort_keys=True),
                                encoding="utf-8")
        raise
    return {"out_dir": str(out_dir),
            "experiment_identity": EXPERIMENT_ID,
            "primary_contrast": paired_ll,
            "mean_multiclass_logloss_control": report[
                "mean_multiclass_logloss_control"],
            "mean_multiclass_logloss_platoon": report[
                "mean_multiclass_logloss_platoon"],
            "k_count": report["k_count"],
            "reconstruction": reconstruction,
            "outputs": outputs,
            "receipt_initial_sha256": initial_sha}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Platoon-information value comparison. Technical ack "
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
    p.add_argument("--cohort-keys", required=True)
    p.add_argument("--expected-cohort-hash", required=True)
    p.add_argument("--reconstruction-reference", required=True)
    p.add_argument("--expected-reconstruction-sha256", required=True)
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
    res = run_platoon_comparison(
        pa, lineups, assessment, args.out_dir,
        train_start=args.train_start, train_end=args.train_end,
        execution_ack=args.execution_ack, raw_events=raw_events,
        cohort_keys=cohort_keys,
        expected_cohort_hash=args.expected_cohort_hash,
        reconstruction_reference=recon_ref,
        reconstruction_reference_sha256=(
            input_identities["reconstruction_reference"]),
        input_identities=input_identities,
        ack_route="cli")
    print(json.dumps({
        "experiment": res["experiment_identity"],
        "primary_contrast": res["primary_contrast"],
        "mean_multiclass_logloss_control": res[
            "mean_multiclass_logloss_control"],
        "mean_multiclass_logloss_platoon": res[
            "mean_multiclass_logloss_platoon"],
        "out_dir": res["out_dir"]},
        indent=1, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
