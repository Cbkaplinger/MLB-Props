"""Level 3 - rolling features -> model-ready training frames.

The **bottom** of the pipeline. Reads the Level 2 rolling files (and the park
dimension table) and produces frames that go straight into the training script
with minimal further transformation:

- ``pitcher_training.parquet`` - the strikeout-model spine: pitcher rolling
  features + opposing-lineup aggregates (from the batter rolling file) + park
  factor. Label column ``k_rate`` is present; drop it and the other label
  columns (``K``, ``PA``, ``Outs``) from ``X`` at fit time.
- ``batter_training.parquet`` - batter rolling features + park factor, ready for
  a batter-side model. (Opposing-starter features are the analogous cross-join to
  add here later, mirroring the pitcher side's opposing-lineup join.)

Season-opening pitcher rows intentionally retain null opponent-lineup features:
every batter has zero prior-season PA before their first game, so no leakage-safe
season-to-date rate exists yet. Training must impute these nulls or use a model
that handles them natively rather than backfilling from the game being predicted.

This layer only *joins*, so all leakage guarantees from Level 2 are preserved.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from .. import config

_BASE_LINEUP_RATE_COLUMNS = {
    "opp_lineup_whiff": "whiff_rate_std",
    "opp_lineup_swstr": "swstr_rate_std",
    "opp_lineup_chase": "chase_rate_std",
    "opp_lineup_zswing": "zswing_rate_std",
    "opp_lineup_swing": "swing_rate_std",
    "opp_lineup_zcontact": "zcontact_rate_std",
    "opp_lineup_bb": "bb_rate_std",
    **{
        f"opp_lineup_{output}_P{window}": f"{source}_P{window}"
        for output, source in (
            ("zswing", "zswing_rate"),
            ("swing", "swing_rate"),
            ("zcontact", "zcontact_rate"),
            ("bb", "bb_rate"),
        )
        for window in (5, 10, 20)
    },
}
_RESEARCH_LINEUP_BASES = {
    "k": "k_rate",
    "whiff": "whiff_rate",
    "swstr": "swstr_rate",
    "chase": "chase_rate",
    "zswing": "zswing_rate",
    "swing": "swing_rate",
    "zcontact": "zcontact_rate",
    "bb": "bb_rate",
    "babip": "babip",
    "hard_hit": "hard_hit_rate",
    "barrel": "barrel_rate",
    "sweet_spot": "sweet_spot_rate",
    "avg_ev": "avg_exit_velocity",
    "avg_la": "avg_launch_angle",
    "xba": "xBA",
    "woba": "wOBA",
    "xwoba": "xwOBA",
    "hr": "hr_rate",
    "fb": "fb_rate",
    "hr_fb": "hr_fb_rate",
    "pull_air": "pull_air_rate",
    "rv_per_pitch": "rv_per_pitch",
}
_RESEARCH_LINEUP_RATE_COLUMNS = {
    f"opp_lineup_{output}{suffix}": f"{source}_{'std' if not suffix else suffix[1:]}"
    for output, source in _RESEARCH_LINEUP_BASES.items()
    for suffix in ("", "_P5", "_P10", "_P20")
}
_LINEUP_VS_HAND_RATE_SOURCES = {
    "opp_lineup_zswing_vs_hand": ("zswing_rate_std_vR", "zswing_rate_std_vL"),
    "opp_lineup_swing_vs_hand": ("swing_rate_std_vR", "swing_rate_std_vL"),
    "opp_lineup_zcontact_vs_hand": ("zcontact_rate_std_vR", "zcontact_rate_std_vL"),
    "opp_lineup_bb_vs_hand": ("bb_rate_std_vR", "bb_rate_std_vL"),
    "opp_lineup_whiff_vs_hand": ("whiff_rate_std_vR", "whiff_rate_std_vL"),
}
_LINEUP_RATE_COLUMNS = {
    **_RESEARCH_LINEUP_RATE_COLUMNS,
    **_BASE_LINEUP_RATE_COLUMNS,
}
_REQUIRED_BATTER_COLUMNS = {
    "batter",
    "game_pk",
    "bat_team",
    "is_initial_lineup",
    "k_rate_std",
    "k_rate_std_vL",
    "k_rate_std_vR",
    *_BASE_LINEUP_RATE_COLUMNS.values(),
}


def opposing_lineup_features(
    starts: pl.DataFrame,
    batters: pl.DataFrame,
) -> pl.DataFrame:
    """Aggregate each opposing batter's pregame rates onto a pitcher start.

    Every hitter rate is computed before this join. Level 3 emits the existing
    flat lineup mean plus research-only batting-order-opportunity weighted means
    and weighted standard deviations. It never rolls a realized team lineup
    aggregate, which would mix changing rosters and risk same-game leakage.

    Season-opening games (including early neutral-site openers) will have
    null lineup features here: batters have zero season-to-date PA before
    their own first game, so the K and discipline rates are null for the whole
    opposing lineup. This is intentional -- it preserves the leakage boundary
    rather than backfilling with a synthetic constant.
    Downstream training must handle these nulls explicitly (imputation or native
    NaN-tolerant model).
    """
    missing = sorted(_REQUIRED_BATTER_COLUMNS - set(batters.columns))
    if missing:
        raise ValueError(f"batter rolling data is missing lineup columns: {missing}")

    keys = starts.select("game_pk", "pitcher", "p_throws", "opp_team")
    available_rates = {
        output: source
        for output, source in _LINEUP_RATE_COLUMNS.items()
        if source in batters.columns
    }
    optional_columns = [
        column
        for column in ("lineup_slot", "lineup_pa_weight")
        if column in batters.columns
    ]
    rate_source_columns = [
        source
        for source in dict.fromkeys(available_rates.values())
        if source not in {"k_rate_std", "k_rate_std_vL", "k_rate_std_vR"}
    ]
    hand_split_columns = [
        column
        for right, left in _LINEUP_VS_HAND_RATE_SOURCES.values()
        for column in (right, left)
        if column in batters.columns and column not in rate_source_columns
    ]
    has_lineup_weight = "lineup_pa_weight" in batters.columns
    joined = keys.join(
        batters.filter(pl.col("is_initial_lineup")).select(
            "game_pk", "batter", "bat_team", "k_rate_std", "k_rate_std_vL",
            "k_rate_std_vR", *optional_columns,
            *rate_source_columns,
            *hand_split_columns,
        ),
        left_on=["game_pk", "opp_team"],
        right_on=["game_pk", "bat_team"],
        how="left",
    ).with_columns(
        pl.when(pl.col("p_throws") == "R")
        .then(pl.col("k_rate_std_vR"))
        .when(pl.col("p_throws") == "L")
        .then(pl.col("k_rate_std_vL"))
        .otherwise(None)
        .alias("_k_vs_hand"),
        *(
            pl.when(pl.col("p_throws") == "R")
            .then(pl.col(right))
            .when(pl.col("p_throws") == "L")
            .then(pl.col(left))
            .otherwise(None)
            .alias(f"_{output.removeprefix('opp_lineup_')}")
            for output, (right, left) in _LINEUP_VS_HAND_RATE_SOURCES.items()
            if right in batters.columns and left in batters.columns
        ),
        (
            pl.col("lineup_pa_weight")
            if has_lineup_weight
            else pl.lit(1.0)
        ).alias("_lineup_weight"),
    )

    def weighted_mean(source: str, output: str) -> pl.Expr:
        valid = pl.col(source).is_not_null() & (pl.col("_lineup_weight") > 0)
        denominator = pl.when(valid).then(pl.col("_lineup_weight")).otherwise(0.0).sum()
        numerator = (
            pl.when(valid)
            .then(pl.col(source) * pl.col("_lineup_weight"))
            .otherwise(0.0)
            .sum()
        )
        return pl.when(denominator > 0).then(numerator / denominator).otherwise(None).alias(output)

    def weighted_sd(source: str, output: str) -> pl.Expr:
        valid = pl.col(source).is_not_null() & (pl.col("_lineup_weight") > 0)
        denominator = pl.when(valid).then(pl.col("_lineup_weight")).otherwise(0.0).sum()
        mean = (
            pl.when(valid)
            .then(pl.col(source) * pl.col("_lineup_weight"))
            .otherwise(0.0)
            .sum()
            / denominator
        )
        second_moment = (
            pl.when(valid)
            .then(pl.col(source).pow(2) * pl.col("_lineup_weight"))
            .otherwise(0.0)
            .sum()
            / denominator
        )
        variance = (second_moment - mean.pow(2)).clip(lower_bound=0.0)
        return pl.when(denominator > 0).then(variance.sqrt()).otherwise(None).alias(output)

    aggregations = [
        pl.col("batter").count().alias("opp_lineup_size"),
        pl.col("k_rate_std").mean().alias("opp_lineup_k"),
        pl.col("_k_vs_hand").mean().alias("opp_lineup_k_vs_hand"),
        weighted_mean("_k_vs_hand", "opp_lineup_k_vs_hand_order_weighted"),
        weighted_sd("_k_vs_hand", "opp_lineup_k_vs_hand_order_sd"),
    ]
    for output, (right, left) in _LINEUP_VS_HAND_RATE_SOURCES.items():
        alias = f"_{output.removeprefix('opp_lineup_')}"
        if alias in joined.columns:
            aggregations.append(pl.col(alias).mean().alias(output))
    aggregations.extend(
        pl.col(source).mean().alias(output)
        for output, source in available_rates.items()
        if output not in {"opp_lineup_k"}
    )
    aggregations.extend(
        expression
        for output, source in available_rates.items()
        for expression in (
            weighted_mean(source, f"{output}_order_weighted"),
            weighted_sd(source, f"{output}_order_sd"),
        )
    )
    return joined.group_by("game_pk", "pitcher").agg(aggregations)


def _age_key(name: str | None) -> str:
    """Order-invariant name key (L3 family-first vs map given-first)."""
    import re
    import unicodedata

    ascii_s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(sorted(re.sub(r"[^a-z ]", "", ascii_s.lower()).split()))


def _join_command_features(frame: pl.DataFrame) -> pl.DataFrame:
    """Attach trailing-30d rolling command (open-command, research stage).

    Leakage-safe: cmd_roll30 uses strictly prior dates. Same-day aggregates
    (cmd_med/cmd_tail) are NEVER joined (in-game pitches = leakage).
    Missing (pre-2024, <2 priors) stays null (LightGBM-native).
    Requires data/Open-Command/start_command.parquet (build_start_command.py).
    """
    from Python import config as _config

    cmd = pl.read_parquet(
        _config.PROJECT_ROOT / "data" / "Open-Command" / "start_command.parquet"
    ).select(["date", "key", "cmd_roll30"])
    return frame.with_columns(
        pl.col("player_name").map_elements(_age_key, return_dtype=pl.Utf8).alias("_ckey"),
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("_cdate"),
    ).join(cmd, left_on=["_cdate", "_ckey"], right_on=["date", "key"], how="left").drop(
        ["_ckey", "_cdate"])


def _join_age_features(frame: pl.DataFrame) -> pl.DataFrame:
    """Attach pitcher age + age interactions from local dimensions.

    DOB is static public info (known pregame) — leakage-safe by construction.
    Requires data/dimensions/player_id_map.parquet + player_ages.parquet;
    rebuild the latter with production/ops/market_research/build_age_table.py.
    Missing ages stay null (LightGBM-native); no silent median fill.
    Missing dimension FILES degrade the same way (null columns + loud print),
    matching _join_command_features/_join_kadj_features: CI and fresh clones
    have no data/dimensions, and a rebuild must never hard-fail on that.
    Null-rate drift is watched by feature-freshness monitoring.
    """
    from Python import config as _config

    try:
        idmap = pl.read_parquet(_config.PROJECT_ROOT / "data" / "dimensions" / "player_id_map.parquet")
        ages = pl.read_parquet(_config.PROJECT_ROOT / "data" / "dimensions" / "player_ages.parquet")
    except FileNotFoundError:
        print("[level 3] age dimensions absent; age terms null (see build_age_table.py)")
        return frame.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("pitcher_age"),
            pl.lit(None, dtype=pl.Float64).alias("pitcher_age2"),
            pl.lit(None, dtype=pl.Float64).alias("age_x_whiff_gap"),
            pl.lit(None, dtype=pl.Float64).alias("age_x_velo_gap"),
        )
    if "mlb_id" not in idmap.columns or "birth_date" not in ages.columns:
        raise ValueError("age dimensions missing expected columns; see build_age_table.py")
    dim = idmap.select(["mlb_id", "player_name"]).join(
        ages.select(["mlb_id", "birth_date"]), on="mlb_id", how="inner"
    ).with_columns(
        pl.col("player_name").map_elements(_age_key, return_dtype=pl.Utf8).alias("_agekey"),
        pl.col("birth_date").str.strptime(pl.Date, "%Y-%m-%d").alias("_dob"),
    ).select(["_agekey", "_dob"]).unique(subset=["_agekey"], keep="first")
    out = frame.with_columns(
        pl.col("player_name").map_elements(_age_key, return_dtype=pl.Utf8).alias("_agekey"),
        pl.col("game_date").cast(pl.Date).alias("_gdate"),
    ).join(dim, on="_agekey", how="left").with_columns(
        ((pl.col("_gdate") - pl.col("_dob")).dt.total_days() / 365.25).alias("pitcher_age"),
    ).with_columns(
        (pl.col("pitcher_age") * pl.col("pitcher_age")).alias("pitcher_age2"),
        (pl.col("pitcher_age") * (pl.col("whiff_rate_P5").cast(pl.Float64)
                                  - pl.col("whiff_rate_P20").cast(pl.Float64))).alias("age_x_whiff_gap"),
        (pl.col("pitcher_age") * (pl.col("ff_velo_P1").cast(pl.Float64)
                                  - pl.col("ff_velo_P10").cast(pl.Float64))).alias("age_x_velo_gap"),
    ).drop(["_agekey", "_dob", "_gdate"])
    n_missing = out["pitcher_age"].null_count()
    if n_missing:
        print(f"[level 3] age join: {n_missing}/{out.height} rows lack DOB (null, kept)")
    return out


def _null_kadj_frame(frame: pl.DataFrame) -> pl.DataFrame:
    """kadj-absent fallback: null column + all-missing flag (never silent zeros)."""
    return frame.with_columns(
        pl.lit(None, dtype=pl.Float64).alias("kadj"),
        pl.lit(1, dtype=pl.Int8).alias("kadj_missing"),
    )


def _join_kadj_features(
    frame: pl.DataFrame,
    pitch_type_games: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Attach usage-weighted per-pitch CSW residual vs league (WS8 kAdj).

    For each start G (strictly prior dates only):
        kadj = sum_pt usage_prior5_pt * (pitcher_roll20_csw_pt - league_prior_csw_pt)

    League prior = expanding pitch-weighted CSW per pitch_type over dates < G.
    Pitcher roll = pitch-weighted CSW per pitch_type over prior 20 starts.
    Usage = pitch shares over prior 5 starts. Gates: >=5 prior starts AND
    >=300 prior pitches, else null + kadj_missing=1 (LightGBM-native).

    Same algorithm as the validated probe
    (production/ops/market_research/ws8_kadj_probe.py) — L3 parity is
    behavioral (coverage ~93%, YoY r ~0.75). Missing/low-history stays null;
    no silent zero-fill (a zero residual is a claim, a null is honesty).
    """
    from Python import config as _config

    if pitch_type_games is None:
        path = _config.PITCH_TYPE_GAMES_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"Missing pitch-type games: {path} (Level 2 output)"
            )
        pitch_type_games = pl.read_parquet(path)
    required = {"game_pk", "pitcher", "game_date", "pitch_type", "Pitches", "CSW"}
    if missing := sorted(required - set(pitch_type_games.columns)):
        raise ValueError(f"pitch_type_games is missing columns: {missing}")
    if missing := sorted({"game_pk", "pitcher", "game_date"} - set(frame.columns)):
        raise ValueError(f"frame is missing kadj keys: {missing}")

    pt = (
        pitch_type_games.filter(pl.col("Pitches") > 0)
        .with_columns(pl.col("game_date").cast(pl.Date))
        .sort(["game_date", "game_pk"])
    )
    fr = frame.with_columns(pl.col("game_date").cast(pl.Date))
    if fr.select("game_pk", "pitcher").is_duplicated().any():
        raise ValueError("frame contains duplicate (game_pk, pitcher) keys")

    # Expanding league prior per (pitch_type, date), strictly prior dates.
    daily = (
        pt.group_by(["pitch_type", "game_date"])
        .agg(pl.col("CSW").sum().alias("csw"), pl.col("Pitches").sum().alias("pit"))
        .sort(["pitch_type", "game_date"])
        .with_columns(
            pl.col("csw").cum_sum().shift(1).over("pitch_type").alias("pcsw"),
            pl.col("pit").cum_sum().shift(1).over("pitch_type").alias("ppit"),
        )
        .with_columns(
            pl.when(pl.col("ppit") > 0)
            .then(pl.col("pcsw") / pl.col("ppit"))
            .otherwise(None)
            .alias("prior_mean")
        )
    )
    league: dict[tuple[str, str], float] = {}
    for r in daily.select(["pitch_type", "game_date", "prior_mean"]).to_dicts():
        if r["prior_mean"] is not None:
            league[(r["pitch_type"], str(r["game_date"]))] = float(r["prior_mean"])

    pt_by_pitcher: dict[int, list[dict]] = {}
    for r in pt.to_dicts():
        pt_by_pitcher.setdefault(int(r["pitcher"]), []).append(r)

    rows = []
    for r in fr.sort(["game_date", "game_pk"]).to_dicts():
        pid = int(r["pitcher"])
        gdate = r["game_date"]
        hist = [h for h in pt_by_pitcher.get(pid, []) if h["game_date"] < gdate]
        starts = sorted({(h["game_date"], int(h["game_pk"])) for h in hist})
        n_prior = len(starts)
        tot_pit = sum(int(h["Pitches"]) for h in hist)
        if n_prior < 5 or tot_pit < 300:
            rows.append({"game_pk": r["game_pk"], "pitcher": pid,
                         "kadj": None})
            continue
        last20 = set(starts[-20:])
        last5 = set(starts[-5:])
        roll: dict[str, list[int]] = {}
        use: dict[str, int] = {}
        use_tot = 0
        for h in hist:
            key = (h["game_date"], int(h["game_pk"]))
            if key in last20:
                slot = roll.setdefault(h["pitch_type"], [0, 0])
                slot[0] += int(h["CSW"])
                slot[1] += int(h["Pitches"])
            if key in last5:
                use[h["pitch_type"]] = use.get(h["pitch_type"], 0) + int(h["Pitches"])
                use_tot += int(h["Pitches"])
        kadj = 0.0
        wsum = 0.0
        gstr = str(gdate)
        for ptype, pcount in use.items():
            w = pcount / use_tot if use_tot else 0.0
            csw, pit = roll.get(ptype, (0, 0))
            base = league.get((ptype, gstr))
            if pit <= 0 or base is None:
                continue
            kadj += w * (csw / pit - base)
            wsum += w
        rows.append({"game_pk": r["game_pk"], "pitcher": pid,
                     "kadj": kadj if wsum else None})

    kj = pl.DataFrame(
        rows,
        schema={"game_pk": pl.Int64, "pitcher": pl.Int64, "kadj": pl.Float64},
        strict=False,
    ).with_columns(
        pl.col("kadj").cast(pl.Float64),
        pl.col("kadj").is_null().cast(pl.Int8).alias("kadj_missing"),
    )
    out = fr.join(kj, on=["game_pk", "pitcher"], how="left", validate="1:1")
    if out.height != fr.height:
        raise ValueError(f"kadj join changed row count: {fr.height} -> {out.height}")
    n_missing = out["kadj"].null_count()
    if n_missing:
        print(f"[level 3] kadj join: {n_missing}/{out.height} rows lack history (null, kept)")
    return out


