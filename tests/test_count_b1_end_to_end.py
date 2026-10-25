"""Synthetic end-to-end test for the count_b1 runner write/finalize path.

Exercises the COMPLETE write/finalize machinery of
research/offseason_2026/bf_lane/run_count_b1_v1.py in a temporary directory
with synthetic fixtures: NO real data, NO lake reads, NO model fitting, NO
registered destination. Asserts that every declared 22-file inventory name
is created, the parquet files read back, manifest generation and inventory
enforcement work, and DataFrame.write_parquet is always called with an
explicit destination (regression guard for the 2026-10-16 failed attempt,
whose bare write_parquet() calls raised
"TypeError: DataFrame.write_parquet() missing 1 required positional
argument: 'file'").

Also tests the additive freeze "recovery_run_v1" convention: the original
FAILED destination stays preserved and the recovery execution targets the
registered sibling destination count_b1_recovery_v1.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest

REPO = Path(__file__).resolve().parents[1]
RUNNER_PATH = (REPO / "research" / "offseason_2026" / "bf_lane"
               / "run_count_b1_v1.py")
FREEZE_PATH = RUNNER_PATH.parent / "freeze_count_eval_v1.json"

FROZEN_OUTPUT_LOCATION = (
    "C:\\Users\\ckaplinger\\MLB-Props-Research"
    "\\bf-2026-eval-v1-outputs\\count_b1\\")
REGISTRATION_ID = "bf-2026-eval-v1-count_b1"

JSON_FILES = [
    "count_b1_aggregates_block_2024H2.json",
    "count_b1_aggregates_block_2025H1.json",
    "count_b1_aggregates_pooled.json",
    "count_b1_calibration_deciles_block_2024H2.json",
    "count_b1_calibration_deciles_block_2025H1.json",
    "count_b1_calibration_deciles_pooled.json",
    "count_b1_contrast.json",
    "count_b1_coverage_width.json",
    "count_b1_flagged_recenter_records.json",
    "count_b1_identity_gate.json",
    "count_b1_p_bar_inventory.json",
    "count_b1_row_count_assertions.json",
]
PARQUET_FILES = [
    "count_b1_per_row_scores.parquet",
    "count_b1_per_row_pmf_b0.parquet",
    "count_b1_per_row_pmf_b1.parquet",
]
BYTE_FILES = [
    "lgbm_equal_info_config.json",
    "metrics.json",
    "tracking_status.json",
    "retrieved/lgbm_equal_info_config.json",
]


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_count_b1_v1_e2e", str(RUNNER_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def runner():
    return _load_runner()


@pytest.fixture()
def run_dir(tmp_path, monkeypatch, runner):
    """A synthetic recovery run dir wired in as the runner's RUN_DIR."""
    d = tmp_path / "outputs" / "count_b1_recovery_v1"
    monkeypatch.setattr(runner, "RUN_DIR", d)
    return d


def _synthetic_scores() -> pl.DataFrame:
    n = 12
    return pl.DataFrame({
        "game_pk": list(range(700000, 700000 + n)),
        "side": ["H"] * n,
        "pitcher": [100000 + i for i in range(n)],
        "game_date": ["2025-04-%02d" % (1 + i % 4) for i in range(n)],
        "fold": ["block_2024H2" if i % 2 == 0 else "block_2025H1"
                 for i in range(n)],
        "b0_rps": np.linspace(0.2, 0.4, n),
        "b1_rps": np.linspace(0.19, 0.39, n),
    })


