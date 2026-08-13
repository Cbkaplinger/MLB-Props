"""Postgame exit-anomaly labels for evaluation/training hygiene.

These labels are *not* pregame features. They are used to:
- audit process metrics with and without exogenous exits, and
- optionally mask/downweight rows during retraining experiments.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

DEFAULT_OVERRIDE_PATH = (
    Path(__file__).resolve().parents[2] / "production" / "ops" / "exit_anomaly_overrides.csv"
)

KEY_COLS = ["game_pk", "pitcher", "game_date"]


def _normalize_game_date(df: pl.DataFrame, col: str = "game_date") -> pl.DataFrame:
    if col not in df.columns:
        return df
    return df.with_columns(pl.col(col).cast(pl.Utf8).str.slice(0, 10).alias(col))


def _normalize_pitcher(df: pl.DataFrame, col: str = "pitcher") -> pl.DataFrame:
    if col not in df.columns:
        return df
    return df.with_columns(pl.col(col).cast(pl.Int64, strict=False).alias(col))


def normalize_anomaly_keys(df: pl.DataFrame) -> pl.DataFrame:
    """Normalize key columns used for anomaly joins."""
    out = df
    out = _normalize_game_date(out, "game_date")
    out = _normalize_pitcher(out, "pitcher")
    if "game_pk" in out.columns:
        out = out.with_columns(pl.col("game_pk").cast(pl.Int64, strict=False).alias("game_pk"))
    return out


def load_exit_anomaly_overrides(path: str | Path | None = None) -> pl.DataFrame:
    """Load manual/automated anomaly tags keyed by game_pk, pitcher, game_date."""
    p = Path(path) if path is not None else DEFAULT_OVERRIDE_PATH
    if not p.exists():
        return pl.DataFrame()
    if p.suffix.lower() == ".parquet":
        raw = pl.read_parquet(p)
    else:
        raw = pl.read_csv(p)
    if raw.is_empty():
        return raw
    out = normalize_anomaly_keys(raw)
    # Ensure required columns exist with safe defaults.
    defaults: list[pl.Expr] = []
    if "exit_anomaly_flag" not in out.columns:
        defaults.append(pl.lit(True).alias("exit_anomaly_flag"))
    if "exit_anomaly_type" not in out.columns:
        defaults.append(pl.lit("other_exogenous").alias("exit_anomaly_type"))
    if "exit_anomaly_confidence" not in out.columns:
        defaults.append(pl.lit("manual").alias("exit_anomaly_confidence"))
    if "exit_anomaly_source" not in out.columns:
        defaults.append(pl.lit("manual_override").alias("exit_anomaly_source"))
    if defaults:
        out = out.with_columns(defaults)
    keep = [c for c in KEY_COLS + ["exit_anomaly_flag", "exit_anomaly_type", "exit_anomaly_confidence", "exit_anomaly_source", "note"] if c in out.columns]
    out = out.select(keep)
    return out.unique(subset=[c for c in KEY_COLS if c in out.columns], keep="last")


def apply_exit_anomaly_overrides(
    frame: pl.DataFrame,
    overrides: pl.DataFrame | None = None,
    *,
    path: str | Path | None = None,
) -> pl.DataFrame:
    """Attach anomaly labels to a frame; missing rows default to non-anomaly."""
    if frame.is_empty():
        return frame
    base = normalize_anomaly_keys(frame)
    ov = overrides if overrides is not None else load_exit_anomaly_overrides(path)
    if ov is None or ov.is_empty():
        return base.with_columns(
            pl.lit(False).alias("exit_anomaly_flag"),
            pl.lit(None).cast(pl.Utf8).alias("exit_anomaly_type"),
            pl.lit(None).cast(pl.Utf8).alias("exit_anomaly_confidence"),
            pl.lit(None).cast(pl.Utf8).alias("exit_anomaly_source"),
        )

    join_keys = [c for c in KEY_COLS if c in base.columns and c in ov.columns]
    if len(join_keys) < 2:
        # Not enough reliable keys to join; return base with neutral defaults.
        return base.with_columns(
            pl.lit(False).alias("exit_anomaly_flag"),
            pl.lit(None).cast(pl.Utf8).alias("exit_anomaly_type"),
            pl.lit(None).cast(pl.Utf8).alias("exit_anomaly_confidence"),
            pl.lit(None).cast(pl.Utf8).alias("exit_anomaly_source"),
        )

    out = base.join(ov, on=join_keys, how="left")
    out = out.with_columns(
        pl.col("exit_anomaly_flag").fill_null(False).cast(pl.Boolean),
        pl.col("exit_anomaly_type").fill_null(pl.lit(None).cast(pl.Utf8)),
        pl.col("exit_anomaly_confidence").fill_null(pl.lit(None).cast(pl.Utf8)),
        pl.col("exit_anomaly_source").fill_null(pl.lit(None).cast(pl.Utf8)),
    )
    return out


def add_training_mask(frame: pl.DataFrame) -> pl.DataFrame:
    """Add include_for_training flag (False for anomaly-tagged rows)."""
    if frame.is_empty():
        return frame
    if "exit_anomaly_flag" not in frame.columns:
        return frame.with_columns(pl.lit(True).alias("include_for_training"))
    return frame.with_columns((~pl.col("exit_anomaly_flag")).alias("include_for_training"))
