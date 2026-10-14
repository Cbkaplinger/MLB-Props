"""P1 harness v2 step 2+3: strictly-prior features + fixed chronological splits.

v2 corrections vs v1 (owner rulings 2026-10-13):
  2. OPENING-DAY PRIOR: the v1 backward-filled same-date lg_rate on 2022-04-07
     (508 rows) is REMOVED. Day-1 league prior is now a documented fixed prior:
       - if eligible PAs exist on 2022-04-01..2022-04-06 in the raw data, the
         league K rate of those PAs (source_type "external_fixed_prior");
       - else the fixed constant 0.2245, derived from the 2022-2025 pooled K
         rate and explicitly labeled a fixed prior NOT observed from the
         evaluated period (source_type "external_fixed_prior").
     Every row records a non-null source_type; source dates are never null.
  3. ALL-PITCHERS POLICY: kept; pitcher_role is carried through and slice
     counts per split are reported.
  4. Splits: TRAIN / DEV_VALIDATION / EVAL. The v1 "CALIBRATION" split is
     relabeled "development/validation"; NO calibration is fitted anywhere.
  Leakage validator: rows with NULL source dates now FAIL (v1 skipped them).
     Cold-start pitcher/batter rows record source_type
     "league_prior_no_entity_history" with the league source date, so no
     source date is ever null.

For each PA, computes pitcher and batter shrunk K rates using ONLY PAs with
game_date < the PA's game_date (strict prior, date granularity).

Shrunk rate: (k_prior + W * lg_prior) / (n_prior + W), W in {150, 500},
lg_prior = league K rate through the prior activity date (event-weighted).

Outputs:
  data/features.parquet   keyed to pa_table (game_pk, at_bat_number, batter)
  reports/leakage_check.json
  reports/split_counts.json
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl

HARNESS = Path(__file__).resolve().parent.parent
OUT_DIR = HARNESS / "data"
REPORTS = HARNESS / "reports"

W_LEVELS = [150, 500]
LEAK_SAMPLE_N = 10_000
LEAK_SEED = 42

# Owner-ruled fixed prior for the 2022 opening day (2022-04-07): the league K
# rate 2022-04-01..2022-04-06 has no eligible PAs in the raw data (2022 regular
# season starts 2022-04-07), so this FIXED constant is used. 0.2245 = the
# 2022-2025 pooled K rate (164,467 / 732,552). It is a fixed prior, NOT a rate
# observed from the evaluated period, and is labeled external_fixed_prior.
FIXED_LG_PRIOR = 0.2245
FIXED_LG_PRIOR_SRC_DATE = pl.date(2022, 4, 6)
FIXED_LG_PRIOR_TYPE = "external_fixed_prior"

TRAIN_END = "2025-01-01"
DEV_END = "2025-07-01"
SPLIT_DEFINITION = {
    "TRAIN": "game_date < 2025-01-01",
    "DEV_VALIDATION": "2025-01-01 <= game_date < 2025-07-01 (development/validation; "
    "v1 'CALIBRATION' relabeled; NO calibration is fitted)",
    "EVAL": "2025-07-01 <= game_date <= 2026-12-31 (2026 rows reserved out of the "
    "PA table; 2026 is retrospective validation, NOT an untouched holdout)",
}

SOURCE_TYPE_ENTITY = "entity_history"
SOURCE_TYPE_COLD = "league_prior_no_entity_history"
SOURCE_TYPE_LEAGUE = "league_history"

SOURCE_SPECS = [
    ("pitcher", "src_date_pitcher", "n_prior_pitcher", "src_type_pitcher"),
    ("batter", "src_date_batter", "n_prior_batter", "src_type_batter"),
    ("league", "lg_src_date", "lg_n_prior", "src_type_lg"),
]


def daily_cumulative(pa: pl.DataFrame, entity: str) -> pl.DataFrame:
    """Per-entity daily K sums -> cumulative through end of day -> shifted to
    strict-prior values plus the source date of that cumulative."""
    daily = (
        pa.group_by(entity, "game_date")
        .agg(k=pl.col("y").sum(), n=pl.len())
        .sort(entity, "game_date")
        .with_columns(
            pl.col("k").cum_sum().over(entity).alias("cum_k"),
            pl.col("n").cum_sum().over(entity).alias("cum_n"),
        )
        .with_columns(
            pl.col("cum_k").shift(1).over(entity).fill_null(0).alias("prior_k"),
            pl.col("cum_n").shift(1).over(entity).fill_null(0).alias("prior_n"),
            pl.col("game_date").shift(1).over(entity).alias("src_date"),
        )
        .drop("k", "n", "cum_k", "cum_n")
    )
    return daily.sort("game_date", entity)


def league_daily(pa: pl.DataFrame) -> pl.DataFrame:
    """League-wide daily cumulative K rate, shifted to strict prior. The first
    activity day's null is REPLACED by the owner-ruled fixed prior (never
    backward-filled from same-date data)."""
    daily = (
        pa.group_by("game_date")
        .agg(k=pl.col("y").sum(), n=pl.len())
        .sort("game_date")
        .with_columns(
            pl.col("k").cum_sum().alias("cum_k"),
            pl.col("n").cum_sum().alias("cum_n"),
        )
        .with_columns(
            pl.col("cum_k").shift(1).alias("lg_k_prior"),
            pl.col("cum_n").shift(1).alias("lg_n_prior"),
            pl.col("game_date").shift(1).alias("lg_src_date"),
        )
        .drop("k", "n", "cum_k", "cum_n")
        .with_columns(
            pl.when(pl.col("lg_n_prior") > 0)
            .then(pl.col("lg_k_prior") / pl.col("lg_n_prior"))
            .otherwise(pl.lit(FIXED_LG_PRIOR))
            .alias("lg_rate")
        )
        .with_columns(
            pl.col("lg_src_date").fill_null(FIXED_LG_PRIOR_SRC_DATE),
            pl.col("lg_n_prior").fill_null(0),
            pl.when(pl.col("lg_src_date").is_null())
            .then(pl.lit(FIXED_LG_PRIOR_TYPE))
            .otherwise(pl.lit(SOURCE_TYPE_LEAGUE))
            .alias("src_type_lg"),
        )
        .drop("lg_k_prior")
    )
    return daily


def shrunk(k: pl.Expr, n: pl.Expr, lg: pl.Expr, w: int) -> pl.Expr:
    return ((k.cast(pl.Float64) + w * lg) / (n.cast(pl.Float64) + w)).alias(
        f"p_w{w}"
    )


def validate_no_future_leakage(features_df: pl.DataFrame) -> None:
    """Hard guard (v2): every source date must be non-null and strictly less
    than its game_date, and every row must record a non-null source_type.

    v1 skipped rows with null source dates; v2 FAILS on them (owner ruling:
    every fallback must record its source_type; null source dates FAIL).
    Raises AssertionError listing every violating entity.
    """
    violations = []
    for label, src_col, _n_col, type_col in SOURCE_SPECS:
        null_dates = features_df.filter(pl.col(src_col).is_null())
        if null_dates.height > 0:
            violations.append(
                {
                    "entity": label,
                    "violation": "null_source_date",
                    "n_rows": null_dates.height,
                }
            )
        null_types = features_df.filter(pl.col(type_col).is_null())
        if null_types.height > 0:
            violations.append(
                {
                    "entity": label,
                    "violation": "null_source_type",
                    "n_rows": null_types.height,
                }
            )
        bad = features_df.filter(
            pl.col(src_col).is_not_null() & (pl.col(src_col) >= pl.col("game_date"))
        )
        if bad.height > 0:
            violations.append(
                {
                    "entity": label,
                    "violation": "src_date_ge_game_date",
                    "n_rows": bad.height,
                    "max_src_date": str(bad[src_col].max()),
                    "min_game_date": str(bad["game_date"].min()),
                }
            )
    if violations:
        raise AssertionError(f"future leakage detected: {violations}")


def leakage_check(feat: pl.DataFrame) -> dict:
    """Assert every row has non-null source_type, and max(feature source date)
    < game_date with NO null source dates, on a 10k-row sample."""
    sample = feat.sample(n=min(LEAK_SAMPLE_N, feat.height), seed=LEAK_SEED)
    violations = []
    checks = {}
    for label, src_col, n_col, type_col in SOURCE_SPECS:
        with_src = sample.filter(pl.col(src_col).is_not_null())
        bad = sample.filter(pl.col(src_col) >= pl.col("game_date")).height
        n_null = sample.filter(pl.col(src_col).is_null()).height
        n_zero = sample.filter(pl.col(n_col) == 0).height
        checks[label] = {
            "rows_with_source": with_src.height,
            "violations_src_ge_game_date": bad,
            "null_source_dates": n_null,
            "rows_with_no_prior_support": n_zero,
            "source_types": sample.group_by(type_col).agg(n=pl.len()).sort(type_col).to_dicts(),
        }
        if bad > 0 or n_null > 0:
            violations.append(label)
    result = {
        "sample_size": sample.height,
        "seed": LEAK_SEED,
        "assertion": "every row: non-null source_type AND max(feature source date) "
        "< game_date; null source dates FAIL (v2)",
        "fixed_lg_prior": {
            "value": FIXED_LG_PRIOR,
            "source_type": FIXED_LG_PRIOR_TYPE,
            "src_date": "2022-04-06",
            "note": "applied to 2022-04-07 rows (no eligible PAs 2022-04-01..06 in raw data)",
        },
        "checks": checks,
        "passed": len(violations) == 0,
        "violated": violations,
    }
    if not result["passed"]:
        raise AssertionError(f"leakage check failed: {result}")
    return result


def main() -> None:
    pa = pl.read_parquet(OUT_DIR / "pa_table.parquet")

    lg = league_daily(pa)

    p_daily = daily_cumulative(pa, "pitcher").rename(
        {"prior_k": "pk", "prior_n": "pn", "src_date": "src_date_pitcher"}
    )
    b_daily = daily_cumulative(pa, "batter").rename(
        {"prior_k": "bk", "prior_n": "bn", "src_date": "src_date_batter"}
    )

    keys = ["game_pk", "at_bat_number", "batter"]

    feat = (
        pa.select(*keys, "game_date", "pitcher", "pitcher_role")
        .sort("game_date")
        .join_asof(
            p_daily,
            left_on="game_date",
            right_on="game_date",
            by="pitcher",
            strategy="backward",
        )
        .sort("game_date")
        .join_asof(
            b_daily.select(
                pl.col("game_date"), pl.col("batter").alias("batter_key"),
                "bk", "bn", "src_date_batter",
            ),
            left_on="game_date",
            right_on="game_date",
            by_left="batter",
            by_right="batter_key",
            strategy="backward",
        )
        .sort("game_date")
        .join_asof(
            lg.select("game_date", "lg_rate", "lg_n_prior", "lg_src_date", "src_type_lg"),
            left_on="game_date",
            right_on="game_date",
            strategy="backward",
        )
    )

    # Entity source types: entity_history when the entity has prior PAs,
    # league_prior_no_entity_history (cold start) otherwise, with the league
    # source date so no source date is ever null. Cold-start shrunk rates
    # equal lg_rate exactly ((0 + W*lg)/(0 + W) = lg).
    feat = (
        feat.with_columns(
            *[shrunk(pl.col("pk"), pl.col("pn"), pl.col("lg_rate"), w) for w in W_LEVELS]
        )
        .rename({"p_w150": "p_pitcher_prior_w150", "p_w500": "p_pitcher_prior_w500"})
        .with_columns(
            *[shrunk(pl.col("bk"), pl.col("bn"), pl.col("lg_rate"), w) for w in W_LEVELS]
        )
        .rename({"p_w150": "p_batter_prior_w150", "p_w500": "p_batter_prior_w500"})
        .with_columns(
            (pl.col("pn") == 0).fill_null(True).alias("cold_start_pitcher"),
            (pl.col("bn") == 0).fill_null(True).alias("cold_start_batter"),
        )
        .with_columns(
            (pl.col("cold_start_pitcher") | pl.col("cold_start_batter"))
            .cast(pl.Int8)
            .alias("cold_start")
        )
        .with_columns(
            pl.when(pl.col("pn") == 0)
            .then(pl.lit(SOURCE_TYPE_COLD))
            .otherwise(pl.lit(SOURCE_TYPE_ENTITY))
            .alias("src_type_pitcher"),
            pl.when(pl.col("bn") == 0)
            .then(pl.lit(SOURCE_TYPE_COLD))
            .otherwise(pl.lit(SOURCE_TYPE_ENTITY))
            .alias("src_type_batter"),
        )
        .with_columns(
            pl.col("src_date_pitcher").fill_null(pl.col("lg_src_date")),
            pl.col("src_date_batter").fill_null(pl.col("lg_src_date")),
        )
        .rename({"pn": "n_prior_pitcher", "bn": "n_prior_batter"})
        .select(
            *keys,
            "game_date",
            "p_pitcher_prior_w150",
            "p_batter_prior_w150",
            "p_pitcher_prior_w500",
            "p_batter_prior_w500",
            "lg_rate",
            "n_prior_pitcher",
            "n_prior_batter",
            "cold_start",
            "pitcher_role",
            "src_date_pitcher",
            "src_date_batter",
            "lg_src_date",
            "lg_n_prior",
            "src_type_pitcher",
            "src_type_batter",
            "src_type_lg",
        )
    )

    # full-frame hard guard (v2: nulls FAIL), then the sampled report
    validate_no_future_leakage(feat)
    leak = leakage_check(feat)
    (REPORTS / "leakage_check.json").write_text(json.dumps(leak, indent=2, default=str))

    # fixed chronological splits; v1 CALIBRATION relabeled DEV_VALIDATION
    feat = feat.with_columns(
        pl.when(pl.col("game_date") < pl.date(2025, 1, 1))
        .then(pl.lit("TRAIN"))
        .when(pl.col("game_date") < pl.date(2025, 7, 1))
        .then(pl.lit("DEV_VALIDATION"))
        .otherwise(pl.lit("EVAL"))
        .alias("split")
    )

    feat.write_parquet(OUT_DIR / "features.parquet")

    counts = feat.group_by("split").agg(n=pl.len()).sort("split")
    slice_counts = (
        feat.group_by("split", "pitcher_role")
        .agg(n=pl.len())
        .sort("split", "pitcher_role")
    )
    split_counts = {
        "definition": SPLIT_DEFINITION,
        "counts": {r["split"]: r["n"] for r in counts.to_dicts()},
        "pitcher_role_slices": {
            f"{r['split']}/{r['pitcher_role']}": r["n"] for r in slice_counts.to_dicts()
        },
        "note": "EVAL here contains only 2025-07-01..2025-12-31 rows because the PA "
        "table covers 2022-2025; 2026 is reserved and joins EVAL retrospectively later. "
        "pitcher_role: starter_pa = pitcher is the side's first pitcher of record "
        "(opener-inclusive); reliever_pa otherwise.",
    }
    (REPORTS / "split_counts.json").write_text(json.dumps(split_counts, indent=2))

    print("leakage check:", json.dumps(leak, indent=2, default=str))
    print("split counts:", json.dumps(split_counts["counts"], indent=2))
    print("pitcher_role slices:", json.dumps(split_counts["pitcher_role_slices"], indent=2))
    print("null feature values on TRAIN+DEV:",
          feat.filter(pl.col("split") != "EVAL")
          .select(pl.exclude("src_type_pitcher", "src_type_batter", "src_type_lg", "split"))
          .null_count().to_dicts())


if __name__ == "__main__":
    main()
