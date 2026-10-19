# test_lgbm_equal_info_v2.py -- SYNTHETIC TEST SUITE for the corrected
# equal-information LightGBM packet (lgbm-equal-info-v2, runner
# run_lgbm_equal_info_v2.py, freeze_lgbm_equal_info_v2.json).
# SYNTHETIC ONLY: temp tracking stores + temp artifacts + synthetic parquets;
# the canonical mlflow.db and the real lake destination are never touched,
# and NO real-data execution happens here.
#
# What these prove:
#   * end-to-end: the frozen v2 command on synthetic parquets runs the whole
#     corrected pipeline -- registered identity verification, fold
#     construction, iteration selection on the training-only inner carve-out
#     WITH the per-round eval history persisted, FRESH refit on the FULL
#     base_train at the chosen fixed iteration, logistic reference on the
#     SAME rows, full persistence (keyed RAW+CAL predictions/labels for both
#     arms, per-arm fit-row IDs, inner histories, boosters, reference models,
#     bootstrap draws, per-fold + pooled metrics, sha inventory), and the
#     SHARED wrapper's MLflow log -> fresh-process retrieval + hash
#     verification;
#   * regression (the v1 defect): logistic fit rows == LightGBM refit rows
#     per fold (matched exposure), asserted on the persisted per-arm fit-row
#     ID parquets;
#   * refit-at-chosen-iteration: the scoring booster has exactly the chosen
#     number of trees and differs from the selection-stage booster;
#   * refusal gate: no --i-accept-real-data-execution flag -> exit 2,
#     nothing read or written.
#
# Run: .venv python -m pytest test_lgbm_equal_info_v2.py -q
# ASCII-only (cp1252 consoles).
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
# sys.path order matters (amendment-2, same as test_auto_tracking.py): the
# lake count-eval-v1 dir holds a HISTORICAL amendment-1 mirror of
# track_and_verify.py (preserved, not updated), so it is inserted FIRST and
# this harness dir is inserted LAST so the registered harness modules shadow
# the stale mirror.
sys.path.insert(0, r"C:\Users\ckaplinger\MLB-Props-Research\count-eval-v1")
sys.path.insert(0, HERE)

LOG_MODE = "log"
VERIFY_MODE = "verify"
HANDOFF = "v2_auto_tracking_handoff.json"

