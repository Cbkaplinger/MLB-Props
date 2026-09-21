"""OPS-1A: DST-safe Modal schedules (owner 2026-09-17).

Every wall-clock job runs on explicit America/New_York with a LOCAL cron
expression (not UTC + attached timezone). Tests parse modal_app.py by AST so
they hold with or without the modal package installed.
"""

from __future__ import annotations

import ast
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODAL_APP = ROOT / "production" / "cloud" / "modal_app.py"
REGISTRY = ROOT / "docs" / "reference" / "pipeline_registry.json"
NY = ZoneInfo("America/New_York")

# Function -> (local cron, IANA timezone). Local wall-clock times match the
# pre-change summer behavior documented in production/cloud/README.md.
EXPECTED = {
    "morning_workflow": ("0 8 * * *", "America/New_York"),
    "hourly_refresh": ("0 9-22 * * *", "America/New_York"),
    "close_sweep": ("*/20 12-22 * * *", "America/New_York"),
    "end_of_day_settle": ("0 3 * * *", "America/New_York"),
    "nightly_drift": ("30 5 * * *", "America/New_York"),
}

# Pre-change summer (EDT) local times from README timing table + code
# comments. Post-change local times must match exactly (no behavior change).
PRE_SUMMER_LOCAL = {
    "morning_workflow": [(8, 0)],
    "hourly_refresh": [(h, 0) for h in range(9, 23)],
    "close_sweep": [(h, m) for h in range(12, 23) for m in (0, 20, 40)],
    "end_of_day_settle": [(3, 0)],
    "nightly_drift": [(5, 30)],
}


def _expand_field(field: str, lo: int, hi: int) -> list[int]:
    """Minimal cron field expander (*, ranges, steps, lists)."""
    out: list[int] = []
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
        if part == "*":
            out.extend(range(lo, hi + 1, step))
        elif "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1, step))
        else:
            out.append(int(part))
    return sorted(set(out))


def _cron_times_today(expr: str) -> list[tuple[int, int]]:
    minute, hour, *_ = expr.split()
    return [(h, m) for h in _expand_field(hour, 0, 23)
            for m in _expand_field(minute, 0, 59)]


