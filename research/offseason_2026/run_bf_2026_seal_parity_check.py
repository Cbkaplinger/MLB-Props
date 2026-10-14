"""2026 execution-path parity check: canonical v3 on a staged seal-dir.

Demonstrates, on SYNTHETIC data (no 2026 outcomes touched):
  1. the v3-native seal-dir format written by run_bf_2026_seal_prep.py
     (row_keys.json + arm_A_pmf.npy + arm_B_pmf.npy) is consumed by the
     UNCHANGED canonical scorer run_bf_ab_score_v3.py;
  2. metric parity: the scorer's report is IDENTICAL (exact float
     equality) to computing the same metrics in-process from the same
     payload arrays via v3's own shared functions
     (run_bf_ab_score_v2.compute_stats + run_bf_ab_score_v3 views).

Conclusion recorded for Chat 2: NO thin adapter is required - canonical
v3 consumes the 2026 seal payload unchanged (adapter-parity result:
NOT-REQUIRED / PASS). No 2026 scoring is performed anywhere; the
synthetic payload and the synthetic label parquet are generated here.

Run from the repo: python research/offseason_2026/run_bf_2026_seal_parity_check.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
V3 = HERE / "run_bf_ab_score_v3.py"
N = 134  # run_bf_ab_score_v2.compute_stats pins the pilot cohort size
K_EVENTS = ["strikeout", "strikeout_double_play"]


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    spec = importlib.util.spec_from_file_location(
        "run_bf_ab_score_v3", str(V3))
    v3 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v3)
    assert Path(v3.__file__).resolve().is_relative_to(REPO), (
        "v3 resolved outside the checkout: %s" % v3.__file__)
    s2 = v3.s2
    assert Path(s2.__file__).resolve().is_relative_to(REPO), (
        "vendored v2 resolved outside the checkout: %s" % s2.__file__)
    kc = v3.kc
    assert Path(kc.__file__).resolve().is_relative_to(REPO), (
        "kcount_combiner resolved outside the checkout: %s" % kc.__file__)

    rng = np.random.default_rng(20261014)
    seal = Path(tempfile.mkdtemp(prefix="seal_parity_")) / "seal"
    seal.mkdir(parents=True)
    keys = []
    A = np.zeros((N, 24))
    B = np.zeros((N, 24))
    rng_pmf = np.random.default_rng(20261014 + 1)
    rng_pmf = np.random.default_rng(20261014 + 1)
    cutoffs = ["2026-08-07 22:45:00+00:00", "2026-08-14 22:45:00+00:00"]
    for i in range(N):
        gp = 900000 + i
        pid = 700000 + i
        keys.append({"game_pk": gp, "pitcher": pid,
                     "forecast_cutoff": cutoffs[i % 2],
                     "arm_B_status": "ok_confirmed",
                     "arm_B_equals_A": False})
        logits = rng_pmf.normal(1.0, 0.55, 24)
        pa = np.exp(logits - logits.max())
        pa /= pa.sum()
        logits_b = logits + 0.08
        pb = np.exp(logits_b - logits_b.max())
        pb /= pb.sum()
        A[i] = pa
        B[i] = pb
    (seal / "row_keys.json").write_text(
        json.dumps(keys, indent=1), encoding="ascii")
    np.save(seal / "arm_A_pmf.npy", A)
    np.save(seal / "arm_B_pmf.npy", B)

    data_root = Path(tempfile.mkdtemp(prefix="seal_parity_data_"))
    d26 = data_root / "Savant-Data" / "regular" / "2026"
    d26.mkdir(parents=True)
    rows = []
    for i, k in enumerate(keys):
        kk = i % 20
        for _ in range(kk):
            rows.append({"game_pk": k["game_pk"], "pitcher": k["pitcher"],
                         "events": "strikeout"})
        rows.append({"game_pk": k["game_pk"], "pitcher": k["pitcher"],
                     "events": "walk"})
    pl.DataFrame(rows).write_parquet(d26 / "statcast_2026_regular.parquet")

    # in-process expected values (v3's own shared metric functions)
    v2_stats = s2.compute_stats(seal, data_root)
    kk = np.array([v2_stats["actual_K"]["%s|%s" % (k["game_pk"],
                                                   k["pitcher"])]
                   for k in keys])
    expected = {
        "population_all": v2_stats["population_all"],
        "population_usable_B": v2_stats["population_usable_B"],
        "secondary": v2_stats["secondary"],
        "rmse_and_milestone_brier": v3.views(keys, A, B, kk),
        "bootstrap_date_draw":
            v3.bootstrap_date_draw_fraction(keys),
    }

    out = Path(tempfile.mkdtemp(prefix="seal_parity_out_"))
    proc = subprocess.run(
        [sys.executable, str(V3), "--seal-dir", str(seal),
         "--data-root", str(data_root), "--out", str(out)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit("PARITY BLOCKER: v3 subprocess failed:\n%s\n%s"
                         % (proc.stdout, proc.stderr))
    rep = json.loads(
        (out / "scoring_report_v3.json").read_text(encoding="ascii"))

    def cmp(a, b, path=""):
        if isinstance(a, dict):
            assert set(a) == set(b), "key mismatch at %s" % path
            for k in a:
                cmp(a[k], b[k], "%s.%s" % (path, k))
        elif isinstance(a, float):
            assert a == b, "float mismatch at %s: %r vs %r" % (path, a, b)
        else:
            assert a == b, "value mismatch at %s: %r vs %r" % (path, a, b)

    cmp(expected["population_all"], rep["population_all"],
        "population_all")
    cmp(expected["population_usable_B"], rep["population_usable_B"],
        "population_usable_B")
    cmp(expected["secondary"], rep["secondary"], "secondary")
    cmp(expected["rmse_and_milestone_brier"],
        rep["rmse_and_milestone_brier"], "rmse_and_milestone_brier")
    cmp(expected["bootstrap_date_draw"], rep["bootstrap_date_draw"],
        "bootstrap_date_draw")
    assert rep["n_rows"] == N and rep["unmatched"] == 0

    result = {
        "parity": "PASS",
        "adapter_required": False,
        "conclusion": ("canonical run_bf_ab_score_v3.py consumed the "
                       "builder-staged v3-native seal-dir unchanged; all "
                       "reported statistics are exactly identical to the "
                       "in-process payload metrics on the same inputs"),
        "inputs": {
            "n_rows": N,
            "seed": 20261014,
            "synthetic_seal_sha256": {
                f: sha256_file(seal / f)
                for f in ("row_keys.json", "arm_A_pmf.npy",
                          "arm_B_pmf.npy")},
        },
        "import_resolution": {
            "run_bf_ab_score_v3": str(Path(v3.__file__).resolve()),
            "run_bf_ab_score_v2 (vendored)": str(
                Path(s2.__file__).resolve()),
            "kcount_combiner": str(Path(kc.__file__).resolve()),
        },
        "scorer_report": {
            "population_all_est": rep["population_all"]["est"],
            "population_usable_B_est": rep["population_usable_B"]["est"],
            "usable_B_n": rep["rmse_and_milestone_brier"]["usable_B_11"]["n"],
        },
    }
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
