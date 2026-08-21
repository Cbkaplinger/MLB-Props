"""Aggregate chunked feature screening outputs into one leaderboard."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "artifacts" / "model_quality" / "full_feature_importance_screen"
OUT = BASE / "chunk_aggregate"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    chunk_dirs = sorted(
        [p for p in BASE.glob("chunk_*") if p.is_dir() and (p / "feature_scores.csv").exists()]
    )
    if not chunk_dirs:
        raise FileNotFoundError(f"No chunk outputs found under {BASE}")

    feat_parts = []
    grp_parts = []
    stab_parts = []
    for d in chunk_dirs:
        feat = pd.read_csv(d / "feature_scores.csv")
        feat["chunk"] = d.name
        feat_parts.append(feat)
        grp = pd.read_csv(d / "group_scores.csv")
        grp["chunk"] = d.name
        grp_parts.append(grp)
        stab = pd.read_csv(d / "stability_selection.csv")
        stab["chunk"] = d.name
        stab_parts.append(stab)

    feat_all = pd.concat(feat_parts, ignore_index=True)
    grp_all = pd.concat(grp_parts, ignore_index=True)
    stab_all = pd.concat(stab_parts, ignore_index=True)

    feat_agg = (
        feat_all.groupby("feature", as_index=False)
        .agg(
            mean_delta_mae=("mean_delta_mae", "mean"),
            std_delta_mae=("mean_delta_mae", "std"),
            positive_share=("positive_share", "mean"),
            chunks_seen=("chunk", "nunique"),
        )
        .sort_values(["mean_delta_mae", "positive_share"], ascending=[False, False])
    )
    grp_agg = (
        grp_all.groupby("group", as_index=False)
        .agg(
            mean_delta_mae=("mean_delta_mae", "mean"),
            std_delta_mae=("mean_delta_mae", "std"),
            positive_share=("positive_share", "mean"),
            chunks_seen=("chunk", "nunique"),
            n_features=("n_features", "max"),
            group_features=("group_features", "first"),
        )
        .sort_values("mean_delta_mae", ascending=False)
    )
    stab_agg = (
        stab_all.groupby("feature", as_index=False)
        .agg(
            selection_probability=("selection_probability", "mean"),
            chunks_seen=("chunk", "nunique"),
        )
        .sort_values("selection_probability", ascending=False)
    )

    feat_all.to_csv(OUT / "feature_scores_all_chunks.csv", index=False)
    feat_agg.to_csv(OUT / "feature_scores_aggregate.csv", index=False)
    grp_all.to_csv(OUT / "group_scores_all_chunks.csv", index=False)
    grp_agg.to_csv(OUT / "group_scores_aggregate.csv", index=False)
    stab_all.to_csv(OUT / "stability_all_chunks.csv", index=False)
    stab_agg.to_csv(OUT / "stability_aggregate.csv", index=False)

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_chunks": len(chunk_dirs),
        "chunks": [d.name for d in chunk_dirs],
        "files": {
            "feature_scores_aggregate_csv": str(OUT / "feature_scores_aggregate.csv"),
            "group_scores_aggregate_csv": str(OUT / "group_scores_aggregate.csv"),
            "stability_aggregate_csv": str(OUT / "stability_aggregate.csv"),
        },
    }
    (OUT / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(feat_agg.head(30).to_string(index=False))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
