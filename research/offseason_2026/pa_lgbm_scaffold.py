"""PA-LGBM scaffold: pa_completed_v1 labels + pooled pregame snapshots.

Implements `research/offseason_2026/pa-lgbm-contract-2026-10-09.md` (frozen
2026-10-09 before this file was written). Pure functions over injected
frames; NO file I/O, NO model fitting, NO real-data scoring. Real-data use
goes through `run_pa_label_reconciliation.py` (bounded reconciliation only).

Design principles (contract Section 2):
- Pooled sufficient statistics (counts, sums, valid-observation counts,
  variance inputs). Derived means/rates are computed at read time.
- Every rate feature ships its numerator and denominator columns.
- Feature aggregation weights (how history is pooled) and training-row
  weights (which population a fit prioritizes) are separate decisions;
  this scaffold implements aggregation only, v1 training rows unweighted.
- All snapshots use strictly `game_date < cutoff`; same-day excluded (v1).
"""

from __future__ import annotations

import math

import polars as pl

# --- Event mapping (contract Section 1) ------------------------------------

CLASS_COMPLETED = "completed_pa"
CLASS_BASERUNNING = "baserunning_only"
CLASS_INCOMPLETE = "incomplete"

# Inherited from production statcast.py NON_PA_EVENTS (starting
# classification, not majority vote; reconciliation quantifies it).
BASERUNNING_EVENTS = frozenset({
    "caught_stealing_2b", "caught_stealing_3b", "caught_stealing_home",
    "pickoff_1b", "pickoff_2b", "pickoff_3b",
    "pickoff_caught_stealing_2b", "pickoff_caught_stealing_3b",
    "pickoff_caught_stealing_home",
    "stolen_base_2b", "stolen_base_3b", "stolen_base_home",
    "wild_pitch", "passed_ball", "other_out", "runner_double_play",
})
INCOMPLETE_EVENTS = frozenset({"truncated_pa"})

K_EVENTS = frozenset({"strikeout", "strikeout_double_play"})

COMPLETED_EVENTS = frozenset({
    "strikeout", "strikeout_double_play", "walk", "intent_walk",
    "hit_by_pitch", "single", "double", "triple", "home_run",
    "ground_rule_double", "field_out", "force_out", "fielders_choice",
    "fielders_choice_out", "triple_play",
    "grounded_into_double_play", "double_play", "sac_fly",
    "sac_fly_double_play", "sac_bunt", "sac_bunt_double_play",
    "field_error", "catcher_interf", "fan_interference",
    "defensive_indiff",
})

EVENT_MAP: dict[str, str] = {}
for _e in COMPLETED_EVENTS:
    EVENT_MAP[_e] = CLASS_COMPLETED
for _e in BASERUNNING_EVENTS:
    EVENT_MAP[_e] = CLASS_BASERUNNING
for _e in INCOMPLETE_EVENTS:
    EVENT_MAP[_e] = CLASS_INCOMPLETE

# Swing/contact description sets mirror statcast.py (scaffold is pure; the
# reconciliation runner asserts equality with src.Python.statcast).
SWING_DESCRIPTIONS = frozenset({
    "swinging_strike", "swinging_strike_blocked", "foul_tip", "foul",
    "hit_into_play",
})
CONTACT_DESCRIPTIONS = frozenset({"foul", "hit_into_play"})

W_SHRINK = 150.0
SHORT_START_PA = 9

PA_ROW_COLUMNS = ("game_pk", "game_date", "pitcher", "batter", "stand",
                  "p_throws", "events", "at_bat_number", "pitch_number")


def classify_event(event: str | None) -> str:
    """Map one Savant event to its pa_completed_v1 class; fail loud."""
    if event is None:
        return CLASS_INCOMPLETE
    try:
        return EVENT_MAP[event]
    except KeyError:
        raise ValueError("unmapped event %r (contract Section 1)" % (event,))


def _require_columns(df: pl.DataFrame, cols, what: str) -> None:
    missing = sorted(set(cols) - set(df.columns))
    if missing:
        raise ValueError("%s missing columns: %s" % (what, missing))


