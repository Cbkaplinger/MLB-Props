"""Write immutable model-lineage records for governance and reproducibility.

This is intentionally lightweight and free-tier friendly:
- appends one JSON object per run to a JSONL ledger
- also writes a normalized CSV snapshot for quick filtering in notebooks
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "artifacts" / "model_registry"
OUT_JSONL = OUT_DIR / "model_lineage_log.jsonl"
OUT_CSV = OUT_DIR / "model_lineage_log.csv"


def _sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _git_sha() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip()
    except Exception:
        return None


def _append_csv(row: dict[str, object]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "timestamp_utc",
        "run_label",
        "feature_set",
        "calibration_mode",
        "decision_action",
        "decision_reason",
        "dataset_window",
        "dataset_path",
        "dataset_sha256",
        "params_json",
        "metrics_json",
        "artifact_paths_json",
        "git_sha",
        "operator",
    ]
    exists = OUT_CSV.exists()
    with OUT_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k) for k in fields})


def _normalize_json_text(value: str) -> str:
    txt = (value or "").strip()
    if not txt:
        return "{}"
    try:
        return json.dumps(json.loads(txt), sort_keys=True, separators=(",", ":"))
    except Exception:
        pass
    # PowerShell often strips double quotes inside CLI args.
    # Try a conservative quote-repair for simple key:value maps.
    repaired = re.sub(r'([{,]\s*)([A-Za-z0-9_./-]+)\s*:', r'\1"\2":', txt)
    repaired = re.sub(r':\s*([A-Za-z_./-][A-Za-z0-9_./-]*)\s*([,}])', r':"\1"\2', repaired)
    try:
        return json.dumps(json.loads(repaired), sort_keys=True, separators=(",", ":"))
    except Exception:
        return txt


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-label", required=True)
    p.add_argument("--feature-set", required=True)
    p.add_argument("--calibration-mode", default="isotonic")
    p.add_argument("--decision-action", default="HOLD")
    p.add_argument("--decision-reason", default="")
    p.add_argument("--dataset-window", default="")
    p.add_argument("--dataset-path", default="")
    p.add_argument("--params-json", default="{}")
    p.add_argument("--metrics-json", default="{}")
    p.add_argument("--artifact-paths-json", default="{}")
    p.add_argument("--operator", default="")
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset_path = Path(args.dataset_path) if args.dataset_path else None
    dataset_sha = _sha256_file(dataset_path) if dataset_path else None
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "timestamp_utc": now,
        "run_label": args.run_label,
        "feature_set": args.feature_set,
        "calibration_mode": args.calibration_mode,
        "decision_action": args.decision_action,
        "decision_reason": args.decision_reason,
        "dataset_window": args.dataset_window,
        "dataset_path": str(dataset_path) if dataset_path else "",
        "dataset_sha256": dataset_sha,
        "params_json": _normalize_json_text(args.params_json),
        "metrics_json": _normalize_json_text(args.metrics_json),
        "artifact_paths_json": _normalize_json_text(args.artifact_paths_json),
        "git_sha": _git_sha(),
        "operator": args.operator,
    }
    with OUT_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    _append_csv(row)
    print(f"wrote {OUT_JSONL}")
    print(f"wrote {OUT_CSV}")
    print(json.dumps(row, indent=2))


if __name__ == "__main__":
    main()

