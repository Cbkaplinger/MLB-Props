"""Close-sweep: fill CLV closes on today's open tickets (container-safe).

Replaces the 8-hour idle watcher daemon for cloud/cron use: each run fetches
latest SharpAPI quotes for tickets still needing a close and exits. Run
q5min inside game windows (12:00-22:12 ET); outside windows it no-ops.
Per-ticket urgency gate (owner 2026-09-21): runs with no ticket tipping
within 45 min (or started in the last 5) exit before any API call, so a
flat q5m cron behaves like game-anchored bursts without spamming the vendor.
Idempotent by construction (fill_closes skips filled rows); best-effort
(exit 0 with a report, nonzero only on crash).

Usage:
  python production/ops/run_close_sweep.py [--dry-run]
         [--urgency-min 45] [--live-after-min 5]
         [--burst-within-min 6] [--burst-iters 8] [--burst-sleep-s 60] [--no-burst]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
ET = ZoneInfo("America/New_York")
WINDOW_START_H = 12
WINDOW_END_H = 22.2  # last first-pitch ~22:07 ET
URGENCY_MIN = 45  # fetch when any open ticket tips within 45 min
LIVE_AFTER_MIN = 5  # ... or started within the last 5 min, then stop.
# T+5 stop (owner 2026-09-21): no live betting means a pulled market is
# unfillable — chasing it burns vendor calls for nothing. Dated-but-delayed
# games share this cutoff (no delay feed exists); unknown tips still fail
# open, and paid consensus backfills measurement either way.
BURST_WITHIN_MIN = 6  # inside this many minutes to tip, scan every 60s
BURST_ITERS = 8  # hard cap on burst loops per invocation (~8 min max)
BURST_SLEEP_S = 60


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


def should_burst(minutes: list[float | None], *,
                 within_min: float = BURST_WITHIN_MIN,
                 live_after_min: float = LIVE_AFTER_MIN) -> bool:
    """One more 60s look? Pure (testable).

    True only when a KNOWN tip sits inside [live_after, within] — the
    minutes where books pull markets and a 5-minute grid is too coarse.
    Unknown clocks do NOT burst (the initial fetch already covered them;
    the next cron retries anyway). Bounded by the caller, never infinite.
    """
    known = [m for m in minutes if m is not None]
    if not known:
        return False
    return any(-live_after_min <= m <= within_min for m in known)


def _need_minutes(slate: str, now: datetime) -> list[float | None]:
    from Python.odds_close import open_needing_close, row_minutes_to_tip
    from Python.odds_ledger import load_ledger

    need = open_needing_close(load_ledger(), slate=slate)
    if need.is_empty():
        return []
    return [row_minutes_to_tip(r, as_of=now) for r in need.to_dicts()]


STATUS_NAME = "close_sweep_latest.json"


def write_status(path: Path | None, payload: dict) -> None:
    """Write the sweep-outcome sidecar (owner 2026-09-23).

    Lets the heartbeat note say what the run DID (quiet/fetch/burst) instead
    of only that it ran. Best-effort: never raises.
    """
    try:
        from Python.odds_ledger import LEDGER_PATH

        target = path or (LEDGER_PATH.parent / STATUS_NAME)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    except Exception:
        pass


def status_summary(payload: dict) -> str:
    """One-line heartbeat note fragment (capped, no newlines)."""
    mode = str(payload.get("mode") or "?")
    why = str(payload.get("why") or "")[:80].replace("\n", " ")
    burst = int(payload.get("burst_iters") or 0)
    extra = f" burst={burst}" if burst else ""
    return f"sweep:{mode}{extra} {why}"[:140]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--urgency-min", type=float, default=URGENCY_MIN)
    ap.add_argument("--live-after-min", type=float, default=LIVE_AFTER_MIN)
    ap.add_argument("--burst-within-min", type=float, default=BURST_WITHIN_MIN)
    ap.add_argument("--burst-iters", type=int, default=BURST_ITERS)
    ap.add_argument("--burst-sleep-s", type=float, default=BURST_SLEEP_S)
    ap.add_argument("--no-burst", action="store_true",
                    help="disable the 60s burst loop (single poll only)")
    args = ap.parse_args()
    now_et = datetime.now(timezone.utc).astimezone(ET)
    hour = now_et.hour + now_et.minute / 60.0
    run_utc = now_et.astimezone(timezone.utc).isoformat(timespec="seconds")
    if not (WINDOW_START_H <= hour <= WINDOW_END_H):
        print(f"close-sweep no-op outside game windows (ET {now_et:%H:%M})")
        write_status(None, {"utc": run_utc, "mode": "off_window",
                            "why": "outside 12-22 ET", "burst_iters": 0})
        return
    from Python.odds_ledger import load_ledger

    slate = now_et.date().isoformat()
    fetch, why = should_fetch(
        load_ledger(), slate=slate, now=now_et,
        urgency_min=args.urgency_min, live_after_min=args.live_after_min)
    print(f"close-sweep urgency: {why}")
    if not fetch:
        write_status(None, {"utc": run_utc, "mode": "quiet",
                            "why": why, "burst_iters": 0})
        return
    cmd = [sys.executable, "-u", "production/odds/poll_odds.py",
           "--snapshot", "close"]
    if args.dry_run:
        cmd.append("--dry-run")
    print(f"close-sweep firing inside window (ET {now_et:%H:%M})")
    proc = subprocess.run(cmd, cwd=REPO)
    if proc.returncode != 0:
        raise SystemExit(f"close-sweep poll exited {proc.returncode}")
    # Burst mode (owner 2026-09-21): inside ~6 min of first pitch a 5-minute
    # grid is too coarse and books pull markets. Re-poll every 60s, bounded
    # (default 8 iters), stopping early when nothing still needs a close.
    # Skipped entirely under --dry-run (no writes to chase) and --no-burst.
    if not args.dry_run and not args.no_burst:
        burst_n = 0
        for _ in range(max(0, args.burst_iters)):
            remaining = _need_minutes(slate, datetime.now(timezone.utc))
            if not should_burst(remaining, within_min=args.burst_within_min,
                                live_after_min=args.live_after_min):
                break
            time.sleep(max(1.0, args.burst_sleep_s))
            burst = subprocess.run(cmd, cwd=REPO)
            burst_n += 1
            if burst.returncode != 0:
                print(f"close-sweep burst poll exited {burst.returncode}; stopping burst")
                break
        else:
            print("close-sweep burst cap reached; next cron continues")
        write_status(None, {"utc": run_utc, "mode": "fetched",
                            "why": why, "burst_iters": burst_n})
    else:
        write_status(None, {"utc": run_utc, "mode": "fetched",
                            "why": why, "burst_iters": 0})


if __name__ == "__main__":
    main()
