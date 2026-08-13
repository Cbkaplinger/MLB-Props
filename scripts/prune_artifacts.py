"""Safe artifact pruning utility (dry-run by default).

This script only targets dated files in selected artifact subfolders and never
touches protected files/folders unless explicitly changed in this script.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"

# Keep these folders and files untouched by automated pruning.
PROTECTED_DIR_NAMES = {
    "models",
    "projection_log",
    "odds_log",
    "feature_research",
    "stabilization",
    "count_layer",
}
PROTECTED_FILE_NAMES = {
    "README.md",
}

# Match common date-tagged artifact names, e.g.
# live_scores_2026-08-10.json, historical_scores_2025-09-20.parquet
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class Candidate:
    path: Path
    date: datetime
    age_days: int


def _parse_date_from_name(name: str) -> datetime | None:
    m = DATE_RE.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _is_protected(path: Path) -> bool:
    if path.name in PROTECTED_FILE_NAMES:
        return True
    return any(part in PROTECTED_DIR_NAMES for part in path.parts)


def _iter_candidates(*, min_age_days: int) -> list[Candidate]:
    if not ARTIFACTS.exists():
        return []
    now = datetime.now(timezone.utc)
    out: list[Candidate] = []
    for p in ARTIFACTS.rglob("*"):
        if not p.is_file():
            continue
        if _is_protected(p):
            continue
        dt = _parse_date_from_name(p.name)
        if dt is None:
            continue
        age = (now - dt).days
        if age < min_age_days:
            continue
        out.append(Candidate(path=p, date=dt, age_days=age))
    return sorted(out, key=lambda c: (c.path.as_posix(), c.date))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-age-days",
        type=int,
        default=45,
        help="Minimum age in days for date-tagged artifacts to be considered.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete candidates. Without this flag, run is dry-run only.",
    )
    args = parser.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.min_age_days)
    print(f"artifact root: {ARTIFACTS}")
    print(f"dry_run: {not args.apply}")
    print(f"min_age_days: {args.min_age_days} (cutoff={cutoff.date()})")

    candidates = _iter_candidates(min_age_days=args.min_age_days)
    if not candidates:
        print("No prune candidates found.")
        return

    print(f"candidates: {len(candidates)}")
    for c in candidates:
        rel = c.path.relative_to(ROOT)
        print(f"- {rel} (age_days={c.age_days})")

    if not args.apply:
        print("Dry-run complete. Re-run with --apply to delete listed files.")
        return

    deleted = 0
    for c in candidates:
        c.path.unlink(missing_ok=True)
        deleted += 1
    print(f"Deleted {deleted} artifact files.")


if __name__ == "__main__":
    main()
