# test_auto_tracking.py -- AUTOMATIC MLFLOW TRACKING TESTS for the LightGBM
# equal-info harness path (count-eval-v1). SYNTHETIC ONLY: temp tracking
# stores + temp artifacts; the canonical mlflow.db is never touched.
#
# D-1 (2026-10-15): every test here goes through the SHARED tracking wrapper
# (track_and_verify.py: compare -> save -> log(MLflow) -> verify (retrieve +
# hash check)) -- the exact wrapper the frozen LightGBM command
# (run_lgbm_equal_info.py, registered in freeze_lgbm_equal_info_v1.json
# amendment-1) invokes. No test hand-replicates logging calls.
#
# What these prove:
#   * round-trip: a synthetic run logs itself through the wrapper into a
#     TEMP sqlite store in one process, and a FRESH second process retrieves
#     the run by id and verifies metrics (exact round-trip) + the artifact
#     byte hash through the artifact API (verify_run is the wrapper's own
#     verifier);
#   * failure injection (D-1 contract): an MLflow logging failure (injected
#     via monkeypatch, or a genuinely unreachable tracking store) SURFACES to
#     the caller (TrackingFailure), preserves the computed canonical outputs
#     untouched, records status "tracking_failed" (the batch is never
#     reported fully successful), and does NOT trigger a refit (compare runs
#     exactly once);
#   * D-2 identity verification: verify_registered_identities re-derives the
#     registered identities from disk and fails loud before any fitting
#     (synthetic freeze ok + tamper detection, plus the REAL amended freeze
#     checked end-to-end against disk).
#
# Run: .venv python -m pytest test_auto_tracking.py -q
# ASCII-only (cp1252 consoles).
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
# sys.path order matters (amendment-2): the lake count-eval-v1 dir holds a
# HISTORICAL amendment-1 mirror of track_and_verify.py (preserved, not
# updated), so it is inserted FIRST and the builder-worktree harness dir is
# inserted LAST so the REGISTERED harness modules (track_and_verify,
# comparison) shadow the stale mirror; the lake dir still supplies
# lgbm_equal_info_adapter (registered there and nowhere else).
sys.path.insert(0, r"C:\Users\ckaplinger\MLB-Props-Research\count-eval-v1")
sys.path.insert(0, HERE)
sys.path.insert(0, (r"C:\Users\ckaplinger\Downloads\Personal-Projects"
                    r"\MLB-Props-worktrees\market-eval-v2\research"
                    r"\offseason_2026\specs\count-eval-v2-spec\harness"))

LOG_MODE = "log"
VERIFY_MODE = "verify"
HANDOFF = "auto_tracking_handoff.json"

ORIGINAL_CONFIG_SHA256 = (
    "8dec7352957b8d4f09073a8b296450f69ae551a2d27e758da3c1bf2fdac6f294")

AMENDMENT1_CONFIG_SHA256 = (
    "b33e2a845c929f5f6dafba9c0adfcab49b4ee26655ed42e4f09428d9a2a100cf")

AMENDMENT2_CONFIG_SHA256 = (
    "bcfc2a15a4351f9bff44fb55a3830c9715360ac8d9e60870039c05b4e75ef260")

EXECUTED_RUN_ID = (
    "b8bc222c703a4a60e1eb0736143800e34601f61db0ced84cc067597b7796fd05")


# ---------------------------------------------------------------------------
# Mode implementations (each runs in its OWN process; both use the wrapper)
# ---------------------------------------------------------------------------

