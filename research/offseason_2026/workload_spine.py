"""Outcome-independent forecast spine + prior-appearance history builder.

Implements the frozen v2.2 rules from
`specs/pregame-workload-dev-spec.md`:

- Spine: forecast rows exist for ALL first pitchers regardless of
  current-game outcomes (row existence never depends on BF/K).
- History: prior appearances only (starts AND relief), strictly prior
  dates (same-day doubleheaders excluded), MLBAM-id matched, prior
  short outings preserved. Identity/history, capacity reset, and
  debut status are SEPARATE dimensions.
- Capacity reset (frozen convention, threshold 365*3 = 1095 days,
  strictly-greater operator): a gap > 1095 days between consecutive
  appearances truncates CAPACITY summaries to the post-gap suffix; a
  gap > 1095 days between the last appearance and the forecast empties
  capacity history. Reset NEVER erases experience metadata
  (all-season counts are preserved alongside). Fallback when no
  post-reset appearances exist: population mean, flagged.
- Labels: `no_prior_appearance_observed` (with coverage bounds) --
  NEVER a proven debut; `first_mlb_pitching_appearance` requires
  independent debut evidence; `no_prior_start_observed` (limited
  history does not prove a first MLB start); `season_debut`,
  `returning_after_gap` (days recorded), `injury_return` (independent
  evidence only), `capacity_reset`, `join_failed`, `ordinary`.
- Summaries separated by role: actual total workload (all prior
  appearances), start-capacity summaries (is_start only), relief
  summaries (is_start==False only) + explicit no-prior-starts
  fallback. EWMA is a RECENCY-SENSITIVE summary, not outlier
  protection; the recent median is the robust capacity summary;
  shrinkage limits instability (K=20 prior appearances toward the
  population mean BF). No clipping added anywhere.
- Lineage: every frame reports rule version, information cutoff,
  coverage bounds, reset/debut/shrinkage definitions (leakage L7).

Pure functions over injected polars frames; NO file I/O and NO
real-data execution here. L6 (inner-fit isolation) is a property of
the FUTURE fitting pipeline and must be tested there -- it is not
inherited from Run 1.
"""

from __future__ import annotations

import json

import polars as pl

CAPACITY_RESET_DAYS = 365 * 3  # strictly greater-than boundary
RETURNING_GAP_DAYS = 30
SHRINK_K_APPEARANCES = 20  # units: prior APPEARANCES (start capacity)
WINDOWS = (5, 10, 20)
EWMA_HALF_LIVES = (3, 5, 10)
RULE_VERSION = "workload_spine_v2.2"


# ---------------------------------------------------------------------------
# Spine (outcome-independent row existence)
# ---------------------------------------------------------------------------


def first_pitcher_keys(pitch_rows: pl.DataFrame) -> pl.DataFrame:
    """First-pitcher keys for BOTH teams -- canonical delegation.

    This is a thin wrapper around the CANONICAL first-pitcher
    definition `Python.pitcher_features._starter_keys` (imported,
    never reimplemented): (game_pk, pitcher) pairs for the pitcher
    who opened each half of inning 1, ordered by
    (inning_topbot, at_bat_number, pitch_number) -- so a mid-PA
    substitution selects the pitcher who BEGAN the half, not the
    completer. This function only adds: game_date (must be
    single-valued per game, fail loud otherwise), `side`
    (Top/Bot of the opened half), and `is_home` (home team pitches
    the Top; the build_pitcher_starts convention) for team-side
    identity. A game missing either half fails loud (explicitly
    quarantined by the caller, never silently dropped).
    """
    from Python.pitcher_features import _starter_keys

    required = {"game_pk", "pitcher", "game_date", "inning",
                "inning_topbot", "at_bat_number", "pitch_number"}
    missing = sorted(required - set(pitch_rows.columns))
    if missing:
        raise ValueError(
            "first-pitcher keys require columns missing from the "
            "pitch frame: %s" % (missing,))
    sides = (
        pitch_rows.filter(pl.col("inning") == 1)
        .sort(["game_pk", "inning_topbot", "at_bat_number",
               "pitch_number"])
        .group_by(["game_pk", "inning_topbot"], maintain_order=True)
        .agg([
            pl.col("pitcher").first().alias("forecast_pitcher"),
            pl.col("game_date").first().alias("game_date"),
        ])
    )
    per_game = (
        sides.group_by("game_pk")
        .agg(pl.col("inning_topbot").n_unique().alias("n_sides"))
    )
    incomplete = per_game.filter(pl.col("n_sides") != 2)
    if incomplete.height:
        raise ValueError(
            "games missing an inning-1 half (fail-closed, not "
            "silently dropped): %s"
            % (incomplete["game_pk"].to_list(),))
    dates = (
        pitch_rows.group_by("game_pk")
        .agg(pl.col("game_date").n_unique().alias("n_dates"))
        .filter(pl.col("n_dates") > 1)
    )
    if dates.height:
        raise ValueError(
            "contradictory game_date values within games "
            "(fail-closed): %s" % (dates["game_pk"].to_list(),))
    canonical = _starter_keys(pitch_rows).rename(
        {"pitcher": "forecast_pitcher"})
    out = sides.join(canonical, on=["game_pk", "forecast_pitcher"],
                     how="inner")
    if out.height != sides.height:
        raise ValueError(
            "canonical key reconciliation failed: side-preserving "
            "rows %d vs canonical rows %d" % (sides.height, out.height))
    return out.with_columns(
        (pl.col("inning_topbot") == "Top").alias("is_home")
    ).select(["game_pk", "forecast_pitcher", "inning_topbot",
              "is_home", "game_date"])


