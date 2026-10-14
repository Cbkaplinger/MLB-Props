"""Demonstrations for the cohort-aware scoring mode (NO 2026 outcomes).

Three demonstrations, all outcome-free (any labels used are SYNTHETIC,
generated in tempdirs; the real Savant data root is never touched):

  1. PARITY on the accepted 134-row fixture: the real
     bf-2026-predictor-seal-v1 payload passes the cohort-aware
     validation against the PINNED pilot-134 manifest, with exactly the
     checks the canonical scorer enforces (n, unique keys, identical
     arm populations, PMF validity) plus manifest key-set/cutoff
     equality;
  2. METRIC PARITY on a synthetic 134-row payload: canonical
     run_bf_ab_score_v3.py and the cohort-aware scorer produce EXACTLY
     equal statistics (float equality) on the same payload + synthetic
     label parquet - proving the cohort path's metric/bootstrap code is
     unchanged (vendored-v2 pin also hash-verified);
  3. NON-134 ACCEPTANCE: a synthetic 40-row payload with its own
     pinned 40-row manifest is ACCEPTED and scored by the cohort-aware
     mode, while the canonical v3 (hardcoded 134) fails loudly on the
     same payload - expected, recorded behavior.

Run from the repo:
  python research/offseason_2026/run_bf_cohort_mode_demo.py \
      --lake C:\\Users\\ckaplinger\\MLB-Props-Research \
      --card research/offseason_2026/experiments/bf-cohort-scorer-mode-2026-10-14
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).resolve().parent
COHORT = HERE / "run_bf_ab_score_cohort.py"
V3 = HERE / "run_bf_ab_score_v3.py"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def synth_payload(n: int, gp_base: int, pid_base: int, seed: int,
                  cutoffs: list[str]) -> tuple[list, np.ndarray,
                                               np.ndarray]:
    rng = np.random.default_rng(seed)
    keys = [{"game_pk": gp_base + i, "pitcher": pid_base + i,
             "forecast_cutoff": cutoffs[i % len(cutoffs)],
             "arm_B_status": "ok_confirmed", "arm_B_equals_A": False}
            for i in range(n)]
    A = np.zeros((n, 24))
    B = np.zeros((n, 24))
    for i in range(n):
        lg = rng.normal(1.0, 0.55, 24)
        pa = np.exp(lg - lg.max())
        pa /= pa.sum()
        lgb = lg + 0.08
        pb = np.exp(lgb - lgb.max())
        pb /= pb.sum()
        A[i], B[i] = pa, pb
    return keys, A, B


def write_seal(seal: Path, keys: list, A: np.ndarray, B: np.ndarray):
    seal.mkdir(parents=True)
    (seal / "row_keys.json").write_text(json.dumps(keys, indent=1),
                                        encoding="ascii")
    np.save(seal / "arm_A_pmf.npy", A)
    np.save(seal / "arm_B_pmf.npy", B)


def write_manifest(path: Path, manifest_id: str, keys: list,
                   source: str, source_sha: str):
    path.write_text(json.dumps({
        "manifest_id": manifest_id,
        "pinned_from": source,
        "pinned_source_sha256": source_sha,
        "n_rows": len(keys),
        "row_keys": keys,
    }, indent=1), encoding="ascii")


def write_synth_labels(data_root: Path, keys: list, seed: int) -> Path:
    d26 = data_root / "Savant-Data" / "regular" / "2026"
    d26.mkdir(parents=True)
    rng = np.random.default_rng(seed)
    rows = []
    for k in keys:
        kk = int(rng.integers(0, 20))
        for _ in range(kk):
            rows.append({"game_pk": k["game_pk"],
                         "pitcher": k["pitcher"],
                         "events": "strikeout"})
        rows.append({"game_pk": k["game_pk"], "pitcher": k["pitcher"],
                     "events": "walk"})
    p = d26 / "statcast_2026_regular.parquet"
    pl.DataFrame(rows).write_parquet(p)
    return p


def run_py(script: Path, args: list[str]):
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True)


def cmp_exact(a, b, path=""):
    if isinstance(a, dict):
        assert set(a) == set(b), "key mismatch at %s" % path
        for k in a:
            cmp_exact(a[k], b[k], "%s.%s" % (path, k))
    elif isinstance(a, float):
        assert a == b, "float mismatch at %s: %r vs %r" % (path, a, b)
    else:
        assert a == b, "value mismatch at %s: %r vs %r" % (path, a, b)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake",
                    default=r"C:\Users\ckaplinger\MLB-Props-Research")
    ap.add_argument("--card", required=True)
    args = ap.parse_args()
    lake = Path(args.lake)
    card = Path(args.card)
    card.mkdir(parents=True, exist_ok=True)
    seal_dir = lake / "bf-2026-predictor-seal-v1"
    demo: dict = {"demonstrations": {}}

    # ---- pinned pilot-134 manifest (committed artifact) ------------------
    seal_keys = json.loads(
        (seal_dir / "row_keys.json").read_text(encoding="ascii"))
    seal_keys_sha = sha256_file(seal_dir / "row_keys.json")
    manifest134 = card / "pinned_manifest_pilot134.json"
    write_manifest(manifest134, "pilot134-pinned", seal_keys,
                   "bf-2026-predictor-seal-v1/row_keys.json",
                   seal_keys_sha)

    # ---- DEMO 1: validation parity on the real 134-row fixture ----------
    out1 = Path(tempfile.mkdtemp(prefix="cohort_demo1_"))
    proc = run_py(COHORT, ["--seal-dir", str(seal_dir),
                           "--manifest", str(manifest134),
                           "--mode", "validate", "--out", str(out1)])
    assert proc.returncode == 0, proc.stderr
    val = json.loads((out1 / "cohort_validation_report.json")
                     .read_text(encoding="ascii"))
    assert val["n_rows"] == 134 and all(val["checks"].values()), val
    demo["demonstrations"]["demo1_parity_on_seal_fixture"] = {
        "result": "PASS",
        "description": ("real bf-2026-predictor-seal-v1 payload accepted "
                        "by the cohort-aware validation against the "
                        "pinned pilot-134 manifest; checks identical to "
                        "the canonical scorer's gating (n=134 via "
                        "manifest pin, unique keys, identical arm "
                        "populations, 24-bucket PMF validity) plus "
                        "manifest key-set + cutoff equality"),
        "n_rows": val["n_rows"],
        "checks": val["checks"],
        "outcome_reads": 0,
    }

    # ---- DEMO 2: metric parity, synthetic 134-row payload ----------------
    tmp2 = Path(tempfile.mkdtemp(prefix="cohort_demo2_"))
    keys2, A2, B2 = synth_payload(
        134, 900000, 700000, 20261014,
        ["2026-08-07 22:45:00+00:00", "2026-08-14 22:45:00+00:00"])
    seal2 = tmp2 / "seal"
    write_seal(seal2, keys2, A2, B2)
    data2 = tmp2 / "data"
    lab2 = write_synth_labels(data2, keys2, 20261015)
    man2 = tmp2 / "manifest_synth134.json"
    write_manifest(man2, "synthetic-134-demo", keys2, "demo-generated",
                   sha256_file(seal2 / "row_keys.json"))
    out_v3 = tmp2 / "out_v3"
    out_coh = tmp2 / "out_coh"
    p_v3 = run_py(V3, ["--seal-dir", str(seal2), "--data-root",
                       str(data2), "--out", str(out_v3)])
    assert p_v3.returncode == 0, p_v3.stderr
    p_coh = run_py(COHORT, ["--seal-dir", str(seal2),
                            "--manifest", str(man2),
                            "--data-root", str(data2),
                            "--mode", "score", "--out", str(out_coh),
                            "--label-source-note",
                            "SYNTHETIC labels (demo only; no 2026 "
                            "outcomes touched)"])
    assert p_coh.returncode == 0, p_coh.stderr
    r_v3 = json.loads((out_v3 / "scoring_report_v3.json")
                      .read_text(encoding="ascii"))
    r_coh = json.loads((out_coh / "cohort_scoring_report.json")
                       .read_text(encoding="ascii"))
    for block in ("population_all", "population_usable_B", "secondary"):
        cmp_exact(r_v3[block], r_coh["stats"][block], block)
    demo["demonstrations"]["demo2_metric_parity_synth134"] = {
        "result": "PASS",
        "description": ("canonical run_bf_ab_score_v3.py and the "
                        "cohort-aware scorer produce EXACTLY equal "
                        "population_all / population_usable_B / "
                        "secondary statistics on the same synthetic "
                        "134-row payload + synthetic labels (float "
                        "equality on every statistic)"),
        "compared_blocks": ["population_all", "population_usable_B",
                            "secondary"],
        "synthetic_seal_sha256": {
            f: sha256_file(seal2 / f)
            for f in ("row_keys.json", "arm_A_pmf.npy",
                      "arm_B_pmf.npy")},
        "synthetic_labels_sha256": sha256_file(lab2),
        "label_source": "SYNTHETIC (rng 20261015); no 2026 outcomes",
    }

    # ---- DEMO 3: synthetic non-134 (40-row) acceptance -------------------
    tmp3 = Path(tempfile.mkdtemp(prefix="cohort_demo3_"))
    keys3, A3, B3 = synth_payload(
        40, 990000, 880000, 20261016,
        ["2026-08-07 22:45:00+00:00", "2026-08-14 22:45:00+00:00"])
    seal3 = tmp3 / "seal"
    write_seal(seal3, keys3, A3, B3)
    data3 = tmp3 / "data"
    lab3 = write_synth_labels(data3, keys3, 20261017)
    man3 = tmp3 / "manifest_synth40.json"
    write_manifest(man3, "synthetic-40-demo", keys3, "demo-generated",
                   sha256_file(seal3 / "row_keys.json"))
    out3 = tmp3 / "out"
    p_coh3 = run_py(COHORT, ["--seal-dir", str(seal3),
                             "--manifest", str(man3),
                             "--data-root", str(data3),
                             "--mode", "score", "--out", str(out3),
                             "--label-source-note",
                             "SYNTHETIC labels (demo only; no 2026 "
                             "outcomes touched)"])
    assert p_coh3.returncode == 0, p_coh3.stderr
    r3 = json.loads((out3 / "cohort_scoring_report.json")
                    .read_text(encoding="ascii"))
    assert r3["n_rows"] == 40
    p_v3_40 = run_py(V3, ["--seal-dir", str(seal3), "--data-root",
                          str(data3), "--out", str(tmp3 / "out_v3_40")])
    assert p_v3_40.returncode != 0, "canonical v3 unexpectedly accepted n=40"
    assert "134" in (p_v3_40.stderr + p_v3_40.stdout), p_v3_40.stderr
    demo["demonstrations"]["demo3_non134_acceptance"] = {
        "result": "PASS",
        "description": ("synthetic 40-row payload ACCEPTED and scored by "
                        "the cohort-aware mode under its own pinned "
                        "40-row manifest (n=40), while canonical v3 "
                        "(hardcoded 134) fails loudly on the same "
                        "payload - canonical historical behavior "
                        "preserved"),
        "cohort_mode_n_rows": r3["n_rows"],
        "canonical_v3_returncode": p_v3_40.returncode,
        "canonical_v3_stderr_excerpt": p_v3_40.stderr.strip().splitlines()[
            -1][:200] if p_v3_40.stderr else "",
        "label_source": "SYNTHETIC (rng 20261017); no 2026 outcomes",
    }

    demo["vendored_lineage_check"] = {
        "note": ("run_bf_ab_score_cohort.verify_vendored_v2() hash-"
                 "verifies the vendored v2 against pin 6b8cecf2... on "
                 "every invocation (all three demos passed it)"),
    }
    demo["outcome_boundary"] = {
        "real_data_root_touched": False,
        "synthetic_labels_only": True,
        "real_2026_outcome_scoring": "NOT performed (forbidden until "
                                     "seal approval)",
    }
    (card / "demo_report.json").write_text(json.dumps(demo, indent=1),
                                           encoding="ascii")
    print(json.dumps({k: v["result"]
                      for k, v in demo["demonstrations"].items()},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