def _build_all_declared_files(run_dir: Path, runner) -> pl.DataFrame:
    """Write every declared non-manifest inventory file through the
    runner's own write helpers (write_once_parquet / write_once /
    write_once_json) into the synthetic run dir."""
    run_dir.mkdir(parents=True)
    rdf = _synthetic_scores()
    pmf_df = rdf.select("game_pk", "side", "pitcher")
    kpdf = pl.DataFrame(
        np.full((rdf.height, 24), 1.0 / 24),
        schema=["b0_count_%d" % k for k in range(24)])

    # the three REPAIRED parquet writes: explicit destination paths
    runner.write_once_parquet(
        run_dir / "count_b1_per_row_scores.parquet", rdf)
    runner.write_once_parquet(
        run_dir / "count_b1_per_row_pmf_b0.parquet",
        pl.concat([pmf_df, kpdf], how="horizontal"))
    b1_pdf = kpdf.rename({c: c.replace("b0_", "b1_") for c in kpdf.columns})
    runner.write_once_parquet(
        run_dir / "count_b1_per_row_pmf_b1.parquet",
        pl.concat([pmf_df, b1_pdf], how="horizontal"))

    runner.write_once(
        run_dir / "count_b1_per_date_paired_sums.csv",
        b"fold,game_date,n,b0_rps_sum,b1_rps_sum\n")
    buf = io.BytesIO()
    np.save(buf, np.zeros((4, 2)))
    runner.write_once(run_dir / "count_b1_bootstrap_replicates.npy",
                      buf.getvalue())

    for name in JSON_FILES:
        runner.write_once_json(run_dir / name,
                               {"synthetic": True, "n": rdf.height})
    (run_dir / "retrieved").mkdir()
    for name in BYTE_FILES:
        runner.write_once(run_dir / name, b"{}")
    return rdf


# ---------------------------------------------------------------------------
# regression: write_parquet always called with an EXPLICIT destination
# ---------------------------------------------------------------------------

def test_runner_source_has_no_bare_write_parquet_calls():
    src = RUNNER_PATH.read_text(encoding="ascii")
    code = src.split('"""', 2)[2]  # drop the module docstring
    assert ".write_parquet()" not in code
    assert ".write_parquet(" in code
    assert "write_once_parquet(" in code


def test_write_parquet_receives_explicit_destinations(runner, run_dir,
                                                      monkeypatch):
    real = pl.DataFrame.write_parquet
    recorded = []

    def spy(self, file, **kwargs):
        recorded.append(file)
        return real(self, file, **kwargs)

    monkeypatch.setattr(pl.DataFrame, "write_parquet", spy)
    _build_all_declared_files(run_dir, runner)

    assert recorded, "write_parquet was never called"
    for dest in recorded:
        assert dest is not None, (
            "DataFrame.write_parquet was called without an explicit "
            "destination (the 2026-10-16 failure mode)")
        assert isinstance(dest, Path)
    assert sorted(Path(p).name for p in recorded) == sorted(
        "count_b1_per_row_%s.parquet" % tag
        for tag in ("scores", "pmf_b0", "pmf_b1"))


def test_write_once_parquet_enforces_write_once(runner, run_dir):
    _build_all_declared_files(run_dir, runner)
    with pytest.raises(RuntimeError, match="write-once violation"):
        runner.write_once_parquet(
            run_dir / "count_b1_per_row_scores.parquet",
            _synthetic_scores())


# ---------------------------------------------------------------------------
# synthetic end-to-end: all declared files, read-back, manifest, inventory
# ---------------------------------------------------------------------------

def _finalize(runner, run_dir):
    runner.finalize_manifest(
        {"freeze": "a" * 64, "runner": "b" * 64},
        "c" * 64, "d" * 64)


