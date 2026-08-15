"""Run the daily settle/grade/notebook/KPI loop with one command.

This script wraps the operator sequence from docs/reference/daily_kpi_protocol.md
and writes a machine-readable run summary for morning checks.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
OUT_PATH = ROOT / "artifacts" / "odds_log" / "daily_kpi_loop_last_run.json"


def _run_step(label: str, cmd: list[str]) -> dict[str, object]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        raise RuntimeError(
            f"{label} failed (exit={proc.returncode})\n"
            f"stdout:\n{out}\n\nstderr:\n{err}"
        )
    return {
        "label": label,
        "command": " ".join(cmd),
        "stdout_tail": out[-2000:],
    }


def _run_kpi_action(policy_path: str | None) -> dict[str, object]:
    cmd = [str(PYTHON), "production/ops/kpi_daily_action.py", "--json"]
    if policy_path:
        cmd.extend(["--kpi-policy", policy_path])
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"kpi_daily_action failed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-notebooks",
        action="store_true",
        help="Skip notebook execution and run settle/grade/KPI steps only.",
    )
    parser.add_argument(
        "--kpi-policy",
        type=str,
        default=None,
        help="Optional policy path override for production/ops/kpi_daily_action.py.",
    )
    args = parser.parse_args()

    if not PYTHON.exists():
        raise SystemExit(f"Python not found at {PYTHON}")

    steps: list[dict[str, object]] = []
    steps.append(
        _run_step(
            "settle_ledger",
            [
                str(PYTHON),
                "production/odds/grade_odds_ledger.py",
                "--auto-settle-api",
                "--void-scratches",
                "--status",
                "--curve",
            ],
        )
    )
    steps.append(
        _run_step(
            "grade_projections",
            [
                str(PYTHON),
                "production/projections/grade_projections.py",
                "--preferred-only",
            ],
        )
    )
    if not args.skip_notebooks:
        steps.append(
            _run_step(
                "run_operator_notebooks",
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    "production/ops/run_analysis_notebooks.ps1",
                    "-SkipArtifactCheck",
                ],
            )
        )

    action = _run_kpi_action(args.kpi_policy)
    steps.append(
        _run_step(
            "calibration_snapshot",
            [str(PYTHON), "production/ops/calibration_snapshot.py", "--compare"],
        )
    )
    steps.append(
        _run_step(
            "build_operator_summary",
            [str(PYTHON), "production/ops/build_daily_operator_summary.py"],
        )
    )
    summary = {
        "ran_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "skip_notebooks": bool(args.skip_notebooks),
        "steps": steps,
        "kpi_action": action,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps({"output": str(OUT_PATH), "action": action.get("action")}, indent=2))


if __name__ == "__main__":
    main()