def _join_park_factors(
    frame: pl.DataFrame,
    park_factors: pl.DataFrame,
) -> pl.DataFrame:
    """Join a complete, unique park dimension or fail loudly."""
    keys = ["season", "home_team"]
    dimension = park_factors.select(*keys, "park_k_factor")

    if dimension.select(keys).is_duplicated().any():
        raise ValueError("park_factors contains duplicate (season, home_team) keys")

    required_seasons = set(frame["season"].drop_nulls().unique().to_list())
    available_seasons = set(
        dimension["season"].drop_nulls().unique().to_list()
    )
    missing_seasons = sorted(required_seasons - available_seasons)
    if missing_seasons:
        raise ValueError(
            f"park_factors is missing rolling-data seasons: {missing_seasons}"
        )

    out = frame.join(
        dimension,
        on=keys,
        how="left",
        validate="m:1",
    )
    if out.height != frame.height:
        raise ValueError(
            f"park-factor join changed row count: {frame.height} -> {out.height}"
        )

    if out["park_k_factor"].null_count():
        missing_keys = (
            out.filter(pl.col("park_k_factor").is_null())
            .select(keys)
            .unique()
            .sort(keys)
            .head(10)
            .to_dicts()
        )
        raise ValueError(
            "park_factors is missing (season, home_team) keys; "
            f"sample={missing_keys}"
        )
    return out


