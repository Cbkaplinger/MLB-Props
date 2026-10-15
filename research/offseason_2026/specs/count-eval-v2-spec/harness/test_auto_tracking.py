# test_auto_tracking.py -- AUTOMATIC MLFLOW TRACKING TEST for the LightGBM
# equal-info harness path (count-eval-v1). SYNTHETIC ONLY: temp tracking
# store + temp artifacts; the canonical mlflow.db is never touched.
#
# What this proves: the REAL runner's logging path (the same
# lgbm_equal_info_adapter config/params/metric/artifact logging calls the
# harness wrapper makes) works END-TO-END automatically -- a synthetic run
# logs itself through MLflow in one process, and a FRESH second process
# retrieves the run by id and verifies a metric (exact round-trip) and an
# artifact hash (byte-identical) through the artifact API.
#
# Run: .venv python -m pytest test_auto_tracking.py -q
# ASCII-only (cp1252 consoles).
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, (r"C:\Users\ckaplinger\Downloads\Personal-Projects"
                    r"\MLB-Props-worktrees\market-eval-v2\research"
                    r"\offseason_2026\specs\count-eval-v2-spec\harness"))

LOG_MODE = "log"
VERIFY_MODE = "verify"
HANDOFF = "auto_tracking_handoff.json"


# ---------------------------------------------------------------------------
# Mode implementations (each runs in its OWN process)
# ---------------------------------------------------------------------------

def run_and_log(work_dir: str) -> None:
    """LOG side: synthetic comparison through the adapter, logged through
    MLflow automatically (the same logging calls the real runner wrapper
    makes). Writes the handoff record for the fresh-process verifier."""
    import hashlib
    from pathlib import Path

    import mlflow
    import numpy as np

    import lgbm_equal_info_adapter as ad
    from test_lgbm_equal_info_adapter import make_synthetic, split_fold

    work = Path(work_dir)
    tracking_uri = "sqlite:///" + (work / "mlflow.db").as_posix()
    artifact_root = (work / "artifacts").as_uri()
    out_dir = work / "run_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    folds = [split_fold(f) for f in make_synthetic()]
    result = ad.compare_on_synthetic_folds(folds)

    # persist the frozen config artifact the real runner would upload
    cfg_path = out_dir / "lgbm_equal_info_config.json"
    cfg_path.write_text(json.dumps(result["config"], indent=2))
    src_sha = hashlib.sha256(cfg_path.read_bytes()).hexdigest()

    mlflow.set_tracking_uri(tracking_uri)
    client = mlflow.MlflowClient(tracking_uri=tracking_uri)
    exp_id = client.create_experiment("lgbm-equal-info-auto-tracking",
                                      artifact_location=artifact_root)
    with mlflow.start_run(experiment_id=exp_id,
                          run_name="lgbm-equal-info-auto-synthetic") as run:
        for k, v in ad.LGBM_EQUAL_INFO_CONFIG.items():
            mlflow.log_param(k, v)
        mlflow.log_params({
            "candidate": ad.LGBM_CANDIDATE,
            "reference": ad.REFERENCE_CANDIDATE,
            "features": ",".join(ad.FEATURES_BOTH_EW),
            "data": "synthetic-only",
        })
        for k, v in result["pooled"]["brier_raw"].items():
            mlflow.log_metric("pooled_brier_raw__" + k, v)
        for k, v in result["pooled"]["log_loss_raw"].items():
            mlflow.log_metric("pooled_log_loss_raw__" + k, v)
        mlflow.log_metric("contrast_delta_brier_raw",
                          result["contrast"]["delta"])
        mlflow.log_artifact(str(cfg_path), artifact_path="config")
        run_id = run.info.run_id

    (work / HANDOFF).write_text(json.dumps({
        "tracking_uri": tracking_uri,
        "experiment_id": exp_id,
        "run_id": run_id,
        "artifact": "config/lgbm_equal_info_config.json",
        "source_sha256": src_sha,
        "expected_metrics": {
            "contrast_delta_brier_raw": result["contrast"]["delta"],
            "pooled_brier_raw__P2_lgbm_equal_info":
                result["pooled"]["brier_raw"][ad.LGBM_CANDIDATE],
            "pooled_brier_raw__P1_H3_incumbent_refit":
                result["pooled"]["brier_raw"][ad.REFERENCE_CANDIDATE],
        },
        "logged_by_process_pid": os.getpid(),
    }, indent=2))


def retrieve_and_verify(work_dir: str) -> None:
    """VERIFY side: FRESH process, no shared in-memory state. Connects to
    the temp tracking store, retrieves the run by id, and checks one metric
    (exact round-trip) plus one artifact hash (byte-identical) via the
    artifact API."""
    import hashlib
    from pathlib import Path

    from mlflow.tracking import MlflowClient

    work = Path(work_dir)
    hand = json.loads((work / HANDOFF).read_text())
    client = MlflowClient(tracking_uri=hand["tracking_uri"])
    run = client.get_run(hand["run_id"])

    metric_results = {}
    for key, expected in hand["expected_metrics"].items():
        got = run.data.metrics[key]
        metric_results[key] = {
            "expected": expected, "retrieved": got,
            "exact_match": got == expected,
        }
    metrics_ok = all(m["exact_match"] for m in metric_results.values())

    got_path = client.download_artifacts(
        hand["run_id"], hand["artifact"], str(work / "retrieved"))
    got_sha = hashlib.sha256(Path(got_path).read_bytes()).hexdigest()
    artifact_ok = got_sha == hand["source_sha256"]

    status = "VERIFIED" if (metrics_ok and artifact_ok) else "MISMATCH"
    (work / "verify_result.json").write_text(json.dumps({
        "status": status,
        "verifier_process_pid": os.getpid(),
        "logged_by_process_pid": hand["logged_by_process_pid"],
        "separate_processes":
            os.getpid() != hand["logged_by_process_pid"],
        "metrics": metric_results, "metrics_ok": metrics_ok,
        "artifact": hand["artifact"],
        "source_sha256": hand["source_sha256"],
        "retrieved_sha256": got_sha, "artifact_ok": artifact_ok,
    }, indent=2))


# ---------------------------------------------------------------------------
# pytest driver
# ---------------------------------------------------------------------------

def _run_mode(mode: str, work_dir: str) -> None:
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), mode, work_dir],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(
            f"{mode} subprocess failed ({proc.returncode}):\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")


def test_auto_tracking_end_to_end_fresh_process(tmp_path):
    work = str(tmp_path)
    _run_mode(LOG_MODE, work)
    _run_mode(VERIFY_MODE, work)
    res = json.loads((tmp_path / "verify_result.json").read_text())
    assert res["status"] == "VERIFIED", res
    assert res["separate_processes"] is True  # fresh retrieval process
    assert res["metrics_ok"] is True
    assert res["artifact_ok"] is True
    assert res["source_sha256"] == res["retrieved_sha256"]


if __name__ == "__main__":
    mode, work_dir = sys.argv[1], sys.argv[2]
    if mode == LOG_MODE:
        run_and_log(work_dir)
    elif mode == VERIFY_MODE:
        retrieve_and_verify(work_dir)
    else:
        raise SystemExit(f"unknown mode: {mode}")