def _app_schedules() -> dict[str, tuple[str, str | None]]:
    """{function: (cron_expr, timezone-or-None)} parsed from modal_app.py AST."""
    tree = ast.parse(MODAL_APP.read_text(encoding="utf-8"))
    assigns = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Constant):
                assigns[node.targets[0].id] = node.value.value
    found: dict[str, tuple[str, str | None]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            # Schedules hide inside @app.function(..., schedule=modal.Cron(...)).
            for kw in dec.keywords:
                if kw.arg != "schedule" or not isinstance(kw.value, ast.Call):
                    continue
                callee = kw.value.func
                if not (isinstance(callee, ast.Attribute) and callee.attr == "Cron"):
                    continue
                cron_arg = kw.value.args[0]
                expr = cron_arg.value if isinstance(cron_arg, ast.Constant) \
                    else assigns.get(cron_arg.id)
                tz = None
                for ck in kw.value.keywords:
                    if ck.arg == "timezone":
                        tz = ck.value.value if isinstance(ck.value, ast.Constant) \
                            else assigns.get(ck.value.id)
                found[node.name] = (expr, tz)
    return found


def _transitions_2026() -> tuple[date, date]:
    """Spring-forward and fall-back dates from the tz database (not hardcoded)."""
    def offset(d: date) -> timedelta:
        return datetime(d.year, d.month, d.day, 12, tzinfo=NY).utcoffset()

    spring = fall = None
    prev = offset(date(2026, 1, 1))
    day = date(2026, 1, 2)
    while day.year == 2026 and (spring is None or fall is None):
        cur = offset(day)
        if cur != prev:
            if cur > prev:
                spring = day
            else:
                fall = day
            prev = cur
        day += timedelta(days=1)
    assert spring is not None and fall is not None
    return spring, fall


def test_all_five_schedules_exact() -> None:
    found = _app_schedules()
    assert set(found) == set(EXPECTED), f"schedule set changed: {sorted(found)}"
    for func, (expr, tz) in EXPECTED.items():
        assert found[func] == (expr, tz), f"{func}: {found[func]}"


def test_no_implicit_utc_nor_period() -> None:
    src = MODAL_APP.read_text(encoding="utf-8")
    assert "modal.Period" not in src
    for func, (_, tz) in _app_schedules().items():
        assert tz, f"{func} has no explicit timezone"
        ZoneInfo(tz)


def test_registry_matches_code() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    rows = {r["job"]: r for r in registry["schedules"]
            if r["job"].startswith("Modal ")}
    assert len(rows) == 5
    suffix = {
        "Modal morning_workflow": "morning_workflow",
        "Modal hourly_refresh": "hourly_refresh",
        "Modal close_sweep": "close_sweep",
        "Modal end_of_day_settle": "end_of_day_settle",
        "Modal nightly_drift": "nightly_drift",
    }
    for job, func in suffix.items():
        expr, tz = EXPECTED[func]
        assert rows[job]["cron"] == expr, job
        assert rows[job]["tz"].startswith(tz), job


def test_summer_local_times_unchanged() -> None:
    """No-behavior-change: post-change local times equal documented EDT times."""
    for func, (expr, _) in EXPECTED.items():
        assert _cron_times_today(expr) == PRE_SUMMER_LOCAL[func], func


def _dst_matrix_dates() -> list[date]:
    spring, fall = _transitions_2026()
    return [date(2026, 1, 15), date(2026, 7, 15),
            spring - timedelta(days=1), spring, spring + timedelta(days=1),
            fall - timedelta(days=1), fall, fall + timedelta(days=1)]


def test_dst_wall_clock_stable() -> None:
    """Local H:M constant on all 8 probe days; UTC shifts across the boundary."""
    for day in _dst_matrix_dates():
        summer = datetime(day.year, day.month, day.day, 12, tzinfo=NY).utcoffset() \
            == timedelta(hours=-4)
        for func, (expr, _) in EXPECTED.items():
            runs = _cron_times_today(expr)
            assert runs, f"{func} has no runs on {day}"
            for h, m in runs:
                local = datetime(day.year, day.month, day.day, h, m, tzinfo=NY)
                assert (local.hour, local.minute) == (h, m)
                expect = timedelta(hours=-4 if summer else -5)
                assert local.utcoffset() == expect, f"{func} {day} {h:02d}:{m:02d}"
                utc = local.astimezone(timezone.utc)
                assert utc.utcoffset() == timedelta(0)


def test_once_daily_jobs_fire_once() -> None:
    for day in _dst_matrix_dates():
        for func in ("morning_workflow", "end_of_day_settle", "nightly_drift"):
            assert len(_cron_times_today(EXPECTED[func][0])) == 1, f"{func} {day}"


def test_no_ambiguous_window_jobs() -> None:
    """No run inside 01:00-02:59 local (duplicated/skipped at transitions)."""
    for day in _dst_matrix_dates():
        for func, (expr, _) in EXPECTED.items():
            for h, m in _cron_times_today(expr):
                assert not (1 <= h < 3), f"{func} {day} {h:02d}:{m:02d}"


def test_chain_ordering_both_seasons() -> None:
    """settle < drift < morning < hourly holds in winter and summer."""
    for day in (date(2026, 1, 15), date(2026, 7, 15)):
        times = {f: _cron_times_today(EXPECTED[f][0]) for f in EXPECTED}
        assert max(times["end_of_day_settle"]) < min(times["nightly_drift"])
        assert max(times["nightly_drift"]) < min(times["morning_workflow"])
        assert max(times["morning_workflow"]) < min(times["hourly_refresh"])
        assert max(times["hourly_refresh"]) == (22, 0)
        sweeps = times["close_sweep"]
        assert min(sweeps) == (12, 0) and all((h, m) <= (22, 40) for h, m in sweeps)


def test_modal_sdk_supports_timezone() -> None:
    modal = pytest.importorskip("modal")
    import inspect

    assert "timezone" in inspect.signature(modal.Cron.__init__).parameters
    major, minor = (int(x) for x in str(modal.__version__).split(".")[:2])
    assert (major, minor) >= (1, 0), modal.__version__


def test_hourly_heals_before_scoring() -> None:
    """Heal-first (owner 2026-09-21): hourly repairs staleness before scoring.

    If this is removed, mid-afternoon stale slates ride through tagged
    instead of getting a repair attempt — the soft-quit the owner refused.
    """
    tree = ast.parse(MODAL_APP.read_text(encoding="utf-8"))
    hourly = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "hourly_refresh"
    )
    segment = ast.get_source_segment(MODAL_APP.read_text(encoding="utf-8"), hourly)
    assert segment is not None
    heal_at = segment.find("heal_stale_slate.py")
    log_at = segment.find("log_projections.py")
    assert heal_at != -1 and log_at != -1 and heal_at < log_at
