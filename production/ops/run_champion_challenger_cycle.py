"""Run champion/challenger cycle end-to-end with one command.

Pipeline:
1) Sparse72 family ablation (model cross-compare)
2) Open-market skill compare (optionally 2025 holdout window)
3) Edge-floor governance sweep
4) Optional deduped ensemble sweep + open->manual top-N transfer replay
5) Optional lineage append from latest decision artifact
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(script_rel: str, args: list[str]) -> None:
    script = ROOT / script_rel
    cmd = [sys.executable, str(script), *args]
    print(f"+ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(ROOT))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-tag", default="")
    p.add_argument("--families", default="linear,ridge,lasso,elasticnet,knn,lightgbm,xgboost,random_forest,histgbr,arima,sarimax")
    p.add_argument("--holdout-2025", action="store_true", help="Use 2025-only open-skill window.")
    p.add_argument("--run-ensemble", action="store_true", help="Run deduped weighted ensemble sweep.")
    p.add_argument("--ensemble-weight-step", type=float, default=0.05)
    p.add_argument("--ensemble-floor-min", type=float, default=0.005)
    p.add_argument("--ensemble-floor-max", type=float, default=0.12)
    p.add_argument("--ensemble-floor-step", type=float, default=0.005)
    p.add_argument("--ensemble-min-bets", type=int, default=25)
    p.add_argument("--transfer-top-n", type=int, default=3)
    p.add_argument("--transfer-floors", default="0.08,0.10,0.12")
    p.add_argument("--append-lineage", action="store_true")
    p.add_argument("--operator", default="")
    p.add_argument("--lineage-run-label", default="")
    args = p.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = args.output_tag.strip() or f"cc_cycle_{ts}"

    _run(
        "models/Strikeout-Model/research/ablate_sparse72_model_families.py",
        [
            "--feature-set",
            "production_sparse72",
            "--feature-set",
            "production_sparse72_monotone",
            "--families",
            args.families,
            "--output-tag",
            tag,
        ],
    )

    skill_args = [
        "--feature-set",
        "production_sparse72",
        "--feature-set",
        "production_sparse72_monotone",
        "--feature-set",
        "production_final58_consensus",
        "--output-tag",
        tag,
    ]
    if args.holdout_2025:
        skill_args.extend(["--eval-start-date", "2025-01-01", "--eval-end-date", "2025-12-31"])
    _run("production/ops/compare_feature_set_market_skill.py", skill_args)

    _run(
        "production/ops/edge_floor_sweep_governance.py",
        [
            "--feature-set",
            "production_sparse72",
            "--feature-set",
            "production_sparse72_monotone",
            "--feature-set",
            "production_final58_consensus",
            "--calibration-mode",
            "isotonic",
            "--floor-min",
            "0.005",
            "--floor-max",
            "0.08",
            "--floor-step",
            "0.005",
            "--min-bets",
            "25",
        ],
    )

    if args.run_ensemble:
        ensemble_tag = f"ensemble_{tag}"
        _run(
            "production/ops/run_model_ensemble_sweep.py",
            [
                "--feature-set",
                "production_sparse72",
                "--feature-set",
                "production_sparse72_monotone",
                "--feature-set",
                "production_final58_consensus",
                "--calibration-mode",
                "isotonic",
                "--weight-step",
                str(args.ensemble_weight_step),
                "--floor-min",
                str(args.ensemble_floor_min),
                "--floor-max",
                str(args.ensemble_floor_max),
                "--floor-step",
                str(args.ensemble_floor_step),
                "--min-bets",
                str(args.ensemble_min_bets),
                "--dedupe-manual",
                "--output-tag",
                ensemble_tag,
            ],
        )
        ranked_csv = ROOT / "artifacts" / "odds_log" / f"ensemble_sweep_ranked_{ensemble_tag}.csv"
        _run(
            "production/ops/recalibrate_top3_ensembles_open_to_manual.py",
            [
                "--ranked-ensemble-csv",
                str(ranked_csv),
                "--top-n",
                str(args.transfer_top_n),
                "--calibration-mode",
                "isotonic",
                "--floors",
                args.transfer_floors,
                "--dedupe-manual",
                "--output-tag",
                f"{tag}_transfer",
            ],
        )

    if args.append_lineage:
        label = args.lineage_run_label.strip() or f"champion-challenger-{tag}"
        _run(
            "production/ops/run_post_score_automation.py",
            [
                "--skip-monitoring",
                "--append-lineage",
                "--run-label",
                label,
                "--operator",
                args.operator,
            ],
        )

    print(f"Champion/challenger cycle complete. tag={tag}")


if __name__ == "__main__":
    main()