def run_and_log(work_dir: str) -> None:
    """LOG side: synthetic comparison through the adapter, logged through
    the SHARED wrapper (track_and_verify.track_and_verify), which saves the
    canonical outputs, logs params/metrics/artifact into the temp sqlite
    store, and verifies in-process. Writes the handoff record for the
    fresh-process verifier."""
    from pathlib import Path

    import lgbm_equal_info_adapter as ad
    import track_and_verify as tv
    from test_lgbm_equal_info_adapter import make_synthetic, split_fold

    work = Path(work_dir)
    tracking_uri = "sqlite:///" + (work / "mlflow.db").as_posix()
    artifact_root = (work / "artifacts").as_uri()
    out_dir = work / "run_outputs"

    folds = [split_fold(f) for f in make_synthetic()]

    def compare_fn():
        return ad.compare_on_synthetic_folds(folds)

    status = tv.track_and_verify(
        compare_fn, out_dir, tracking_uri,
        experiment="lgbm-equal-info-auto-tracking",
        run_name="lgbm-equal-info-auto-synthetic",
        artifact_location=artifact_root)
    assert status["status"] == "VERIFIED", status

    src_sha = status["config_artifact_sha256"]
    (work / HANDOFF).write_text(json.dumps({
        "tracking_uri": tracking_uri,
        "run_id": status["run_id"],
        "artifact": status["config_artifact_relpath"],
        "source_sha256": src_sha,
        "expected_metrics": {
            "contrast_delta_brier_raw":
                json.loads((out_dir / "metrics.json").read_text())
                ["contrast"]["delta"],
        },
        "logged_by_process_pid": os.getpid(),
    }, indent=2))