def build_pitcher_training(
    pitcher_rolling: pl.DataFrame,
    batter_rolling: pl.DataFrame,
    park_factors: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Spine + opposing-lineup + park -> model-ready pitcher frame."""
    lineup = opposing_lineup_features(pitcher_rolling, batter_rolling)
    invalid_sizes = lineup.filter(pl.col("opp_lineup_size") != 9)
    if invalid_sizes.height:
        sample = invalid_sizes.select(
            "game_pk", "pitcher", "opp_lineup_size"
        ).head(10).to_dicts()
        raise ValueError(
            "opposing initial-lineup coverage must contain exactly 9 batters; "
            f"sample={sample}"
        )
    lineup_keys = ["game_pk", "pitcher"]
    if lineup.select(lineup_keys).is_duplicated().any():
        raise ValueError("opposing lineup contains duplicate (game_pk, pitcher) keys")

    out = pitcher_rolling.join(
        lineup,
        on=lineup_keys,
        how="left",
        validate="1:1",
    )
    if out.height != pitcher_rolling.height:
        raise ValueError(
            "lineup join changed row count: "
            f"{pitcher_rolling.height} -> {out.height}"
        )
    if park_factors is not None:
        out = _join_park_factors(out, park_factors)
    out = _join_age_features(out)
    try:
        out = _join_kadj_features(out)
    except FileNotFoundError:
        print("[level 3] pitch-type games absent; kadj null (Level 2 output missing)")
        out = _null_kadj_frame(out)
    try:
        out = _join_command_features(out)
    except FileNotFoundError:
        print("[level 3] Open-Command parquet absent; cmd_roll30 null (see build_start_command.py)")
        out = out.with_columns(pl.lit(None, dtype=pl.Float64).alias("cmd_roll30"))
    return out.sort(["game_date", "player_name"])


def build_batter_training(
    batter_rolling: pl.DataFrame,
    park_factors: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Batter rolling + park factor -> model-ready batter frame.

    Opposing-starter features are not yet implemented, so this frame is not
    feature-complete for a batter-side production model.
    """
    out = batter_rolling
    if park_factors is not None and "home_team" in out.columns:
        out = _join_park_factors(out, park_factors)
    sort_keys = [c for c in ("game_date", "game_pk", "batter") if c in out.columns]
    return out.sort(sort_keys) if sort_keys else out


def _write(df: pl.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
    return path


def run() -> dict[str, Path]:
    """Read Level 2 + park factors, build training frames, write Level 3 files."""
    pitcher_rolling = pl.read_parquet(config.PITCHER_ROLLING_PATH)
    batter_rolling = pl.read_parquet(config.BATTER_ROLLING_PATH)
    if not config.PARK_FACTORS_PATH.exists():
        raise FileNotFoundError(
            f"Missing park-factor dimension: {config.PARK_FACTORS_PATH}"
        )
    park_factors = pl.read_parquet(config.PARK_FACTORS_PATH)

    paths = {
        "pitcher_training": _write(
            build_pitcher_training(pitcher_rolling, batter_rolling, park_factors),
            config.PITCHER_TRAINING_PATH,
        ),
        "batter_training": _write(
            build_batter_training(batter_rolling, park_factors),
            config.BATTER_TRAINING_PATH,
        ),
    }
    for name, path in paths.items():
        print(f"[level 3] wrote {name}: {path}")
    return paths


if __name__ == "__main__":
    run()
