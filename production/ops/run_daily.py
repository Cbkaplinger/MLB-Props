"""One-shot daily production chain: Statcast → features → slate score.

Examples:
    python production/ops/run_daily.py
    python production/ops/run_daily.py --skip-features --allow-stale
    python production/ops/run_daily.py --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROD = Path(__file__).resolve().parent


def _run(script: Path, extra: list[str]) -> None:
    cmd = [sys.executable, str(script), *extra]
    print(f"+ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-statcast",
        action="store_true",
        help="Skip incremental Savant refresh.",
    )
    parser.add_argument(
        "--skip-features",
        action="store_true",
        help="Skip Level 1–3 rebuild (use existing rolling).",
    )
    parser.add_argument(
        "--skip-score",
        action="store_true",
        help="Stop after data refresh.",
    )
    parser.add_argument(
        "--skip-exit-anomaly-refresh",
        action="store_true",
        help="Skip exit anomaly override/mask refresh.",
    )
    parser.add_argument(
        "--refresh-trailing-days",
        type=int,
        default=0,
        help="Passed to refresh_statcast.py.",
    )
    parser.add_argument(
        "--skip-training",
        action="store_true",
        help="Passed to refresh_features.py (L1–L2 only).",
    )
    parser.add_argument(
        "--allow-stale",
        action="store_true",
        help="Passed to score_slate.py.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch slate only; do not score.",
    )
    parser.add_argument(
        "--require-confirmed",
        action="store_true",
        help="Fail unless every RotoGrinders lineup is confirmed.",
    )
    args = parser.parse_args()

    if not args.skip_statcast:
        trailing = ["--refresh-trailing-days", str(args.refresh_trailing_days)]
        _run(PROD / "refresh_statcast.py", trailing)

    if not args.skip_features:
        feat_args: list[str] = []
        if args.skip_training:
            feat_args.append("--skip-training")
        _run(PROD / "refresh_features.py", feat_args)

    if not args.skip_exit_anomaly_refresh:
        _run(ROOT / "scripts" / "build_exit_anomaly_overrides.py", [])
        _run(ROOT / "scripts" / "build_exit_anomaly_training_mask.py", [])

    if args.skip_score:
        print("Skipped scoring (--skip-score).")
        return

    score_args: list[str] = []
    if args.dry_run:
        score_args.append("--dry-run")
    else:
        score_args.append("--live")
    if args.allow_stale:
        score_args.append("--allow-stale")
    if args.require_confirmed:
        score_args.append("--require-confirmed")
    _run(PROD / "score_slate.py", score_args)


if __name__ == "__main__":
    main()