# ---------------------------------------------------------------------------
# Capacity reset (frozen convention)
# ---------------------------------------------------------------------------


def _apply_capacity_reset(history: pl.DataFrame,
                          forecast_date) -> tuple[pl.DataFrame, bool]:
    """Boundary operator: gap STRICTLY GREATER than 1095 days.

    Internal gap > threshold -> keep the post-gap suffix. Gap between
    the last appearance and the forecast > threshold -> empty capacity
    history. Returns (capacity_history, reset_occurred).
    """
    if history.is_empty():
        return history, False
    dates = history["game_date"].to_list()
    if (forecast_date - dates[-1]).days > CAPACITY_RESET_DAYS:
        return history.slice(0, 0), True
    if history.height < 2:
        return history, False
    gaps = [(dates[i] - dates[i - 1]).days
            for i in range(1, len(dates))]
    reset_idx = None
    for i, gap in enumerate(gaps):
        if gap > CAPACITY_RESET_DAYS:
            reset_idx = i + 1  # keep dates[i:] (suffix after the gap)
    if reset_idx is None:
        return history, False
    return history.slice(reset_idx), True


def _ewma(values: list[float], half_life: float) -> float | None:
    """Recency-sensitive weighted mean (oldest->newest).

    NOT outlier protection: a recent short outing pulls this down.
    Robustness comes from the median; a robust EWMA would need a
    separately frozen transformation (none is added here).
    """
    if not values:
        return None
    alpha = 0.5 ** (1.0 / half_life)
    weight = 1.0
    num, den = 0.0, 0.0
    for v in values:
        num += weight * v
        den += weight
        weight *= alpha
    return num / den


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def build_appearance_history(
    appearances: pl.DataFrame,
    forecast_rows: pl.DataFrame,
    population_mean_bf: float,
    coverage_start,
    coverage_end=None,
    debut_evidence: dict | None = None,
    injury_evidence: dict | None = None,
) -> pl.DataFrame:
    """Attach strictly-prior history features + labels to forecast rows.

    `appearances` columns: pitcher (MLBAM id), game_pk, game_date
    (date), is_start (bool), pitches (int), outs (int), bf (int, 0
    allowed -- prior short outings are real data). `forecast_rows`
    columns: game_pk, pitcher, game_date. Same game_pk is excluded
    from history (current game never enters features).
    """
    debut_evidence = debut_evidence or {}
    injury_evidence = injury_evidence or {}
    import math

    if not math.isfinite(population_mean_bf):
        raise ValueError(
            "population_mean_bf must be finite (caller-supplied; the "
            "fitting pipeline must verify its information cutoff "
            "before use)")
    out_rows = []
    for row in forecast_rows.iter_rows(named=True):
        f_date = row["game_date"]
        pid = row["pitcher"]
        hist = (
            appearances.filter(
                (pl.col("pitcher") == pid)
                & (pl.col("game_date") < f_date)
                & (pl.col("game_pk") != row["game_pk"])
            )
            .sort("game_date")
        )

        # Known identity/history metadata is computed on the FULL
        # prior record -- a capacity reset never erases experience.
        n_all = hist.height
        starts_all = int(hist["is_start"].sum()) if n_all else 0
        relief_all = n_all - starts_all
        dates_all = hist["game_date"].to_list()

        hist_cap, did_reset = _apply_capacity_reset(hist, f_date)
        n_cap = hist_cap.height

        cap_bf = hist_cap["bf"].to_list()
        cap_pitches = hist_cap["pitches"].to_list()
        cap_is_start = hist_cap["is_start"].to_list()
        cap_dates = hist_cap["game_date"].to_list()
        start_rows = hist_cap.filter(pl.col("is_start"))
        relief_rows = hist_cap.filter(~pl.col("is_start"))

        # ---- Labels (first matching rule) --------------------------
        # Debut evidence overrides everything (independent only).
        if row["game_pk"] in debut_evidence:
            label = "first_mlb_pitching_appearance"
        elif n_all == 0:
            label = "no_prior_appearance_observed"
        elif did_reset:
            label = "capacity_reset"
        elif not any(d.year == f_date.year for d in cap_dates):
            label = "season_debut"
        elif cap_dates and (f_date - cap_dates[-1]).days \
                > RETURNING_GAP_DAYS:
            label = "returning_after_gap"
        elif start_rows.is_empty():
            label = "no_prior_start_observed"
        else:
            label = "ordinary"
        if row["game_pk"] in injury_evidence:
            label = "injury_return"

        # ---- Actual total workload (ALL prior appearances, pre-reset
        # boundary applied for recency only via windows; expanding uses
        # the capacity-truncated frame to honor the reset convention) --
        start_bf = start_rows["bf"].to_list()
        start_pitches = start_rows["pitches"].to_list()
        relief_bf = relief_rows["bf"].to_list()
        relief_pitches = relief_rows["pitches"].to_list()

        features = {
            "game_pk": row["game_pk"],
            "pitcher": pid,
            "game_date": f_date,
            "info_cutoff": f_date,
            "label": label,
            # Identity/history dimension (preserved across resets).
            "n_prior_all_seasons": n_all,
            "prior_starts_all": starts_all,
            "prior_relief_all": relief_all,
            "days_since_last_all": (
                (f_date - dates_all[-1]).days if n_all else None),
            # Capacity dimension (post-reset; starts separated).
            "n_capacity_appearances": n_cap,
            "capacity_reset": did_reset,
            "no_prior_start_fallback": start_rows.is_empty(),
            "start_capacity_mean_bf": _mean(start_bf),
            "start_capacity_mean_pitches": _mean(start_pitches),
            "start_capacity_median_bf_5": (
                sorted(start_bf[-5:])[len(start_bf[-5:]) // 2]
                if start_bf else None),
            "start_capacity_shrunk_bf": (
                (len(start_bf) * _mean(start_bf)
                 + SHRINK_K_APPEARANCES * population_mean_bf)
                / (len(start_bf) + SHRINK_K_APPEARANCES)
                if start_bf else population_mean_bf),
            # Relief summaries (history, not starter capacity).
            "relief_mean_bf": _mean(relief_bf),
            "relief_mean_pitches": _mean(relief_pitches),
            # Actual total workload across all appearances.
            "actual_expanding_mean_bf": _mean(cap_bf),
            "actual_expanding_mean_pitches": _mean(cap_pitches),
            "days_since_last_capacity": (
                (f_date - cap_dates[-1]).days if n_cap else None),
        }
        for w in WINDOWS:
            tail = start_bf[-w:]
            features[f"start_bf_mean_last{w}"] = _mean(tail)
            tail_p = start_pitches[-w:]
            features[f"start_pitches_mean_last{w}"] = _mean(tail_p)
            tail_all = cap_bf[-w:]
            features[f"actual_bf_mean_last{w}"] = _mean(tail_all)
        for hl in EWMA_HALF_LIVES:
            features[f"actual_bf_ewma_hl{hl}"] = _ewma(cap_bf, hl)
            features[f"start_bf_ewma_hl{hl}"] = _ewma(start_bf, hl)
        out_rows.append(features)

    lineage = {
        "rule_version": RULE_VERSION,
        "info_cutoff": "strictly prior dates; same game_pk excluded",
        "coverage_bounds": {
            "coverage_start": str(coverage_start),
            "coverage_end": str(coverage_end)
            if coverage_end is not None else None,
        },
        "identity_rule": "MLBAM pitcher id matching only; starts and "
        "relief both counted and distinguished",
        "capacity_reset_rule": f"gap > {CAPACITY_RESET_DAYS} days "
        "(strictly greater) truncates CAPACITY summaries to the "
        "post-gap suffix, or empties them when the gap reaches the "
        "forecast; frozen convention, not an established scientific "
        "boundary; identity metadata is NEVER erased; fallback when "
        "no post-reset capacity exists: population mean, flagged via "
        "no_prior_start_fallback / population shrinkage term",
        "debut_rule": "no_prior_appearance_observed (with coverage "
        "bounds) is NOT a proven debut; first_mlb_pitching_appearance "
        "ONLY via independent debut evidence",
        "start_rule": "no_prior_start_observed is NOT proven first "
        "MLB start; start-capacity falls back to the population mean, "
        "flagged",
        "role_separation": "actual total workload, start-capacity, "
        "and relief summaries are computed separately; relief "
        "appearances never dilute starter capacity; start/relief "
        "classifications describe REALIZED history, not verified "
        "pregame intent",
        "coverage_bounds_rule": "coverage_start/coverage_end must "
        "describe ACTUAL SOURCE COVERAGE (caller-verified), not the "
        "pitcher's observed min/max dates; debut decisions are valid "
        "only against true coverage bounds",
        "population_mean_rule": "population_mean_bf is caller-supplied "
        "and must carry a strictly-prior information cutoff; the "
        "fitting pipeline MUST verify that cutoff before use and "
        "refuse undocumented scalars",
        "robustness_note": "median = robust typical-capacity summary; "
        "shrinkage limits instability (K=20 prior appearances toward "
        "population mean BF, cutoff strictly prior); EWMA is "
        "recency-sensitive, NOT outlier protection; no robust-EWMA "
        "transformation or clipping is applied",
        "injury_rule": "injury_return label ONLY from independent "
        "evidence; never from pitch/BF counts",
        "population_mean_bf": population_mean_bf,
    }
    return _with_lineage(pl.DataFrame(out_rows), lineage)


def _with_lineage(frame: pl.DataFrame, lineage: dict) -> pl.DataFrame:
    return frame.with_columns(
        pl.lit(json.dumps(lineage)).alias("lineage")
    )
