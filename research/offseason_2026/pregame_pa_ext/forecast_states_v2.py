"""Forecast-cutoff state construction v2 (states-v2-forecast-cutoff-v1).

VERSIONED CORRECTION of the legacy as-of-activity state boundary,
adopted by architect decision after the published row-presence
reproducer (6b64d0d): for a prediction request with cutoff t, prior
state must aggregate ALL eligible observations with game_date strictly
before t within the declared history window, regardless of whether the
source carries a row on or after the target date.

Legacy construction (adapter.entity_daily_state + backward as-of) is
preserved UNCHANGED for historical results; this module is the
separately identified corrected path for the new baseline. Shrinkage
(w150) and EW decay (90d) settings are unchanged -- only the cutoff
semantics differ. Construction reuses the frozen entity/league state
arithmetic over the explicitly truncated history (rows strictly before
each cutoff) and relabels the resulting state row to the cutoff date,
so the frozen backward as-of in adapter.attach_prior_features matches
exactly one row per (entity, cutoff) and the prior columns carry the
FULL pre-cutoff aggregate (the truncated table's cumulative, not its
own shifted prior).

Entities with no eligible pre-cutoff rows receive no state row and fall
through to the registered cold-start path. Same-date and future rows
cannot enter any state by construction (they are filtered out before
the state arithmetic runs).
"""
from __future__ import annotations

import polars as pl

from pregame_pa_ext import adapter as ad  # noqa: E402

STATES_V2_ID = "forecast_cutoff_states_v1"


def _entity_states_at_cutoffs(pa: pl.DataFrame, ent: str,
                              cutoffs: list) -> pl.DataFrame:
    """Per (entity, cutoff) prior state over rows strictly before the
    cutoff. Same registered arithmetic as entity_daily_state (w150 is
    applied downstream; EW decay 2^(dnum/90), HALF_LIFE_DAYS=90), but the
    aggregate boundary is the requested CUTOFF, not the last activity
    date: prior_k/prior_n/ew_* cover every eligible row strictly before
    the cutoff, and same-date/future rows cannot enter (filtered out
    before aggregation)."""
    frames = []
    for t in sorted(set(cutoffs)):
        sub = pa.filter(pl.col("game_date") < t)
        if sub.height == 0:
            continue
        frames.append(
            sub.with_columns(
                (2.0 ** (((pl.col("game_date") - pl.date(1970, 1, 1))
                          .dt.total_days()) / ad.HALF_LIFE_DAYS))
                .alias("_w"))
            .group_by(ent)
            .agg(pl.col("y").sum().alias("prior_k"),
                 pl.len().alias("prior_n"),
                 (pl.col("_w") * pl.col("y")).sum().alias("ew_k"),
                 pl.col("_w").sum().alias("ew_den"),
                 pl.col("game_date").max().alias("src_date"))
            .with_columns(
                pl.col("prior_k").cast(pl.Float64),
                pl.col("prior_n").cast(pl.Float64),
                pl.col("src_date").alias("ew_src"),
                pl.lit(t).alias("game_date"))
            .select(pl.col(ent), "prior_k", "prior_n", "src_date",
                    "ew_k", "ew_den", "ew_src", "game_date"))
    if not frames:
        return pl.DataFrame(schema={
            ent: pl.Int64, "prior_k": pl.Float64, "prior_n": pl.Float64,
            "src_date": pl.Date, "ew_k": pl.Float64, "ew_den": pl.Float64,
            "game_date": pl.Date})
    return pl.concat(frames).sort("game_date", ent)


def _league_state_at_cutoffs(pa: pl.DataFrame,
                             cutoffs: list) -> pl.DataFrame:
    """League rate at each cutoff = aggregate over rows strictly before
    the cutoff (registered lg_rate definition, cutoff-correct support)."""
    frames = []
    for t in sorted(set(cutoffs)):
        sub = pa.filter(pl.col("game_date") < t)
        if sub.height == 0:
            continue
        k = float(sub["y"].sum())
        n = float(sub.height)
        frames.append(pl.DataFrame({
            "game_date": [t],
            "lg_rate": [k / n if n > 0 else 0.0],
            "lg_src_date": [sub["game_date"].max()],
        }))
    if not frames:
        return pl.DataFrame(schema={
            "game_date": pl.Date, "lg_rate": pl.Float64,
            "lg_src_date": pl.Date})
    return pl.concat(frames).sort("game_date")


def build_v2_states(pa: pl.DataFrame, cutoffs: list) -> tuple[
        pl.DataFrame, pl.DataFrame, pl.DataFrame, dict]:
    """Return (p_daily, b_daily, lg, meta) state frames keyed at the
    requested cutoffs, ready for the frozen attach_prior_features."""
    cutoffs = list(cutoffs)
    if not cutoffs:
        raise ValueError("no forecast cutoffs supplied")
    p = _entity_states_at_cutoffs(pa, "pitcher", cutoffs)
    b = _entity_states_at_cutoffs(pa, "batter", cutoffs)
    lg = _league_state_at_cutoffs(pa, cutoffs)
    meta = {
        "state_contract": STATES_V2_ID,
        "cutoff_dates": [str(t) for t in sorted(set(cutoffs))],
        "n_pitcher_states": p.height,
        "n_batter_states": b.height,
        "cutoff_rule": ("prior = aggregate over rows with game_date "
                        "strictly before the requested cutoff; target-date "
                        "and future rows cannot enter by construction"),
    }
    return p, b, lg, meta
