"""Close-sweep: fill CLV closes on today's open tickets (container-safe).

Replaces the 8-hour idle watcher daemon for cloud/cron use: each run fetches
latest SharpAPI quotes for tickets still needing a close and exits. Run
q5min inside game windows (12:00-22:12 ET); outside windows it no-ops.
Per-ticket urgency gate (owner 2026-09-21): runs with no ticket tipping
within 45 min (or started in the last 15) exit before any API call, so a
flat q5m cron behaves like game-anchored bursts without spamming the vendor.
Idempotent by construction (fill_closes skips filled rows); best-effort
(exit 0 with a report, nonzero only on crash).

Usage:
  python production/ops/run_close_sweep.py [--dry-run]
         [--urgency-min 45] [--live-after-min 15]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
ET = ZoneInfo("America/New_York")
WINDOW_START_H = 12
WINDOW_END_H = 22.2  # last first-pitch ~22:07 ET
URGENCY_MIN = 45  # fetch when any open ticket tips within 45 min
LIVE_AFTER_MIN = 15  # or started within the last 15 min (live-fallback)


def should_fetch(ledger, *, slate: str, now: datetime,
                 urgency_min: float = URGENCY_MIN,
                 live_after_min: float = LIVE_AFTER_MIN) -> tuple[bool, str]:
    """Per-ticket urgency gate: fetch only when a close is actually near.

    Pure (testable). No open tickets, or every tip farther than the urgency
    window (and none recently started), means a quiet exit with zero API
    calls. Unknown/missing tip times fail OPEN — never skip on uncertainty.
    """
    from Python.odds_close import open_needing_close, row_minutes_to_tip

    need = open_needing_close(ledger, slate=slate)
    if need.is_empty():
        return False, "no open tickets needing close"
    seen_tip = False
    nearest: float | None = None
    for row in need.to_dicts():
        minutes = row_minutes_to_tip(row, as_of=now)
        if minutes is None:
            return True, "unknown tip time — fail open, fetching"
        seen_tip = True
        if nearest is None or minutes < nearest:
            nearest = minutes
        if minutes <= urgency_min and minutes >= -live_after_min:
            return True, f"ticket {minutes:.0f}m to tip — fetching"
    if not seen_tip:
        return True, "no parseable tips — fail open, fetching"
    return False, f"nearest tip {nearest:.0f}m out — quiet (no API calls)"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--urgency-min", type=float, default=URGENCY_MIN)
    ap.add_argument("--live-after-min", type=float, default=LIVE_AFTER_MIN)
    args = ap.parse_args()
    now_et = datetime.now(timezone.utc).astimezone(ET)
    hour = now_et.hour + now_et.minute / 60.0
    if not (WINDOW_START_H <= hour <= WINDOW_END_H):
        print(f"close-sweep no-op outside game windows (ET {now_et:%H:%M})")
        return
    from Python.odds_ledger import load_ledger

    slate = now_et.date().isoformat()
    fetch, why = should_fetch(
        load_ledger(), slate=slate, now=now_et,
        urgency_min=args.urgency_min, live_after_min=args.live_after_min)
    print(f"close-sweep urgency: {why}")
    if not fetch:
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
