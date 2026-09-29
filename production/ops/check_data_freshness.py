"""Data freshness flags + refresh-on-stale (never-again guard for Sep-2026 gaps).

Read-only by default: checks Savant max, L1/L2/L3 max dates, and lockstep
spread between them. Fails LOUD (exit 2 on RED) but never mutates data.
With --refresh, runs refresh_statcast + full refresh_features (L1-L3 lockstep)
when stale, then re-checks. No policy/model/schedule changes.

Season rule: Apr-Sep expects data through ~yesterday ET; Oct-Mar expects the
last completed season (max on/after Sep 20 of that year).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

GREEN, YELLOW, RED = "GREEN", "YELLOW", "RED"

SAVANT_2026 = ROOT / "data/Savant-Data/regular/2026/statcast_2026_regular.parquet"
L1 = ROOT / "data/processed/pitcher_games.parquet"
L2 = ROOT / "data/processed/pitcher_rolling.parquet"
L3 = ROOT / "data/processed/pitcher_training.parquet"


def classify_lag(lag_days: int, in_season: bool) -> str:
    """Pure: lag status. In-season tolerates 2d (last night's finals)."""
    if lag_days <= (2 if in_season else 400):
        return GREEN
    if in_season and lag_days <= 5:
        return YELLOW
    return RED


def in_season(today: dt.date) -> bool:
    return dt.date(today.year, 4, 1) <= today <= dt.date(today.year, 10, 5)


def season_end_ok(max_date: dt.date) -> str:
    """Offseason: max must be a completed season end (Sep 20+ of some year)."""
    if max_date.month == 9 and max_date.day >= 20:
        return GREEN
    if max_date.month in (8, 10):
        return YELLOW
    return RED


def max_game_date(path: Path) -> dt.date | None:
    import polars as pl

    if not path.exists():
        return None
    val = pl.scan_parquet(path).select(pl.col("game_date").max()).collect().item()
    if val is None:
        return None
    return val.date() if isinstance(val, dt.datetime) else val


def check(today: dt.date | None = None) -> dict:
    import polars as _  # noqa: F401 (ensures dep present before IO)

    today = today or dt.date.today()
    season = in_season(today)
    ref = (today - dt.timedelta(days=1)) if season else None
    files = {"savant_2026": SAVANT_2026, "L1_pitcher_games": L1,
             "L2_pitcher_rolling": L2, "L3_pitcher_training": L3}
    maxima = {name: max_game_date(p) for name, p in files.items()}
    missing = sorted(n for n, v in maxima.items() if v is None)
    statuses: dict[str, str] = {}
    for name, mx in maxima.items():
        if mx is None:
            statuses[name] = RED
        elif season and ref is not None:
            statuses[name] = classify_lag((ref - mx).days, True)
        else:
            statuses[name] = season_end_ok(mx)
    present = [v for v in maxima.values() if v is not None]
    spread = (max(present) - min(present)).days if present else None
    lockstep = GREEN if spread is not None and spread <= 1 else RED
    overall = RED if (RED in statuses.values() or lockstep == RED or missing) else (
        YELLOW if YELLOW in statuses.values() else GREEN)
    return {
        "today": today.isoformat(), "in_season": season,
        "maxima": {n: (v.isoformat() if v else None) for n, v in maxima.items()},
        "statuses": statuses, "missing": missing,
        "lockstep_spread_days": spread, "lockstep": lockstep,
        "verdict": overall,
    }


def run_refresh(year: int) -> None:
    for cmd in (
        [sys.executable, "production/ops/refresh_statcast.py", "--year", str(year),
         "--retries", "3", "--retry-wait-s", "60"],
        [sys.executable, "production/ops/refresh_features.py"],
    ):
        print(f"FRESHNESS-REFRESH: running {' '.join(cmd[1:])}", flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true",
                        help="Run refresh_statcast + full refresh_features when stale, then re-check.")
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()

    result = check()
    print(json.dumps(result, indent=2))
    if args.refresh and result["verdict"] in (YELLOW, RED):
        run_refresh(args.year)
        result = check()
        print(json.dumps(result, indent=2))
    return 0 if result["verdict"] == GREEN else (1 if result["verdict"] == YELLOW else 2)


if __name__ == "__main__":
    raise SystemExit(main())
