"""Level 2 - game-level tables -> leakage-safe rolling features.

The **middle** of the pipeline. Reads the Level 1 game files, applies the
leakage-safe rolling / season-to-date manipulations (the windows chosen from
stabilization analysis), and keeps the static identity/context columns the model
and the Level 3 joins need (game keys, date, teams, home/away, batter hand).

Everything raw and same-game is dropped **except** the pitcher label columns
(``K``, ``PA``, ``Outs``, ``k_rate``), which are the training targets, not
features. This keeps the rolling files clean and hard to leak from. Pass
``keep_raw=True`` if you want to inspect the same-game inputs alongside.

Outputs:
- ``pitcher_rolling.parquet``
- ``batter_rolling.parquet``
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import polars as pl

from .. import config
from ..exit_anomalies import apply_exit_anomaly_overrides
from ..batter_rolling import add_leakage_safe_k
from ..bullpen import (
    add_bullpen_lookback_features,
    bullpen_lookback_column_names,
)
from ..pitcher_rolling import (
    DEFAULT_MEAN_COLS,
    DEFAULT_RATE_STATS,
    DEFAULT_WORKLOAD_COLS,
    add_rolling_pitcher_features,
)

# Any rolling / season-to-date output column ends with one of these.
_ROLLING_RE = re.compile(r"(_P\d+|_std(_vL|_vR|_shrunk)?)$")

# Static identity/context to carry through (kept when present).
_PITCHER_STATIC = (
    "game_pk", "game_date", "season", "pitcher", "player_name", "pitcher_name",
    "p_throws", "home_team", "away_team", "is_home", "opp_team",
    # Phase A / A.1 TBF covariates (pregame; not same-game labels).
    "days_rest", "days_rest_capped", "is_season_debut", "rest_is_long_gap",
    "rest_gap_severity", "is_career_mlb_debut",
    # Phase C bullpen lookbacks (flat team priors).
    *bullpen_lookback_column_names(),
)
# Pitcher label / target-support columns (same-game, but they are the labels).
_PITCHER_LABELS = ("K", "PA", "Outs", "k_rate")

_BATTER_STATIC = (
    "game_pk", "game_date", "season", "batter", "batter_name", "stand",
    "bat_team", "home_team", "away_team", "is_home", "opp_team",
    "is_initial_lineup", "lineup_slot", "lineup_pa_weight",
)

EXIT_ANOMALY_ROLLING_POLICY_VERSION = "v1"
EXIT_ANOMALY_ROLLING_WEIGHTS: dict[str, float] = {
    "high": 0.0,
    "medium": 0.5,
    "low": 1.0,
}


def _rolling_policy_weights() -> dict[str, float]:
    """Resolve rolling anomaly weights with optional env overrides."""
    out = dict(EXIT_ANOMALY_ROLLING_WEIGHTS)
    env_map = {
        "high": "MLB_PROPS_EXIT_ANOMALY_WEIGHT_HIGH",
        "medium": "MLB_PROPS_EXIT_ANOMALY_WEIGHT_MEDIUM",
        "low": "MLB_PROPS_EXIT_ANOMALY_WEIGHT_LOW",
    }
    for key, env_name in env_map.items():
        raw = os.getenv(env_name)
        if raw is None or raw == "":
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        out[key] = min(max(value, 0.0), 1.0)
    return out


def _select(df: pl.DataFrame, keep: tuple[str, ...], keep_raw: bool) -> pl.DataFrame:
    """Keep ``keep`` columns (when present) plus every rolling column."""
    if keep_raw:
        return df
    cols = [c for c in df.columns if c in keep or _ROLLING_RE.search(c)]
    return df.select(cols)


def _apply_exit_anomaly_rolling_policy(starts: pl.DataFrame) -> pl.DataFrame:
    """Confidence-weight starts before rolling updates to limit contamination.

    Policy:
    - high confidence anomaly: weight 0.0 (exclude from rolling updates)
    - medium confidence anomaly: weight 0.5 (partial influence)
    - low / untagged: weight 1.0

    Notes:
    - This affects only the rolling feature computation input.
    - True labels are restored after rolling features are computed.
    """
    override_path = os.getenv("MLB_PROPS_EXIT_ANOMALY_OVERRIDE_PATH")
    tagged = apply_exit_anomaly_overrides(
        starts,
        path=Path(override_path) if override_path else None,
    )
    if tagged.is_empty() or "exit_anomaly_flag" not in tagged.columns:
        return starts
    # restore original game_date dtype for downstream rolling date ops
    if "game_date" in starts.columns:
        source_dtype = tagged.schema.get("game_date")
        target_dtype = starts.schema.get("game_date")
        date_expr = (
            pl.col("game_date").str.to_date(strict=False)
            if source_dtype == pl.Utf8 and target_dtype == pl.Date
            else pl.col("game_date").cast(target_dtype, strict=False)
        )
        tagged = tagged.with_columns(
            date_expr.alias("game_date")
        )

    weights = _rolling_policy_weights()
    weight = (
        pl.when(pl.col("exit_anomaly_flag") & (pl.col("exit_anomaly_confidence") == "high"))
        .then(pl.lit(weights["high"]))
        .when(pl.col("exit_anomaly_flag") & (pl.col("exit_anomaly_confidence") == "medium"))
        .then(pl.lit(weights["medium"]))
        .otherwise(pl.lit(weights["low"]))
        .alias("__rolling_anomaly_weight")
    )
    out = tagged.with_columns(weight)

    # Scale denominator/numerator count columns used by rolling rate/workload features.
    rate_cols = {
        col
        for pair in DEFAULT_RATE_STATS.values()
        for col in pair
        if col in out.columns
    }
    workload_cols = {col for col in DEFAULT_WORKLOAD_COLS if col in out.columns}
    scale_cols = sorted(rate_cols | workload_cols)
    if scale_cols:
        out = out.with_columns(
            (pl.col(col).cast(pl.Float64) * pl.col("__rolling_anomaly_weight")).alias(col)
            for col in scale_cols
        )

    # For high-confidence anomalies, suppress per-start mean/arsenal inputs.
    mean_cols = [c for c in DEFAULT_MEAN_COLS if c in out.columns]
    if mean_cols:
        out = out.with_columns(
            pl.when(pl.col("__rolling_anomaly_weight") == 0.0)
            .then(None)
            .otherwise(pl.col(col))
            .alias(col)
            for col in mean_cols
        )
    return out.drop("__rolling_anomaly_weight")


def build_pitcher_rolling(
    games: pl.DataFrame,
    keep_raw: bool = False,
    bullpen_team_games: pl.DataFrame | None = None,
    bullpen_appearances: pl.DataFrame | None = None,
    use_exit_anomaly_policy: bool = True,
    **kw,
) -> pl.DataFrame:
    """Add leakage-safe rolling pitcher features and trim to statics + rolling."""
    feature_input = _apply_exit_anomaly_rolling_policy(games) if use_exit_anomaly_policy else games
    rolled = add_rolling_pitcher_features(feature_input, **kw)
    # Preserve true labels for evaluation/training targets after feature updates.
    label_cols = [c for c in _PITCHER_LABELS if c in games.columns and c in rolled.columns]
    key_cols = [c for c in ("pitcher", "game_pk") if c in rolled.columns and c in games.columns]
    if label_cols and len(key_cols) == 2:
        truth = games.select([*key_cols, *label_cols])
        rolled = (
            rolled.drop(label_cols)
            .join(truth, on=key_cols, how="left", validate="1:1")
        )
    if bullpen_team_games is not None:
        rolled = add_bullpen_lookback_features(
            rolled,
            bullpen_team_games,
            appearances=bullpen_appearances,
        )
    return _select(rolled, _PITCHER_STATIC + _PITCHER_LABELS, keep_raw)


def build_batter_rolling(games: pl.DataFrame, keep_raw: bool = False, **kw) -> pl.DataFrame:
    """Add leakage-safe rolling batter features and trim to statics + rolling."""
    rolled = add_leakage_safe_k(games, **kw)
    return _select(rolled, _BATTER_STATIC, keep_raw)


def _write(df: pl.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
    return path


def run(keep_raw: bool = False) -> dict[str, Path]:
    """Read Level 1 game files, build rolling features, write Level 2 files."""
    pitcher_games = pl.read_parquet(config.PITCHER_GAMES_PATH)
    batter_games = pl.read_parquet(config.BATTER_GAMES_PATH)
    bullpen_team_games = (
        pl.read_parquet(config.BULLPEN_TEAM_GAMES_PATH)
        if config.BULLPEN_TEAM_GAMES_PATH.exists()
        else None
    )
    bullpen_appearances = (
        pl.read_parquet(config.BULLPEN_APPEARANCES_PATH)
        if config.BULLPEN_APPEARANCES_PATH.exists()
        else None
    )
    if bullpen_team_games is None:
        print(
            "[level 2] warning: missing bullpen_team_games.parquet; "
            "Phase C lookbacks skipped. Re-run Level 1."
        )

    paths = {
        "pitcher_rolling": _write(
            build_pitcher_rolling(
                pitcher_games,
                keep_raw=keep_raw,
                bullpen_team_games=bullpen_team_games,
                bullpen_appearances=bullpen_appearances,
            ),
            config.PITCHER_ROLLING_PATH,
        ),
        "batter_rolling": _write(
            build_batter_rolling(batter_games, keep_raw=keep_raw),
            config.BATTER_ROLLING_PATH,
        ),
    }
    for name, path in paths.items():
        print(f"[level 2] wrote {name}: {path}")
    return paths


if __name__ == "__main__":
    run()
