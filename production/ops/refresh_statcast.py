"""Incremental Statcast YTD refresh for production.

Reuses the on-disk season parquet and only downloads calendar days after the
cached max through yesterday (America/New_York). Full re-download is still
available via ``Python.statcast.download_statcast_season`` for repairs.

Examples:
    python production/ops/refresh_statcast.py
    python production/ops/refresh_statcast.py --year 2026 --refresh-trailing-days 1
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help=(
            "Attempts for the Statcast fetch (default 1). The 8:30am scheduled "
            "run fires right after wake-from-sleep when the network is often "
            "not ready yet; --retries 3 with --retry-wait-s 60 rides that out "
            "instead of killing the whole morning workflow in step 1a."
        ),
    )
    parser.add_argument(
        "--retry-wait-s",
        type=int,
        default=60,
        help="Seconds to wait between fetch attempts.",
    )
    args = parser.parse_args()

    last_err: Exception | None = None
    for attempt in range(max(1, int(args.retries))):
        try:
            report = update_statcast_season(
                args.year,
                end_dt=args.end_dt or yesterday_et(),
                refresh_trailing_days=args.refresh_trailing_days,
                verbose=not args.quiet,
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"refresh_statcast attempt {attempt + 1} failed: {exc}", flush=True)
            if attempt + 1 < max(1, int(args.retries)):
                import time

                time.sleep(max(0, int(args.retry_wait_s)))
    else:
        raise SystemExit(f"refresh_statcast failed after {args.retries} attempts: {last_err}")
    print(json.dumps(report, indent=2))
    if report.get("skipped_fetch"):
        print("Cache already current through pull_end - no Statcast fetch.")


if __name__ == "__main__":
    main()
