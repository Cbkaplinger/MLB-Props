"""Run expanded open-market model diagnostics from built artifacts.

Analyses:
- Edge-bin monotonicity by line/maturity/book.
- Regime drift (correction sign flip rate by segment over time).
- DK vs FD correction deltas by line/price bucket.
- Execution sensitivity (baseline model vs corrected model proxy).

Outputs:
- artifacts/odds_log/open_model_edge_bin_monotonicity.parquet
- artifacts/odds_log/open_model_regime_drift_flips.parquet
- artifacts/odds_log/open_model_dk_fd_correction_deltas.parquet
- artifacts/odds_log/open_model_execution_sensitivity.parquet
- artifacts/odds_log/open_model_deltas_summary.json
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
ODDS_DIR = ROOT / "artifacts" / "odds_log"

ROWS_PATH = ODDS_DIR / "open_proj_calibration_rows.parquet"
CORR_PATH = ODDS_DIR / "line_price_correction_table.parquet"

EDGE_MONO_OUT = ODDS_DIR / "open_model_edge_bin_monotonicity.parquet"
DRIFT_OUT = ODDS_DIR / "open_model_regime_drift_flips.parquet"
DKFD_OUT = ODDS_DIR / "open_model_dk_fd_correction_deltas.parquet"
EXEC_OUT = ODDS_DIR / "open_model_execution_sensitivity.parquet"
SUMMARY_OUT = ODDS_DIR / "open_model_deltas_summary.json"


def _price_bucket_expr(price_col: str) -> pl.Expr:
    p = pl.col(price_col).cast(pl.Float64)
    return (
        pl.when(p <= -170).then(pl.lit("fav_le_-170"))
        .when(p <= -140).then(pl.lit("fav_-169_to_-140"))
        .when(p <= -115).then(pl.lit("fav_-139_to_-115"))
        .when(p <= -105).then(pl.lit("coin_-114_to_-105"))
        .when(p <= 105).then(pl.lit("coin_-104_to_+105"))
        .when(p <= 130).then(pl.lit("dog_+106_to_+130"))
        .when(p <= 160).then(pl.lit("dog_+131_to_+160"))
        .otherwise(pl.lit("dog_gt_+160"))
    )


def _load_rows() -> pl.DataFrame:
    if not ROWS_PATH.exists():
        raise FileNotFoundError(f"Missing {ROWS_PATH}")
    rows = pl.read_parquet(ROWS_PATH).filter(pl.col("actual_over").is_not_null())
    return rows.with_columns(
        _price_bucket_expr("over_odds").alias("over_price_bucket"),
        pl.col("game_date_d").cast(pl.Date),
    )


def _edge_bin_monotonicity(rows: pl.DataFrame) -> pl.DataFrame:
    scoped = rows.filter(pl.col("bookmaker").is_in(["draftkings", "fanduel"])).with_columns(
        pl.col("edge_vs_open_novig")
        .qcut(
            10,
            labels=["q01", "q02", "q03", "q04", "q05", "q06", "q07", "q08", "q09", "q10"],
            allow_duplicates=True,
        )
        .alias("edge_decile")
    )
    bins = (
        scoped.group_by(["bookmaker", "line", "maturity_bucket", "edge_decile"])
        .agg(
            pl.len().alias("n"),
            pl.col("edge_vs_open_novig").mean().alias("mean_edge"),
            pl.col("p_model_over").mean().alias("model_prob"),
            pl.col("actual_over").mean().alias("hit_rate"),
            pl.col("p_over_novig").mean().alias("market_prob"),
        )
        .sort(["bookmaker", "line", "maturity_bucket", "mean_edge"])
    )
    # Monotonicity proxy: first difference in hit_rate over sorted deciles.
    bins = bins.with_columns(
        (pl.col("hit_rate") - pl.col("hit_rate").shift(1))
        .over(["bookmaker", "line", "maturity_bucket"])
        .alias("hit_rate_step"),
    )
    return bins


def _regime_drift_flips(rows: pl.DataFrame, corr: pl.DataFrame) -> pl.DataFrame:
    merged = rows.join(
        corr.select("line", "over_price_bucket", "maturity_bucket", "prob_offset"),
        on=["line", "over_price_bucket", "maturity_bucket"],
        how="left",
    ).with_columns(
        pl.col("prob_offset").fill_null(0.0),
        pl.when(pl.col("prob_offset") > 0)
        .then(pl.lit(1))
        .when(pl.col("prob_offset") < 0)
        .then(pl.lit(-1))
        .otherwise(pl.lit(0))
        .alias("offset_sign"),
    )

    daily = (
        merged.group_by(["line", "over_price_bucket", "maturity_bucket", "game_date_d"])
        .agg(
            pl.len().alias("n"),
            pl.col("actual_over").mean().alias("hit_rate"),
            pl.col("p_model_over").mean().alias("model_prob"),
            pl.col("prob_offset").mean().alias("mean_offset"),
            pl.col("offset_sign").mode().first().alias("dominant_sign"),
        )
        .sort(["line", "over_price_bucket", "maturity_bucket", "game_date_d"])
        .with_columns(
            (pl.col("dominant_sign") != pl.col("dominant_sign").shift(1))
            .over(["line", "over_price_bucket", "maturity_bucket"])
            .fill_null(False)
            .alias("sign_flip"),
        )
    )
    latest_day = daily.select(pl.col("game_date_d").max()).item()
    recent_start = latest_day - timedelta(days=13)
    daily = daily.with_columns((pl.col("game_date_d") >= recent_start).alias("is_recent_14d"))

    return (
        daily.group_by(["line", "over_price_bucket", "maturity_bucket"])
        .agg(
            pl.len().alias("n_days"),
            pl.col("sign_flip").sum().alias("n_sign_flips"),
            (pl.col("sign_flip").sum() / pl.len()).alias("flip_rate"),
            pl.col("is_recent_14d").sum().alias("n_days_recent_14d"),
            pl.col("sign_flip")
            .filter(pl.col("is_recent_14d"))
            .sum()
            .alias("n_sign_flips_recent_14d"),
            (
                pl.col("sign_flip").filter(pl.col("is_recent_14d")).sum()
                / pl.col("is_recent_14d").sum().cast(pl.Float64)
            ).alias("flip_rate_recent_14d"),
            pl.col("mean_offset").mean().alias("avg_offset"),
            pl.col("n").mean().alias("avg_rows_per_day"),
        )
        .with_columns(
            pl.col("flip_rate_recent_14d")
            .fill_nan(0.0)
            .fill_null(0.0)
            .alias("flip_rate_recent_14d")
        )
        .sort(["flip_rate", "n_days"], descending=[True, True])
    )


def _dk_fd_deltas(rows: pl.DataFrame) -> pl.DataFrame:
    scoped = rows.filter(pl.col("bookmaker").is_in(["draftkings", "fanduel"]))
    agg = (
        scoped.group_by(["bookmaker", "line", "over_price_bucket", "maturity_bucket"])
        .agg(
            pl.len().alias("n"),
            pl.col("p_model_over").mean().alias("model_prob"),
            pl.col("actual_over").mean().alias("hit_rate"),
            (pl.col("p_model_over") - pl.col("actual_over")).mean().alias("model_minus_actual"),
        )
    )
    dk = agg.filter(pl.col("bookmaker") == "draftkings").drop("bookmaker").rename(
        {c: f"{c}_dk" for c in agg.columns if c != "bookmaker"}
    )
    fd = agg.filter(pl.col("bookmaker") == "fanduel").drop("bookmaker").rename(
        {c: f"{c}_fd" for c in agg.columns if c != "bookmaker"}
    )
    merged = dk.join(
        fd,
        left_on=["line_dk", "over_price_bucket_dk", "maturity_bucket_dk"],
        right_on=["line_fd", "over_price_bucket_fd", "maturity_bucket_fd"],
        how="inner",
    )
    return merged.with_columns(
        (pl.col("model_minus_actual_dk") - pl.col("model_minus_actual_fd")).alias("gap_dk_minus_fd"),
        (pl.col("n_dk") + pl.col("n_fd")).alias("n_total"),
    ).sort("gap_dk_minus_fd", descending=True)


def _execution_sensitivity(rows: pl.DataFrame, corr: pl.DataFrame) -> pl.DataFrame:
    merged = rows.join(
        corr.select("line", "over_price_bucket", "maturity_bucket", "prob_offset"),
        on=["line", "over_price_bucket", "maturity_bucket"],
        how="left",
    ).with_columns(
        pl.col("prob_offset").cast(pl.Float64).fill_null(0.0).alias("prob_offset"),
        (pl.col("p_model_over") + pl.col("prob_offset")).clip(1e-6, 1 - 1e-6).alias(
            "p_model_corrected"
        ),
    ).with_columns(
        (pl.col("p_model_over") - pl.col("actual_over")).pow(2).alias("brier_base"),
        (pl.col("p_model_corrected") - pl.col("actual_over")).pow(2).alias("brier_corrected"),
    )
    out = (
        merged.group_by(["line", "maturity_bucket"])
        .agg(
            pl.len().alias("n"),
            pl.col("brier_base").mean().alias("brier_base"),
            pl.col("brier_corrected").mean().alias("brier_corrected"),
            (pl.col("brier_base").mean() - pl.col("brier_corrected").mean()).alias(
                "brier_gain_from_correction"
            ),
            pl.col("prob_offset").mean().alias("mean_offset"),
        )
        .sort("brier_gain_from_correction", descending=True)
    )
    return out


def main() -> None:
    rows = _load_rows()
    if not CORR_PATH.exists():
        raise FileNotFoundError(f"Missing {CORR_PATH}")
    corr = pl.read_parquet(CORR_PATH)

    edge = _edge_bin_monotonicity(rows)
    drift = _regime_drift_flips(rows, corr)
    dkfd = _dk_fd_deltas(rows)
    exec_sens = _execution_sensitivity(rows, corr)

    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    edge.write_parquet(EDGE_MONO_OUT)
    drift.write_parquet(DRIFT_OUT)
    dkfd.write_parquet(DKFD_OUT)
    exec_sens.write_parquet(EXEC_OUT)

    summary = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows": int(rows.height),
        "outputs": {
            "edge_monotonicity": str(EDGE_MONO_OUT),
            "regime_drift": str(DRIFT_OUT),
            "dk_fd_deltas": str(DKFD_OUT),
            "execution_sensitivity": str(EXEC_OUT),
        },
        "top_execution_gain_segments": exec_sens.filter(
            pl.col("brier_gain_from_correction").is_not_null() & (pl.col("n") >= 250)
        )
        .sort("brier_gain_from_correction", descending=True)
        .head(10)
        .to_dicts(),
    }
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {EDGE_MONO_OUT}")
    print(f"wrote {DRIFT_OUT}")
    print(f"wrote {DKFD_OUT}")
    print(f"wrote {EXEC_OUT}")
    print(f"wrote {SUMMARY_OUT}")
    print(summary)


if __name__ == "__main__":
    main()
