"""Backfill laptop CLV closes from the Modal volume ledger (one-way merge).

Why this exists (2026-09-16): the laptop close-watcher only fills closes while
the box is awake inside game windows, so laptop game_dates 9/12+ have no
closes. The Modal close_sweep cron runs 24/7 and captured them into the volume
ledger. This script merges those closes into the laptop ledger — close prices
and close_status come from the cloud row, but CLV is recomputed canonically
from the LAPTOP row's own bet price via ``odds_ledger.apply_close`` (never
copied, since bet prices can differ across the fork).

Matching key: (game_date, norm_player_name, line, side, book). Prefer
same-book (``ok``) donors over cross-book; latest closed_at wins ties.
Idempotent: rows that already have clv_pp are never touched. Only game_dates
older than today (today's closes belong to the live sweeps).

Usage:
  python production/ops/backfill_closes_from_cloud.py --cloud-ledger <path>
  python production/ops/backfill_closes_from_cloud.py --download  # modal volume get, then merge
  python production/ops/backfill_closes_from_cloud.py --dry-run   # report only
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from Python.odds_ledger import (  # noqa: E402
    apply_close,
    load_ledger,
    norm_player_name,
    save_ledger,
)

CLOUD_VOLUME = "mlb-props-state"
CLOUD_LEDGER_PATH = "artifacts/odds_log/ledger.parquet"
TAG = "close_src=cloud_backfill_20260916"
OK_STATUSES = ("ok", "ok_cross_book")


def match_key(game_date: object, player: object, line: object,
              side: object, book: object) -> tuple:
    return (str(game_date)[:10], norm_player_name(str(player or "")),
            float(line), str(side or "").lower(), str(book or "").lower())


def pick_donors(cloud_rows: list[dict]) -> dict[tuple, dict]:
    """Best cloud close donor per match key.

    Donor must carry close prices + a terminal ok status. Prefer same-book
    (``ok``) over cross-book; latest closed_at wins remaining ties.
    """
    donors: dict[tuple, dict] = {}
    for r in cloud_rows:
        if r.get("close_over") is None or r.get("close_under") is None:
            continue
        if r.get("close_status") not in OK_STATUSES:
            continue
        key = match_key(r.get("game_date"), r.get("player_name"),
                        r.get("line"), r.get("side"), r.get("book"))
        rank = (0 if r.get("close_status") == "ok" else 1,
                str(r.get("closed_at_utc") or ""))
        prev = donors.get(key)
        prev_rank = (0 if (prev or {}).get("close_status") == "ok" else 1,
                     str((prev or {}).get("closed_at_utc") or ""))
        if prev is None or rank < prev_rank:
            donors[key] = r
    return donors


def plan_merges(laptop: pl.DataFrame, cloud: pl.DataFrame,
                today: str) -> list[dict]:
    """Return merge plans for laptop rows missing closes (pure, testable)."""
    donors = pick_donors(cloud.to_dicts())
    plans = []
    for r in laptop.to_dicts():
        if r.get("clv_pp") is not None or r.get("close_status") is not None:
            continue
        if str(r.get("game_date") or "")[:10] >= today:
            continue
        key = match_key(r.get("game_date"), r.get("player_name"),
                        r.get("line"), r.get("side"), r.get("book"))
        donor = donors.get(key)
        if donor is None:
            continue
        plans.append({
            "ticket_id": str(r["ticket_id"]),
            "close_over": float(donor["close_over"]),
            "close_under": float(donor["close_under"]),
            "close_status": str(donor["close_status"]),
            "closed_at": str(donor.get("closed_at_utc") or ""),
        })
    return plans


def download_cloud_ledger(dest: Path) -> None:
    modal = shutil.which("modal")
    if modal is None:
        raise SystemExit("modal CLI not found; pass --cloud-ledger explicitly")
    proc = subprocess.run(
        [modal, "volume", "get", CLOUD_VOLUME, CLOUD_LEDGER_PATH, str(dest)],
        cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"modal volume get exited {proc.returncode}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cloud-ledger", default="",
                    help="Path to a cloud ledger.parquet copy")
    ap.add_argument("--download", action="store_true",
                    help="Fetch the cloud ledger via modal volume get first")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cloud_path = Path(args.cloud_ledger) if args.cloud_ledger else None
    tmpdir = None
    if args.download or cloud_path is None:
        tmpdir = tempfile.mkdtemp(prefix="cloud_ledger_")
        cloud_path = Path(tmpdir) / "cloud_ledger.parquet"
        download_cloud_ledger(cloud_path)
    assert cloud_path is not None and cloud_path.exists(), cloud_path

    laptop = load_ledger()
    cloud = pl.read_parquet(cloud_path)
    plans = plan_merges(laptop, cloud, date.today().isoformat())
    print(f"laptop rows={len(laptop)} cloud rows={len(cloud)} merge_plans={len(plans)}")
    by_status: dict[str, int] = {}
    for p in plans:
        by_status[p["close_status"]] = by_status.get(p["close_status"], 0) + 1
    print(f"by donor status: {by_status}")
    if args.dry_run or not plans:
        print("dry-run (no write)." if args.dry_run else "nothing to merge.")
        return

    from datetime import datetime, timezone

    updated = laptop
    for p in plans:
        try:
            closed_at = datetime.fromisoformat(p["closed_at"].replace("Z", "+00:00")) \
                if p["closed_at"] else None
        except ValueError:
            closed_at = None
        updated = apply_close(
            updated, ticket_id=p["ticket_id"],
            close_over=p["close_over"], close_under=p["close_under"],
            closed_at=closed_at, close_status=p["close_status"])
    tag_mask = pl.col("ticket_id").is_in([p["ticket_id"] for p in plans])
    updated = updated.with_columns(
        pl.when(tag_mask & ~pl.col("note").fill_null("").str.contains(TAG))
        .then(pl.col("note").fill_null("") + f" | {TAG}")
        .otherwise(pl.col("note")).alias("note"))
    save_ledger(updated)
    filled = updated.filter(pl.col("ticket_id").is_in(
        [p["ticket_id"] for p in plans]) & pl.col("clv_pp").is_not_null()).height
    print(f"merged {filled}/{len(plans)} closes (CLV recomputed from laptop bet prices).")


if __name__ == "__main__":
    main()