import comparison as cmp_mod  # noqa: E402  (registered harness modules win)
import run_lgbm_equal_info_v2 as runner  # noqa: E402
import track_and_verify as tv  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic inputs (same shape as the v1 frozen-command test: all four
# registered fold windows covered, 2023-01-05..2025-09-25)
# ---------------------------------------------------------------------------

def _synthetic_real_frames():
    import polars as pl

    feat_names = cmp_mod.FEAT_H3
    rng = np.random.default_rng(20261001)
    dates = [date(2023, 1, 5) + timedelta(days=10 * i) for i in range(97)]
    rows = []
    n = 0
    for d in dates:
        for _ in range(8):
            feats = [
                float(np.clip(rng.normal(0.22, 0.06), 0.01, 0.99)),
                float(np.clip(rng.normal(0.22, 0.06), 0.01, 0.99)),
                float(np.clip(rng.normal(0.22, 0.01), 0.01, 0.99)),
                float(rng.integers(0, 800)),
                float(rng.integers(0, 800)),
                float(rng.integers(0, 2)),
                float(rng.normal(0.0, 0.05)),
                float(rng.normal(0.0, 0.05)),
            ]
            y = int(rng.random() < 0.45)
            rows.append((n + 1, 1, (n % 50) + 1, d, y, *feats))
            n += 1
    cols = ["game_pk", "at_bat_number", "batter", "game_date", "y",
            *feat_names]
    full = pl.DataFrame(rows, schema=cols, orient="row")
    pa_df = full.select(["game_pk", "at_bat_number", "batter", "game_date",
                         "y"])
    feat_df = full.select(["game_pk", "at_bat_number", "batter", "game_date",
                           *feat_names])
    return feat_df, pa_df


def _write_synthetic_parquets(tmp_path):
    feat_df, pa_df = _synthetic_real_frames()
    feat_path = tmp_path / "features_v3.parquet"
    pa_path = tmp_path / "pa_table.parquet"
    sm_path = tmp_path / "start_metrics_v2.parquet"
    feat_df.write_parquet(feat_path)
    pa_df.write_parquet(pa_path)
    # registered PATH+HASH ONLY: content never read or joined by the command
    pa_df.head(1).write_parquet(sm_path)
    return feat_path, pa_path, sm_path


def _make_synthetic_freeze(tmp_path, input_paths=None, extra_cfg=None):
    """Synthetic freeze with the REAL runner/wrapper/comparison hashes and
    SYNTHETIC input files (or caller-supplied input paths)."""
    files = {}
    for name in ("pa_table", "features_v3", "start_metrics_outcome_source"):
        if input_paths is not None:
            files[name] = Path(input_paths[name])
            continue
        f = tmp_path / f"{name}.bin"
        f.write_bytes(f"synthetic {name} bytes".encode("ascii"))
        files[name] = f
    runner_path = os.path.join(HERE, "run_lgbm_equal_info_v2.py")
    cfg = {
        "interface_version": "lgbm-equal-info-v2-synthetic",
        "text_source_identity_convention": tv.TEXT_SOURCE_IDENTITY_CONVENTION,
        "lgbm_hyperparameters": dict(runner.LGBM_EQUAL_INFO_CONFIG),
        "iteration_selection_procedure":
            "synthetic declaration of the corrected procedure",
        "registered_inputs": {
            k: {"path": str(files[k]),
                "sha256": tv.sha256_file(files[k])}
            for k in files},
        "adapter": {"path": runner_path,
                    "file_sha256": tv.sha256_file(runner_path),
                    "file_sha256_normalized":
                        tv.sha256_file_identity(runner_path)[
                            "lf_normalized"],
                    "config_sha256": runner.config_sha256()},
        "tracking_wrapper": {
            "path": tv.__file__,
            "file_sha256": tv.sha256_file(tv.__file__),
            "file_sha256_normalized":
                tv.sha256_file_identity(tv.__file__)["lf_normalized"]},
        "builder_worktree_harness": {
            "comparison_path": str(cmp_mod.__file__),
            "comparison_sha256": tv.sha256_file(cmp_mod.__file__),
            "comparison_sha256_normalized":
                tv.sha256_file_identity(cmp_mod.__file__)["lf_normalized"],
            "runner_sha256": tv.sha256_file(runner_path),
            "runner_sha256_normalized":
                tv.sha256_file_identity(runner_path)["lf_normalized"]},
    }
    if extra_cfg:
        cfg.update(extra_cfg)
    freeze = {
        "batch": "lgbm-equal-info-v2-synthetic",
        "batch_id": "lgbm-equal-info-v2-synthetic",
        "config_sha256": tv.freeze_config_sha256(cfg),
        "config_hash_definition": tv.CONFIG_HASH_DEFINITION,
        "config": cfg,
    }
    path = tmp_path / "freeze_v2_synthetic.json"
    path.write_text(json.dumps(freeze, indent=2), encoding="utf-8")
    return path, files


def _synthetic_fold_dicts(tmp_path):
    """The runner's own fold construction over the synthetic parquets."""
    import polars as pl

    feat_path, pa_path, _ = _write_synthetic_parquets(tmp_path)
    df = cmp_mod.load_pa_rows(pa_path, feat_path)
    return runner.build_real_folds(df, runner.FEATURES_BOTH_EW)


# ---------------------------------------------------------------------------
# Refusal gate
# ---------------------------------------------------------------------------

def test_refusal_gate_exit_2(tmp_path):
    feat_path, pa_path, sm_path = _write_synthetic_parquets(tmp_path)
    freeze_path, _ = _make_synthetic_freeze(
        tmp_path,
        input_paths={"pa_table": pa_path, "features_v3": feat_path,
                     "start_metrics_outcome_source": sm_path},
        extra_cfg={"output_destination": str(tmp_path / "out"),
                   "equal_information_contract": {
                       "features": list(cmp_mod.FEAT_H3)},
                   "tracking": {
                       "tracking_uri":
                           "sqlite:///" + (tmp_path / "mlflow.db").as_posix(),
                       "experiment": "v2-synthetic-refusal"}})
    assert runner.main(["--freeze", str(freeze_path)]) == 2
    assert not (tmp_path / "out").exists()  # nothing was read or written


# ---------------------------------------------------------------------------
# End-to-end: every output write, eval history, refit-at-chosen-iteration,
# both arms' predictions, MLflow round-trip (in-process wrapper verify)
# ---------------------------------------------------------------------------

def test_v2_end_to_end_synthetic_full_persistence(tmp_path):
    import lightgbm as lgb
    import polars as pl

    feat_path, pa_path, sm_path = _write_synthetic_parquets(tmp_path)
    freeze_path, _ = _make_synthetic_freeze(
        tmp_path,
        input_paths={"pa_table": pa_path, "features_v3": feat_path,
                     "start_metrics_outcome_source": sm_path},
        extra_cfg={
            "output_destination": str(tmp_path / "out"),
            "final_fit_declaration": runner.FINAL_FIT_DECLARATION_V2,
            "equal_information_contract": {
                "features": list(cmp_mod.FEAT_H3)},
            "tracking": {
                "tracking_uri":
                    "sqlite:///" + (tmp_path / "mlflow.db").as_posix(),
                "experiment": "lgbm-equal-info-v2-synthetic"},
        })

    rc = runner.main(["--freeze", str(freeze_path),
                      "--i-accept-real-data-execution"])
    assert rc == 0
    out_dirs = list((tmp_path / "out").iterdir())
    assert len(out_dirs) == 1
    out_dir = out_dirs[0]

    # tracking: the SHARED wrapper verified the MLflow round-trip in-process
    status = json.loads((out_dir / "tracking_status.json").read_text())
    assert status["status"] == "VERIFIED"

    manifest = json.loads((out_dir / "run_manifest.json").read_text())
    assert manifest["folds_executed"] == cmp_mod.DEV_BLOCKS
    assert manifest["confirm_block_status"] == "EXCLUDED - NOT SCORED " \
        "(dev blocks only)"
    # the execution record states the identity convention (LF-normalized
    # text sources, byte-exact binaries)
    assert "TEXT-SOURCE IDENTITY CONVENTION" in \
        manifest["identity_convention"]["text_source_identity_convention"]
    assert "byte-exact" in manifest["identity_convention"]["eol_note"]

    metrics = json.loads((out_dir / "metrics.json").read_text())
    assert set(metrics["per_fold"]) == set(cmp_mod.DEV_BLOCKS)
    assert metrics["pooled"]["n"] == sum(
        metrics["per_fold"][f]["n_eval"] for f in cmp_mod.DEV_BLOCKS)

    # --- per-fold output writes for BOTH arms -----------------------------
    for fold in cmp_mod.DEV_BLOCKS:
        for cand in (runner.LGBM_CANDIDATE, runner.REFERENCE_CANDIDATE):
            preds_path = out_dir / f"preds_{fold}__{cand}.parquet"
            assert preds_path.is_file()
            preds = pl.read_parquet(preds_path)
            for col in (*cmp_mod.IDENTITY_COLS, "game_date", "y",
                        "pred_raw", "pred_cal"):
                assert col in preds.columns, (fold, cand, col)
            assert preds["pred_raw"].is_between(0.0, 1.0).all()
            assert preds["pred_cal"].is_between(0.0, 1.0).all()
            assert preds.height == metrics["per_fold"][fold]["n_eval"]
            # keyed RAW + CAL predictions/labels saved for both arms
            assert preds["y"].n_unique() >= 1
        # per-arm fit-row ID parquets exist and MATCH (regression below
        # re-asserts the row identity explicitly)
        assert (out_dir / f"fit_rows_{fold}__{runner.LGBM_CANDIDATE}"
                ".parquet").is_file()
        assert (out_dir / f"fit_rows_{fold}__{runner.REFERENCE_CANDIDATE}"
                ".parquet").is_file()
        # inner validation history + selected iteration persisted
        hist_path = out_dir / f"inner_eval_history_{fold}.json"
        assert hist_path.is_file()
        hist = json.loads(hist_path.read_text())
        ev = hist["eval_history"]["inner_block"]
        assert set(ev) == {"binary_logloss", "binary_error"}
        n_rounds = len(ev["binary_logloss"])
        assert n_rounds == len(ev["binary_error"]) >= 1
        sel = hist["selected_iteration"]
        assert 1 <= sel <= 400 and sel <= n_rounds
        assert hist["first_metric_only"] is True
        # with first_metric_only=True the selected iteration minimizes the
        # FIRST metric up to the stop (when early stopping actually fired)
        if n_rounds < hist["num_boost_round_cap"]:
            ll = ev["binary_logloss"]
            assert ll[sel - 1] == min(ll[:sel])
        # saved models: refit booster reloads with exactly the chosen trees;
        # the logistic reference fit is persisted
        booster = lgb.Booster(model_file=str(
            out_dir / "boosters" / f"{fold}__{runner.LGBM_CANDIDATE}.txt"))
        assert booster.num_trees() == sel
        assert (out_dir / "reference_models"
                / f"{fold}__{runner.REFERENCE_CANDIDATE}.joblib").is_file()

    # bootstrap draws persisted with the registered shape
    draws = pl.read_parquet(
        out_dir / "bootstrap"
        / f"contrast_draws__{runner.CONTRAST_ID}.parquet")
    assert draws.height == 2000
    assert set(draws.columns) == {
        "draw_index", f"rep_brier_raw__{runner.LGBM_CANDIDATE}",
        f"rep_brier_raw__{runner.REFERENCE_CANDIDATE}",
        "delta_rep_brier_raw"}
    contrast = metrics["contrast"]
    assert contrast["id"] == runner.CONTRAST_ID
    assert contrast["n_boot"] == 2000 and contrast["seed"] == 20261001
    assert "p_holm" in contrast
    assert metrics["hypothesis_test"]["n_resamples"] == 2000

    # sha inventory matches the on-disk bytes (byte-exact; text outputs
    # also carry the LF-normalized value)
    for entry in metrics["persistence"]:
        p = out_dir / entry["relpath"]
        assert p.is_file(), entry["relpath"]
        assert tv.sha256_file(p) == entry["sha256"], entry["relpath"]
        if entry["identity_class"] == "text":
            assert tv.sha256_file_identity(p)["lf_normalized"] == \
                entry["lf_normalized_sha256"], entry["relpath"]
    assert len(metrics["persistence"]) == 3 * 7 + 1  # 3 folds x 7 + draws


# ---------------------------------------------------------------------------
# Regression (the v1 defect): logistic fit rows == LightGBM refit rows
# ---------------------------------------------------------------------------

def test_matched_exposure_logistic_rows_equal_lgbm_refit_rows(tmp_path):
    import polars as pl

    fold_dicts = _synthetic_fold_dicts(tmp_path)
    out = tmp_path / "out"
    result = runner.compare_on_dev_folds(fold_dicts, out)

    for fold, rec in result["per_fold"].items():
        # recorded counts: LightGBM refit consumed the FULL base_train, the
        # same rows the logistic reference consumed
        assert rec["lgbm"]["n_fit_rows_refit"] == rec["n_base_train"]
        assert rec["reference"]["n_fit_rows"] == rec["n_base_train"]
        assert rec["fit_rows_matched"] is True
        assert result["matched_exposure"]["per_fold_fit_rows"][fold][
            "equal"] is True
        # persisted per-arm fit-row IDs are row-identical
        a = pl.read_parquet(
            out / f"fit_rows_{fold}__{runner.LGBM_CANDIDATE}.parquet")
        b = pl.read_parquet(
            out / f"fit_rows_{fold}__{runner.REFERENCE_CANDIDATE}.parquet")
        assert a.height == b.height == rec["n_base_train"]
        assert cmp_mod.eval_identity_hash(a) == \
            cmp_mod.eval_identity_hash(b) == \
            rec["fit_rows_identity_sha256"]


# ---------------------------------------------------------------------------
# Eval history recorded per round + refit at the chosen fixed iteration
# ---------------------------------------------------------------------------

def test_eval_history_recorded_and_refit_at_chosen_iteration(tmp_path):
    fd = _synthetic_fold_dicts(tmp_path)[0]
    X = np.asarray(fd["X_train"], dtype=np.float64)
    y = np.asarray(fd["y_train"], dtype=np.int64)
    d = np.asarray(fd["dates_train"], dtype=object)

    selected, history, info, sel_booster = runner.select_iteration(X, y, d)
    ev = history["inner_block"]
    assert set(ev) == {"binary_logloss", "binary_error"}
    n_rounds = len(ev["binary_logloss"])
    assert n_rounds == len(ev["binary_error"]) >= 1
    assert 1 <= selected <= 400 and selected <= n_rounds
    assert info["n_inner_rows"] + info["n_selection_fit_rows"] == X.shape[0]
    assert info["first_metric_only"] is True

    # refit at the chosen fixed iteration: exactly that many trees
    refit = runner.refit_full_at_iteration(X, y, selected)
    assert refit.num_trees() == selected
    p_refit = runner.predict_raw_refit(refit, fd["X_eval"])
    assert p_refit.shape == (fd["X_eval"].shape[0],)
    assert np.all(np.isfinite(p_refit)) and p_refit.min() >= 0.0 \
        and p_refit.max() <= 1.0

    # FRESH refit proof: predictions differ from the selection-stage booster
    # at its best iteration (the refit consumed the FULL base_train, the
    # selection booster only base_train minus the inner block)
    p_sel = sel_booster.predict(fd["X_eval"],
                                num_iteration=selected)
    assert not np.allclose(p_refit, p_sel)

    # refit iteration bounds are enforced
    with pytest.raises(ValueError):
        runner.refit_full_at_iteration(X, y, 0)
    with pytest.raises(ValueError):
        runner.refit_full_at_iteration(X, y, 401)


# ---------------------------------------------------------------------------
# Fresh-process MLflow round-trip through the SHARED wrapper (executed path)
# ---------------------------------------------------------------------------

def run_and_log(work_dir: str) -> None:
    """LOG side (own process): the full v2 frozen command on synthetic
    parquets, logged through the SHARED wrapper into a TEMP sqlite store."""
    import json
    import tempfile
    from pathlib import Path as P

    work = P(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    tmp = P(tempfile.mkdtemp(prefix="v2log_", dir=str(work)))
    feat_path, pa_path, sm_path = _write_synthetic_parquets(tmp)
    freeze_path, _ = _make_synthetic_freeze(
        tmp,
        input_paths={"pa_table": pa_path, "features_v3": feat_path,
                     "start_metrics_outcome_source": sm_path},
        extra_cfg={
            "output_destination": str(tmp / "out"),
            "final_fit_declaration": runner.FINAL_FIT_DECLARATION_V2,
            "equal_information_contract": {
                "features": list(cmp_mod.FEAT_H3)},
            "tracking": {
                "tracking_uri":
                    "sqlite:///" + (tmp / "mlflow.db").as_posix(),
                "experiment": "lgbm-equal-info-v2-synthetic-fresh"},
        })
    rc = runner.main(["--freeze", str(freeze_path),
                      "--i-accept-real-data-execution"])
    assert rc == 0
    out_dir = next(iter((tmp / "out").iterdir()))
    status = json.loads((out_dir / "tracking_status.json").read_text())
    assert status["status"] == "VERIFIED", status
    metrics = json.loads((out_dir / "metrics.json").read_text())
    preds_rel = f"preds_{cmp_mod.DEV_BLOCKS[0]}__{runner.LGBM_CANDIDATE}" \
        ".parquet"
    (work / HANDOFF).write_text(json.dumps({
        "tracking_uri": "sqlite:///" + (tmp / "mlflow.db").as_posix(),
        "run_id": status["run_id"],
        # the wrapper's fixed canonical config-artifact relpath
        # (track_and_verify.save_canonical_outputs)
        "artifact": "config/lgbm_equal_info_config.json",
        "source_sha256": status["config_artifact_sha256"],
        "expected_metrics": runner._v2_metrics(metrics),
        "metrics_artifact": "metrics/metrics.json",
        "metrics_disk_sha256": tv.sha256_file(out_dir / "metrics.json"),
        "preds_artifact": "predictions/" + preds_rel,
        "preds_disk_sha256": tv.sha256_file(out_dir / preds_rel),
        "logged_by_process_pid": os.getpid(),
    }, indent=2))


def retrieve_and_verify(work_dir: str) -> None:
    """VERIFY side (FRESH process): retrieve the run by id through the SHARED
    wrapper's verifier (metrics exact round-trip + config artifact byte
    hash) and additionally hash-verify the metrics + preds artifacts through
    the artifact API."""
    import json
    from pathlib import Path as P

    from mlflow.tracking import MlflowClient

    import track_and_verify as tv2

    work = P(work_dir)
    hand = json.loads((work / HANDOFF).read_text())
    res = tv2.verify_run(hand["tracking_uri"], hand["run_id"],
                         hand["expected_metrics"], hand["artifact"],
                         hand["source_sha256"], work / "retrieved_fresh")
    client = MlflowClient(tracking_uri=hand["tracking_uri"])
    got_metrics = client.download_artifacts(
        hand["run_id"], hand["metrics_artifact"], str(work / "retr_metrics"))
    got_preds = client.download_artifacts(
        hand["run_id"], hand["preds_artifact"], str(work / "retr_preds"))
    (work / "verify_result.json").write_text(json.dumps({
        "status": res["status"],
        "separate_processes": os.getpid() != hand["logged_by_process_pid"],
        "metrics_ok": res["metrics_ok"],
        "artifact_ok": res["artifact_ok"],
        "source_sha256": res["source_sha256"],
        "retrieved_sha256": res["retrieved_sha256"],
        "metrics_artifact_ok":
            tv2.sha256_file(P(got_metrics)) == hand["metrics_disk_sha256"],
        "preds_artifact_ok":
            tv2.sha256_file(P(got_preds)) == hand["preds_disk_sha256"],
    }, indent=2))


def _run_mode(mode: str, work_dir: str) -> None:
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), mode, work_dir],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(
            f"{mode} subprocess failed ({proc.returncode}):\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")


