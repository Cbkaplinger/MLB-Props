"""Check required artifacts before notebook review.

Usage:
    python scripts/check_notebook_artifacts.py
"""

from __future__ import annotations

from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]

REQUIRED = {
    "projection_log": ROOT / "artifacts" / "projection_log" / "projections.parquet",
    "projection_grades": ROOT / "artifacts" / "projection_log" / "graded.parquet",
    "odds_ledger": ROOT / "artifacts" / "odds_log" / "ledger.parquet",
}

OPTIONAL = {
    "k_error_decomposition": ROOT / "artifacts" / "odds_log" / "k_error_decomposition.parquet",
    "k_error_decomposition_daily": ROOT / "artifacts" / "odds_log" / "k_error_decomposition_daily.parquet",
    "model_health_scorecard_daily": ROOT / "artifacts" / "odds_log" / "model_health_scorecard_daily.parquet",
    "clv_reliability": ROOT / "artifacts" / "odds_log" / "clv_reliability.parquet",
}


def _fmt(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    stat = path.stat()
    return f"ok ({stat.st_size} bytes)"


def main() -> int:
    print("== Required artifacts ==")
    missing = 0
    for name, path in REQUIRED.items():
        status = _fmt(path)
        print(f"- {name:28} {status}  {path}")
        if status == "MISSING":
            missing += 1

    print("\n== Optional diagnostics artifacts ==")
    for name, path in OPTIONAL.items():
        print(f"- {name:28} {_fmt(path)}  {path}")

    summary = {
        "missing_required": missing,
        "required_total": len(REQUIRED),
    }
    print("\nSummary:")
    print(json.dumps(summary, indent=2))
    if missing:
        print("\nAction: run production refresh/log/grade flow before notebook review.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
