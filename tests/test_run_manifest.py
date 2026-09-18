"""Unit tests for the shared run-manifest writer (OBS-1)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python.run_manifest import (  # noqa: E402
    NO_BET_REASONS,
    RUN_STATUSES,
    emit_manifest_safely,
    finish_run,
    manifest_from_alert,
    manifest_from_drift,
    manifest_path,
    new_run,
    notification_key,
    ticket_set_hash,
    write_manifest,
)


def test_schema_keys_present() -> None:
    out = finish_run(new_run("P4-SERVE", slate_date="2026-09-17"), "SUCCESS_FRESH")
    for key in ("run_id", "pipeline_id", "prop_id", "mode", "status",
                "started_at_utc", "finished_at_utc", "slate_date", "as_of_utc",
                "input_cutoff_utc", "model_version", "calibration_version",
                "policy_version", "feature_version", "input_artifacts",
                "output_artifacts", "input_rows", "output_rows",
                "population_funnel", "data_quality", "warnings", "errors",
                "duration_seconds", "notification_key", "no_bet_reason"):
        assert key in out, key
    assert out["duration_seconds"] is not None and out["duration_seconds"] >= 0


def test_bad_status_and_reason_rejected() -> None:
    with pytest.raises(ValueError):
        finish_run(new_run("P4-SERVE"), "GREEN")
    with pytest.raises(ValueError):
        finish_run(new_run("P4-SERVE"), "SUCCESS_NO_BETS", no_bet_reason="BOGUS")
    with pytest.raises(ValueError):
        finish_run(new_run("P4-SERVE"), "SUCCESS_FRESH", no_bet_reason="BELOW_FLOOR")
    out = finish_run(new_run("P4-SERVE"), "SUCCESS_NO_BETS", no_bet_reason="BELOW_FLOOR")
    assert out["no_bet_reason"] == "BELOW_FLOOR"
    assert set(NO_BET_REASONS) >= {"BELOW_FLOOR", "VETOED", "STALE_QUOTES"}
    assert set(RUN_STATUSES) >= {"SUCCESS_FRESH", "FAILED", "SKIPPED_OFFSEASON"}


def test_notification_key_deterministic_and_sensitive() -> None:
    base = dict(slate_date="2026-09-17", prop_id="pitcher_strikeouts",
                policy_version="champion", model_version="frozen",
                calibration_version="ws1c", selection_window="morning")
    h1 = ticket_set_hash(["b", "a", "c"])
    h2 = ticket_set_hash(["a", "b", "c"])
    assert h1 == h2  # order-invariant
    k1 = notification_key(ticket_hash=h1, **base)
    k2 = notification_key(ticket_hash=h1, **base)
    assert k1 == k2
    k3 = notification_key(ticket_hash=ticket_set_hash(["a", "b"]), **base)
    assert k3 != k1  # any ticket difference flips the key


def test_write_round_trip_and_safe_emit(tmp_path: Path) -> None:
    out = finish_run(new_run("P6-SETTLE"), "SUCCESS_FRESH",
                     output_rows={"ledger": 10})
    path = write_manifest(out, tmp_path / "m.json")
    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == out["run_id"]
    assert manifest_path(tmp_path, "P4-SERVE").name == "run_manifest_p4_serve_latest.json"
    # A bad destination never raises — jobs must not die on provenance.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    assert emit_manifest_safely(out, blocker / "m.json") is False


def test_alert_and_drift_mappings() -> None:
    failed = manifest_from_alert(any_sent=False, failure_message="statcast boom")
    assert failed["status"] == "FAILED" and failed["errors"] == ["statcast boom"]
    sent = manifest_from_alert(any_sent=True)
    assert sent["status"] == "SUCCESS_FRESH"
    silent = manifest_from_alert(any_sent=False)
    assert silent["status"] == "DEGRADED_NO_PAGE" and silent["warnings"]
    assert manifest_from_drift(verdict="GREEN", today="2026-09-17")["status"] == "SUCCESS_FRESH"
    yellow = manifest_from_drift(verdict="YELLOW", today="2026-09-17",
                                 failing_checks=["settle_freshness"])
    assert yellow["status"] == "DEGRADED_NO_PAGE"
    assert yellow["warnings"] == ["settle_freshness"]
    red = manifest_from_drift(verdict="RED", today="2026-09-17",
                              failing_checks=["veto_leak"])
    assert red["status"] == "FAILED" and red["errors"] == ["veto_leak"]