def test_synthetic_end_to_end_write_and_finalize(runner, run_dir):
    rdf = _build_all_declared_files(run_dir, runner)
    _finalize(runner, run_dir)

    # every declared output filename exists (22-file inventory)
    for rel in runner.RUN_FILES_SCHEMA:
        assert (run_dir / rel).is_file(), "missing declared file: %s" % rel

    # parquet files read back with the written contents
    back = pl.read_parquet(run_dir / "count_b1_per_row_scores.parquet")
    assert back.equals(rdf)
    b0 = pl.read_parquet(run_dir / "count_b1_per_row_pmf_b0.parquet")
    assert b0.height == rdf.height
    assert b0.columns[:3] == ["game_pk", "side", "pitcher"]
    assert b0["b0_count_0"].sum() == pytest.approx(rdf.height / 24)
    b1 = pl.read_parquet(run_dir / "count_b1_per_row_pmf_b1.parquet")
    assert b1["b1_count_23"].sum() == pytest.approx(rdf.height / 24)

    # manifest generation succeeded and is internally consistent
    manifest = json.loads(
        (run_dir / "run_manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "count_b1_run_manifest_v1"
    assert manifest["declared_inventory_schema"] == runner.RUN_FILES_SCHEMA
    inventory = manifest["artifact_inventory_sha256"]
    assert sorted(inventory) == sorted(
        set(runner.RUN_FILES_SCHEMA) - {"run_manifest.json"})
    for rel, sha in inventory.items():
        actual = hashlib.sha256((run_dir / rel).read_bytes()).hexdigest()
        assert sha == actual, "manifest hash drift for %s" % rel

    # the synthetic run dir is registered as a recovery destination, so the
    # manifest carries the recovery block that makes it distinguishable
    rec = manifest["recovery_run_v1"]
    assert rec["recovery_run_id"] == REGISTRATION_ID + "_recovery_v1"
    assert rec["original_status"].startswith("FAILED")


def test_inventory_enforcement_rejects_missing_file(runner, run_dir):
    _build_all_declared_files(run_dir, runner)
    (run_dir / "count_b1_contrast.json").unlink()
    with pytest.raises(RuntimeError, match="declared inventory file missing"):
        _finalize(runner, run_dir)


def test_inventory_enforcement_rejects_extra_file(runner, run_dir):
    _build_all_declared_files(run_dir, runner)
    (run_dir / "count_b1_stray_artifact.json").write_text("{}")
    with pytest.raises(RuntimeError, match="output inventory mismatch"):
        _finalize(runner, run_dir)


# ---------------------------------------------------------------------------
# recovery addendum convention (additive freeze key recovery_run_v1)
# ---------------------------------------------------------------------------

def _synthetic_freeze(out_root: Path, **overrides) -> dict:
    out = out_root / "count_b1"
    rec = {
        "original_destination": str(out) + "\\",
        "original_status": "FAILED",
        "preserves_original_failure_directory": True,
        "recovery_run_id": REGISTRATION_ID + "_recovery_v1",
        "destination": str(out_root / "count_b1_recovery_v1") + "\\",
    }
    rec.update(overrides)
    return {"output": {"location": str(out) + "\\"},
            "recovery_run_v1": rec}


def test_freeze_recovery_addendum_convention():
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    rec = freeze["recovery_run_v1"]
    assert rec["additive"] is True
    assert rec["original_destination"] == freeze["output"]["location"]
    assert rec["original_destination"] == FROZEN_OUTPUT_LOCATION
    assert rec["original_status"] == "FAILED"
    assert "write_parquet" in rec["original_error"]
    assert rec["preserves_original_failure_directory"] is True
    assert rec["recovery_run_id"] == (
        freeze["registration_id"] + "_recovery_v1")
    dest = Path(rec["destination"].rstrip("\\"))
    orig = Path(freeze["output"]["location"].rstrip("\\"))
    assert dest.parent == orig.parent
    assert dest.name == orig.name + "_recovery_v1"
    # the scientific contract is untouched: same output root, same
    # endpoint/bootstrap/no-rerun rules
    assert freeze["output"]["location"] == FROZEN_OUTPUT_LOCATION
    assert freeze["output"]["write_once"] is True
    assert freeze["endpoint"]["bootstrap"]["seed"] == 20261001
    assert freeze["endpoint"]["holm_family"]["size"] == 1
    assert any("destination must not exist" in r
               for r in freeze["fail_closed_rules"])
    # the amendment still pins the repaired runner bytes
    # (git-blob extraction: platform-independent LF content, NOT the
    #  working-tree file which may have CRLF from core.autocrlf)
    import subprocess
    runner_rel = "research/offseason_2026/bf_lane/run_count_b1_v1.py"
    git_bytes = subprocess.run(
        ["git", "-C", str(REPO), "show", f"HEAD:{runner_rel}"],
        capture_output=True).stdout
    runner_sha = hashlib.sha256(git_bytes).hexdigest()
    assert freeze["execution_amendment_v1"]["runner"]["sha256"] == runner_sha


def test_resolve_recovery_destination_synthetic(runner, tmp_path):
    freeze = _synthetic_freeze(tmp_path / "outputs")
    dest = runner.resolve_recovery_destination(freeze)
    assert dest == tmp_path / "outputs" / "count_b1_recovery_v1"


def test_resolve_recovery_destination_accepts_registered_pair(runner):
    """Regression (2026-10-17 CI failure): the EXACT registered pair --
    failed evidence destination count_b1, recovery destination
    count_b1_recovery_v1 -- must be accepted on ANY platform. The freeze
    carries Windows-style trailing-backslash paths; raw-string or
    platform-flavored Path.name comparisons rejected them on POSIX."""
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    rec = freeze["recovery_run_v1"]
    orig_comps = runner.path_components(rec["original_destination"])
    dest_comps = runner.path_components(rec["destination"])
    assert orig_comps[-1] == "count_b1"
    assert dest_comps[-1] == "count_b1_recovery_v1"
    assert orig_comps[-2] == dest_comps[-2] == "bf-2026-eval-v1-outputs"
    dest = runner.resolve_recovery_destination(freeze)  # must not raise
    assert runner.path_components(str(dest))[-1] == "count_b1_recovery_v1"


@pytest.mark.parametrize("dest", [
    "C:\\root\\count_b1_recovery_v1\\",
    "C:\\root\\count_b1_recovery_v1",
    "C:/root/count_b1_recovery_v1/",
    "C:/root/count_b1_recovery_v1",
])
def test_resolve_recovery_destination_normalizes_separators(runner, dest):
    """Trailing and platform separators must not affect acceptance."""
    freeze = {
        "output": {"location": "C:\\root\\count_b1\\"},
        "recovery_run_v1": {
            "original_destination": "C:\\root\\count_b1\\",
            "original_status": "FAILED",
            "preserves_original_failure_directory": True,
            "recovery_run_id": REGISTRATION_ID + "_recovery_v1",
            "destination": dest,
        },
    }
    out = runner.resolve_recovery_destination(freeze)  # must not raise
    assert runner.path_components(str(out))[-1] == "count_b1_recovery_v1"


def test_resolve_recovery_no_addendum_returns_registered_destination(runner):
    assert runner.resolve_recovery_destination(
        {"output": {"location": FROZEN_OUTPUT_LOCATION}}) == runner.OUT_DIR


@pytest.mark.parametrize("overrides, match", [
    ({"original_destination": "C:\\somewhere\\else\\"}, "original_destination"),
    ({"original_status": "OK"}, "original_status"),
    ({"preserves_original_failure_directory": False},
     "preserves_original_failure_directory"),
    ({"recovery_run_id": "some-other-id"}, "recovery_run_id"),
    ({"destination": "C:\\somewhere\\else\\count_b1_recovery_v1\\"},
     "sibling"),
    ({"destination": None}, "recovery convention"),
])
def test_resolve_recovery_rejects_nonconforming_addendum(
        runner, tmp_path, overrides, match):
    freeze = _synthetic_freeze(tmp_path / "outputs", **overrides)
    with pytest.raises(RuntimeError, match=match):
        runner.resolve_recovery_destination(freeze)


def test_recovery_requires_preserved_failure_evidence(runner, tmp_path,
                                                      monkeypatch):
    fake_out = tmp_path / "count_b1"
    monkeypatch.setattr(runner, "OUT_DIR", fake_out)
    freeze = {"recovery_run_v1": {"anything": True}}
    with pytest.raises(RuntimeError, match="failure evidence"):
        runner.assert_original_failure_preserved(freeze)
    fake_out.mkdir()
    (fake_out / "count_b1_error_log.json").write_text("{}")
    runner.assert_original_failure_preserved(freeze)  # no raise


def test_recovery_evidence_check_skipped_without_addendum(runner, tmp_path,
                                                          monkeypatch):
    monkeypatch.setattr(runner, "OUT_DIR", tmp_path / "never_created")
    runner.assert_original_failure_preserved(
        {"output": {"location": "x"}})  # no raise, no recovery key
