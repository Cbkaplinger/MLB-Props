# run_lgbm_equal_info_v2.py -- EXECUTABLE FROZEN RUNNER for lgbm-equal-info-v2
# (freeze_lgbm_equal_info_v2.json, 2026-10-16): the CORRECTED equal-information
# LightGBM packet. SYNTHETIC-TESTED ONLY at freeze time; real-data execution
# additionally requires --i-accept-real-data-execution AND the owner readiness
# gate (this file alone authorizes nothing).
#
# Corrections vs the v1 nonconforming run b8bc222c (RUN_ASSESSMENT.md,
# 2026-10-16, in MLB-Props-Research\lgbm-equal-info-v1):
#   * MATCHED EXPOSURE (the fix): iteration selection runs on a training-only
#     inner carve-out of base_train WITH the per-round evaluation history
#     persisted; then a FRESH LightGBM refit on the FULL base_train at the
#     chosen fixed iteration (no early stopping in the refit). The logistic
#     reference is fit on the SAME full base_train, so both arms consume
#     exactly the same fit rows. v1 fit the LightGBM on base_train minus the
#     inner block while the logistic saw all of base_train (undisclosed
#     fit-row asymmetry: 98,466/176,080/245,633 vs 123,081/219,078/306,791).
#   * EVAL HISTORY: lgb.record_evaluation persists the inner-block metric
#     trajectory per round (v1 recorded no eval history anywhere).
#   * first_metric_only=True on the FIRST registered metric (binary_logloss)
#     is declared as a PREDECLARED DIAGNOSTIC in the freeze BEFORE execution
#     (addresses the v1 assessment's mechanism-2 confound: the coarse
#     binary_error metric could have triggered the stop).
#   * FULL PERSISTENCE: keyed RAW + CAL predictions/labels for both arms,
#     training-row IDs/counts per arm per fold, inner validation history +
#     selected iteration, per-fold + pooled metrics, paired bootstrap
#     draws/contrasts/intervals/p-values (2000 resamples, seed 20261001,
#     block-stratified, null-centered p-values + Holm per the registered
#     C3.8 method), booster.save_model per fold, logistic reference models
#     per fold. MLflow logging + fresh retrieval + hash verification stay
#     with the SHARED wrapper (track_and_verify.py, the executed path).
#
# Structure is identical to the v1 runner (run_lgbm_equal_info.py): execution
# gate -> registered identity verification BEFORE any fitting (D-2, LF-
# normalized hashes for declared text sources, byte-exact for binaries; the
# run manifest states this convention) -> write-once run dir -> fold
# construction from the registered inputs (existing chronological dev folds;
# confirm_2025H2 EXCLUDED - NOT SCORED; 2026 CLOSED) -> the shared wrapper
# (compare -> save -> log -> verify) -> run manifest.
#
# NO hyperparameter/feature/window/calibration search anywhere: the frozen
# hyperparameters below are byte-identical to the v1 adapter's
# LGBM_EQUAL_INFO_CONFIG (lake count-eval-v1 lgbm_equal_info_adapter.py).
#
# ASCII-only (cp1252 consoles).
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import comparison as cmp  # noqa: E402  (executed harness; registered by sha)
import track_and_verify as tv  # noqa: E402  (shared D-1 wrapper)

ACCEPT_FLAG = "--i-accept-real-data-execution"
RUN_NAME = "lgbm-equal-info-v2"

# ---------------------------------------------------------------------------
# Frozen config (REGISTERED-FROZEN; identical to the v1 frozen hyperparameters
# -- any change is a new config, not an edit). Byte-identical dict to
# lake count-eval-v1 lgbm_equal_info_adapter.LGBM_EQUAL_INFO_CONFIG
# (config_sha256 f7e3726a...); the v2 correction changes the PROCEDURE
# (selection -> refit; persistence), NOT the hyperparameters.
# ---------------------------------------------------------------------------

LGBM_EQUAL_INFO_CONFIG = {
    "interface": "count-eval-v1-lgbm-equal-info-1.0",
    "objective": "binary",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 100,
    "feature_fraction": 1.0,
    "bagging_fraction": 1.0,
    "bagging_freq": 0,
    "lambda_l1": 0.0,
    "lambda_l2": 0.0,
    "seed": 20261001,
    "feature_fraction_seed": 20261001,
    "data_random_seed": 20261001,
    "deterministic": True,
    "force_row_wise": True,
    "num_boost_round": 400,
    "early_stopping_rounds": 50,
    "early_stopping_data": "inner_block(base_train carve-out) ONLY",
    "class_weighting": "NONE (no scale_pos_weight, no is_unbalance)",
    "verbosity": -1,
    "metric": ["binary_logloss", "binary_error"],
}

# Same frozen feature set as the both-EW logistic reference (8 both-EW).
FEATURES_BOTH_EW = tuple(cmp.FEAT_H3)

REFERENCE_CANDIDATE = "P1_H3_incumbent_refit"
LGBM_CANDIDATE = "P2_lgbm_equal_info_v2"

CONTRAST_ID = "C_lgbm_v2_vs_both_EW_logistic"

