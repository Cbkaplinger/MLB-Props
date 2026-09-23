"""Heal a stale slate before the board runs (owner 2026-09-17).

Replaces the repealed fail-closed rule AND the ps1-only >3d auto-heal (which
missed exactly-3d staleness on 9/16): when the projection log is more than
`--threshold` days old (default 1, same scale as the old board cap), run ONE
deeper refresh cycle (trailing statcast re-pull + features + re-log), then let
the board score whatever resulted — fresh or still-stale, bets stand.

Best-effort throughout and ALWAYS exits 0: this step must never block the
board. Staleness stays visible via the board's `stale_data` tag + banner.
Shared by the laptop morning workflow and the Modal morning function.

Usage:
  python production/ops/heal_stale_slate.py [--threshold 1]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
LAST_LOG = ROOT / "artifacts" / "projection_log" / "last_log.json"
DEFAULT_THRESHOLD = 1


def stale_days() -> int | None:
    """Days between today and the projection log's rolling max (None=unknown)."""
    try:
        meta = json.loads(LAST_LOG.read_text(encoding="utf-8")).get("build_meta", {})
        max_s = str(meta.get("rolling_max_date") or "")[:10]
        if not max_s:
            return None
        from datetime import date

        from Python.odds_ledger import et_today  # noqa: E402

        return (date.fromisoformat(et_today()) - date.fromisoformat(max_s)).days
    except Exception:
        return None


def heal(threshold: int = DEFAULT_THRESHOLD) -> tuple[bool, str]:
    """One refresh cycle if stale. Returns (healed_or_fresh, note)."""
    stale = stale_days()
    if stale is None:
        return True, "unknown freshness — nothing to heal, board decides"
    if stale <= threshold:
        return True, f"fresh ({stale}d <= {threshold}d)"
    failures: list[str] = []
    steps = [
        ("heal_statcast", [sys.executable, "-u", "production/ops/refresh_statcast.py",
                           "--retries", "3", "--refresh-trailing-days", "3"]),
        ("heal_features", [sys.executable, "-u", "production/ops/refresh_features.py",
                           "--skip-training"]),
        ("heal_projections", [sys.executable, "-u", "production/projections/log_projections.py",
                              "--allow-stale"]),
    ]
    for label, cmd in steps:
        try:
            proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
            if proc.returncode != 0:
                failures.append(f"{label} exit {proc.returncode}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{label} error {exc}")
    after = stale_days()
    if failures:
        return False, (f"stale {stale}d -> heal attempted, still issues "
                       f"({'; '.join(failures)}); board bets anyway (owner 2026-09-17)")
    return True, f"stale {stale}d -> healed (now {after}d)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    args = ap.parse_args()
    ok, note = heal(args.threshold)
    print(f"heal_stale_slate: {'HEAL_OK' if ok else 'HEAL_FAILED'}: {note}")
    return 0  # never blocks the board


if __name__ == "__main__":
    raise SystemExit(main())
