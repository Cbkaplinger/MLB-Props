"""Close-sweep: fill CLV closes on today's open tickets (container-safe).

Replaces the 8-hour idle watcher daemon for cloud/cron use: each run fetches
latest SharpAPI quotes for tickets still needing a close and exits. Run
q15-20min inside game windows (13:00-23:30 ET); outside windows it no-ops.
Idempotent by construction (fill_closes skips filled rows); best-effort
(exit 0 with a report, nonzero only on crash).

Usage:
  python production/ops/run_close_sweep.py [--dry-run]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
ET = ZoneInfo("America/New_York")
WINDOW_START_H = 13
WINDOW_END_H = 23.5


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    now_et = datetime.now(timezone.utc).astimezone(ET)
    hour = now_et.hour + now_et.minute / 60.0
    if not (WINDOW_START_H <= hour <= WINDOW_END_H):
        print(f"close-sweep no-op outside game windows (ET {now_et:%H:%M})")
        return
    cmd = [sys.executable, "-u", "production/odds/poll_odds.py",
           "--snapshot", "close"]
    if args.dry_run:
        cmd.append("--dry-run")
    print(f"close-sweep firing inside window (ET {now_et:%H:%M})")
    proc = subprocess.run(cmd, cwd=REPO)
    if proc.returncode != 0:
        raise SystemExit(f"close-sweep poll exited {proc.returncode}")


if __name__ == "__main__":
    main()
