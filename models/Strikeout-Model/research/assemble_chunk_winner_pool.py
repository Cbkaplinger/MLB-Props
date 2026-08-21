"""Assemble a ranked winner pool from chunked feature-screen outputs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "artifacts" / "model_quality" / "full_feature_importance_screen"
OUT = ROOT / "artifacts" / "model_quality" / "chunk_winner_pool"


def _read_chunk(chunk_dir: Path, top_n: int) -> pl.DataFrame:
    feat = pl.read_csv(chunk_dir / "feature_scores.csv").with_columns(
        pl.lit(chunk_dir.name).alias("chunk")
    )
    stab = pl.read_csv(chunk_dir / "stability_selection.csv")
    joined = feat.join(stab, on="feature", how="left").with_columns(
        pl.col("selection_probability").fill_null(0.0),
        pl.col("positive_share").fill_null(0.0),
        (
            pl.col("mean_delta_mae").cast(pl.Float64)
            + pl.col("positive_share").cast(pl.Float64) * 2e-5
            + pl.col("selection_probability").cast(pl.Float64) * 1e-5
        ).alias("chunk_rank_score"),
    )
    return joined.sort("chunk_rank_score", descending=True).head(top_n)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    top_n_per_chunk = 30
    chunk_dirs = sorted(
        [p for p in BASE.glob("chunk_*") if p.is_dir() and (p / "feature_scores.csv").exists()]
    )
    if not chunk_dirs:
        raise FileNotFoundError(f"No chunk feature outputs found under {BASE}")

    parts = [_read_chunk(d, top_n_per_chunk) for d in chunk_dirs]
    pool = pl.concat(parts, how="diagonal_relaxed")
    agg = (
        pool.group_by("feature")
        .agg(
            pl.mean("mean_delta_mae").alias("mean_delta_mae"),
            pl.std("mean_delta_mae").fill_null(0.0).alias("std_delta_mae"),
            pl.mean("positive_share").alias("positive_share"),
            pl.mean("selection_probability").alias("selection_probability"),
            pl.len().alias("chunk_hits"),
            pl.col("chunk").implode().alias("chunks_raw"),
        )
        .with_columns(
            pl.col("chunks_raw").list.join("|").alias("chunks"),
        )
        .drop("chunks_raw")
        .with_columns(
            (
                pl.col("mean_delta_mae").cast(pl.Float64)
                + pl.col("positive_share").cast(pl.Float64) * 2e-5
                + pl.col("selection_probability").cast(pl.Float64) * 1e-5
                + pl.col("chunk_hits").cast(pl.Float64) * 1e-6
            ).alias("global_score")
        )
        .sort(["global_score", "mean_delta_mae"], descending=[True, True])
    )

    pool.write_csv(OUT / "winner_pool_rows.csv")
    agg.write_csv(OUT / "winner_pool_ranked.csv")

    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "top_n_per_chunk": top_n_per_chunk,
        "n_chunks": len(chunk_dirs),
        "n_unique_features": int(agg.height),
        "files": {
            "winner_pool_rows_csv": str(OUT / "winner_pool_rows.csv"),
            "winner_pool_ranked_csv": str(OUT / "winner_pool_ranked.csv"),
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(agg.head(40).to_pandas().to_string(index=False))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