def build_pa_label_table(pa_rows: pl.DataFrame) -> pl.DataFrame:
    """One row per (game_pk, at_bat_number) under pa_completed_v1.

    Group outcome = the LAST row whose event maps to completed_pa; if none
    exists, the terminal (max pitch_number) row classifies the group as
    baserunning_only or incomplete. Attribution: defining-row pitcher.
    Mixed-batter groups become incomplete with the explicit `mixed_batter`
    reason flag (contract Amendment 2026-10-09). Fails loud on unmapped
    events or duplicate PA identity in the output.
    """
    _require_columns(pa_rows, PA_ROW_COLUMNS, "pa_rows")
    unmapped = (pa_rows.filter(pl.col("events").is_not_null())
                .get_column("events").unique().to_list())
    bad = sorted(e for e in unmapped if e not in EVENT_MAP)
    if bad:
        raise ValueError("unmapped events: %s" % bad)
    df = (pa_rows.select(PA_ROW_COLUMNS)
          .with_columns(pl.col("game_date").cast(pl.Date))
          .sort(["game_pk", "at_bat_number", "pitch_number"]))
    is_completed = (pl.col("events").is_not_null()
                    & pl.col("events").is_in(list(COMPLETED_EVENTS)))
    g = df.group_by(["game_pk", "at_bat_number"], maintain_order=True).agg(
        pl.col("game_date").last().alias("game_date"),
        pl.col("batter").last().alias("batter"),
        pl.col("batter").n_unique().alias("n_batters"),
        pl.col("pitcher").filter(is_completed).last().alias("def_pitcher"),
        pl.col("stand").filter(is_completed).last().alias("def_stand"),
        pl.col("p_throws").filter(is_completed).last().alias("def_p_throws"),
        pl.col("events").filter(is_completed).last().alias("def_event"),
        pl.col("pitcher").last().alias("terminal_pitcher"),
        pl.col("stand").last().alias("terminal_stand"),
        pl.col("p_throws").last().alias("terminal_p_throws"),
        pl.col("events").last().alias("terminal_event"),
        pl.col("pitcher").n_unique().alias("n_distinct_pitchers"),
        pl.len().alias("n_pitches"),
    )
    if (g["n_batters"] > 1).any():
        pass  # handled explicitly below: incomplete + mixed_batter flag
    def_filled = g["def_event"].is_not_null()
    out = g.with_columns([
        pl.when(def_filled).then(pl.col("def_event"))
          .otherwise(pl.col("terminal_event")).alias("event"),
        pl.when(def_filled).then(pl.col("def_pitcher"))
          .otherwise(pl.col("terminal_pitcher")).alias("pitcher"),
        pl.when(def_filled).then(pl.col("def_stand"))
          .otherwise(pl.col("terminal_stand")).alias("stand"),
        pl.when(def_filled).then(pl.col("def_p_throws"))
          .otherwise(pl.col("terminal_p_throws")).alias("p_throws"),
    ]).with_columns(
        (g["n_batters"] > 1).alias("mixed_batter"),
    ).with_columns(
        pl.when(pl.col("mixed_batter"))
        .then(pl.lit(CLASS_INCOMPLETE, dtype=pl.String))
        .otherwise(
            pl.struct("event").map_elements(
                lambda s: classify_event(s["event"]),
                return_dtype=pl.String))
        .alias("pa_class")
    ).with_columns(
        (pl.col("pa_class") == CLASS_COMPLETED)
        .alias("is_completed"),
    ).with_columns(
        pl.when(pl.col("is_completed"))
        .then(pl.col("event").is_in(list(K_EVENTS)).cast(pl.Int8))
        .otherwise(None).cast(pl.Int8, strict=False).alias("y"),
        (pl.col("n_distinct_pitchers") > 1).alias("mid_pa_pitcher_change"),
    ).drop(["def_pitcher", "def_stand", "def_p_throws", "def_event",
            "terminal_pitcher", "terminal_stand", "terminal_p_throws",
            "terminal_event", "n_batters", "n_distinct_pitchers",
            "is_completed"])
    if out.select(pl.struct(["game_pk", "at_bat_number"]).n_unique()
                  ).item() != out.height:
        raise ValueError("duplicate PA identity in output")
    return out


def first_pitcher_filter(label_table: pl.DataFrame,
                         first_pitcher_keys: pl.DataFrame) -> pl.DataFrame:
    """Keep PA rows whose pitcher is the game's first (spine) pitcher.

    first_pitcher_keys: frame with game_pk, forecast_pitcher.
    """
    _require_columns(first_pitcher_keys, ("game_pk", "forecast_pitcher"),
                     "first_pitcher_keys")
    return (label_table.join(
        first_pitcher_keys.select(["game_pk",
                                   pl.col("forecast_pitcher")
                                   .alias("fp_pitcher")]),
        on="game_pk", how="inner")
        .filter(pl.col("pitcher") == pl.col("fp_pitcher"))
        .drop("fp_pitcher"))