def retrieve_and_verify(work_dir: str) -> None:
    """VERIFY side: FRESH process, no shared in-memory state. Connects to
    the temp tracking store and verifies through the SHARED wrapper's own
    verifier (track_and_verify.verify_run): metric exact round-trip +
    artifact byte-hash via the artifact API."""
    from pathlib import Path

    import track_and_verify as tv

    work = Path(work_dir)
    hand = json.loads((work / HANDOFF).read_text())
    res = tv.verify_run(hand["tracking_uri"], hand["run_id"],
                        hand["expected_metrics"], hand["artifact"],
                        hand["source_sha256"], work / "retrieved_fresh")
    (work / "verify_result.json").write_text(json.dumps({
        "status": res["status"],
        "verifier_process_pid": os.getpid(),
        "logged_by_process_pid": hand["logged_by_process_pid"],
        "separate_processes":
            os.getpid() != hand["logged_by_process_pid"],
        "metrics_ok": res["metrics_ok"], "metrics": res["metrics"],
        "artifact": res["artifact"],
        "source_sha256": res["source_sha256"],
        "retrieved_sha256": res["retrieved_sha256"],
        "artifact_ok": res["artifact_ok"],
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


# ---------------------------------------------------------------------------
# D-1 failure injection: MLflow failure surfaces, outputs preserved, no refit
# ---------------------------------------------------------------------------

def _reference_outputs(tmp_path):
    """One canonical compare + save OUTSIDE the wrapper, as the byte-level
    reference for the preserved-outputs assertions."""
    import lgbm_equal_info_adapter as ad
    import track_and_verify as tv
    from test_lgbm_equal_info_adapter import make_synthetic, split_fold

    folds = [split_fold(f) for f in make_synthetic()]
    result = ad.compare_on_synthetic_folds(folds)
    ref_dir = tmp_path / "reference"
    saved = tv.save_canonical_outputs(result, ref_dir)
    return folds, ref_dir, saved


def test_logging_failure_surfaces_and_preserves_outputs(tmp_path,
                                                        monkeypatch):
    import mlflow

    import lgbm_equal_info_adapter as ad
    import track_and_verify as tv

    folds, ref_dir, _ = _reference_outputs(tmp_path)

    def _boom(*a, **k):
        raise ConnectionError("unreachable tracking store (injected)")

    monkeypatch.setattr(mlflow, "start_run", _boom)

    out_dir = tmp_path / "run"
    calls = {"n": 0}

    def compare_fn():
        calls["n"] += 1
        return ad.compare_on_synthetic_folds(folds)

    with pytest.raises(tv.TrackingFailure) as excinfo:
        tv.track_and_verify(compare_fn, out_dir,
                            "sqlite:///" + (tmp_path / "mlflow.db").as_posix())
    assert isinstance(excinfo.value.__cause__, ConnectionError)
    assert calls["n"] == 1  # compare ran exactly ONCE: no refit on failure
    status = json.loads((out_dir / "tracking_status.json").read_text())
    assert status["status"] == "tracking_failed"
    assert status["phase"] == "log"
    # canonical outputs preserved untouched (byte-identical to reference)
    assert (out_dir / "metrics.json").read_bytes() == \
        (ref_dir / "metrics.json").read_bytes()
    assert (out_dir / "lgbm_equal_info_config.json").read_bytes() == \
        (ref_dir / "lgbm_equal_info_config.json").read_bytes()


def test_unreachable_tracking_store_surfaces_as_tracking_failed(tmp_path):
    import lgbm_equal_info_adapter as ad
    import track_and_verify as tv
    from test_lgbm_equal_info_adapter import make_synthetic, split_fold

    folds = [split_fold(f) for f in make_synthetic()]
    out_dir = tmp_path / "run"
    # closed port on loopback: a genuinely unreachable tracking store
    bad_uri = "http://127.0.0.1:9"
    with pytest.raises(tv.TrackingFailure):
        tv.track_and_verify(lambda: ad.compare_on_synthetic_folds(folds),
                            out_dir, bad_uri)
    status = json.loads((out_dir / "tracking_status.json").read_text())
    assert status["status"] == "tracking_failed"
    assert (out_dir / "metrics.json").exists()  # canonical outputs preserved


def test_verification_mismatch_surfaces_as_tracking_failed(tmp_path,
                                                           monkeypatch):
    from mlflow.tracking import MlflowClient

    import lgbm_equal_info_adapter as ad
    import track_and_verify as tv

    folds, ref_dir, saved = _reference_outputs(tmp_path)
    orig = MlflowClient.download_artifacts

    def tampered(self, run_id, path, dst_path=None):
        got = Path(orig(self, run_id, path, dst_path))
        bad = got.with_name("tampered_" + got.name)
        bad.write_bytes(got.read_bytes() + b"TAMPERED")
        return str(bad)

    monkeypatch.setattr(MlflowClient, "download_artifacts", tampered)
    out_dir = tmp_path / "run"
    with pytest.raises(tv.TrackingFailure):
        tv.track_and_verify(lambda: ad.compare_on_synthetic_folds(folds),
                            out_dir,
                            "sqlite:///" + (tmp_path / "mlflow.db").as_posix())
    status = json.loads((out_dir / "tracking_status.json").read_text())
    assert status["status"] == "tracking_failed"
    assert status["phase"] == "verify"
    # the canonical outputs were never modified by the tampering
    assert (out_dir / "lgbm_equal_info_config.json").read_bytes() == \
        (ref_dir / "lgbm_equal_info_config.json").read_bytes()
    assert tv.sha256_file(out_dir / "lgbm_equal_info_config.json") == \
        saved["config_artifact_sha256"]


# ---------------------------------------------------------------------------
# D-2: registered identity verification
# ---------------------------------------------------------------------------

def _make_synthetic_freeze(tmp_path, input_paths=None, extra_cfg=None):
    """Synthetic freeze with REAL adapter/wrapper/comparison/runner hashes
    and SYNTHETIC input files (or caller-supplied input paths)."""
    import comparison as cmp_mod
    import lgbm_equal_info_adapter as ad
    import track_and_verify as tv

    files = {}
    for name in ("pa_table", "features_v3", "start_metrics_outcome_source"):
        if input_paths is not None:
            files[name] = Path(input_paths[name])
            continue
        f = tmp_path / f"{name}.bin"
        f.write_bytes(f"synthetic {name} bytes".encode("ascii"))
        files[name] = f
    cfg = {
        "interface_version": "synthetic",
        "text_source_identity_convention": tv.TEXT_SOURCE_IDENTITY_CONVENTION,
        "lgbm_hyperparameters": dict(ad.LGBM_EQUAL_INFO_CONFIG),
        "registered_inputs": {
            k: {"path": str(files[k]),
                "sha256": tv.sha256_file(files[k])}
            for k in files},
        "adapter": {"path": str(ad.__file__),
                    "file_sha256": tv.sha256_file(ad.__file__),
                    "file_sha256_normalized":
                        tv.sha256_file_identity(ad.__file__)[
                            "lf_normalized"],
                    "config_sha256": ad.config_sha256()},
        "tracking_wrapper": {"path": str(tv.__file__),
                             "file_sha256": tv.sha256_file(tv.__file__),
                             "file_sha256_normalized":
                                 tv.sha256_file_identity(tv.__file__)[
                                     "lf_normalized"]},
        "builder_worktree_harness": {
            "comparison_path": str(cmp_mod.__file__),
            "comparison_sha256": tv.sha256_file(cmp_mod.__file__),
            "comparison_sha256_normalized":
                tv.sha256_file_identity(cmp_mod.__file__)["lf_normalized"],
            "runner_sha256": tv.sha256_file(
                os.path.join(HERE, "run_lgbm_equal_info.py")),
            "runner_sha256_normalized":
                tv.sha256_file_identity(
                    os.path.join(HERE, "run_lgbm_equal_info.py"))[
                        "lf_normalized"]},
    }
    if extra_cfg:
        cfg.update(extra_cfg)
    freeze = {
        "batch": "synthetic-identity-check",
        "batch_id": "synthetic-identity-check",
        "config_sha256": tv.freeze_config_sha256(cfg),
        "config_hash_definition": tv.CONFIG_HASH_DEFINITION,
        "config": cfg,
    }
    path = tmp_path / "freeze_synthetic.json"
    path.write_text(json.dumps(freeze, indent=2))
    return path, files


def test_verify_registered_identities_synthetic_ok_and_tamper(tmp_path):
    import track_and_verify as tv

    freeze_path, files = _make_synthetic_freeze(tmp_path)
    runner = os.path.join(HERE, "run_lgbm_equal_info.py")

    out = tv.verify_registered_identities(freeze_path,
                                          runner_path=runner)
    assert out["ok"] is True
    assert "input.features_v3.sha256" in out["checked"]

    # tamper one registered input byte -> IdentityMismatch naming it
    f = files["features_v3"]
    orig = f.read_bytes()
    f.write_bytes(orig + b"x")
    with pytest.raises(tv.IdentityMismatch, match="features_v3"):
        tv.verify_registered_identities(freeze_path)
    f.write_bytes(orig)

    # tamper the freeze config hash -> IdentityMismatch
    freeze = json.loads(freeze_path.read_text())
    freeze["config_sha256"] = "0" * 64
    freeze_path.write_text(json.dumps(freeze, indent=2))
    with pytest.raises(tv.IdentityMismatch, match="config_sha256"):
        tv.verify_registered_identities(freeze_path)


def test_amended_freeze_registration_integrity():
    """The REAL amended freeze (amendment-2): hash integrity, historical
    preservation (both superseded registrations), the declared text-source
    identity convention, D-3 declaration, literal command, and full on-disk
    identity verification against the registered files."""
    import lgbm_equal_info_adapter as ad
    import track_and_verify as tv

    freeze_path = os.path.join(HERE, "freeze_lgbm_equal_info_v1.json")
    freeze = json.loads(open(freeze_path, encoding="utf-8").read())
    cfg = freeze["config"]
    assert freeze["config_sha256"] == AMENDMENT2_CONFIG_SHA256
    assert tv.freeze_config_sha256(cfg) == freeze["config_sha256"]

    # amendment-2: the declared text-source identity convention is registered
    # verbatim (single owner: track_and_verify.TEXT_SOURCE_IDENTITY_CONVENTION)
    assert cfg["text_source_identity_convention"] == \
        tv.TEXT_SOURCE_IDENTITY_CONVENTION

    # D-2: both prior registrations preserved as historical, hash-verified
    hist = freeze["historical_registrations"]
    assert len(hist) == 2
    assert hist[0]["config_sha256"] == ORIGINAL_CONFIG_SHA256
    assert tv.freeze_config_sha256(hist[0]["config"]) == \
        ORIGINAL_CONFIG_SHA256
    assert "SUPERSEDED" in hist[0]["annotation"]
    assert hist[1]["config_sha256"] == AMENDMENT1_CONFIG_SHA256
    assert tv.freeze_config_sha256(hist[1]["config"]) == \
        AMENDMENT1_CONFIG_SHA256
    assert "SUPERSEDED" in hist[1]["annotation"]

    # amendment-2 execution note: the executed run predates this convention
    note = cfg["amendment_2"]["execution_note"]
    assert EXECUTED_RUN_ID in note
    assert "PREDATES" in note

    # D-3: final-fit declaration present and explicit
    decl = cfg["final_fit_declaration"]
    assert "best_iteration" in decl
    assert "no refit on the full training fold" in decl.lower()

    # D-2: literal command with the outcome-scoring-equivalent flag
    cmd = cfg["execution"]["command"]
    assert "run_lgbm_equal_info.py" in cmd
    assert "--i-accept-real-data-execution" in cmd

    # registered hashes are full 64-hex sha256s; binary inputs byte-exact
    for key in ("pa_table", "features_v3", "start_metrics_outcome_source"):
        sha = cfg["registered_inputs"][key]["sha256"]
        assert len(sha) == 64 and all(c in "0123456789abcdef" for c in sha)
        assert cfg["registered_inputs"][key]["identity_class"].startswith(
            "binary")
    assert cfg["registered_inputs"]["start_metrics_outcome_source"][
        "join_status"].startswith("REGISTERED-PATH-ONLY")

    # full on-disk identity verification (real files, this machine)
    out = tv.verify_registered_identities(
        freeze_path, adapter_module=ad,
        runner_path=os.path.join(HERE, "run_lgbm_equal_info.py"))
    assert out["ok"] is True
    # text-source identities verified via their LF-normalized values
    for key in ("adapter.file_sha256_normalized",
                "wrapper.file_sha256_normalized",
                "harness.comparison.comparison_sha256_normalized",
                "runner.runner_sha256_normalized"):
        assert key in out["checked"]

    # destination: the amendment-1 real-data run executed 2026-10-15 under
    # this output_destination (write-once run dir b8bc222c...; it PREDATES
    # amendment-2 and is NOT re-registered here) - the write-once rule pins
    # that the executed run dir exists untouched and canonical outputs are
    # never overwritten
    dest = Path(cfg["output_destination"])
    assert dest.is_dir()
    run_dir = dest / EXECUTED_RUN_ID
    assert run_dir.is_dir()
    assert (run_dir / "metrics.json").is_file()
    assert (run_dir / "run_manifest.json").is_file()
    manifest = json.loads((run_dir / "run_manifest.json").read_text(
        encoding="utf-8"))
    # the executed run carries the amendment-1 registration identity
    assert manifest["freeze_config_sha256"] == AMENDMENT1_CONFIG_SHA256


def test_text_source_identity_convention_eol_portability(tmp_path):
    """Amendment-2 portability: the REAL registered freeze verifies against
    both LF-materialized and CRLF-materialized copies of every registered
    text-source file (fresh-checkout equivalence under either git EOL
    setting), while a CONTENT tamper still fails loud and the registered
    binary inputs stay byte-exact."""
    import lgbm_equal_info_adapter as ad
    import track_and_verify as tv

    freeze_path = os.path.join(HERE, "freeze_lgbm_equal_info_v1.json")
    freeze = json.loads(open(freeze_path, encoding="utf-8").read())
    cfg = json.loads(json.dumps(freeze["config"]))  # deep copy
    runner_path = os.path.join(HERE, "run_lgbm_equal_info.py")

    text_files = {
        "adapter": cfg["adapter"]["path"],
        "wrapper": cfg["tracking_wrapper"]["path"],
        "comparison": cfg["builder_worktree_harness"]["comparison_path"],
        "runner": runner_path,
    }
    lf_dir = tmp_path / "eol_portability_lf"
    crlf_dir = tmp_path / "eol_portability_crlf"
    lf_dir.mkdir()
    crlf_dir.mkdir()

    def materialized_freeze(materialize: str, workdir: Path):
        """Copy of the real freeze whose registered text identities are the
        LF-content hashes (exactly how the real amendment-2 freeze
        registers them), while each registered text-source file is
        re-materialized on disk with the requested EOL (LF like the repo
        blobs, or CRLF like an autocrlf fresh checkout)."""
        cfg2 = json.loads(json.dumps(cfg))
        for name, src in text_files.items():
            norm = tv.normalize_text_bytes(Path(src).read_bytes())
            data = norm if materialize == "lf" else norm.replace(
                b"\n", b"\r\n")
            dst = workdir / f"{name}.py"
            dst.write_bytes(data)
            # registered values: LF-content hashes (EOL-invariant identity)
            byte_exact_lf = hashlib.sha256(norm).hexdigest()
            lf_normalized = hashlib.sha256(norm).hexdigest()
            assert tv.sha256_file_identity(dst)["lf_normalized"] == \
                lf_normalized
            if name == "adapter":
                cfg2["adapter"]["path"] = str(dst)
                cfg2["adapter"]["file_sha256"] = byte_exact_lf
                cfg2["adapter"]["file_sha256_normalized"] = lf_normalized
            elif name == "wrapper":
                cfg2["tracking_wrapper"]["path"] = str(dst)
                cfg2["tracking_wrapper"]["file_sha256"] = byte_exact_lf
                cfg2["tracking_wrapper"]["file_sha256_normalized"] = \
                    lf_normalized
            elif name == "comparison":
                cfg2["builder_worktree_harness"]["comparison_path"] = \
                    str(dst)
                cfg2["builder_worktree_harness"]["comparison_sha256"] = \
                    byte_exact_lf
                cfg2["builder_worktree_harness"][
                    "comparison_sha256_normalized"] = lf_normalized
            else:
                cfg2["builder_worktree_harness"]["runner_sha256"] = \
                    byte_exact_lf
                cfg2["builder_worktree_harness"][
                    "runner_sha256_normalized"] = lf_normalized
        out_freeze = {
            "batch": freeze["batch"], "batch_id": freeze["batch_id"],
            "config_sha256": tv.freeze_config_sha256(cfg2),
            "config_hash_definition": freeze["config_hash_definition"],
            "config": cfg2,
        }
        p = workdir / "freeze_materialized.json"
        p.write_text(json.dumps(out_freeze, indent=2), encoding="utf-8")
        return p

    # 1. CRLF-materialized fresh-checkout simulation PASSES (the registered
    #    LF-normalized values are EOL-invariant; the CRLF copies really do
    #    differ byte-exact from every registered value - exactly the
    #    fresh-checkout situation amendment-1 could not survive)
    crlf_freeze = materialized_freeze("crlf", crlf_dir)
    out = tv.verify_registered_identities(crlf_freeze, adapter_module=ad,
                                          runner_path=str(
                                              crlf_dir / "runner.py"))
    assert out["ok"] is True
    crlf_observed = {k: v for k, v in out["checks"].items()
                     if k.endswith("byte_exact_observed")}
    assert len(crlf_observed) == len(text_files)
    assert all(v["ok"] is False for v in crlf_observed.values())

    # 2. LF-materialized copies also PASS (repo-blob equivalence), and their
    #    byte-exact values match the registered LF-content hashes
    lf_freeze = materialized_freeze("lf", lf_dir)
    out = tv.verify_registered_identities(lf_freeze, adapter_module=ad,
                                          runner_path=str(lf_dir / "runner.py"))
    assert out["ok"] is True
    lf_observed = {k: v for k, v in out["checks"].items()
                   if k.endswith("byte_exact_observed")}
    assert all(v["ok"] is True for v in lf_observed.values())

    # 3. a CONTENT tamper of a registered text-source file still FAILS loud
    tampered = materialized_freeze("lf", lf_dir)
    cfg3 = json.loads(tampered.read_text(encoding="utf-8"))
    comp = Path(cfg3["config"]["builder_worktree_harness"]
                ["comparison_path"])
    comp.write_bytes(comp.read_bytes() + b"\n# tampered\n")
    with pytest.raises(tv.IdentityMismatch, match="comparison"):
        tv.verify_registered_identities(tampered, adapter_module=ad,
                                        runner_path=str(lf_dir / "runner.py"))

    # 4. binary registered inputs remain byte-exact under the convention:
    #    a binary-class file's identity is its raw bytes (byte_exact ==
    #    lf_normalized) and any byte change changes it
    bin_dir = lf_dir / "_binary"
    bin_dir.mkdir(exist_ok=True)
    bin_file = bin_dir / "pa_table.parquet"
    bin_file.write_bytes(b"binary bytes")
    before = tv.sha256_file_identity(bin_file)
    bin_file.write_bytes(b"binary bytes!")
    after = tv.sha256_file_identity(bin_file)
    assert before["class"] == after["class"] == "binary"
    assert before["byte_exact"] == before["lf_normalized"]
    assert after["byte_exact"] == after["lf_normalized"]
    assert before["byte_exact"] != after["byte_exact"]


# ---------------------------------------------------------------------------
# D-1: the frozen LightGBM command end-to-end on SYNTHETIC parquet inputs
# ---------------------------------------------------------------------------

def _synthetic_real_frames():
    """Synthetic PA-table + features_v3-shaped frames covering all four
    registered fold windows (2023-01-05..2025-09-25, every 10 days, 8 PA
    rows/date); identical rows in both frames (join identity holds)."""
    import polars as pl

    import comparison as cmp_mod

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


def test_frozen_command_end_to_end_synthetic(tmp_path):
    """The frozen LightGBM command (run_lgbm_equal_info.main) on synthetic
    parquet inputs: refuses without the outcome-scoring-equivalent flag,
    then verifies registered identities, builds the real fold structure,
    and runs the SHARED wrapper (compare -> save -> log -> verify) to a
    VERIFIED tracking receipt. No real data, no canonical store."""
    import comparison as cmp_mod
    import run_lgbm_equal_info as runner

    feat_df, pa_df = _synthetic_real_frames()
    feat_path = tmp_path / "features_v3.parquet"
    pa_path = tmp_path / "pa_table.parquet"
    sm_path = tmp_path / "start_metrics_v2.parquet"
    feat_df.write_parquet(feat_path)
    pa_df.write_parquet(pa_path)
    # registered PATH+HASH ONLY: content never read or joined by the command
    pa_df.head(1).write_parquet(sm_path)

    freeze_path, _ = _make_synthetic_freeze(
        tmp_path,
        input_paths={"pa_table": pa_path, "features_v3": feat_path,
                     "start_metrics_outcome_source": sm_path},
        extra_cfg={
            "output_destination": str(tmp_path / "out"),
            "final_fit_declaration":
                "synthetic declaration: predictions use best_iteration; "
                "no refit on the full training fold",
            "equal_information_contract": {
                "features": list(cmp_mod.FEAT_H3)},
            "tracking": {
                "tracking_uri": "sqlite:///" + (tmp_path / "mlflow.db"
                                                ).as_posix(),
                "experiment": "lgbm-equal-info-frozen-command-synthetic"},
        })

    # D-2 gate: refuses (exit 2) without the acknowledgment flag
    assert runner.main(["--freeze", str(freeze_path)]) == 2
    assert not (tmp_path / "out").exists()  # nothing was read or written

    rc = runner.main(["--freeze", str(freeze_path),
                      "--i-accept-real-data-execution"])
    assert rc == 0
    out_dirs = list((tmp_path / "out").iterdir())
    assert len(out_dirs) == 1
    out_dir = out_dirs[0]
    status = json.loads((out_dir / "tracking_status.json").read_text())
    assert status["status"] == "VERIFIED"
    manifest = json.loads((out_dir / "run_manifest.json").read_text())
    assert manifest["folds_executed"] == cmp_mod.DEV_BLOCKS
    assert manifest["confirm_block_status"] == "EXCLUDED - NOT SCORED " \
        "(dev blocks only)"
    assert manifest["tracking"]["status"] == "VERIFIED"
    assert "best_iteration" in manifest["final_fit_declaration"]
    # the outcome source was registered path-only: identity verified, no join
    assert manifest["start_metrics_outcome_source"]["join_status"] \
        .startswith("REGISTERED-PATH-ONLY")


if __name__ == "__main__":
    mode, work_dir = sys.argv[1], sys.argv[2]
    if mode == LOG_MODE:
        run_and_log(work_dir)
    elif mode == VERIFY_MODE:
        retrieve_and_verify(work_dir)
    else:
        raise SystemExit(f"unknown mode: {mode}")
