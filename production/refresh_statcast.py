"""Incremental Statcast YTD refresh for production.

Reuses the on-disk season parquet and only downloads calendar days after the
cached max through yesterday (America/New_York). Full re-download is still
available via ``Python.statcast.download_statcast_season`` for repairs.

Examples:
    python production/refresh_statcast.py
    python production/refresh_statcast.py --year 2026 --refresh-trailing-days 1
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402
from Python.statcast import update_statcast_season, yesterday_et  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--year",
        type=int,
        default=config.PROJECTION_SEASON,
        help=f"Season to refresh (default: {config.PROJECTION_SEASON}).",
    )
    parser.add_argument(
        "--end-dt",
        type=date.fromisoformat,
        default=None,
        help="Inclusive pull end (YYYY-MM-DD). Default: yesterday ET.",
    )
    parser.add_argument(
        "--refresh-trailing-days",
        type=int,
        default=0,
        help="Also re-fetch the last N cached days (late Savant corrections).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress pybaseball progress bars.",
    )
    args = parser.parse_args()

    report = update_statcast_season(
        args.year,
        end_dt=args.end_dt or yesterday_et(),
        refresh_trailing_days=args.refresh_trailing_days,
        verbose=not args.quiet,
    )
    print(json.dumps(report, indent=2))
    if report.get("skipped_fetch"):
        print("Cache already current through pull_end - no Statcast fetch.")


if __name__ == "__main__":
    main()
