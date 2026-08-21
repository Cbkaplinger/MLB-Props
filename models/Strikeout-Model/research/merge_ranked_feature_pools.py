"""Merge multiple ranked feature pools into one consensus ranking."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "model_quality" / "merged_feature_pool"


def _normalized_score(df: pl.DataFrame) -> pl.DataFrame:
    n = max(df.height, 1)
    return df.with_row_index("rank").with_columns(
        (1.0 - (pl.col("rank").cast(pl.Float64) / float(n))).alias("norm_rank_score")
    )


def _load(path: Path, weight: float, source: str) -> pl.DataFrame:
    df = pl.read_csv(path)
    if "feature" not in df.columns:
        raise ValueError(f"missing feature column in {path}")
    if "global_score" in df.columns:
        df = df.with_columns(pl.col("global_score").cast(pl.Float64).alias("raw_score"))
    elif "score" in df.columns:
        df = df.with_columns(pl.col("score").cast(pl.Float64).alias("raw_score"))
    elif "mean_delta_mae" in df.columns:
        df = df.with_columns(pl.col("mean_delta_mae").cast(pl.Float64).alias("raw_score"))
    else:
        df = df.with_columns(pl.lit(0.0).alias("raw_score"))
    return (
        _normalized_score(df.sort("raw_score", descending=True))
        .select("feature", "raw_score", "norm_rank_score")
        .with_columns(pl.lit(weight).alias("weight"), pl.lit(source).alias("source"))
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-tag", default="consensus", help="Output subfolder tag.")
    parser.add_argument(
        "--pool",
        action="append",
        required=True,
        help="Pool spec in form path::weight::source",
    )
    args = parser.parse_args()

    out_dir = OUT / args.out_tag
    out_dir.mkdir(parents=True, exist_ok=True)

    parts = []
    for spec in args.pool:
        path_s, weight_s, source = spec.split("::", 2)
        parts.append(_load(Path(path_s), float(weight_s), source))
    merged = pl.concat(parts, how="diagonal_relaxed")
    ranked = (
        merged.group_by("feature")
        .agg(
            (pl.col("norm_rank_score") * pl.col("weight")).sum().alias("score"),
            pl.mean("raw_score").alias("mean_raw_score"),
            pl.count().alias("sources_seen"),
            pl.col("source").implode().alias("sources_raw"),
        )
        .with_columns(pl.col("sources_raw").list.join("|").alias("sources"))
        .drop("sources_raw")
        .sort(["score", "mean_raw_score"], descending=[True, True])
    )

    merged.write_csv(out_dir / "pool_rows.csv")
    ranked.write_csv(out_dir / "ranked.csv")
    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "out_tag": args.out_tag,
        "n_sources": len(args.pool),
        "n_ranked_features": int(ranked.height),
        "files": {
            "pool_rows_csv": str(out_dir / "pool_rows.csv"),
            "ranked_csv": str(out_dir / "ranked.csv"),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(ranked.head(30).to_pandas().to_string(index=False))
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
