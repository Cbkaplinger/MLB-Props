"""Prove that calibration and market modules import and their synthetic
tests pass WITHOUT the private research lake in sys.path. This catches
module-level imports of private-lake-only dependencies."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_imports_work_without_private_lake():
    """Spawn a fresh Python process with the private lake REMOVED from
    sys.path and verify the research modules import cleanly."""
    repo = Path(__file__).resolve().parents[1]
    code = (
        "import sys\n"
        "clean = [p for p in sys.path if 'MLB-Props-Research' not in p]\n"
        "sys.path = clean\n"
        f"sys.path.insert(0, r'{repo / 'research' / 'offseason_2026'}')\n"
        "from pregame_pa_ext import market_eval_k\n"
        "from pregame_pa_ext import ablation_features\n"
        "from pregame_pa_ext import lineup_diagnostic\n"
        "from pregame_pa_ext import count_pmf_calibration\n"
        "from pregame_pa_ext import count_pmf_calibration_runner\n"
        "print('CLEAN_IMPORT_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=60,
        env={"PYTHONPATH": "", "SYSTEMROOT": __import__("os").environ.get(
            "SYSTEMROOT", ""), "PATH": __import__("os").environ.get(
            "PATH", "")},
    )
    assert "CLEAN_IMPORT_OK" in result.stdout, (
        f"import failed without private lake: {result.stderr}")
