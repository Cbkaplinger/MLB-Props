"""bf-lane-v1 B1 run: LOG-PHASE-ONLY recovery (no refit, no rescore).

Context (2026-10-16): run_b1_ridge_v1.py executed compare EXACTLY ONCE and
finalize SAVE succeeded; the MLflow LOG phase failed on a caller bug in
describe() (relative artifact path passed to log_artifact instead of the
wrapper's absolute saved["config_artifact_path"]). Per the D-1 failure
contract of the shared track_and_verify.py chain: canonical outputs are
preserved untouched, tracking_status.json recorded "tracking_failed", and
"logging recovery is SEPARATE from fitting: compare runs exactly once and
an upload failure NEVER triggers a refit".

This script performs ONLY the log + verify phases against the untouched
canonical outputs in b1_run_v1:
  1. load metrics.json (canonical, byte-untouched; sha recorded before +
     after to prove no rewrite);
  2. rebuild params/metrics/artifacts via the runner's describe();
  3. log_run(...) then verify_run(...) via the shared wrapper functions
     (fresh-process MLflow client, exact metric round-trip + artifact
     byte-hash check);
  4. write tracking_status.json with the wrapper's success record on
     VERIFIED.

No fitting, no scoring, no rewrite of any canonical output.
ASCII-only (cp1252 consoles).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

HARNESS = Path(
    r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees"
    r"\market-eval-v2\research\offseason_2026\specs\count-eval-v2-spec\harness"
)
BF_LANE = Path(r"C:\Users\ckaplinger\MLB-Props-Research\bf-lane-v1")
OUT_DIR = BF_LANE / "b1_run_v1"
RUNNER_DIR = Path(
    r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees"
    r"\market-eval-v2\research\offseason_2026\bf_lane"
)
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(RUNNER_DIR))

from track_and_verify import log_run, verify_run, _write_status  # noqa: E402
from run_b1_ridge_v1 import describe, LAKE  # noqa: E402

TRACKING_URI = "sqlite:///" + str(LAKE / "mlflow.db")
EXPERIMENT = "bf-lane-v1"
RUN_NAME = "b1_ridge_v1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    metrics_path = OUT_DIR / "metrics.json"
    cfg_path = OUT_DIR / "lgbm_equal_info_config.json"
    for p in (metrics_path, cfg_path):
        if not p.exists():
            raise SystemExit("canonical output missing: %s" % p)
    sha_before = sha256_file(metrics_path)
    result = json.loads(metrics_path.read_text(encoding="ascii"))
    saved = {
        "metrics_path": str(metrics_path),
        "metrics_sha256": sha_before,
        "config_artifact_relpath": "config/lgbm_equal_info_config.json",
        "config_artifact_path": str(cfg_path),
        "config_artifact_sha256": sha256_file(cfg_path),
    }
    params, metrics, artifacts = describe(result, OUT_DIR, saved)
    run_id = log_run(TRACKING_URI, EXPERIMENT, RUN_NAME, params, metrics,
                     artifacts)
    verdict = verify_run(TRACKING_URI, run_id, metrics,
                         saved["config_artifact_relpath"],
                         saved["config_artifact_sha256"],
                         OUT_DIR / "retrieved")
    if verdict["status"] != "VERIFIED":
        _write_status(OUT_DIR, "tracking_failed", run_id=run_id,
                      phase="verify", detail=verdict,
                      note="retrieved run mismatched logged content")
        raise SystemExit("verification MISMATCH; batch NOT successful")
    sha_after = sha256_file(metrics_path)
    if sha_after != sha_before:
        raise SystemExit("canonical metrics.json changed during recovery")
    _write_status(OUT_DIR, verdict["status"], run_id=run_id, phase="verify",
                  tracking_uri=TRACKING_URI,
                  metrics_sha256=saved["metrics_sha256"],
                  config_artifact_sha256=saved["config_artifact_sha256"],
                  recovery_note="log-phase-only recovery 2026-10-16 after "
                  "describe() artifact-path caller bug; compare executed "
                  "EXACTLY ONCE (no refit, no rescore); canonical outputs "
                  "byte-untouched (metrics.json sha equal before/after)")
    print("VERIFIED run_id", run_id)
    print("metrics.json sha256 (unchanged):", sha_before)
    return 0


if __name__ == "__main__":
    sys.exit(main())
