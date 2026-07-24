"""Leakage-safe rolling / season-to-date batter rates (Polars).

This is the batter-side companion to the per-game table produced by
``batter_features.build_batter_games``. It turns each hitter's game log into
**pregame** K% features: for any game ``G`` every value uses only plate
appearances from earlier calendar dates. Same-day doubleheader games cannot
feed one another, so the features are safe even when both games are priced
before the first one starts.

Two flavors are produced, and they are intentionally kept separate so you can
inspect and validate each on its own:

1. **Season-to-date** (``k_rate_std`` and the vs-LHP / vs-RHP splits):
   an expanding, PA-weighted rate that *resets every season*.
2. **Rolling last-N games** (``*_P{w}``): denominator-weighted rates over the
   previous ``w`` games, allowed to carry across the season boundary because
   they are recent-form signals.

The season-to-date rate is also offered in an **empirical-Bayes shrunk** form
(``k_rate_std_shrunk``) that regresses a small sample toward the league K% for
that season, so April lines are not dominated by a handful of PAs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import polars as pl

# Sort key that guarantees a deterministic within-batter game order.
_ORDER: tuple[str, ...] = ("batter", "game_date", "game_pk")

DEFAULT_WINDOWS: tuple[int, ...] = (5, 10, 20)

# Prior strength (in PA) for empirical-Bayes shrinkage of season-to-date K%.
# ~200 PA is a common stabilization neighborhood for strikeout rate.
DEFAULT_SHRINK_PA: float = 200.0
DEFAULT_FALLBACK_K_RATE: float | None = None

# Extra leakage-safe rates: {feature: (numerator, denominator)}. These feed
# Level 3 opposing-lineup discipline, contact-quality, and batted-ball research
# features. Missing Level 1 count pairs are skipped.
DEFAULT_EXTRA_RATE_STATS: dict[str, tuple[str, str]] = {
    "swstr_rate": ("Whiffs", "Pitches"),   # SwStr%: whiffs per pitch
    "whiff_rate": ("Whiffs", "Swings"),    # Whiff%: whiffs per swing
    "chase_rate": ("Chases", "OutZone"),   # O-Swing%
    "zswing_rate": ("ZSwings", "InZone"),  # Z-Swing%
    "swing_rate": ("Swings", "Pitches"),   # Swing%
    "zcontact_rate": ("ZContacts", "ZSwings"),  # Z-Contact%
    "bb_rate": ("BB", "PA"),               # BB%
    "babip": ("BABIP_num", "BABIP_den"),
    "hard_hit_rate": ("HardHit", "EV_den"),
    "barrel_rate": ("Barrels", "xBA_den"),
    "sweet_spot_rate": ("SweetSpot", "LA_den"),
    "avg_exit_velocity": ("EV_num", "EV_den"),
    "avg_launch_angle": ("LA_num", "LA_den"),
    "xBA": ("xBA_num", "xBA_den"),
    "wOBA": ("wOBA_num", "wOBA_den"),
    "xwOBA": ("xwOBA_num", "wOBA_den"),
    "hr_rate": ("HR", "PA"),
    "fb_rate": ("FB", "BIP"),
    "hr_fb_rate": ("HR", "FB"),
    "pull_air_rate": ("PullAir", "BIP"),
    "rv_per_pitch": ("RV_num", "RV_den"),
}
ROLLING_RATE_STATS: frozenset[str] = frozenset(DEFAULT_EXTRA_RATE_STATS)


def _prior_rate(num: str, den: str, by: list[str]) -> pl.Expr:
    """Expanding rate using only rows *before* the current one (shift-free).

    ``cumulative_sum - current`` is the sum over all prior games within ``by``;
    dividing the two prior sums yields a leakage-safe expanding rate.
    """
    prior_num = pl.col(num).cum_sum().over(by) - pl.col(num)
    prior_den = pl.col(den).cum_sum().over(by) - pl.col(den)
    return (
        pl.when(prior_den > 0)
        .then(prior_num / prior_den)
        .otherwise(None)
    )


def _rolling_rate(num: str, den: str, window: int, min_games: int) -> pl.Expr:
    """PA-weighted rate over the previous ``window`` games (current excluded).

    ``shift(1)`` drops the current game before the rolling sum, so the value is
    known pregame. Carries across seasons by design (recent-form signal).
    """
    roll_num = pl.col(num).shift(1).rolling_sum(window_size=window, min_samples=min_games).over("batter")
    roll_den = pl.col(den).shift(1).rolling_sum(window_size=window, min_samples=min_games).over("batter")
    return (
        pl.when(roll_den > 0)
        .then(roll_num / roll_den)
        .otherwise(None)
    )


def add_leakage_safe_k(
    games: pl.DataFrame,
    windows: Iterable[int] = DEFAULT_WINDOWS,
    min_games: int = 1,
    shrink_pa: float = DEFAULT_SHRINK_PA,
    fallback_k_rate: float = DEFAULT_FALLBACK_K_RATE,
    extra_rate_stats: Mapping[str, tuple[str, str]] | None = None,
) -> pl.DataFrame:
    """Append leakage-safe batter K% (and extra) features to a per-game table.

    Args:
        games: Output of ``batter_features.build_batter_games``. Must carry
            ``batter, game_date, game_pk, PA, K`` and the handedness splits
            ``PA_vL, K_vL, PA_vR, K_vR``.
        windows: Rolling window sizes (in games) for ``k_rate_P{w}``.
        min_games: Minimum prior games required to emit a rolling value.
        shrink_pa: Empirical-Bayes prior strength (in PA) for the shrunk
            season-to-date rate. Set to 0 to skip shrinkage.
        fallback_k_rate: Explicit sourced league prior used only when no
            earlier date exists. If omitted, ``prior_league_k_rate`` from
            Level 1 is used; otherwise the first date remains null.
        extra_rate_stats: Additional ``{feature: (num, den)}`` rates. All are
            emitted season-to-date and over ``windows``. Missing Level 1 count
            pairs are skipped. Pass ``{}`` to skip.

    Returns:
        The input frame (same rows, original order preserved via re-sort) with
        added columns:
            ``season``,
            ``k_rate_std``, ``k_rate_std_vL``, ``k_rate_std_vR``,
            ``k_rate_std_shrunk`` (if ``shrink_pa > 0``),
            ``k_rate_P{w}`` for each window,
            ``{extra}_std`` and ``{extra}_P{w}`` for each available rate,
            plus ``lineup_pa_weight`` derived from prior-date league PA by
            batting-order slot.
    """
    if games.select("batter", "game_pk").is_duplicated().any():
        raise ValueError("games contains duplicate (batter, game_pk) keys")

    windows = list(windows)
    extras = DEFAULT_EXTRA_RATE_STATS if extra_rate_stats is None else extra_rate_stats
    extras = {n: (num, den) for n, (num, den) in extras.items()
              if num in games.columns and den in games.columns}

    df = games.with_columns(pl.col("game_date").dt.year().alias("season")).sort(_ORDER)

    feature_specs: list[tuple[pl.Expr, str]] = [
        (_prior_rate("K", "PA", ["batter", "season"]), "k_rate_std"),
        (_prior_rate("K_vL", "PA_vL", ["batter", "season"]), "k_rate_std_vL"),
        (_prior_rate("K_vR", "PA_vR", ["batter", "season"]), "k_rate_std_vR"),
        *[
            (_prior_rate(num, den, ["batter", "season"]), f"{name}_std")
            for name, (num, den) in extras.items()
        ],
        *[
            (_rolling_rate("K", "PA", w, min_games), f"k_rate_P{w}")
            for w in windows
        ],
        *[
            (_rolling_rate(num, den, w, min_games), f"{name}_P{w}")
            for name, (num, den) in extras.items()
            if name in ROLLING_RATE_STATS
            for w in windows
        ],
    ]
    temporary = [f"__pregame_{index}" for index in range(len(feature_specs))]
    df = df.with_columns(
        expr.alias(column)
        for column, (expr, _name) in zip(temporary, feature_specs, strict=True)
    )
    df = df.with_columns(
        pl.col(column)
        .first()
        .over(["batter", "game_date"])
        .alias(name)
        for column, (_expr, name) in zip(temporary, feature_specs, strict=True)
    ).drop(temporary)

    if shrink_pa and shrink_pa > 0:
        if fallback_k_rate is None and "prior_league_k_rate" in df.columns:
            prior_rates = (
                df["prior_league_k_rate"].drop_nulls().unique().to_list()
            )
            if len(prior_rates) != 1:
                raise ValueError(
                    "prior_league_k_rate must contain exactly one value"
                )
            fallback_k_rate = float(prior_rates[0])
        df = _add_shrunk_std(df, shrink_pa, fallback_k_rate)

    return _add_lineup_opportunity_weight(df).sort(_ORDER)


def _add_lineup_opportunity_weight(df: pl.DataFrame) -> pl.DataFrame:
    """Estimate batting-order opportunity from league games on prior dates.

    The weight is prior-date league-average PA for the hitter's lineup slot.
    Current-date realized PA never contributes, so this can safely distinguish
    leadoff/middle-order opportunity from lower-order opportunity at game time.
    Older/synthetic frames without lineup slots remain usable with equal weight.
    """
    required = {"lineup_slot", "is_initial_lineup", "PA", "game_date"}
    if not required.issubset(df.columns):
        return df.with_columns(pl.lit(1.0).alias("lineup_pa_weight"))

    daily = (
        df.filter(
            pl.col("is_initial_lineup")
            & pl.col("lineup_slot").is_between(1, 9, closed="both")
        )
        .group_by("game_date", "lineup_slot")
        .agg(
            pl.col("PA").sum().alias("_slot_pa"),
            pl.len().alias("_slot_starts"),
        )
        .sort(["lineup_slot", "game_date"])
        .with_columns(
            pl.col("_slot_pa")
            .cum_sum()
            .shift(1)
            .over("lineup_slot")
            .alias("_prior_slot_pa"),
            pl.col("_slot_starts")
            .cum_sum()
            .shift(1)
            .over("lineup_slot")
            .alias("_prior_slot_starts"),
        )
        .with_columns(
            pl.when(pl.col("_prior_slot_starts") > 0)
            .then(pl.col("_prior_slot_pa") / pl.col("_prior_slot_starts"))
            .otherwise(1.0)
            .alias("lineup_pa_weight")
        )
        .select("game_date", "lineup_slot", "lineup_pa_weight")
    )
    return df.join(
        daily,
        on=["game_date", "lineup_slot"],
        how="left",
        validate="m:1",
    ).with_columns(pl.col("lineup_pa_weight").fill_null(1.0))


def _add_shrunk_std(
    df: pl.DataFrame,
    shrink_pa: float,
    fallback_k_rate: float | None,
) -> pl.DataFrame:
    """Shrink season-to-date K% toward league K% through the previous date.

    ``k_rate_std_shrunk = (priorK + shrink_pa * lg_k) / (priorPA + shrink_pa)``

    The league prior is cumulative across all games strictly before the current
    date. Same-day and future outcomes are excluded. The first date uses the
    explicitly sourced ``fallback_k_rate`` or remains null.
    """
    league = (
        df.group_by("game_date")
        .agg(
            pl.col("K").sum().alias("_daily_k"),
            pl.col("PA").sum().alias("_daily_pa"),
        )
        .sort("game_date")
        .with_columns(
            pl.col("_daily_k").cum_sum().shift(1).alias("_prior_lg_k"),
            pl.col("_daily_pa").cum_sum().shift(1).alias("_prior_lg_pa"),
        )
        .with_columns(
            pl.when(pl.col("_prior_lg_pa") > 0)
            .then(pl.col("_prior_lg_k") / pl.col("_prior_lg_pa"))
            .otherwise(pl.lit(fallback_k_rate))
            .alias("lg_k")
        )
        .select("game_date", "lg_k")
    )

    prior_k = pl.col("K").cum_sum().over(["batter", "season"]) - pl.col("K")
    prior_pa = pl.col("PA").cum_sum().over(["batter", "season"]) - pl.col("PA")

    return (
        df.join(league, on="game_date", how="left")
        .with_columns(
            prior_k.alias("_prior_batter_k"),
            prior_pa.alias("_prior_batter_pa"),
        )
        .with_columns(
            pl.col("_prior_batter_k")
            .first()
            .over(["batter", "game_date"]),
            pl.col("_prior_batter_pa")
            .first()
            .over(["batter", "game_date"]),
        )
        .with_columns(
            (
                (
                    pl.col("_prior_batter_k")
                    + shrink_pa * pl.col("lg_k")
                )
                / (pl.col("_prior_batter_pa") + shrink_pa)
            ).alias("k_rate_std_shrunk")
        )
        .drop("lg_k", "_prior_batter_k", "_prior_batter_pa")
    )