# --- Shrinkage / rates (contract Section 2, v1 recipe) ---------------------


def shrunk_rate(k: int, n: int, lg: float, w: float = W_SHRINK) -> float:
    """(k + w*lg) / (n + w); lg = training-window prior league rate."""
    return (k + w * lg) / (n + w)


def league_rate(label_table: pl.DataFrame, as_of) -> float:
    """Training-window K share over completed PAs strictly before as_of."""
    prior = label_table.filter(
        (pl.col("pa_class") == CLASS_COMPLETED)
        & (pl.col("game_date") < as_of))
    n = prior.height
    if n == 0:
        return float("nan")
    return float(prior["y"].sum()) / n


# --- Snapshot keys ----------------------------------------------------------

PITCHER_SNAPSHOT_COLUMNS = ("key_game_pk", "cutoff_date", "pitcher")
BATTER_SNAPSHOT_COLUMNS = ("key_game_pk", "cutoff_date", "batter")


def pitcher_snapshot_keys(spine_rows: pl.DataFrame) -> pl.DataFrame:
    """One key per pitcher-game snapshot: (key_game_pk, cutoff_date, pitcher).

    spine_rows: one row per pitcher-game (game_pk, game_date, pitcher).
    """
    _require_columns(spine_rows, ("game_pk", "game_date", "pitcher"),
                     "spine_rows")
    return (spine_rows.select(
        pl.col("game_pk").alias("key_game_pk"),
        pl.col("game_date").cast(pl.Date).alias("cutoff_date"),
        "pitcher").unique())


def batter_snapshot_keys(spine_rows: pl.DataFrame) -> pl.DataFrame:
    """One key per (game, batter) snapshot from PA rows to score.

    spine_rows: label-table rows carrying game_pk, game_date, batter.
    """
    _require_columns(spine_rows, ("game_pk", "game_date", "batter"),
                     "spine_rows")
    return (spine_rows.select(
        pl.col("game_pk").alias("key_game_pk"),
        pl.col("game_date").cast(pl.Date).alias("cutoff_date"),
        "batter").unique())


def _prior_join(keys: pl.DataFrame, rows: pl.DataFrame, entity: str,
                entity_in_rows: str) -> pl.DataFrame:
    joined = keys.join(rows, left_on=entity, right_on=entity_in_rows,
                       how="inner")
    return joined.filter(pl.col("game_date") < pl.col("cutoff_date"))


# --- Pitcher priors ----------------------------------------------------------


def pitcher_rate_priors(label_table: pl.DataFrame,
                        keys: pl.DataFrame) -> pl.DataFrame:
    """Prior completed-PA K statistics per pitcher snapshot.

    Returns key_game_pk, cutoff_date, pitcher, k_prior, n_prior,
    n_prior_season, last_prior_pa_date. Only pa_completed_v1 completed rows
    carry labels; incomplete/baserunning rows never enter.
    """
    _require_columns(keys, PITCHER_SNAPSHOT_COLUMNS, "keys")
    lab = label_table.filter(pl.col("pa_class") == CLASS_COMPLETED).select(
        "game_pk", "game_date", "pitcher", "y")
    j = _prior_join(keys, lab, "pitcher", "pitcher")
    return j.group_by(PITCHER_SNAPSHOT_COLUMNS, maintain_order=True).agg(
        pl.col("y").sum().alias("k_prior"),
        pl.len().alias("n_prior"),
        (pl.col("game_date").dt.year()
         == pl.col("cutoff_date").dt.year()).sum().alias("n_prior_season"),
        pl.col("game_date").max().alias("last_prior_pa_date"),
    )


