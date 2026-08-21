"""Run free-tier monitoring cycle (t=0 data drift, t+1 quality drift).

t=0:
- refresh open-market diagnostics (input quality/drift proxy)

t+1:
- refresh validation/ops report (realized quality when labels have settled)

Writes one consolidated cycle report for auditing and automation.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "artifacts" / "odds_log"
OUT_JSON = OUT_DIR / "monitoring_cycle_latest.json"
HISTORY_JSONL = OUT_DIR / "monitoring_cycle_history.jsonl"


def _run_py(script_rel: str) -> dict[str, object]:
    script = ROOT / script_rel
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    ended = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "script": script_rel,
        "started_utc": started,
        "ended_utc": ended,
        "exit_code": int(proc.returncode),
        "stdout_tail": proc.stdout[-4000:] if proc.stdout else "",
        "stderr_tail": proc.stderr[-4000:] if proc.stderr else "",
    }


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _drift_flags(open_summary: dict[str, object], val_summary: dict[str, object]) -> list[str]:
    flags: list[str] = []
    rows = (open_summary.get("rows") or {}) if isinstance(open_summary, dict) else {}
    matched = int(rows.get("projection_matched_rows") or 0)
    unmatched = int(rows.get("unmatched_rows") or 0)
    total = max(1, int(rows.get("open_rows_total") or 0))
    unmatched_rate = unmatched / total
    if matched == 0:
        flags.append("projection_match_zero")
    if unmatched_rate > 0.35:
        flags.append("unmatched_rate_high")
    dq = (val_summary.get("data_quality") or {}) if isinstance(val_summary, dict) else {}
    for a in dq.get("alerts", []) if isinstance(dq, dict) else []:
        flags.append(f"data_quality::{a}")
    return flags


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-open",
        action="store_true",
        help="Skip t=0 open-market diagnostics refresh.",
    )
    parser.add_argument(
        "--skip-quality",
        action="store_true",
        help="Skip t+1 validation quality refresh.",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, object]] = []
    if not args.skip_open:
        steps.append(_run_py("production/ops/build_open_market_diagnostics.py"))
    if not args.skip_quality:
        steps.append(_run_py("production/ops/build_validation_ops_report.py"))

    open_summary = _read_json(OUT_DIR / "open_market_diagnostics_summary.json")
    val_summary = _read_json(OUT_DIR / "validation_ops_daily.json")
    flags = _drift_flags(open_summary, val_summary)
    status = "ok" if not flags and all(s["exit_code"] == 0 for s in steps) else "warn"
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "flags": flags,
        "steps": steps,
        "references": {
            "open_market_diagnostics_summary": str(OUT_DIR / "open_market_diagnostics_summary.json"),
            "validation_ops_daily": str(OUT_DIR / "validation_ops_daily.json"),
        },
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with HISTORY_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")
    print(f"wrote {OUT_JSON}")
    print(f"appended {HISTORY_JSONL}")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

