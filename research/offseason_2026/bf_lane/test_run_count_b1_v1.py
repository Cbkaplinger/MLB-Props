"""Tests for the count_b1 execution amendment (run_count_b1_v1.py).

Validates amendment/config parsing and the runner's import + CLI surfaces.
NO real-data output generation, NO execution of the comparison: every test
here either parses JSON, imports the module, or invokes the runner in a
mode that refuses before touching any data.

    python -m pytest test_run_count_b1_v1.py -q
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_count_b1_v1.py"
FREEZE = HERE / "freeze_count_eval_v1.json"

AMENDMENT_STATEMENT = ("No scientific fields changed; this amendment only "
                       "pins execution plumbing.")
RUNNER_SHA256 = (
    "fc097b5697f75934e286002a18653a00046ca540d7b6050d5e8744b782e47be3")

FROZEN_SCIENTIFIC = {
    "registration_id": "bf-2026-eval-v1-count_b1",
    "primary": "paired count-RPS, B1 - B0 (C_b1_ridge_vs_b0_empirical)",
    "n_boot": 2000,
    "seed": 20261001,
    "holm_family_size": 1,
    "n_dev_rows": 4866,
    "n_slate_dates": 186,
    "flagged": 217,
    "output_location": ("C:\\Users\\ckaplinger\\MLB-Props-Research"
                        "\\bf-2026-eval-v1-outputs\\count_b1\\"),
}


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_count_b1_v1_under_test", str(RUNNER))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _canonical_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(
        obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def test_runner_import_and_declared_schema():
    mod = _load_runner()
    assert len(mod.RUN_FILES_SCHEMA) == 22
    assert len(set(mod.RUN_FILES_SCHEMA)) == 22
    assert "run_manifest.json" in mod.RUN_FILES_SCHEMA
    assert "metrics.json" in mod.RUN_FILES_SCHEMA
    assert mod.SEED_REGISTERED == FROZEN_SCIENTIFIC["seed"]
    assert mod.N_BOOT_REGISTERED == FROZEN_SCIENTIFIC["n_boot"]
    assert mod.REGISTRATION_ID == FROZEN_SCIENTIFIC["registration_id"]
    assert mod.AMENDMENT_STATEMENT == AMENDMENT_STATEMENT


def test_cli_help_exits_zero_without_data_access():
    r = subprocess.run([sys.executable, str(RUNNER), "--help"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0
    assert "--i-accept-real-data-execution" in r.stdout


def test_cli_refuses_without_acceptance_flag():
    r = subprocess.run([sys.executable, str(RUNNER)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 2
    assert "REFUSED" in r.stdout


def test_preflight_destination_absent(tmp_path):
    mod = _load_runner()
    mod.preflight_destination_absent(tmp_path / "missing_dir")  # no raise
    existing = tmp_path / "exists_dir"
    existing.mkdir()
    with pytest.raises(RuntimeError, match="write-once destination"):
        mod.preflight_destination_absent(existing)


def test_freeze_json_parses_and_amendment_pins_execution():
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    am = freeze["execution_amendment_v1"]
    assert am["amendment_id"] == "execution_amendment_v1"
    assert am["statement"] == AMENDMENT_STATEMENT
    assert am["runner"]["sha256"] == RUNNER_SHA256
    assert RUNNER.is_file()
    assert (hashlib.sha256(RUNNER.read_bytes()).hexdigest() == RUNNER_SHA256)
    cmd = am["literal_command"]
    assert "run_count_b1_v1.py" in cmd
    assert "freeze_count_eval_v1.json" in cmd
    assert "--i-accept-real-data-execution" in cmd
    assert Path(am["working_directory"]).is_dir()
    assert am["output_root"] == FROZEN_SCIENTIFIC["output_location"]
    assert "pip freeze" in am["environment_identity_capture_command"]
    assert am["preflight_assertion"]
    assert len(am["output_inventory_schema_22_files"]) == 22
    assert am["manifest_schema"]


def test_freeze_scientific_fields_unchanged():
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    ep = freeze["endpoint"]
    assert ep["primary"] == FROZEN_SCIENTIFIC["primary"]
    assert ep["bootstrap"]["n_boot"] == FROZEN_SCIENTIFIC["n_boot"]
    assert ep["bootstrap"]["seed"] == FROZEN_SCIENTIFIC["seed"]
    assert ep["holm_family"]["size"] == FROZEN_SCIENTIFIC["holm_family_size"]
    ra = freeze["row_accounting"]["dev_scored_expectation"]
    assert ra["n_rows"] == FROZEN_SCIENTIFIC["n_dev_rows"]
    assert ra["n_slate_dates"] == FROZEN_SCIENTIFIC["n_slate_dates"]
    assert (freeze["row_accounting"]["flagged_recenter_records"]["count"]
            == FROZEN_SCIENTIFIC["flagged"])
    assert freeze["output"]["location"] == FROZEN_SCIENTIFIC["output_location"]
    assert freeze["output"]["write_once"] is True
    assert freeze["fail_closed_rules"]


def test_amendment_section_hash_is_stable():
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    am = freeze["execution_amendment_v1"]
    assert _canonical_sha256(am) == (
        "b760a1a88b5fc2a41ba43eed9b0e979abbfcd30596655ecb5f42cba5aec7b2ae")
