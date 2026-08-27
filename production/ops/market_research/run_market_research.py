"""Orchestrate open-market research artifact builds in dependency order."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

STEPS = [
    ("backfill overlap", "production/ops/backfill_open_projection_overlap.py"),
    ("open projection signal", "production/ops/build_open_projection_signal.py"),
    ("calibration suite", "production/ops/build_open_projection_calibration_suite.py"),
    ("book scorecard", "production/ops/build_book_quality_scorecard.py"),
    (
        "line price gap (DK/FD baseline)",
        "production/ops/build_line_price_calibration_gap.py --baseline-books draftkings,fanduel",
    ),
    ("line price correction table", "production/ops/build_line_price_correction_table.py"),
    ("open model deltas", "production/ops/market_research/analyze_open_model_deltas.py"),
    ("apply calibration policy", "production/ops/market_research/apply_calibration_policy.py"),
    ("probability scoring report", "production/ops/market_research/build_prob_scoring_report.py"),
    ("calibration deploy matrix", "production/ops/market_research/build_calibration_deploy_matrix.py"),
    ("clv basis reconcile", "production/ops/market_research/clv_basis_reconcile.py"),
    ("line policy settled lookback", "production/ops/market_research/line_policy_settled_lookback.py"),
]


def main() -> None:
    for label, cmd in STEPS:
        print(f"--- {label} ---")
        full = [str(PYTHON), *cmd.split(" ")]
        proc = subprocess.run(full, cwd=str(ROOT))
        if proc.returncode != 0:
            print(f"FAILED: {label}", file=sys.stderr)
            raise SystemExit(proc.returncode)
    print("market research pipeline complete")


if __name__ == "__main__":
    main()
