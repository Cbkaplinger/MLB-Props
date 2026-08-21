"""Post-score production automation: monitoring cycle + optional lineage append."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "production" / "ops"
ODDS_DIR = ROOT / "artifacts" / "odds_log"


def _run(script: Path, extra: list[str]) -> None:
    cmd = [sys.executable, str(script), *extra]
    print(f"+ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(ROOT))


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--skip-monitoring", action="store_true")
    p.add_argument("--append-lineage", action="store_true")
    p.add_argument("--run-label", default="")
    p.add_argument("--operator", default="")
    args = p.parse_args()

    if not args.skip_monitoring:
        _run(OPS / "run_monitoring_cycle.py", [])

    if not args.append_lineage:
        print("Lineage append skipped (use --append-lineage to enable).")
        return

    decision = _read_json(ODDS_DIR / "champion_challenger_decision.json")
    winner = decision.get("winner") if isinstance(decision, dict) else None
    if not isinstance(winner, dict):
        print("No champion decision found; lineage append skipped.")
        return

    label = args.run_label.strip() or f"post-score-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    feature_set = str(winner.get("feature_set") or "unknown")
    calibration_mode = str(winner.get("calibration_mode") or decision.get("calibration_mode") or "isotonic")
    action = str(decision.get("action") or "HOLD")
    reason = "Automated append from champion_challenger_decision.json"
    params = json.dumps(
        {
            "edge_floor": winner.get("edge_floor"),
            "min_bets_gate": decision.get("min_bets_gate"),
            "window_label": decision.get("window_label"),
        },
        separators=(",", ":"),
    )
    metrics = json.dumps(
        {
            "brier_skill_vs_market": winner.get("brier_skill_vs_market"),
            "logloss_skill_vs_market": winner.get("logloss_skill_vs_market"),
            "roi": winner.get("roi"),
            "sortino": winner.get("sortino"),
            "n_bets": winner.get("n_bets"),
        },
        separators=(",", ":"),
    )
    artifacts = json.dumps(decision.get("artifacts") or {}, separators=(",", ":"))

    _run(
        OPS / "log_model_lineage.py",
        [
            "--run-label",
            label,
            "--feature-set",
            feature_set,
            "--calibration-mode",
            calibration_mode,
            "--decision-action",
            action,
            "--decision-reason",
            reason,
            "--dataset-window",
            str(decision.get("window_label") or "full"),
            "--params-json",
            params,
            "--metrics-json",
            metrics,
            "--artifact-paths-json",
            artifacts,
            "--operator",
            args.operator,
        ],
    )


if __name__ == "__main__":
    main()

