"""Unit tests for frozen_edge_watch catch-up + mute helpers."""

import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "frozen_edge_watch",
        ROOT / "production" / "ops" / "frozen_edge_watch.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["frozen_edge_watch"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_mod()


def _write(tmp_path: Path, rec: dict) -> Path:
    p = tmp_path / "morning_alert_latest.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    return p


def test_board_posted_today_success(tmp_path: Path) -> None:
    p = _write(tmp_path, {"sent_utc": "2026-09-16T12:01:32Z",
                          "message": "9/16/26 MLB Props - Daily Recs K.\n..."})
    assert _mod._morning_board_posted_today("2026-09-16", p) is True


def test_board_not_posted_failure_banner(tmp_path: Path) -> None:
    p = _write(tmp_path, {"sent_utc": "2026-09-16T12:01:32Z",
                          "message": "AUTOMATION FAILURE\nstatcast FAILED"})
    assert _mod._morning_board_posted_today("2026-09-16", p) is False


def test_board_not_posted_stale_date(tmp_path: Path) -> None:
    p = _write(tmp_path, {"sent_utc": "2026-09-14T12:01:32Z",
                          "message": "9/14/26 MLB Props - Daily Recs K.\n..."})
    assert _mod._morning_board_posted_today("2026-09-15", p) is False


def test_board_not_posted_missing_file(tmp_path: Path) -> None:
    assert _mod._morning_board_posted_today(
        "2026-09-15", tmp_path / "nope.json") is False


def test_alerts_muted_env(monkeypatch) -> None:
    monkeypatch.setenv("MLB_PROPS_NO_ALERT", "1")
    assert _mod._alerts_muted() is True
    monkeypatch.delenv("MLB_PROPS_NO_ALERT")
    assert _mod._alerts_muted() is False
