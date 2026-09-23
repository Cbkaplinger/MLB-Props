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


def test_l3_null_flag_not_rebuilt_is_green() -> None:
    # Live skips training: zero recent L3 rows is the healthy steady state,
    # not drift (owner 2026-09-23: this shape YELLOWed every morning).
    v, note = drift.l3_null_flag_verdict(0, None, 0.014)
    assert v == "GREEN"
    assert "not_rebuilt" in note
    # Thin-but-nonzero stays unjudgeable...
    v, _ = drift.l3_null_flag_verdict(5, None, 0.014)
    assert v == "YELLOW"
    # ...and real ratios keep the existing rule.
    v, _ = drift.l3_null_flag_verdict(60, 0.02, 0.014)
    assert v == "GREEN"


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


def test_page_red_quiet_without_red() -> None:
    ok, info = drift._page_red([{"name": "side_drift", "verdict": "GREEN"}])
    assert ok is True and info == "no red checks"


def _board(rows: list[dict]):
    import polars as pl
    return pl.DataFrame(rows, schema={"game_date": pl.String, "line": pl.Float64,
                                      "best_side": pl.String, "recommendation": pl.String})


def test_veto_leak_missing_file(tmp_path) -> None:
    import datetime
    out = drift.veto_leak_check(tmp_path / "nope.parquet", datetime.date(2026, 9, 17))
    assert out["verdict"] == "YELLOW"


def test_veto_leak_empty_board_never_raises(tmp_path) -> None:
    # Owner 2026-09-17: 0-row parquet crashed the chain (exit 3, no report).
    import datetime
    import polars as pl
    p = tmp_path / "rec.parquet"
    _board([]).write_parquet(p)
    out = drift.veto_leak_check(p, datetime.date(2026, 9, 17))
    assert out["verdict"] == "YELLOW" and out["note"] == "board empty"


def test_veto_leak_schemaless_parquet_never_raises(tmp_path) -> None:
    # Exact 2026-09-17 production crash: 0-col parquet raised
    # ColumnNotFoundError (valid columns: []) -> exit 3, no report.
    import datetime
    import polars as pl
    p = tmp_path / "blank.parquet"
    pl.DataFrame(schema={}).write_parquet(p)
    out = drift.veto_leak_check(p, datetime.date(2026, 9, 17))
    assert out["verdict"] == "YELLOW" and "unreadable" in out["note"]


def test_veto_leak_clean_and_leak(tmp_path) -> None:
    import datetime
    import polars as pl
    today = datetime.date(2026, 9, 17)
    p = tmp_path / "rec.parquet"
    _board([{"game_date": "2026-09-17", "line": 4.5, "best_side": "under",
             "recommendation": "BET"}]).write_parquet(p)
    out = drift.veto_leak_check(p, today)
    assert out["verdict"] == "GREEN" and out["n_leaked"] == 0
    _board([{"game_date": "2026-09-17", "line": 4.5, "best_side": "over",
             "recommendation": "BET"}]).write_parquet(p)
    out = drift.veto_leak_check(p, today)
    assert out["verdict"] == "RED" and out["n_leaked"] == 1


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


def _beat_line(job: str, ts: str, ok: bool = True) -> str:
    import json

    return json.dumps({"job": job, "utc": ts, "ok": ok, "note": "t"})


def test_heartbeat_counts_window(tmp_path) -> None:
    import datetime

    now = datetime.datetime(2026, 9, 18, 12, 0, tzinfo=datetime.timezone.utc)
    path = tmp_path / "hb.jsonl"
    path.write_text("\n".join([
        _beat_line("morning_workflow", "2026-09-18T11:59:00+00:00"),
        *[_beat_line("hourly_refresh", f"2026-09-18T{i:02d}:00:00+00:00")
          for i in range(12)],
        _beat_line("old_job", "2026-09-10T12:00:00+00:00"),
        "not json{{",
    ]), encoding="utf-8")
    counts, note = drift.heartbeat_beats(path, now=now)
    assert counts is not None
    assert counts.get("morning_workflow") == 1
    assert counts.get("hourly_refresh") == 12
    assert "old_job" not in counts  # outside the 24h window
    assert "13 beats" in note


def test_heartbeat_missing_is_unknown(tmp_path) -> None:
    import datetime

    counts, note = drift.heartbeat_beats(
        tmp_path / "absent.jsonl",
        now=datetime.datetime(2026, 9, 18, 12, 0, tzinfo=datetime.timezone.utc))
    assert counts is None
    assert "no heartbeat file" in note