def test_mlflow_fresh_process_roundtrip(tmp_path):
    work = str(tmp_path)
    _run_mode(LOG_MODE, work)
    _run_mode(VERIFY_MODE, work)
    res = json.loads((tmp_path / "verify_result.json").read_text())
    assert res["status"] == "VERIFIED", res
    assert res["separate_processes"] is True  # fresh retrieval process
    assert res["metrics_ok"] is True
    assert res["artifact_ok"] is True
    assert res["metrics_artifact_ok"] is True
    assert res["preds_artifact_ok"] is True
    assert res["source_sha256"] == res["retrieved_sha256"]


# ---------------------------------------------------------------------------
# Real freeze registration integrity (on-disk identities, synthetic-freeze
# conventions; destination confirmed absent at registration time)
# ---------------------------------------------------------------------------

def test_v2_freeze_registration_integrity():
    import json as _json

    freeze_path = os.path.join(HERE, "freeze_lgbm_equal_info_v2.json")
    if not os.path.exists(freeze_path):
        pytest.skip("freeze_lgbm_equal_info_v2.json not yet generated")
    freeze = _json.loads(open(freeze_path, encoding="utf-8").read())
    cfg = freeze["config"]
    assert freeze["batch_id"] == "lgbm-equal-info-v2"
    assert tv.freeze_config_sha256(cfg) == freeze["config_sha256"]
    assert cfg["text_source_identity_convention"] == \
        tv.TEXT_SOURCE_IDENTITY_CONVENTION
    # original hyperparameters: byte-identical to the v1 adapter's frozen
    # config (lake lgbm_equal_info_adapter.LGBM_EQUAL_INFO_CONFIG)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "lgbm_equal_info_adapter_v1_check",
        r"C:\Users\ckaplinger\MLB-Props-Research\count-eval-v1"
        r"\lgbm_equal_info_adapter.py")
    v1ad = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v1ad)
    assert cfg["lgbm_hyperparameters"] == v1ad.LGBM_EQUAL_INFO_CONFIG
    assert runner.config_sha256() == v1ad.config_sha256()
    # first_metric_only predeclared diagnostic declared in the freeze
    assert "PREDECLARED DIAGNOSTIC" in cfg["first_metric_only_diagnostic"]
    # final-fit declaration: fresh refit on FULL base_train, no early stop
    decl = cfg["final_fit_declaration"].lower()
    assert "refit on the full base_train" in decl
    assert "no early stopping in the refit" in decl
    # literal command + gate flag
    assert "run_lgbm_equal_info_v2.py" in cfg["execution"]["command"]
    assert "--i-accept-real-data-execution" in cfg["execution"]["command"]
    # destination confirmed nonexistent at registration; write-once: if it
    # exists now (post-execution), every child is a valid run dir
    reg = cfg["output_destination_confirmed_nonexistent"]
    assert reg["confirmed"] is True and "2026-10-16" in reg["date"]
    dest = Path(cfg["output_destination"])
    if dest.exists():
        for child in dest.iterdir():
            assert (child / "metrics.json").is_file()
            assert (child / "run_manifest.json").is_file()
    # full on-disk identity verification (real files, this machine)
    out = tv.verify_registered_identities(
        freeze_path, adapter_module=runner,
        runner_path=os.path.join(HERE, "run_lgbm_equal_info_v2.py"))
    assert out["ok"] is True
    for key in ("adapter.file_sha256_normalized",
                "wrapper.file_sha256_normalized",
                "harness.comparison.comparison_sha256_normalized",
                "runner.runner_sha256_normalized"):
        assert key in out["checked"]


if __name__ == "__main__":
    mode, work_dir = sys.argv[1], sys.argv[2]
    if mode == LOG_MODE:
        run_and_log(work_dir)
    elif mode == VERIFY_MODE:
        retrieve_and_verify(work_dir)
    else:
        raise SystemExit(f"unknown mode: {mode}")
