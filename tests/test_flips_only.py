"""Flips-only hourly alert gate (smoke fix #1, owner 2026-09-18).

The Modal hourly chain pages the full board every hour unless gated.
--flips-only restores the flips-only design: page on failure, unknown
watch state (fail-open), or non-empty flips — quiet otherwise.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "send_morning_alert",
        ROOT / "production" / "ops" / "send_morning_alert.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["send_morning_alert"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_mod()


def test_failure_always_pages() -> None:
    fire, _ = _mod._flips_fire({"flips": []}, failure_message="statcast boom")
    assert fire is True


def test_unknown_state_fails_open() -> None:
    fire, why = _mod._flips_fire(None)
    assert fire is True
    assert "fail-open" in why


def test_flips_page() -> None:
    fire, why = _mod._flips_fire({"flips": [{"a": 1}, {"b": 2}]})
    assert fire is True
    assert "2-flips" in why


def test_empty_flips_quiet() -> None:
    fire, why = _mod._flips_fire({"flips": [], "n": 26})
    assert fire is False
    assert "quiet" in why


def test_missing_report_is_unknown(tmp_path: Path) -> None:
    assert _mod._load_edge_watch_today(tmp_path / "nope.json") is None


def test_report_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "edge_watch_report_2026-09-18.json"
    path.write_text(json.dumps({"flips": [], "n": 26}), encoding="utf-8")
    state = _mod._load_edge_watch_today(path)
    assert state is not None and state["flips"] == []
    fire, _ = _mod._flips_fire(state)
    assert fire is False


def test_garbage_report_is_unknown(tmp_path: Path) -> None:
    path = tmp_path / "edge_watch_report_2026-09-18.json"
    path.write_text("not json{{", encoding="utf-8")
    assert _mod._load_edge_watch_today(path) is None


def test_newest_candidate_wins(monkeypatch, tmp_path: Path) -> None:
    # NOTE: discrimination needs et_day != utc_day (00:00-03:59 UTC window);
    # otherwise both candidates coincide and this only smoke-tests the read.
    import os
    import time

    from datetime import datetime, timezone

    monkeypatch.setattr(_mod, "ODDS_DIR", tmp_path)
    et_day = datetime.now(_mod.ET).date().isoformat()
    utc_day = datetime.now(timezone.utc).date().isoformat()
    old = tmp_path / f"edge_watch_report_{et_day}.json"
    new = tmp_path / f"edge_watch_report_{utc_day}.json"
    old.write_text(json.dumps({"flips": [], "n": 1}), encoding="utf-8")
    new.write_text(json.dumps({"flips": [{"x": 1}], "n": 1}), encoding="utf-8")
    # Force newest-first regardless of creation order granularity.
    now = time.time()
    os.utime(old, (now - 100, now - 100))
    os.utime(new, (now, now))
    state = _mod._load_edge_watch_today()
    assert state is not None
    fire, _ = _mod._flips_fire(state)
    if et_day == utc_day:
        # Same path: last write wins, which carries the flip.
        assert fire is True
    else:
        assert fire is True  # freshest report carries the flip
