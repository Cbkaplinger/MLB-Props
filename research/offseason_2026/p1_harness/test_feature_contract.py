"""Executable checks for FEATURE_CONTRACT.md (P1 harness, frozen logistic).

(a) mutating current-game outcomes of a PA's own game cannot change that PA's
    pregame features;
(b) appending a future game cannot change earlier rows' features;
(c) on the executed artifact data/features.parquet, the declared v2 schema
    holds: every source date is non-null and strictly precedes its game_date,
    every row records a non-null source_type, and cold-start rows fall back
    to the league rate exactly;
(d) on the executed artifact data/eval_predictions.parquet, all four declared
    prediction columns (A, log5, logistic B, C placeholder) are present and
    non-null, and the three contract candidates (reference A, log5, logistic
    B) predict the identical EVAL key set.

(a) and (b) rebuild features from synthetic PA tables using the executed
builder primitives imported from scripts/build_features.py, mirroring the
declared v2 production schema assembly in its main() (league_daily with the
owner-ruled fixed prior + strict-prior daily cumulatives + shrunk rates +
v2 src_type derivation + null-date fills + pitcher_role carry-through +
fixed chronological split) exactly, and additionally assert the schema and
source-provenance contract independently (league-rate recomputation,
source-date precedence, source-type/support agreement). The harness modules
are imported from the current checkout via file-relative paths only; the
tests assert the imported module resolved inside this checkout (never a
path fallback outside the repo) and both modules are import-time
side-effect-free.

(c) and (d) need the external-only executed parquets declared in conftest.py
(EXPECTED_ARTIFACTS, sha256-pinned). They SKIP on the default portable lane
when the artifact root is absent, and FAIL on missing or hash-mismatched
inputs in the required-artifact lane (`pytest -m integration`); malformed
data or failed assertions never become skips.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import polars as pl
import pytest

HARNESS = Path(__file__).resolve().parent
REPO_ROOT = HARNESS.parents[2]
sys.path.insert(0, str(HARNESS / "scripts"))

import build_features as bf  # noqa: E402

# Declared v2 production schema: exactly the final .select(...) of
# scripts/build_features.py main(), plus the `split` column appended by
# main() after the leakage guard. Order-sensitive on purpose: the executed
# artifact features.parquet must carry these columns in this order.
DECLARED_V2_SCHEMA = [
    "game_pk",
    "at_bat_number",
    "batter",
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
    "split",
]

KEYS = ["game_pk", "at_bat_number", "batter"]


def test_harness_import_resolves_inside_checkout() -> None:
    """The builder under test is THIS checkout's file, never a path fallback."""
    mod_path = Path(bf.__file__).resolve()
    assert mod_path.is_relative_to(REPO_ROOT), (
        f"imported build_features from outside the checkout: {mod_path}"
    )
    assert mod_path == HARNESS / "scripts" / "build_features.py"


