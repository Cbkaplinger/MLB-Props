"""Workspace boundary test (audit §AF). Static: never imports prod modules."""

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "offseason_2026"))

from boundary import (
    ALLOWED_WRITE_ROOTS,
    FORBIDDEN_MODULES,
    WORKSPACE_ROOT,
    BoundaryError,
    assert_not_forbidden,
    assert_workspace_path,
)

CANONICAL_COPIES = {
    "market.py",
    "count_layer.py",
    "prob_calibration.py",
    "live_assembly.py",
    "odds_ledger.py",
    "odds_board.py",
    "modal_app.py",
    "statcast.py",
}


def _workspace_py_files():
    return [p for p in WORKSPACE_ROOT.rglob("*.py") if p.name != "boundary.py"]


def test_forbidden_list_covers_writers_pagers_scheduler():
    for mod in [
        "poll_odds",
        "grade_odds_ledger",
        "grade_projections",
        "log_projections",
        "send_morning_alert",
        "check_nightly_drift",
        "modal_app",
    ]:
        assert mod in FORBIDDEN_MODULES, mod


def test_workspace_writes_confined():
    ok = WORKSPACE_ROOT / "datasets" / "pa_funnel_manifest.json"
    assert assert_workspace_path(ok) == ok.resolve()
    assert assert_workspace_path("research/offseason_2026/reports/x.json").parent.name == "reports"


def test_outside_writes_refused():
    for bad in [
        "data/processed/x.parquet",
        "artifacts/odds_log/ledger.parquet",
        "artifacts/live_scores/x.parquet",
        "production/ops/x.json",
        "models/Strikeout-Model/x.txt",
        "src/Python/x.py",
        "docs/x.md",
    ]:
        try:
            assert_workspace_path(bad)
        except BoundaryError:
            continue
        raise AssertionError(f"write allowed outside roots: {bad}")


def test_forbidden_import_refused():
    for mod in sorted(FORBIDDEN_MODULES):
        try:
            assert_not_forbidden(mod)
        except BoundaryError:
            continue
        raise AssertionError(f"import allowed for forbidden module: {mod}")


def test_no_forbidden_imports_in_workspace_code():
    violations = []
    for path in _workspace_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            else:
                continue
            for m in mods:
                base = m.split(".")[0]
                if base in FORBIDDEN_MODULES:
                    violations.append(f"{path.name}:{node.lineno} imports {m}")
    assert violations == [], violations


def test_no_canonical_copies():
    copies = [p.name for p in WORKSPACE_ROOT.rglob("*.py") if p.name in CANONICAL_COPIES]
    assert copies == [], copies


def test_write_roots_exist():
    # Write roots are created by experiment runs, not tracked in Git:
    # a clean checkout legitimately lacks them, so skip (never weaken
    # the assertion itself, which still runs wherever roots exist).
    missing = [root for root in ALLOWED_WRITE_ROOTS if not root.is_dir()]
    if missing:
        pytest.skip(f"workspace write roots absent (CI-safe skip): {missing}")
    for root in ALLOWED_WRITE_ROOTS:
        assert root.is_dir(), root
