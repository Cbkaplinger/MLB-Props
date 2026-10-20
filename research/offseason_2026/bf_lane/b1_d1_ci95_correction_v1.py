"""D1 CORRECTION - ci95_rmse_scale lower bound (versioned, additive).

CORRECTION_ID: b1-d1-ci95-rmse-scale-v1 (2026-10-16)

Defect D1 (recorded by the Chat 2 reconciliation, B1_RECONCILIATION_CHAT2.md):
the DESCRIPTIVE-ONLY field
``metrics.json -> bootstrap.paired_deltas_b1_minus_b0.sq_err.ci95_rmse_scale[0]``
was miscomputed by ``run_b1_ridge_v1.py`` (lines ~680-684). The lower bound was
built as ``p2.5(sqrt b1) - p2.5(sqrt b0)`` instead of the correct difference-of-
replicates percentile endpoint ``p2.5(sqrt b1) - p97.5(sqrt b0)``. The stored
upper bound already equals the correct upper endpoint.

Stored (WRONG lower):  [-0.7098076573910497, -0.4527807057818549]
Correct interval:      [-0.9848014609216529, -0.4527807057818549]

UNAFFECTED (stated explicitly): the registered primary endpoint (paired
count-RPS B1-B0), the paired contrast C_b1_ridge_vs_b0_empirical, the
bootstrap p-value / Holm p (0.0004997501249375312), the percentile CI on the
paired count-RPS delta, and the gate verdict are NOT touched by this defect.
The field is labelled "descriptive" in metrics.json and was never consumed by
any decision or registered CI.

Versioning policy: ``run_b1_ridge_v1.py`` is the executed runner and is
committed at its executed byte identity (sha256
ead15e2b42144c58f9418df8beff048320e77493af94352815da2a4a7bff30ae, recorded in
B1_RECONCILIATION_CHAT2.md section 1). It is NOT edited. This module is the
versioned correction; ``test_b1_d1_ci95_correction.py`` is the regression
test. metrics.json is never rewritten (write-once run dir).

ASCII-only per research-script convention (cp1252 consoles).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np

CORRECTION_ID = "b1-d1-ci95-rmse-scale-v1"
CORRECTION_UTC = "2026-10-16"

DEFAULT_RUN_DIR = Path(
    r"C:\Users\ckaplinger\MLB-Props-Research\bf-lane-v1\b1_run_v1"
)

# Persisted values recorded in metrics.json (never rewritten).
STORED_CI95_RMSE_SCALE = [-0.7098076573910497, -0.4527807057818549]
CORRECT_LOWER = -0.9848014609216529
CORRECT_UPPER = -0.4527807057818549

# Registered primary endpoint values (must remain EXACTLY these).
PRIMARY_ENDPOINT = {
    "contrast": "C_b1_ridge_vs_b0_empirical",
    "metric": "count_rps (paired, B1 - B0)",
    "delta": -0.028178565433309988,
    "p_value": 0.0004997501249375312,
    "p_holm": 0.0004997501249375312,
    "n_boot": 2000,
    "seed": 20261001,
}

RUNNER_SHA256_EXECUTED = (
    "ead15e2b42144c58f9418df8beff048320e77493af94352815da2a4a7bff30ae"
)

CORRECTION_NOTE = {
    "correction_id": CORRECTION_ID,
    "written_utc": CORRECTION_UTC,
    "kind": "versioned correction (additive); executed runner NOT edited",
    "defect": "D1: descriptive-only ci95_rmse_scale lower bound in "
              "metrics.json used p2.5(sqrt b1) - p2.5(sqrt b0); a correct "
              "difference-of-replicates percentile interval is "
              "[p2.5(sqrt b1) - p97.5(sqrt b0), "
              "p97.5(sqrt b1) - p2.5(sqrt b0)]",
    "stored_value_wrong_lower": STORED_CI95_RMSE_SCALE,
    "corrected_value": [CORRECT_LOWER, CORRECT_UPPER],
    "upper_bound_was_already_correct": True,
    "field_scope": "descriptive only; not the registered contrast, not any "
                   "consumed CI, not part of any decision",
    "primary_endpoint_unaffected": True,
    "unaffected_fields": [
        "paired count-RPS primary endpoint (C_b1_ridge_vs_b0_empirical)",
        "paired contrast delta -0.028178565433309988",
        "bootstrap p-value 0.0004997501249375312 (Holm p identical)",
        "percentile CI on the paired count-RPS delta",
        "gate verdict ACCEPT WITH LIMITATION",
    ],
    "runner_byte_identity_preserved": RUNNER_SHA256_EXECUTED,
    "metrics_json_never_rewritten": True,
}


def ci95_rmse_scale_corrected(
    sq_b1_replicates: np.ndarray, sq_b0_replicates: np.ndarray
) -> list[float]:
    """Correct difference-of-replicates percentile interval on the RMSE scale.

    sq_* arrays are bootstrap MSE-scale replicate draws (one dimension each
    for B1 and B0, paired by slate-date resample).
    """
    b1 = np.sqrt(np.asarray(sq_b1_replicates, dtype=float))
    b0 = np.sqrt(np.asarray(sq_b0_replicates, dtype=float))
    lower = float(np.percentile(b1, 2.5)) - float(np.percentile(b0, 97.5))
    upper = float(np.percentile(b1, 97.5)) - float(np.percentile(b0, 2.5))
    return [lower, upper]


def ci95_rmse_scale_buggy_v1(
    sq_b1_replicates: np.ndarray, sq_b0_replicates: np.ndarray
) -> list[float]:
    """Reproduces the executed runner's formula (D1) for regression evidence.

    lower = p2.5(sqrt b1) - p2.5(sqrt b0)   <-- the stored wrong value
    upper = p97.5(sqrt b1) - p2.5(sqrt b0)  <-- already correct
    Kept ONLY to demonstrate the defect deterministically; never use.
    """
    b1 = np.sqrt(np.asarray(sq_b1_replicates, dtype=float))
    b0 = np.sqrt(np.asarray(sq_b0_replicates, dtype=float))
    lower = float(np.percentile(b1, 2.5)) - float(np.percentile(b0, 2.5))
    upper = float(np.percentile(b1, 97.5)) - float(np.percentile(b0, 2.5))
    return [lower, upper]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_against_run(run_dir: Path | None = None) -> dict:
    """Deterministic check against the persisted B1 run artifacts.

    Read-only. Recomputes the corrected interval from the persisted bootstrap
    replicate matrix (2000 x 10) and compares with the stored metrics.json
    values and the registered primary endpoint.
    """
    rd = Path(run_dir or os.environ.get("B1_RUN_DIR", DEFAULT_RUN_DIR))
    npy = rd / "b1_bootstrap_replicates.npy"
    metrics = rd / "metrics.json"
    if not npy.is_file() or not metrics.is_file():
        raise FileNotFoundError(f"missing artifacts under {rd}")
    with open(metrics, "rb") as fh:
        mj = json.loads(fh.read().decode("utf-8"))

    res = np.load(npy)
    cols = ["b0_rps", "b1_rps", "b0_logscore", "b1_logscore", "b0_abs_err",
            "b1_abs_err", "b0_sq_err", "b1_sq_err", "b0_signed_err",
            "b1_signed_err"]
    i0, i1 = cols.index("b0_sq_err"), cols.index("b1_sq_err")

    corrected = ci95_rmse_scale_corrected(res[:, i1], res[:, i0])
    buggy = ci95_rmse_scale_buggy_v1(res[:, i1], res[:, i0])
    stored = mj["bootstrap"]["paired_deltas_b1_minus_b0"]["sq_err"][
        "ci95_rmse_scale"]
    contrast = mj["contrast"]["contrasts"]["C_b1_ridge_vs_b0_empirical"]

    out = {
        "correction_id": CORRECTION_ID,
        "run_dir": str(rd),
        "metrics_json_sha256": sha256_file(metrics),
        "stored_ci95_rmse_scale": stored,
        "buggy_formula_reproduces_stored": buggy == stored,
        "corrected_ci95_rmse_scale": corrected,
        "corrected_matches_expected": (
            corrected[0] == CORRECT_LOWER and corrected[1] == CORRECT_UPPER
        ),
        "stored_lower_is_wrong": stored[0] != corrected[0],
        "stored_upper_equals_correct_upper": stored[1] == corrected[1],
        "primary_endpoint_unaffected": (
            contrast["delta"] == PRIMARY_ENDPOINT["delta"]
            and contrast["p_value"] == PRIMARY_ENDPOINT["p_value"]
            and contrast["p_holm"] == PRIMARY_ENDPOINT["p_holm"]
        ),
    }
    ok = (
        out["buggy_formula_reproduces_stored"]
        and out["corrected_matches_expected"]
        and out["stored_lower_is_wrong"]
        and out["stored_upper_equals_correct_upper"]
        and out["primary_endpoint_unaffected"]
    )
    out["verdict"] = "PASS" if ok else "FAIL"
    return out


if __name__ == "__main__":
    report = check_against_run()
    print(json.dumps(report, indent=2))
    if report["verdict"] != "PASS":
        raise SystemExit(1)