FIRST_METRIC_ONLY = True
FIRST_METRIC_ONLY_DECLARATION = (
    "PREDECLARED DIAGNOSTIC (declared in the freeze BEFORE execution): "
    "early stopping tracks the FIRST registered metric (binary_logloss) only "
    "(lgb.early_stopping(first_metric_only=True)); binary_error stays "
    "registered and is recorded in the persisted eval history as a "
    "descriptive diagnostic. Addresses the v1 RUN_ASSESSMENT mechanism-2 "
    "confound (coarse binary_error trigger); it is a DIAGNOSTIC declaration, "
    "not a hyperparameter change.")

FINAL_FIT_DECLARATION_V2 = (
    "predictions come from a FRESH LightGBM refit on the FULL base_train at "
    "the chosen fixed iteration (selected on the training-only inner "
    "carve-out with persisted eval history); NO early stopping in the refit; "
    "the logistic reference is fit on the SAME full base_train (matched "
    "exposure; fit rows asserted equal per fold)")

# Short procedure summary (logged as MLflow params alongside the config).
V2_PROCEDURE_PARAMS = {
    "iteration_selection": ("inner base_train carve-out (last 20% of distinct "
                            "base_train slate dates); eval history persisted "
                            "per round; first_metric_only=True (predeclared "
                            "diagnostic)"),
    "final_refit": ("FRESH LightGBM refit on FULL base_train at the chosen "
                    "fixed iteration; no early stopping in the refit"),
    "reference_fit": ("both-EW logistic reference on the SAME full base_train "
                      "(matched exposure)"),
    "no_search": ("no hyperparameter/feature/window/calibration search; "
                  "hyperparameters identical to lgbm-equal-info-v1"),
}

CORRECTION_LINEAGE = {
    "supersedes_run": (
        "lgbm-equal-info-v1 run b8bc222c703a4a60e1eb0736143800e34601f61db0"
        "ced84cc067597b7796fd05 (NONCONFORMING execution, DEVELOPMENT "
        "DIAGNOSTIC)"),
    "assessment": (
        "MLB-Props-Research\\lgbm-equal-info-v1\\RUN_ASSESSMENT.md "
        "(2026-10-16): fit-row asymmetry confirmed; eval history "
        "unrecorded; best_iteration=1 not established"),
    "fixes": ["matched_exposure_refit_on_full_base_train",
              "eval_history_persisted_per_round",
              "first_metric_only_predeclared_diagnostic"],
}

MATCHED_EXPOSURE_CONTRACT = (
    "LightGBM: selection on the training-only inner carve-out, then FRESH "
    "refit on the FULL base_train at the chosen fixed iteration; logistic "
    "reference fit on the SAME full base_train; fit rows equal per fold "
    "(asserted) and persisted per arm")


