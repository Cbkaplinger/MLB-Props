"""Tests for the nightly drift check thresholds (pure logic, no parquet)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

OPS = Path(__file__).resolve().parents[1] / "production" / "ops"
_spec = importlib.util.spec_from_file_location(
    "check_nightly_drift", OPS / "check_nightly_drift.py")
assert _spec is not None and _spec.loader is not None
drift = importlib.util.module_from_spec(_spec)
sys.modules["check_nightly_drift"] = drift
_spec.loader.exec_module(drift)


def test_freshness_verdict_bands() -> None:
    assert drift.freshness_verdict(0) == "GREEN"
    assert drift.freshness_verdict(2) == "GREEN"
    assert drift.freshness_verdict(3) == "YELLOW"
    assert drift.freshness_verdict(4) == "YELLOW"
    assert drift.freshness_verdict(5) == "RED"
    assert drift.freshness_verdict(None) == "RED"


def test_wr_drift_needs_n_and_drop() -> None:
    # Thin-n can never page, even with a bad rate.
    assert drift.wr_drift_verdict(0.30, 5, 0.53) == "YELLOW"
    # Small wobble on real n stays green.
    assert drift.wr_drift_verdict(0.50, 60, 0.53) == "GREEN"
    # A real 8pp+ drop warns.
    assert drift.wr_drift_verdict(0.40, 60, 0.53) == "YELLOW"


def test_mae_drift_bands() -> None:
    assert drift.mae_drift_verdict(1.75, 1.76, 0.10, 0.11, 200) == "GREEN"
    # Thin-n files quietly, never greens/reds.
    assert drift.mae_drift_verdict(2.50, 1.76, 0.90, 0.11, 10) == "YELLOW"
    # +0.2 MAE warns; +0.4 pages.
    assert drift.mae_drift_verdict(1.96, 1.76, 0.10, 0.11, 200) == "YELLOW"
    assert drift.mae_drift_verdict(2.20, 1.76, 0.10, 0.11, 200) == "RED"
    # 0.3 bias shift warns; 0.6 pages.
    assert drift.mae_drift_verdict(1.76, 1.76, 0.40, 0.11, 200) == "YELLOW"
    assert drift.mae_drift_verdict(1.76, 1.76, 0.80, 0.11, 200) == "RED"


def test_null_ratio_two_x_rule() -> None:
    assert drift.null_ratio_verdict(0.01, 0.01) == "GREEN"
    assert drift.null_ratio_verdict(0.021, 0.01) == "YELLOW"
    # Zero baseline with fresh nulls cannot prove a ratio — file, don't green.
    assert drift.null_ratio_verdict(0.05, 0.0) == "YELLOW"
    assert drift.null_ratio_verdict(0.0, 0.0) == "GREEN"


def test_worst_orders() -> None:
    assert drift.worst("GREEN", "GREEN") == "GREEN"
    assert drift.worst("GREEN", "YELLOW") == "YELLOW"
    assert drift.worst("YELLOW", "RED", "GREEN") == "RED"


def test_max_date_never_raises() -> None:
    import datetime
    assert drift._max_date(["2026-09-09", "2026-09-08"]) == datetime.date(2026, 9, 9)
    # Malformed entries are dropped, not fatal.
    assert drift._max_date(["garbage", "2026-09-08", None]) == datetime.date(2026, 9, 8)
    assert drift._max_date([]) is None
    assert drift._max_date(["garbage"]) is None


def _write_last_log(path, rolling_max=None):
    import json

    meta = {"rolling_max_date": rolling_max} if rolling_max else {}
    path.write_text(json.dumps({"build_meta": meta}), encoding="utf-8")


def test_serving_freshness_fresh(monkeypatch, tmp_path) -> None:
    import datetime

    log = tmp_path / "last_log.json"
    _write_last_log(log, "2026-09-17")
    monkeypatch.setattr(drift, "LAST_LOG", log)
    stale, note = drift.serving_freshness(datetime.date(2026, 9, 18))
    assert stale == 1
    assert "2026-09-17" in note


def test_serving_freshness_stale(monkeypatch, tmp_path) -> None:
    import datetime

    log = tmp_path / "last_log.json"
    _write_last_log(log, "2026-09-07")
    monkeypatch.setattr(drift, "LAST_LOG", log)
    stale, _ = drift.serving_freshness(datetime.date(2026, 9, 18))
    assert stale == 11
    assert drift.freshness_verdict(stale) == "RED"


def test_serving_freshness_missing_is_unknown(monkeypatch, tmp_path) -> None:
    import datetime

    monkeypatch.setattr(drift, "LAST_LOG", tmp_path / "absent.json")
    stale, note = drift.serving_freshness(datetime.date(2026, 9, 18))
    assert stale is None
    assert "no last_log" in note


def test_serving_freshness_garbage_is_unknown(monkeypatch, tmp_path) -> None:
    import datetime

    log = tmp_path / "last_log.json"
    log.write_text("{oops", encoding="utf-8")
    monkeypatch.setattr(drift, "LAST_LOG", log)
    stale, _ = drift.serving_freshness(datetime.date(2026, 9, 18))
    assert stale is None