def assert_declared_v2_contract(feat: pl.DataFrame) -> None:
    """Schema + source-provenance assertions shared by (a)/(b) and (c).

    Independent of the builder's own validators: the league rate, source
    dates, and source types are re-derived from the PA table / frame itself.
    """
    assert feat.columns == DECLARED_V2_SCHEMA, (
        f"declared v2 schema mismatch: {feat.columns}"
    )

    # -- source dates: non-null and strictly before game_date (v2: null FAILs)
    for src_col in ["src_date_pitcher", "src_date_batter", "lg_src_date"]:
        nulls = feat.filter(pl.col(src_col).is_null())
        assert nulls.height == 0, f"{src_col}: {nulls.height} null source dates"
        bad = feat.filter(pl.col(src_col) >= pl.col("game_date"))
        assert bad.height == 0, (
            f"{src_col}: {bad.height} rows with source date >= game_date"
        )

    # -- source types: non-null and drawn from the declared value sets
    for type_col in ["src_type_pitcher", "src_type_batter"]:
        allowed = {bf.SOURCE_TYPE_ENTITY, bf.SOURCE_TYPE_COLD}
        seen = set(feat[type_col].unique().to_list())
        assert seen <= allowed, f"{type_col}: undeclared values {seen - allowed}"
    lg_seen = set(feat["src_type_lg"].unique().to_list())
    assert lg_seen <= {bf.SOURCE_TYPE_LEAGUE, bf.FIXED_LG_PRIOR_TYPE}, (
        f"src_type_lg: undeclared values {lg_seen - {bf.SOURCE_TYPE_LEAGUE, bf.FIXED_LG_PRIOR_TYPE}}"
    )

    # -- entity source type <-> support agreement
    for n_col, type_col in [
        ("n_prior_pitcher", "src_type_pitcher"),
        ("n_prior_batter", "src_type_batter"),
    ]:
        mismatch = feat.filter(
            (pl.col(n_col) > 0) & (pl.col(type_col) != bf.SOURCE_TYPE_ENTITY)
            | (pl.col(n_col) == 0) & (pl.col(type_col) != bf.SOURCE_TYPE_COLD)
        )
        assert mismatch.height == 0, (
            f"{type_col} disagrees with {n_col} on {mismatch.height} rows"
        )

    # -- cold-start fallback: zero-support entities use the league rate and
    #    league source date, and the shrunk rate equals lg_rate exactly
    #    ((0 + W*lg) / (0 + W) = lg); flag agrees with support.
    for n_col, rate_col, src_col, type_col in [
        ("n_prior_pitcher", "p_pitcher_prior_w150", "src_date_pitcher", "src_type_pitcher"),
        ("n_prior_batter", "p_batter_prior_w150", "src_date_batter", "src_type_batter"),
    ]:
        cold = feat.filter(pl.col(n_col) == 0)
        if cold.height:
            drift = (cold[rate_col] - cold["lg_rate"]).abs().max()
            assert drift <= 1e-12, f"cold rows {rate_col} != lg_rate (max {drift})"
            assert (cold[src_col] == cold["lg_src_date"]).all(), (
                f"cold rows {src_col} != lg_src_date"
            )
            assert (cold[type_col] == bf.SOURCE_TYPE_COLD).all()
    flag = (
        (pl.col("n_prior_pitcher") == 0) | (pl.col("n_prior_batter") == 0)
    ).cast(pl.Int8)
    flag_ok = feat.select(
        (pl.col("cold_start") == flag).all().alias("ok")
    )["ok"][0]
    assert bool(flag_ok), "cold_start flag disagrees with support"


def assert_league_rate_independent(feat: pl.DataFrame, pa: pl.DataFrame) -> None:
    """Recompute the declared league-prior semantics from the PA table without
    calling bf.league_daily, and compare to the feature column per game_date.

    Declared v2 semantics: strict-prior event-weighted league K rate; day-1
    rows take the owner-ruled fixed prior 0.2245 (external_fixed_prior,
    source date 2022-04-06), never a same-date backward fill.
    """
    daily = (
        pa.group_by("game_date")
        .agg(k=pl.col("y").sum(), n=pl.len())
        .sort("game_date")
        .with_columns(
            pl.col("k").cum_sum().alias("ck"),
            pl.col("n").cum_sum().alias("cn"),
        )
        .with_columns(
            (pl.col("ck") - pl.col("k")).alias("lk"),
            (pl.col("cn") - pl.col("n")).alias("ln"),
            pl.col("game_date").shift(1).alias("prev_activity_date"),
        )
        .with_columns(
            pl.when(pl.col("ln") > 0)
            .then(pl.col("lk") / pl.col("ln"))
            .otherwise(pl.lit(bf.FIXED_LG_PRIOR))
            .alias("lg_rate_expected")
        )
        .with_columns(
            pl.col("prev_activity_date").fill_null(bf.FIXED_LG_PRIOR_SRC_DATE).alias(
                "lg_src_date_expected"
            ),
            pl.when(pl.col("ln") > 0)
            .then(pl.lit(bf.SOURCE_TYPE_LEAGUE))
            .otherwise(pl.lit(bf.FIXED_LG_PRIOR_TYPE))
            .alias("src_type_lg_expected"),
            pl.col("ln").alias("lg_n_prior_expected"),
        )
    )
    check = feat.select(
        "game_date", "lg_rate", "lg_src_date", "lg_n_prior", "src_type_lg"
    ).unique(subset=["game_date"]).join(
        daily.select(
            "game_date",
            "lg_rate_expected",
            "lg_src_date_expected",
            "lg_n_prior_expected",
            "src_type_lg_expected",
        ),
        on="game_date",
        how="inner",
    )
    unmatched = feat.select("game_date").unique().join(
        daily.select("game_date"), on="game_date", how="anti"
    )
    assert unmatched.height == 0, "feature game_date missing from the "
    "independent league recompute"
    drift = (check["lg_rate"] - check["lg_rate_expected"]).abs().max()
    assert drift <= 1e-12, f"lg_rate deviates from independent recompute (max {drift})"
    assert (check["lg_src_date"] == check["lg_src_date_expected"]).all(), (
        "lg_src_date deviates from declared strict-prior / fixed-prior rule"
    )
    assert (check["lg_n_prior"] == check["lg_n_prior_expected"]).all()
    assert (check["src_type_lg"] == check["src_type_lg_expected"]).all()