def config_sha256() -> str:
    blob = json.dumps(LGBM_EQUAL_INFO_CONFIG, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# Fit: iteration selection (training-only inner carve-out) + fresh full refit
# ---------------------------------------------------------------------------

def _inner_split(X_train: np.ndarray, y_train: np.ndarray,
                 dates_train: np.ndarray, frac: float = 0.2):
    """Carve the permitted inner selection block out of base_train by slate
    date (last `frac` of distinct dates). Training-only: the inner block's
    labels are read ONLY through the selection metric; it is never reused for
    calibration or evaluation."""
    d = np.unique(dates_train)
    k = max(1, int(round(frac * d.size)))
    inner_dates = set(d[-k:].tolist())
    inner_mask = np.array([x in inner_dates for x in dates_train], dtype=bool)
    return np.nonzero(~inner_mask)[0], np.nonzero(inner_mask)[0]


def _lgbm_params() -> dict:
    c = LGBM_EQUAL_INFO_CONFIG
    return {
        "objective": c["objective"],
        "learning_rate": c["learning_rate"],
        "num_leaves": c["num_leaves"],
        "min_data_in_leaf": c["min_data_in_leaf"],
        "feature_fraction": c["feature_fraction"],
        "bagging_fraction": c["bagging_fraction"],
        "bagging_freq": c["bagging_freq"],
        "lambda_l1": c["lambda_l1"],
        "lambda_l2": c["lambda_l2"],
        "seed": c["seed"],
        "feature_fraction_seed": c["feature_fraction_seed"],
        "data_random_seed": c["data_random_seed"],
        "deterministic": c["deterministic"],
        "force_row_wise": c["force_row_wise"],
        "verbosity": c["verbosity"],
        "metric": c["metric"],
    }


def select_iteration(X_train: np.ndarray, y_train: np.ndarray,
                     dates_train: np.ndarray):
    """STAGE 1 (selection only): train with early stopping on the training-only
    inner carve-out, recording the per-round evaluation history via
    lgb.record_evaluation, with first_metric_only declared as a predeclared
    diagnostic. Returns (selected_iteration, eval_history, info,
    selection_booster). The returned booster is a selection artifact ONLY --
    scoring never uses it (see refit_full_at_iteration)."""
    import lightgbm as lgb

    fit_idx, inner_idx = _inner_split(X_train, y_train, dates_train)
    if inner_idx.size == 0:
        raise ValueError("inner selection block is empty")
    params = _lgbm_params()
    assert "scale_pos_weight" not in params and "is_unbalance" not in params
    train_set = lgb.Dataset(X_train[fit_idx], label=y_train[fit_idx])
    inner_set = lgb.Dataset(X_train[inner_idx], label=y_train[inner_idx],
                            reference=train_set)
    evals: dict = {}
    booster = lgb.train(
        params,
        train_set,
        num_boost_round=LGBM_EQUAL_INFO_CONFIG["num_boost_round"],
        valid_sets=[inner_set],
        valid_names=["inner_block"],
        callbacks=[
            lgb.early_stopping(
                LGBM_EQUAL_INFO_CONFIG["early_stopping_rounds"],
                first_metric_only=FIRST_METRIC_ONLY, verbose=False),
            lgb.record_evaluation(evals),
        ],
    )
    selected = int(booster.best_iteration or
                   LGBM_EQUAL_INFO_CONFIG["num_boost_round"])
    if not 1 <= selected <= LGBM_EQUAL_INFO_CONFIG["num_boost_round"]:
        raise ValueError(f"selected iteration out of range: {selected}")
    history = {ds: {m: [float(v) for v in vals]
                    for m, vals in metrics.items()}
               for ds, metrics in evals.items()}
    info = {
        "n_selection_fit_rows": int(fit_idx.size),
        "n_inner_rows": int(inner_idx.size),
        "first_metric_only": FIRST_METRIC_ONLY,
        "first_metric_only_declaration": FIRST_METRIC_ONLY_DECLARATION,
        "config_sha256": config_sha256(),
    }
    return selected, history, info, booster


def refit_full_at_iteration(X_train: np.ndarray, y_train: np.ndarray,
                            num_iter: int):
    """STAGE 2 (the scoring model): FRESH LightGBM refit on the FULL base_train
    at the chosen fixed iteration. No valid sets, no early stopping, no
    callbacks: the booster has exactly `num_iter` trees."""
    import lightgbm as lgb

    k = int(num_iter)
    if not 1 <= k <= LGBM_EQUAL_INFO_CONFIG["num_boost_round"]:
        raise ValueError(f"refit iteration out of range: {k}")
    booster = lgb.train(_lgbm_params(),
                        lgb.Dataset(X_train, label=y_train),
                        num_boost_round=k)
    if int(booster.num_trees()) != k:
        raise cmp.AdapterContractError(
            f"refit booster has {booster.num_trees()} trees, expected {k}")
    return booster


def predict_raw_refit(booster, X: np.ndarray) -> np.ndarray:
    """Predictions from the fresh refit booster (all trees = the chosen fixed
    iteration; no num_iteration argument, nothing left to select)."""
    if int(booster.num_trees()) != int(booster.current_iteration()):
        raise cmp.AdapterContractError("refit booster tree count mismatch")
    p = booster.predict(X)
    return cmp._check_proba(p, X.shape[0], LGBM_CANDIDATE + ".raw")


def predict_cal(booster, X_cal: np.ndarray, y_cal: np.ndarray,
                X: np.ndarray) -> np.ndarray:
    """CAL lane, SEPARATE: sigmoid calibrator (1-D unpenalized logistic of y
    on logit(p), identical definition to the executed logistic adapters) fit
    on the calibration sub-block ONLY, then applied."""
    p_raw_cal = predict_raw_refit(booster, X_cal)
    a, b = cmp.sigmoid_fit(y_cal, p_raw_cal)
    return cmp.sigmoid_apply(predict_raw_refit(booster, X), a, b)


# ---------------------------------------------------------------------------
# Reference (both-EW logistic) on the SAME full base_train
# ---------------------------------------------------------------------------

def fit_reference_logistic(X_train: np.ndarray, y_train: np.ndarray):
    """MATCHED EXPOSURE: the reference is fit on the FULL base_train -- the
    exact same rows the fresh LightGBM refit consumed."""
    ref = cmp.LogisticAdapter(REFERENCE_CANDIDATE, FEATURES_BOTH_EW,
                              incumbent_refit=True)
    fitted = ref.fit("fold", X_train, y_train.astype(int))
    return ref, fitted


# ---------------------------------------------------------------------------
# Persistence helpers (write-once files inside the run dir)
# ---------------------------------------------------------------------------

def _write_once(path: Path, write) -> None:
    if path.exists():
        raise cmp.WriteOnceError(
            f"write-once violation: {path} already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    write(path)


def _inventory(out_dir: Path, relpath: str, artifact_subdir: str) -> dict:
    """sha256 inventory entry for one persisted output. Convention: byte-exact
    sha256 for every file; text outputs (.json) additionally carry an
    LF-normalized sha256 (the declared text-source identity convention)."""
    p = out_dir / relpath
    cls = tv.file_identity_class(p)
    entry = {
        "relpath": relpath.replace("\\", "/"),
        "artifact_subdir": artifact_subdir,
        "identity_class": cls,
        "sha256": tv.sha256_file(p),
    }
    if cls == "text":
        entry["lf_normalized_sha256"] = (
            tv.sha256_file_identity(p)["lf_normalized"])
    return entry


def _preds_frame(eval_keys: pl.DataFrame, y: np.ndarray,
                 pred_raw: np.ndarray, pred_cal: np.ndarray) -> pl.DataFrame:
    return eval_keys.with_columns([
        pl.Series("y", y.astype(np.int64)),
        pl.Series("pred_raw", pred_raw, dtype=pl.Float64),
        pl.Series("pred_cal", pred_cal, dtype=pl.Float64),
    ])


# ---------------------------------------------------------------------------
# Corrected equal-information comparison with full persistence
# ---------------------------------------------------------------------------

def compare_on_dev_folds(folds: list[dict], out_dir) -> dict:
    """folds: list of dicts with keys
        name, X_train, y_train, dates_train, train_keys,
        X_cal, y_cal, X_eval, y_eval, dates_eval, eval_keys
    (train_keys / eval_keys: Polars frames with the identity columns +
    game_date; eval_keys rows align 1:1 with X_eval/y_eval).

    MATCHED EXPOSURE per fold: LightGBM iteration selection on the inner
    carve-out (eval history persisted) -> FRESH refit on the FULL base_train
    at the chosen fixed iteration; logistic reference fit on the SAME full
    base_train; fit-row IDs persisted per arm and asserted identical.
    """
    out_dir = Path(out_dir)
    per_fold = {}
    pooled = {"y": [], "dates": [], "blocks": [], "raw": {}, "ll": {},
              "cal": {}}
    for c in (LGBM_CANDIDATE, REFERENCE_CANDIDATE):
        pooled["raw"][c], pooled["ll"][c], pooled["cal"][c] = [], [], []

    for fd in folds:
        name = fd["name"]
        X_tr = np.asarray(fd["X_train"], dtype=np.float64)
        y_tr = np.asarray(fd["y_train"], dtype=np.int64)
        d_tr = np.asarray(fd["dates_train"], dtype=object)
        train_keys = fd["train_keys"]
        X_ev = np.asarray(fd["X_eval"], dtype=np.float64)
        y_ev = np.asarray(fd["y_eval"], dtype=np.float64)
        eval_keys = fd["eval_keys"]
        assert X_tr.shape[1] == len(FEATURES_BOTH_EW)
        assert X_ev.shape[1] == len(FEATURES_BOTH_EW)
        assert eval_keys.height == X_ev.shape[0]
        eval_identity = cmp.eval_identity_hash(eval_keys)

        # STAGE 1: selection on the training-only inner carve-out.
        sel_iter, eval_history, sel_info, _sel_booster = select_iteration(
            X_tr, y_tr, d_tr)

        # STAGE 2: fresh refit on the FULL base_train at the chosen iteration.
        booster = refit_full_at_iteration(X_tr, y_tr, sel_iter)

        # Reference on the SAME full base_train -> matched exposure.
        ref, ref_fitted = fit_reference_logistic(X_tr, y_tr)
        n_base = int(X_tr.shape[0])
        n_ref = int(ref_fitted["n_train"])
        if n_ref != n_base:
            raise cmp.AdapterContractError(
                f"{name}: matched-exposure violation "
                f"(base_train={n_base}, lgbm_refit={n_base}, "
                f"logistic_fit={n_ref})")

        # Persist training-row IDs/counts PER ARM (identical rows by
        # construction; both arms' files are saved and hash-compared).
        fit_identity = cmp.eval_identity_hash(train_keys)
        for cand in (LGBM_CANDIDATE, REFERENCE_CANDIDATE):
            _write_once(
                out_dir / f"fit_rows_{name}__{cand}.parquet",
                lambda p, tk=train_keys, cd=cand: tk.write_parquet(
                    p, metadata={"run_metadata": json.dumps({
                        "fold": name, "candidate": cd,
                        "role": "fit-consumed training rows (full base_train)",
                        "n_rows": int(tk.height),
                        "fit_identity_sha256": fit_identity,
                    })}))

        # Predictions (keyed, RAW + CAL, labels) for BOTH arms.
        p_lgb = predict_raw_refit(booster, X_ev)
        p_ref = cmp._check_proba(
            ref.predict_raw(ref_fitted, X_ev), X_ev.shape[0],
            REFERENCE_CANDIDATE + ".raw")
        X_ca = np.asarray(fd["X_cal"], dtype=np.float64)
        y_ca = np.asarray(fd["y_cal"], dtype=np.int64)
        cal_lgb = predict_cal(booster, X_ca, y_ca, X_ev)
        ref_calibrator = ref.calibrate(None, ref_fitted, X_ca, y_ca)
        cal_ref = cmp._check_proba(
            ref.predict_cal(ref_fitted, ref_calibrator, X_ev),
            X_ev.shape[0], REFERENCE_CANDIDATE + ".cal")

        for cand, praw, pcal in ((LGBM_CANDIDATE, p_lgb, cal_lgb),
                                 (REFERENCE_CANDIDATE, p_ref, cal_ref)):
            _write_once(
                out_dir / f"preds_{name}__{cand}.parquet",
                lambda p, cd=cand, pf=_preds_frame(
                    eval_keys, y_ev, praw, pcal): pf.write_parquet(
                    p, metadata={"run_metadata": json.dumps({
                        "fold": name, "candidate": cd,
                        "eval_identity_sha256": eval_identity,
                        "lanes": "pred_raw principal; pred_cal separate",
                        "batch_id": "lgbm-equal-info-v2",
                    })}))

        # Inner validation history + selected iteration (per round, both
        # registered metrics; first_metric_only is the predeclared
        # diagnostic that made binary_logloss the stopping metric).
        hist = eval_history["inner_block"]
        if set(hist) != {"binary_logloss", "binary_error"}:
            raise cmp.AdapterContractError(
                f"{name}: unexpected eval-history keys {sorted(hist)}")
        n_rounds = len(hist["binary_logloss"])
        if len(hist["binary_error"]) != n_rounds or n_rounds < 1:
            raise cmp.AdapterContractError(
                f"{name}: malformed eval history")
        if sel_iter > n_rounds:
            raise cmp.AdapterContractError(
                f"{name}: selected iteration {sel_iter} exceeds recorded "
                f"history length {n_rounds}")
        history_doc = {
            "fold": name,
            "candidate": LGBM_CANDIDATE,
            "selected_iteration": int(sel_iter),
            "num_boost_round_cap": int(
                LGBM_EQUAL_INFO_CONFIG["num_boost_round"]),
            "early_stopping_rounds": int(
                LGBM_EQUAL_INFO_CONFIG["early_stopping_rounds"]),
            "first_metric_only": FIRST_METRIC_ONLY,
            "first_metric_only_declaration": FIRST_METRIC_ONLY_DECLARATION,
            "n_selection_fit_rows": sel_info["n_selection_fit_rows"],
            "n_inner_rows": sel_info["n_inner_rows"],
            "eval_history": eval_history,
            "note": ("per-round metric values on the inner eval set "
                     "(training-only carve-out); recorded via "
                     "lgb.record_evaluation"),
        }
        _write_once(
            out_dir / f"inner_eval_history_{name}.json",
            lambda p, doc=history_doc: p.write_text(
                json.dumps(doc, indent=2), encoding="utf-8"))

        # Saved models where practical: booster.save_model per fold
        # (exactly the chosen fixed iteration of trees) + the logistic
        # reference fit (scaler + lr) via joblib.
        _write_once(
            out_dir / "boosters" / f"{name}__{LGBM_CANDIDATE}.txt",
            lambda p, b=booster: b.save_model(str(p)))
        _write_once(
            out_dir / "reference_models"
            / f"{name}__{REFERENCE_CANDIDATE}.joblib",
            lambda p, ft=ref_fitted: _dump_reference(fitted=ft, path=p))

        per_fold[name] = {
            "n_base_train": n_base,
            "n_cal": int(y_ca.size),
            "n_eval": int(y_ev.size),
            "n_dates": int(np.unique(fd["dates_eval"]).size),
            "eval_identity_sha256": eval_identity,
            "fit_rows_identity_sha256": fit_identity,
            "fit_rows_matched": True,
            "lgbm": {
                "brier_raw": float(np.mean((p_lgb - y_ev) ** 2)),
                "log_loss_raw": float(np.mean(cmp.log_loss(y_ev, p_lgb))),
                "brier_cal": float(np.mean((cal_lgb - y_ev) ** 2)),
                "n_fit_rows_refit": n_base,
                "selected_iteration": int(sel_iter),
                "n_inner_rows": int(sel_info["n_inner_rows"]),
                "n_selection_fit_rows": int(sel_info["n_selection_fit_rows"]),
            },
            "reference": {
                "brier_raw": float(np.mean((p_ref - y_ev) ** 2)),
                "log_loss_raw": float(np.mean(cmp.log_loss(y_ev, p_ref))),
                "brier_cal": float(np.mean((cal_ref - y_ev) ** 2)),
                "n_fit_rows": n_ref,
            },
        }
        pooled["y"].append(y_ev)
        pooled["dates"].append(np.asarray(fd["dates_eval"], dtype=object))
        pooled["blocks"].append(np.asarray(fd["blocks_eval"], dtype=object))
        pooled["raw"][LGBM_CANDIDATE].append((p_lgb - y_ev) ** 2)
        pooled["raw"][REFERENCE_CANDIDATE].append((p_ref - y_ev) ** 2)
        pooled["ll"][LGBM_CANDIDATE].append(cmp.log_loss(y_ev, p_lgb))
        pooled["ll"][REFERENCE_CANDIDATE].append(cmp.log_loss(y_ev, p_ref))
        pooled["cal"][LGBM_CANDIDATE].append((cal_lgb - y_ev) ** 2)
        pooled["cal"][REFERENCE_CANDIDATE].append((cal_ref - y_ev) ** 2)

    # Pooled dev rows (dev folds ONLY; confirm_2025H2 never pooled).
    y = np.concatenate(pooled["y"])
    dates = np.concatenate(pooled["dates"])
    blocks = np.concatenate(pooled["blocks"])
    rows = {c: np.concatenate(pooled["raw"][c]) for c in pooled["raw"]}
    rows_ll = {c: np.concatenate(pooled["ll"][c]) for c in pooled["ll"]}
    rows_cal = {c: np.concatenate(pooled["cal"][c]) for c in pooled["cal"]}

    # Registered C3.8 test: ONE predeclared RAW Brier contrast from ONE
    # shared draw stream; null-centered p-values + Holm across the
    # registered contrast family (2000 resamples, seed 20261001).
    draws = cmp.slate_date_draws(rows, dates, blocks, n_boot=cmp.N_BOOT,
                                 seed=cmp.SEED_BOOTSTRAP)
    ht = cmp.null_centered_contrast_test(
        rows, [(CONTRAST_ID, LGBM_CANDIDATE, REFERENCE_CANDIDATE)],
        dates, blocks, n_boot=cmp.N_BOOT, seed=cmp.SEED_BOOTSTRAP,
        res=draws)
    idx = {n: i for i, n in enumerate(rows)}
    ia, ib = idx[LGBM_CANDIDATE], idx[REFERENCE_CANDIDATE]
    rep_a, rep_b = draws[:, ia], draws[:, ib]
    assert rep_a.ndim == rep_b.ndim == 1
    assert rep_a.shape == rep_b.shape == (cmp.N_BOOT,)
    delta_rep = rep_a - rep_b
    contrast_rec = ht["contrasts"][CONTRAST_ID]
    contrast = {
        "id": CONTRAST_ID,
        "a": LGBM_CANDIDATE, "b": REFERENCE_CANDIDATE,
        "metric": "Brier (RAW, primary)",
        "delta": contrast_rec["delta"],
        "delta_log_loss_secondary": float(
            rows_ll[LGBM_CANDIDATE].mean()
            - rows_ll[REFERENCE_CANDIDATE].mean()),
        "delta_brier_cal_descriptive": float(
            rows_cal[LGBM_CANDIDATE].mean()
            - rows_cal[REFERENCE_CANDIDATE].mean()),
        "ci95_unadjusted": [float(np.percentile(delta_rep, 2.5)),
                            float(np.percentile(delta_rep, 97.5))],
        "p_value_null_centered": contrast_rec["p_value"],
        "p_holm": contrast_rec["p_holm"],
        "n_boot": int(cmp.N_BOOT), "seed": int(cmp.SEED_BOOTSTRAP),
        "baseline_binding": (
            "explicit: contrast = P2_lgbm_equal_info_v2 - "
            "P1_H3_incumbent_refit on identical pooled rows (matched "
            "exposure), shared draw stream, 1-D replicate shapes asserted"),
        "method": ht["method"],
        "multiplicity": ht["multiplicity"],
        "estimand": ht["estimand"],
    }
    per_arm_intervals = cmp.slate_date_bootstrap(
        rows, dates, blocks, n_boot=cmp.N_BOOT, seed=cmp.SEED_BOOTSTRAP)

    # Persist the paired bootstrap draws (shared stream; per-arm replicates
    # + signed delta replicates for the registered contrast).
    draws_df = pl.DataFrame({
        "draw_index": np.arange(cmp.N_BOOT, dtype=np.int64),
        "rep_brier_raw__" + LGBM_CANDIDATE: rep_a,
        "rep_brier_raw__" + REFERENCE_CANDIDATE: rep_b,
        "delta_rep_brier_raw": delta_rep,
    })
    draws_rel = f"bootstrap/contrast_draws__{CONTRAST_ID}.parquet"
    _write_once(out_dir / draws_rel, lambda p: draws_df.write_parquet(p))

    persistence = []
    for fold_name in per_fold:
        for cand in (LGBM_CANDIDATE, REFERENCE_CANDIDATE):
            persistence.append(_inventory(
                out_dir, f"preds_{fold_name}__{cand}.parquet", "predictions"))
            persistence.append(_inventory(
                out_dir, f"fit_rows_{fold_name}__{cand}.parquet",
                "training_rows"))
        persistence.append(_inventory(
            out_dir, f"inner_eval_history_{fold_name}.json",
            "inner_eval_history"))
        persistence.append(_inventory(
            out_dir, f"boosters/{fold_name}__{LGBM_CANDIDATE}.txt",
            "boosters"))
        persistence.append(_inventory(
            out_dir,
            f"reference_models/{fold_name}__{REFERENCE_CANDIDATE}.joblib",
            "reference_models"))
    persistence.append(_inventory(out_dir, draws_rel, "bootstrap"))

    res_cfg = {**LGBM_EQUAL_INFO_CONFIG, **V2_PROCEDURE_PARAMS}
    return {
        "config": res_cfg,
        "config_sha256": config_sha256(),
        "features": list(FEATURES_BOTH_EW),
        "per_fold": per_fold,
        "pooled": {
            "n": int(y.size), "n_dates": int(np.unique(dates).size),
            "brier_raw": {c: float(rows[c].mean()) for c in rows},
            "log_loss_raw": {c: float(rows_ll[c].mean()) for c in rows_ll},
            "brier_cal_descriptive": {c: float(rows_cal[c].mean())
                                      for c in rows_cal},
            "per_candidate_intervals": {
                c: per_arm_intervals[c] for c in rows},
        },
        "contrast": contrast,
        "hypothesis_test": ht,
        "matched_exposure": {
            "contract": MATCHED_EXPOSURE_CONTRACT,
            "per_fold_fit_rows": {
                f: {"lgbm_refit": rec["lgbm"]["n_fit_rows_refit"],
                    "logistic": rec["reference"]["n_fit_rows"],
                    "equal": rec["lgbm"]["n_fit_rows_refit"]
                    == rec["reference"]["n_fit_rows"]}
                for f, rec in per_fold.items()},
            "fit_rows_identity_sha256": {
                f: rec["fit_rows_identity_sha256"]
                for f, rec in per_fold.items()},
        },
        "first_metric_only_diagnostic": FIRST_METRIC_ONLY_DECLARATION,
        "final_fit_declaration": FINAL_FIT_DECLARATION_V2,
        "correction_lineage": CORRECTION_LINEAGE,
        "persistence": persistence,
        "real_data_execution": (
            "PENDING READINESS GATE (not yet READY; the standing conditional "
            "authorization applies after READY - see "
            "freeze_lgbm_equal_info_v2.json)"),
    }


def _dump_reference(*, fitted, path) -> None:
    import joblib

    joblib.dump(fitted, path)


# ---------------------------------------------------------------------------
# MLflow describe: full metric + artifact inventory through the shared wrapper
# ---------------------------------------------------------------------------

def _v2_metrics(result: dict) -> dict:
    metrics: dict[str, float] = {}
    for lane, key in (("brier_raw", "pooled_brier_raw"),
                      ("log_loss_raw", "pooled_log_loss_raw"),
                      ("brier_cal_descriptive", "pooled_brier_cal")):
        for cand, val in result["pooled"][lane].items():
            metrics[f"{key}__{cand}"] = float(val)
    c = result["contrast"]
    metrics["contrast_delta_brier_raw"] = float(c["delta"])
    metrics["contrast_ci_lo"] = float(c["ci95_unadjusted"][0])
    metrics["contrast_ci_hi"] = float(c["ci95_unadjusted"][1])
    metrics["contrast_p_value_null_centered"] = float(
        c["p_value_null_centered"])
    metrics["contrast_p_holm"] = float(c["p_holm"])
    for fold, rec in result["per_fold"].items():
        metrics[f"selected_iteration__{fold}"] = float(
            rec["lgbm"]["selected_iteration"])
        metrics[f"n_fit_rows_matched__{fold}"] = float(
            rec["lgbm"]["n_fit_rows_refit"])
    return metrics


def v2_describe(result: dict, out_dir=None, saved=None,
                extra_params: dict | None = None):
    """Describe for the shared wrapper: params (frozen config + procedure),
    the full metric inventory, and EVERY persisted file as an MLflow
    artifact (the wrapper hash-verifies the config artifact)."""
    params = {}
    for k, v in result["config"].items():
        params[str(k)] = (v if isinstance(v, (int, float, str, bool))
                          else json.dumps(v))
    params["features"] = ",".join(result["features"])
    params["candidates"] = ",".join(result["pooled"]["brier_raw"])
    if extra_params:
        params.update(extra_params)
    metrics = _v2_metrics(result)
    artifacts = []
    if saved is not None:
        artifacts.append((saved["config_artifact_path"], "config"))
    if out_dir is not None:
        out_dir = Path(out_dir)
        artifacts.append((str(out_dir / "metrics.json"), "metrics"))
        for entry in result["persistence"]:
            artifacts.append((str(out_dir / entry["relpath"]),
                              entry["artifact_subdir"]))
    return params, metrics, artifacts


# ---------------------------------------------------------------------------
# Fold construction from the registered inputs (identical to v1 structure)
# ---------------------------------------------------------------------------

def build_real_folds(df: pl.DataFrame, feature_names: tuple) -> list[dict]:
    """Build the fold dicts from the loaded PA frame using the executed
    comparison.py fold derivation (runtime calibration spans). DEV BLOCKS
    ONLY: confirm_2025H2 is EXCLUDED - NOT SCORED. train_keys / eval_keys
    carry the identity columns + game_date so training rows and predictions
    are persisted KEYED."""
    folds = cmp.derive_folds(df)
    out: list[dict] = []
    for name in cmp.DEV_BLOCKS:
        f = folds[name]

        def win(d0, d1):
            return df.filter(
                (pl.col("game_date") >= pl.date(d0.year, d0.month, d0.day))
                & (pl.col("game_date") <= pl.date(d1.year, d1.month, d1.day)))

        train = win(f.train_start, f.cal_first - dt.timedelta(days=1))
        cal = win(f.cal_first, f.cal_last)
        eval_df = win(f.assess_start, f.assess_end)
        cmp.enforce_availability_guard(eval_df)
        if train.height == 0 or cal.height == 0 or eval_df.height == 0:
            raise cmp.FoldConstructionError(
                f"{name}: empty real-data partition "
                f"(train={train.height}, cal={cal.height}, "
                f"eval={eval_df.height})")
        out.append({
            "name": name,
            "X_train": train.select(list(feature_names)).to_numpy(),
            "y_train": train["y"].to_numpy().astype(int),
            # datetime.date objects (not np.datetime64): the inner split and
            # the slate-date bootstrap group by plain date objects
            "dates_train": np.array(train["game_date"].to_list(),
                                    dtype=object),
            "train_keys": train.select([*cmp.IDENTITY_COLS, "game_date"]),
            "X_cal": cal.select(list(feature_names)).to_numpy(),
            "y_cal": cal["y"].to_numpy().astype(int),
            "X_eval": eval_df.select(list(feature_names)).to_numpy(),
            "y_eval": eval_df["y"].to_numpy().astype(int),
            "dates_eval": np.array(eval_df["game_date"].to_list(),
                                   dtype=object),
            "eval_keys": eval_df.select([*cmp.IDENTITY_COLS, "game_date"]),
            "blocks_eval": np.array([name] * eval_df.height),
        })
    return out


# ---------------------------------------------------------------------------
# main: identical structure to the v1 runner
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Frozen lgbm-equal-info-v2 command (corrected "
                    "equal-information packet).")
    p.add_argument("--freeze", required=True,
                   help="path to freeze_lgbm_equal_info_v2.json")
    p.add_argument("--tracking-uri", default=None,
                   help="override the registered MLflow tracking URI")
    p.add_argument(ACCEPT_FLAG, dest="accept_real_data_execution",
                   action="store_true",
                   help="the --i-accept-outcome-scoring equivalent: "
                        "acknowledge this batch scores realized outcomes "
                        "on the registered dev folds")
    args = p.parse_args(argv)
    if not args.accept_real_data_execution:
        print(f"REFUSED: real-data execution requires {ACCEPT_FLAG} "
              "(the --i-accept-outcome-scoring equivalent). Nothing was "
              "read, fitted, scored, or written.")
        return 2

    freeze = json.loads(Path(args.freeze).read_text(encoding="utf-8"))
    cfg = freeze["config"]

    # D-2: registered identity verification BEFORE any fitting. Declared
    # text sources verify LF-normalized; binaries (all registered inputs)
    # verify byte-exact.
    ident = tv.verify_registered_identities(
        args.freeze, adapter_module=sys.modules[__name__],
        runner_path=__file__)
    inputs = cfg["registered_inputs"]

    run_identity = {
        "batch_id": freeze["batch_id"],
        "freeze_config_sha256": freeze["config_sha256"],
        "input_sha256": {k: inputs[k]["sha256"]
                         for k in ("pa_table", "features_v3")},
        "adapter_file_sha256": cfg["adapter"]["file_sha256"],
        "comparison_sha256":
            cfg["builder_worktree_harness"]["comparison_sha256"],
        "wrapper_file_sha256": cfg["tracking_wrapper"]["file_sha256"],
    }
    run_id = hashlib.sha256(
        json.dumps(run_identity, sort_keys=True).encode("utf-8")
    ).hexdigest()

    out_dir = Path(cfg["output_destination"]) / run_id
    if out_dir.exists():
        raise cmp.WriteOnceError(
            f"write-once violation: output dir {out_dir} already exists "
            "(never overwrite a prior run)")
    out_dir.mkdir(parents=True)

    df = cmp.load_pa_rows(inputs["pa_table"]["path"],
                          inputs["features_v3"]["path"])
    feature_names = tuple(cfg["equal_information_contract"]["features"])
    fold_dicts = build_real_folds(df, feature_names)

    def compare_fn():
        return compare_on_dev_folds(fold_dicts, out_dir)

    tracking_uri = args.tracking_uri or cfg["tracking"]["tracking_uri"]
    status = tv.track_and_verify(
        compare_fn, out_dir, tracking_uri,
        experiment=cfg["tracking"]["experiment"], run_name=RUN_NAME,
        describe=v2_describe)

    # The full persistence inventory lives in metrics.json (result dict);
    # the execution record (this manifest) states the identity convention
    # and summarizes the inventory.
    metrics_doc = json.loads(
        (out_dir / "metrics.json").read_text(encoding="utf-8"))
    manifest = {
        "run_id": run_id,
        "batch_id": freeze["batch_id"],
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "freeze_path": str(Path(args.freeze).resolve()),
        "freeze_config_sha256": freeze["config_sha256"],
        "run_identity": run_identity,
        "identity_verification": {"ok": True,
                                  "checked": ident["checked"]},
        # Execution record states the identity convention: EOL-normalized
        # hashes for declared text sources, byte-exact for binaries.
        "identity_convention": {
            "text_source_identity_convention":
                tv.TEXT_SOURCE_IDENTITY_CONVENTION,
            "eol_note": (
                "declared text-source files (.py/.json/.md) are identified "
                "by sha256 over LF-normalized content; declared binary "
                "files and all registered inputs are byte-exact; THIS "
                "execution record states the convention per the v2 freeze"),
        },
        "folds_executed": [fd["name"] for fd in fold_dicts],
        "confirm_block_status": "EXCLUDED - NOT SCORED (dev blocks only)",
        "final_fit_declaration": cfg.get(
            "final_fit_declaration", FINAL_FIT_DECLARATION_V2),
        "first_metric_only_diagnostic": FIRST_METRIC_ONLY_DECLARATION,
        "correction_lineage": CORRECTION_LINEAGE,
        "matched_exposure": {"contract": MATCHED_EXPOSURE_CONTRACT},
        "persistence_inventory": {
            "file_count": len(metrics_doc["persistence"]),
            "files": [e["relpath"] for e in metrics_doc["persistence"]],
            "note": ("sha256 inventory in metrics.json (byte-exact for "
                     "binaries; LF-normalized hashes also recorded for "
                     "text outputs)"),
        },
        "tracking": {
            "wrapper": "track_and_verify.track_and_verify (shared D-1 "
                       "wrapper: compare -> save -> log -> verify)",
            "tracking_uri": tracking_uri,
            "experiment": cfg["tracking"]["experiment"],
            "status": status["status"],
            "run_id": status["run_id"],
        },
        "start_metrics_outcome_source": {
            **inputs["start_metrics_outcome_source"],
            "join_status": "REGISTERED-PATH-ONLY - not read, not joined "
                           "by this command"},
    }
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"run_id": run_id, "output_dir": str(out_dir),
                      "tracking_status": status["status"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
