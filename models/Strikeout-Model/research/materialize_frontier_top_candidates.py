"""Materialize top-N frontier candidates as registry-ready feature CSVs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from Python import config
from Python.registries import validate_pregame_features


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-tag", required=True)
    parser.add_argument("--top-n", type=int, default=3)
    args = parser.parse_args()

    search_dir = config.OUTPUT_DIR / "model_quality" / "final_feature_dataset_search" / args.search_tag
    results_path = search_dir / "candidate_results.csv"
    ranked_pool_path = (
        config.OUTPUT_DIR
        / "model_quality"
        / "full_feature_importance_screen"
        / "refine_top220"
        / "feature_scores.csv"
    )
    if not results_path.exists():
        raise FileNotFoundError(f"Missing {results_path}")
    if not ranked_pool_path.exists():
        raise FileNotFoundError(f"Missing {ranked_pool_path}")

    out_dir = config.OUTPUT_DIR / "model_quality" / "frontier_top_candidates" / args.search_tag
    out_dir.mkdir(parents=True, exist_ok=True)

    results = pd.read_csv(results_path).sort_values(
        ["expected_k_mae_mean", "k_rate_mae_mean", "expected_k_mae_std"]
    )
    ranked = pd.read_csv(ranked_pool_path)
    if "feature" not in ranked.columns:
        raise ValueError("ranked pool missing 'feature'")
    pool = [str(f) for f in ranked["feature"].tolist()]

    frame_cols = set(pl.read_parquet(config.PITCHER_TRAINING_PATH).columns)
    pool = [f for f in pool if f in frame_cols]

    picks = results.head(max(1, int(args.top_n))).to_dict(orient="records")
    manifest = []
    for i, row in enumerate(picks, start=1):
        k = int(row["k_seed"])
        candidate = pool[:k]
        # no window reopt reconstruction here; this is a rank-seed frontier proxy
        # for governance replay triage.
        candidate = list(validate_pregame_features(candidate))
        fpath = out_dir / f"candidate_{i}_k{k}.csv"
        pd.DataFrame({"feature": candidate}).to_csv(fpath, index=False)
        manifest.append(
            {
                "rank": i,
                "k_seed": k,
                "expected_k_mae_mean": float(row["expected_k_mae_mean"]),
                "k_rate_mae_mean": float(row["k_rate_mae_mean"]),
                "csv": str(fpath),
            }
        )

    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "search_tag": args.search_tag,
        "source_results_csv": str(results_path),
        "top_n": len(manifest),
        "candidates": manifest,
    }
    (out_dir / "manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