def pitcher_workload_priors(label_table: pl.DataFrame,
                            keys: pl.DataFrame) -> pl.DataFrame:
    """Prior workload summaries per pitcher snapshot (completed PAs only).

    Returns n_prior_starts, n_prior_pa, days_since_prev_start,
    n_prior_short_starts (prior starts with completed PA < 9; historical
    fact, carried as descriptive evidence).
    """
    _require_columns(keys, PITCHER_SNAPSHOT_COLUMNS, "keys")
    lab = label_table.filter(pl.col("pa_class") == CLASS_COMPLETED).select(
        "game_pk", "game_date", "pitcher", "y")
    per_start = lab.group_by(["pitcher", "game_pk"]).agg(
        pl.col("game_date").first().alias("game_date"),
        pl.len().alias("n_pa_start"))
    j = _prior_join(keys, per_start, "pitcher", "pitcher")
    return j.group_by(PITCHER_SNAPSHOT_COLUMNS, maintain_order=True).agg(
        pl.len().alias("n_prior_starts"),
        pl.col("n_pa_start").sum().alias("n_prior_pa"),
        (pl.col("cutoff_date").first() - pl.col("game_date").max())
        .dt.total_days().alias("days_since_prev_start"),
        (pl.col("n_pa_start") < SHORT_START_PA).sum()
        .alias("n_prior_short_starts"),
    )


def pitcher_pitchtype_priors(pitch_rows: pl.DataFrame,
                             keys: pl.DataFrame) -> pl.DataFrame:
    """Pooled per-pitch-type sufficient statistics per pitcher snapshot.

    Long format, one row per (key, pitch_type). Eligibility universe =
    rows with non-null pitch_type; missing velocity never alters it.
    Returns n_type, n_valid, n_missing_velocity, sum_speed, sum_speed_sq
    (population-variance inputs, ddof=0 by contract), last_valid_speed,
    days_since_last_valid.
    """
    _require_columns(keys, PITCHER_SNAPSHOT_COLUMNS, "keys")
    _require_columns(pitch_rows,
                     ("game_pk", "game_date", "pitcher", "pitch_type",
                      "release_speed"), "pitch_rows")
    pr = pitch_rows.select("game_pk", "game_date", "pitcher", "pitch_type",
                           "release_speed").filter(
        pl.col("pitch_type").is_not_null())
    j = _prior_join(keys, pr, "pitcher", "pitcher")
    valid = pl.col("release_speed").is_not_null()
    return j.group_by(PITCHER_SNAPSHOT_COLUMNS + ("pitch_type",),
                      maintain_order=True).agg(
        pl.len().alias("n_type"),
        valid.sum().alias("n_valid"),
        (~valid).sum().alias("n_missing_velocity"),
        pl.col("release_speed").sum().alias("sum_speed"),
        (pl.col("release_speed") ** 2).sum().alias("sum_speed_sq"),
        pl.col("release_speed").filter(valid).last()
        .alias("last_valid_speed"),
        pl.col("game_date").filter(valid).max().alias("last_valid_date"),
    ).with_columns(
        (pl.col("cutoff_date").first() - pl.col("last_valid_date"))
        .dt.total_days().alias("days_since_last_valid"),
    ).drop("last_valid_date")


def pitcher_swing_priors(pitch_rows: pl.DataFrame,
                         keys: pl.DataFrame) -> pl.DataFrame:
    """Pooled whiff/contact/swing counts per pitcher snapshot.

    Identity holds by construction: swings = whiffs + contacts.
    """
    _require_columns(keys, PITCHER_SNAPSHOT_COLUMNS, "keys")
    _require_columns(pitch_rows, ("game_pk", "game_date", "pitcher",
                                  "description"), "pitch_rows")
    pr = pitch_rows.select("game_pk", "game_date", "pitcher", "description")
    j = _prior_join(keys, pr, "pitcher", "pitcher")
    swing = pl.col("description").is_in(list(SWING_DESCRIPTIONS))
    contact = pl.col("description").is_in(list(CONTACT_DESCRIPTIONS))
    return j.group_by(PITCHER_SNAPSHOT_COLUMNS, maintain_order=True).agg(
        swing.sum().alias("n_swings"),
        (swing & ~contact).sum().alias("n_whiffs"),
        contact.sum().alias("n_contacts"),
    )


# --- Batter priors -----------------------------------------------------------


