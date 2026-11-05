"""Unit tests for the automation self-check task-health rules."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "build_automation_self_check",
        ROOT / "production" / "ops" / "build_automation_self_check.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_automation_self_check"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_mod()


def test_cloud_scheduler_row_is_healthy() -> None:
    row = {"task": "MLBProps_MorningWorkflow", "found": "cloud-scheduler"}
    assert _mod._is_task_healthy(row) is True


def test_missing_task_is_unhealthy() -> None:
    assert _mod._is_task_healthy({"task": "X", "found": "no"}) is False


def test_failed_last_result_is_unhealthy() -> None:
    row = {"task": "X", "found": "yes", "status": "Ready", "last_result": "1"}
    assert _mod._is_task_healthy(row) is False


def test_ready_zero_is_healthy() -> None:
    row = {"task": "X", "found": "yes", "status": "Ready", "last_result": "0"}
    assert _mod._is_task_healthy(row) is True


def test_disabled_task_is_unhealthy() -> None:
    row = {"task": "X", "found": "yes", "status": "Disabled", "last_result": "0"}
    assert _mod._is_task_healthy(row) is False
