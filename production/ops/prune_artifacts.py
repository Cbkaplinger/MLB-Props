"""Deduplicate artifact files by content hash with report-first workflow.

Usage examples:
  python production/ops/prune_artifacts.py --target artifacts/model_quality --dry-run
  python production/ops/prune_artifacts.py --target artifacts/model_quality --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGET = ROOT / "artifacts" / "odds_log"
DEFAULT_REPORT_JSON = ROOT / "artifacts" / "odds_log" / "prune_artifacts_last_report.json"
DEFAULT_REPORT_CSV = ROOT / "artifacts" / "odds_log" / "prune_artifacts_candidates_latest.csv"
CHUNK_SIZE = 1024 * 1024


@dataclass
class FileMeta:
    path: Path
    size_bytes: int
    mtime_ns: int
    digest: str


def _resolve_path(path_str: str) -> Path:
    p = Path(path_str)
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _scan_files(target: Path) -> list[Path]:
    return [p for p in target.rglob("*") if p.is_file()]


def _canonical_sort_key(meta: FileMeta, root: Path, prefer_newest: bool) -> tuple[object, ...]:
    rel = str(meta.path.relative_to(root)).replace("\\", "/")
    time_key = -meta.mtime_ns if prefer_newest else meta.mtime_ns
    return (time_key, len(rel), rel)


def _build_groups(target: Path, prefer_newest: bool) -> tuple[list[dict[str, object]], dict[str, object]]:
    files = _scan_files(target)
    by_digest: dict[str, list[FileMeta]] = {}
    total_bytes = 0
    for p in files:
        stat = p.stat()
        size = int(stat.st_size)
        total_bytes += size
        meta = FileMeta(
            path=p,
            size_bytes=size,
            mtime_ns=int(stat.st_mtime_ns),
            digest=_sha256_file(p),
        )
        by_digest.setdefault(meta.digest, []).append(meta)

    candidates: list[dict[str, object]] = []
    duplicate_groups = 0
    removable_files = 0
    removable_bytes = 0

    for digest, group in by_digest.items():
        if len(group) < 2:
            continue
        duplicate_groups += 1
        ordered = sorted(group, key=lambda m: _canonical_sort_key(m, target, prefer_newest))
        keep = ordered[0]
        for idx, meta in enumerate(ordered):
            action = "keep" if idx == 0 else "delete_candidate"
            if action == "delete_candidate":
                removable_files += 1
                removable_bytes += meta.size_bytes
            candidates.append(
                {
                    "digest": digest,
                    "group_size": len(ordered),
                    "action": action,
                    "size_bytes": meta.size_bytes,
                    "relative_path": str(meta.path.relative_to(ROOT)).replace("\\", "/"),
                    "canonical_relative_path": str(keep.path.relative_to(ROOT)).replace("\\", "/"),
                    "mtime_utc": datetime.fromtimestamp(meta.mtime_ns / 1_000_000_000, tz=timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                }
            )

    summary = {
        "scanned_files": len(files),
        "scanned_bytes": total_bytes,
        "duplicate_groups": duplicate_groups,
        "delete_candidates": removable_files,
        "candidate_bytes": removable_bytes,
    }
    return candidates, summary


def _write_reports(report_json: Path, report_csv: Path, payload: dict[str, object], rows: list[dict[str, object]]) -> None:
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if rows:
        pl.DataFrame(rows).write_csv(report_csv)
    else:
        pl.DataFrame(
            [
                {
                    "digest": "",
                    "group_size": 0,
                    "action": "",
                    "size_bytes": 0,
                    "relative_path": "",
                    "canonical_relative_path": "",
                    "mtime_utc": "",
                }
            ]
        ).clear().write_csv(report_csv)


def _apply_deletes(rows: list[dict[str, object]]) -> tuple[int, int]:
    deleted_files = 0
    deleted_bytes = 0
    for row in rows:
        if row.get("action") != "delete_candidate":
            continue
        p = ROOT / str(row["relative_path"])
        if not p.exists():
            continue
        size = int(row.get("size_bytes", 0))
        p.unlink()
        deleted_files += 1
        deleted_bytes += size
    return deleted_files, deleted_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        type=str,
        default=str(DEFAULT_TARGET),
        help="Directory to scan for duplicates (default: artifacts/odds_log).",
    )
    parser.add_argument("--report-json", type=str, default=str(DEFAULT_REPORT_JSON), help="Path to JSON report output.")
    parser.add_argument("--report-csv", type=str, default=str(DEFAULT_REPORT_CSV), help="Path to CSV report output.")
    parser.add_argument(
        "--prefer-newest",
        action="store_true",
        help="Keep newest file in each duplicate group (default keeps oldest).",
    )
    parser.add_argument("--apply", action="store_true", help="Delete duplicate candidates after writing reports.")
    parser.add_argument("--dry-run", action="store_true", help="Scan and report only (default behavior).")
    args = parser.parse_args()

    target = _resolve_path(args.target)
    report_json = _resolve_path(args.report_json)
    report_csv = _resolve_path(args.report_csv)
    if not target.exists():
        raise SystemExit(f"Target directory does not exist: {target}")
    if not target.is_dir():
        raise SystemExit(f"Target path is not a directory: {target}")

    candidates, summary = _build_groups(target, prefer_newest=bool(args.prefer_newest))
    mode = "apply" if args.apply else "dry_run"
    payload: dict[str, object] = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": mode,
        "target": str(target),
        "prefer_newest": bool(args.prefer_newest),
        "summary": summary,
        "candidates": candidates,
    }
    _write_reports(report_json, report_csv, payload, candidates)

    deleted_files = 0
    deleted_bytes = 0
    if args.apply:
        deleted_files, deleted_bytes = _apply_deletes(candidates)
        payload["applied"] = {"deleted_files": deleted_files, "deleted_bytes": deleted_bytes}
        report_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "target": str(target),
                "mode": mode,
                "report_json": str(report_json),
                "report_csv": str(report_csv),
                "duplicate_groups": summary["duplicate_groups"],
                "delete_candidates": summary["delete_candidates"],
                "candidate_bytes": summary["candidate_bytes"],
                "deleted_files": deleted_files,
                "deleted_bytes": deleted_bytes,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