def batter_rate_priors(label_table: pl.DataFrame,
                       keys: pl.DataFrame) -> pl.DataFrame:
    """Prior completed-PA K statistics per batter snapshot, hand-split.

    Returns k_prior, n_prior, k_prior_vs_rhp, n_prior_vs_rhp,
    k_prior_vs_lhp, n_prior_vs_lhp, last_prior_pa_date. Hand side = the
    defining row's p_throws (pregame-known for the current game, historical
    for prior rows).
    """
    _require_columns(keys, BATTER_SNAPSHOT_COLUMNS, "keys")
    lab = label_table.filter(pl.col("pa_class") == CLASS_COMPLETED).select(
        "game_pk", "game_date", "batter", "y", "p_throws")
    j = _prior_join(keys, lab, "batter", "batter")
    base = j.group_by(BATTER_SNAPSHOT_COLUMNS, maintain_order=True).agg(
        pl.col("y").sum().alias("k_prior"),
        pl.len().alias("n_prior"),
        pl.col("game_date").max().alias("last_prior_pa_date"),
    )
    hand = j.group_by(BATTER_SNAPSHOT_COLUMNS + ("p_throws",),
                      maintain_order=True).agg(
        pl.col("y").sum().alias("k_hand"),
        pl.len().alias("n_hand"),
    ).pivot(values=["k_hand", "n_hand"], index=BATTER_SNAPSHOT_COLUMNS,
            on="p_throws")
    renames = {}
    for side, tag in (("R", "vs_rhp"), ("L", "vs_lhp")):
        renames["k_hand_%s" % side] = "k_prior_%s" % tag
        renames["n_hand_%s" % side] = "n_prior_%s" % tag
    hand = hand.rename(renames)
    keep = ["key_game_pk", "cutoff_date", "batter"] + [
        c for c in renames.values() if c in hand.columns]
    return base.join(hand.select(keep), on=BATTER_SNAPSHOT_COLUMNS,
                     how="left")


# --- Cold-start taxonomy (contract Section 3) --------------------------------


def classify_cold_start(n_prior_career: int, n_prior_season: int,
                        w: float = W_SHRINK) -> str:
    """Mutually exclusive class; failed_join is decided at assembly time."""
    if n_prior_career == 0:
        return "career_debut"
    if n_prior_season == 0:
        return "season_debut"
    if n_prior_career < w:
        return "insufficient_history"
    return "established"


# --- Derived read-time features ----------------------------------------------


def finalize_type_stats(type_stats: pl.DataFrame,
                        eligible_totals: pl.DataFrame) -> pl.DataFrame:
    """Derived velocity/usage features from pooled sufficient statistics.

    Adds mean_speed (sum/n_valid), sd_speed (population variance, ddof=0:
    sqrt(sum_sq/n - mean^2)), usage_share (n_type / n_eligible). Denominator
    separation is structural: usage uses n_eligible from eligible_totals,
    velocity uses n_valid from the type rows themselves.
    """
    totals = eligible_totals.select(
        "key_game_pk", "cutoff_date", "pitcher", "n_eligible")
    out = type_stats.join(totals, on=PITCHER_SNAPSHOT_COLUMNS, how="left")
    return out.with_columns(
        (pl.col("sum_speed") / pl.col("n_valid")).alias("mean_speed"),
        (((pl.col("sum_speed_sq") / pl.col("n_valid"))
          - (pl.col("sum_speed") / pl.col("n_valid")) ** 2)
         .clip(lower_bound=0.0).sqrt().alias("sd_speed")),
        (pl.col("n_type") / pl.col("n_eligible")).alias("usage_share"),
    )


# --- Feature dictionary (contract Section 2; exact denominators) -------------