def assemble_features(pa: pl.DataFrame) -> pl.DataFrame:
    """Mirror build_features.main() assembly on a synthetic PA table,
    producing exactly the declared v2 production schema."""
    lg = bf.league_daily(pa)
    p_daily = bf.daily_cumulative(pa, "pitcher").rename(
        {"prior_k": "pk", "prior_n": "pn", "src_date": "src_date_pitcher"}
    )
    b_daily = bf.daily_cumulative(pa, "batter").rename(
        {"prior_k": "bk", "prior_n": "bn", "src_date": "src_date_batter"}
    )

    feat = (
        pa.select(*KEYS, "game_date", "pitcher", "pitcher_role")
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

    feat = (
        feat.with_columns(
            *[bf.shrunk(pl.col("pk"), pl.col("pn"), pl.col("lg_rate"), w) for w in bf.W_LEVELS]
        )
        .rename({"p_w150": "p_pitcher_prior_w150", "p_w500": "p_pitcher_prior_w500"})
        .with_columns(
            *[bf.shrunk(pl.col("bk"), pl.col("bn"), pl.col("lg_rate"), w) for w in bf.W_LEVELS]
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
            .then(pl.lit(bf.SOURCE_TYPE_COLD))
            .otherwise(pl.lit(bf.SOURCE_TYPE_ENTITY))
            .alias("src_type_pitcher"),
            pl.when(pl.col("bn") == 0)
            .then(pl.lit(bf.SOURCE_TYPE_COLD))
            .otherwise(pl.lit(bf.SOURCE_TYPE_ENTITY))
            .alias("src_type_batter"),
        )
        .with_columns(
            pl.col("src_date_pitcher").fill_null(pl.col("lg_src_date")),
            pl.col("src_date_batter").fill_null(pl.col("lg_src_date")),
        )
        .rename({"pn": "n_prior_pitcher", "bn": "n_prior_batter"})
        .select(*DECLARED_V2_SCHEMA[:-1])  # declared schema minus `split`
    )
    bf.validate_no_future_leakage(feat)

    # fixed chronological splits (main(): v1 CALIBRATION relabeled)
    return feat.with_columns(
        pl.when(pl.col("game_date") < pl.date(2025, 1, 1))
        .then(pl.lit("TRAIN"))
        .when(pl.col("game_date") < pl.date(2025, 7, 1))
        .then(pl.lit("DEV_VALIDATION"))
        .otherwise(pl.lit("EVAL"))
        .alias("split")
    )


def synthetic_pa() -> pl.DataFrame:
    """Four dates, two pitchers, two batters; a PA of interest on date 2.

    pitcher 101 opens (its side's first pitcher of record on its dates ->
    starter_pa); pitcher 102 enters later -> reliever_pa. The role split is
    carried through unchanged by the declared v2 assembly.
    """
    rows = []
    pk = 100
    for d in [date(2024, 4, 1), date(2024, 4, 2), date(2024, 4, 3), date(2024, 4, 4)]:
        ab = 0
        for pitcher in [101, 102]:
            for batter in [201, 202]:
                for _ in range(3):
                    ab += 1
                    rows.append(
                        {
                            "game_pk": pk,
                            "at_bat_number": ab,
                            "batter": batter,
                            "pitcher": pitcher,
                            "game_date": d,
                            "pitcher_role": "starter_pa" if pitcher == 101 else "reliever_pa",
                            "y": (ab + pk) % 2,
                        }
                    )
        pk += 1
    return pl.DataFrame(rows)


def pa_of_interest(pa: pl.DataFrame) -> dict:
    """First PA of pitcher 101 vs batter 201 on the table's second date."""
    row = (
        pa.filter(pl.col("game_date") == date(2024, 4, 2))
        .filter((pl.col("pitcher") == 101) & (pl.col("batter") == 201))
        .sort("at_bat_number")
        .head(1)
    )
    return row.to_dicts()[0]


def test_a_own_game_outcome_mutation_cannot_change_pregame_features() -> None:
    """(a) flipping y inside the PA's own game leaves that PA's entire declared
    v2 feature row (rates, league prior, support, role, source dates/types,
    split) fixed."""
    pa = synthetic_pa()
    target = pa_of_interest(pa)
    base = assemble_features(pa).filter(
        (pl.col("game_pk") == target["game_pk"])
        & (pl.col("at_bat_number") == target["at_bat_number"])
        & (pl.col("batter") == target["batter"])
    )

    mutated = pa.with_columns(
        pl.when(pl.col("game_pk") == target["game_pk"])
        .then(1 - pl.col("y"))
        .otherwise(pl.col("y"))
        .alias("y")
    )
    after = assemble_features(mutated).filter(
        (pl.col("game_pk") == target["game_pk"])
        & (pl.col("at_bat_number") == target["at_bat_number"])
        & (pl.col("batter") == target["batter"])
    )

    assert base.height == 1 and after.height == 1
    assert_declared_v2_contract(base)
    assert_league_rate_independent(base, pa)
    assert base.equals(after), (
        "own-game mutation changed the PA's declared v2 feature row"
    )


def test_b_future_game_append_cannot_change_earlier_rows() -> None:
    """(b) appending a later-dated game leaves every earlier row's full
    declared v2 feature record fixed."""
    pa = synthetic_pa()
    base = assemble_features(pa).sort(*KEYS)
    assert_declared_v2_contract(base)
    assert_league_rate_independent(base, pa)

    future_game = pa.head(3).to_dicts()
    for r in future_game:
        r["game_pk"] = 999
        r["game_date"] = date(2024, 5, 1)
        r["y"] = 1
    appended = pl.concat([pa, pl.DataFrame(future_game)])
    after = assemble_features(appended).sort(*KEYS)

    joined = base.join(after, on=KEYS, suffix="_new")
    assert joined.height == base.height
    compare_cols = [c for c in DECLARED_V2_SCHEMA if c not in KEYS]
    for col in compare_cols:
        same = joined.select(
            (pl.col(col) == pl.col(f"{col}_new")).all().alias("eq")
        )["eq"][0]
        assert bool(same), f"append changed earlier rows' {col}"


@pytest.mark.integration
def test_c_executed_artifact_source_dates_strictly_precede_game_date(
    require_artifact,
) -> None:
    """(c) full-frame declared-v2 contract on the executed features.parquet."""
    feat = pl.read_parquet(require_artifact("data/features.parquet"))
    assert feat.columns == DECLARED_V2_SCHEMA, (
        f"executed features schema != declared v2 schema: {feat.columns}"
    )
    # v2 hard guard: null source dates/types FAIL; strict precedence enforced
    bf.validate_no_future_leakage(feat)
    assert_declared_v2_contract(feat)


@pytest.mark.integration
def test_d_eval_prediction_key_sets_identical_across_candidates(
    require_artifact,
) -> None:
    """(d) all four declared prediction columns are non-null and reference A,
    log5, and logistic B share one EVAL key set."""
    ev = pl.read_parquet(require_artifact("data/eval_predictions.parquet"))
    assert ev.height > 0
    pred_cols = {
        "A_reference": "pred_A_reference",
        "B_logreg": "pred_B_logreg",
        "C_two_shrinkage_placeholder": "pred_C_two_shrinkage_placeholder",
        "LOG5_reference": "pred_LOG5_reference",
    }
    for name, col in pred_cols.items():
        assert col in ev.columns, f"missing {col} for {name}"
        assert ev[col].null_count() == 0, f"{name}: {ev[col].null_count()} nulls"
    assert ev["y"].null_count() == 0, "null labels in eval_predictions"
    # identical key set == every key carries all three contract predictions
    assert ev.select(*KEYS).n_unique() == ev.height, "duplicate EVAL keys"