FEATURE_DICTIONARY = (
    {
        "name": "pitcher_k_rate_shrunk",
        "estimand": "prior K rate of the pitcher over completed PAs",
        "construction": "shrunk_rate(k_prior, n_prior, lg, w=150)",
        "numerator": "k_prior",
        "denominator": "n_prior (completed PAs vs all batters)",
        "history_unit": "completed PA (pa_completed_v1)",
        "cutoff": "game_date < snapshot game_date",
        "evidence_columns": ["k_prior", "n_prior", "n_prior_season"],
    },
    {
        "name": "pitcher_velocity_ff",
        "estimand": "pooled mean release speed of valid FF measurements",
        "construction": "sum_speed / n_valid (per pitch_type; FF headline)",
        "numerator": "sum_speed",
        "denominator": "n_valid (non-null release_speed within FF rows)",
        "history_unit": "measured pitch",
        "cutoff": "game_date < snapshot game_date",
        "evidence_columns": ["n_valid", "n_missing_velocity", "sum_speed",
                             "sum_speed_sq", "last_valid_speed",
                             "days_since_last_valid"],
    },
    {
        "name": "pitcher_usage_ff",
        "estimand": "share of eligible pitches thrown as FF",
        "construction": "n_type / n_eligible",
        "numerator": "n_type (FF rows)",
        "denominator": "n_eligible (rows with non-null pitch_type; "
                       "velocity missingness never alters it)",
        "history_unit": "pitch",
        "cutoff": "game_date < snapshot game_date",
        "evidence_columns": ["n_type", "n_eligible"],
    },
    {
        "name": "pitcher_whiff_rate",
        "estimand": "whiffs per swing induced",
        "construction": "n_whiffs / n_swings",
        "numerator": "n_whiffs (swing and not contact)",
        "denominator": "n_swings (statcast swing descriptions)",
        "history_unit": "pitch",
        "cutoff": "game_date < snapshot game_date",
        "evidence_columns": ["n_swings", "n_whiffs", "n_contacts"],
    },
    {
        "name": "pitcher_contact_rate",
        "estimand": "contacts per swing allowed",
        "construction": "n_contacts / n_swings",
        "numerator": "n_contacts (foul, hit_into_play)",
        "denominator": "n_swings",
        "history_unit": "pitch",
        "cutoff": "game_date < snapshot game_date",
        "evidence_columns": ["n_contacts"],
    },
    {
        "name": "pitcher_workload",
        "estimand": "prior outing pattern of the pitcher",
        "construction": "counts over prior starts: n_prior_starts, "
                        "n_prior_pa, days_since_prev_start, "
                        "n_prior_short_starts",
        "numerator": "per column",
        "denominator": "n/a (counts and day differences)",
        "history_unit": "start (completed-PA count per prior game)",
        "cutoff": "game_date < snapshot game_date",
        "evidence_columns": ["n_prior_starts", "n_prior_pa",
                             "days_since_prev_start",
                             "n_prior_short_starts"],
    },
    {
        "name": "batter_k_rate_shrunk",
        "estimand": "prior K rate of the batter over completed PAs",
        "construction": "shrunk_rate(k_prior, n_prior, lg, w=150), "
                        "hand-split variants carried alongside",
        "numerator": "k_prior",
        "denominator": "n_prior (completed PAs vs all pitchers)",
        "history_unit": "completed PA (pa_completed_v1)",
        "cutoff": "game_date < snapshot game_date",
        "evidence_columns": ["k_prior", "n_prior", "k_prior_vs_rhp",
                             "n_prior_vs_rhp", "k_prior_vs_lhp",
                             "n_prior_vs_lhp"],
    },
)


def feature_dictionary() -> list[dict]:
    """Return the frozen feature dictionary (contract Section 2)."""
    return [dict(f) for f in FEATURE_DICTIONARY]


# --- Convenience: assemble snapshot feature rows ------------------------------


def assemble_pitcher_snapshots(label_table: pl.DataFrame,
                               pitch_rows: pl.DataFrame,
                               keys: pl.DataFrame,
                               lg: float,
                               w: float = W_SHRINK) -> pl.DataFrame:
    """Join all pitcher prior blocks into one snapshot table per key.

    Cold-start class from contract Section 3 (failed_join is decided at
    data-assembly time in the runner, not here). Keys with no prior history
    keep zero counts and career_debut.
    """
    rates = pitcher_rate_priors(label_table, keys)
    workload = pitcher_workload_priors(label_table, keys)
    swings = pitcher_swing_priors(pitch_rows, keys)
    out = (keys
           .join(rates, on=PITCHER_SNAPSHOT_COLUMNS, how="left")
           .join(workload, on=PITCHER_SNAPSHOT_COLUMNS, how="left")
           .join(swings, on=PITCHER_SNAPSHOT_COLUMNS, how="left"))
    count_cols = ["k_prior", "n_prior", "n_prior_season", "n_prior_starts",
                  "n_prior_pa", "n_prior_short_starts", "n_swings",
                  "n_whiffs", "n_contacts"]
    out = out.with_columns([pl.col(c).fill_null(0).cast(pl.Int64)
                            for c in count_cols])
    return out.with_columns(
        pl.struct("k_prior", "n_prior", "n_prior_season").map_elements(
            lambda s: classify_cold_start(int(s["n_prior"]),
                                          int(s["n_prior_season"]), w),
            return_dtype=pl.String).alias("cold_start_class"),
    ).with_columns(
        pl.when(pl.col("n_prior") > 0)
        .then((pl.col("k_prior").cast(pl.Float64) + w * lg)
              / (pl.col("n_prior") + w))
        .otherwise(lg).alias("k_rate_shrunk"),
    )
