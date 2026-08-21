"""Live / historical slate scoring: frozen k-rate × TBF → count layer.

Assembles feature rows and scores with persisted artifacts. Historical mode
uses Level 3 rows already in ``pitcher_training`` (wiring proof). Live mode
builds as-of rows from Level 2 + announced lineups (requires rolling history
through yesterday).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import polars as pl

from Python import config
from Python.bullpen import add_bullpen_lookback_features
from Python.count_layer import DEFAULT_K_LINES, PROJECTION_K_LINES, attach_count_predictions
from Python.daily_lineups import DailySlate
from Python import identity
from Python.projection_support import EXTREME_REST_DAYS, mark_out_of_support
from Python.prob_calibration import (
    apply_prob_calibration,
    default_bundle_path,
    load_bundle,
    p_over_col,
)
from Python.training import lightgbm_matrix, predict_nonnegative

# DFS / MLB abbreviations → Statcast team codes used in Level 1–3.
_TO_STATCAST_TEAM: dict[str, str] = {
    "ARI": "AZ",
    "AZ": "AZ",
    "ATH": "ATH",  # present in 2025 rolling; keep as-is when available
    "OAK": "OAK",
}

_DEFAULT_KRATE = config.MODEL_DIR
DEFAULT_KRATE_STEM = config.MODEL_DIR / "lightgbm_krate_20260803_155401"
DEFAULT_TBF_JOBLIB = (
    config.MODEL_DIR / "tbf_pa_ridge_workload_context_bullpen_20260728_035607.joblib"
)
DEFAULT_KRATE_ENSEMBLE_CONFIG = (
    config.PROJECT_ROOT / "production" / "ops" / "live_krate_ensemble.json"
)

_PRODUCTION_LINEUP_COLS = (
    "opp_lineup_k",
    "opp_lineup_k_vs_hand",
    "opp_lineup_whiff",
    "opp_lineup_swstr",
    "opp_lineup_chase",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_team_code(code: str) -> str:
    """Map daily-lineup abbreviations onto Statcast / training team codes."""
    raw = str(code).strip().upper()
    return _TO_STATCAST_TEAM.get(raw, raw)


def _normalize_team_expr(column: str) -> pl.Expr:
    return (
        pl.col(column)
        .cast(pl.Utf8)
        .str.to_uppercase()
        .replace(_TO_STATCAST_TEAM)
    )


def load_krate_booster(
    stem: Path = DEFAULT_KRATE_STEM,
) -> tuple[lgb.Booster, list[str], dict[str, Any]]:
    """Load the frozen LightGBM text model + feature metadata.

    Prefer ``model_str`` over ``model_file`` on Windows — file-handle loads can
    leave a null booster pointer after Jupyter module reloads, which then AV's
    inside ``predict``.
    """
    txt = stem.with_suffix(".txt")
    meta_path = stem.with_suffix(".json")
    if not txt.exists():
        raise FileNotFoundError(f"Missing LightGBM model text: {txt}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    features = list(meta["features"])
    booster = lgb.Booster(model_str=txt.read_text(encoding="utf-8"))
    # Touch the handle early so a bad load fails here, not inside predict.
    if booster.num_trees() <= 0:
        raise RuntimeError(f"LightGBM model loaded with zero trees: {txt}")
    return booster, features, meta


def load_tbf_bundle(path: Path = DEFAULT_TBF_JOBLIB) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing TBF joblib {path}. Run: "
            "python models/TBF-Model/train.py --model ridge --tune-alpha --persist"
        )
    bundle = joblib.load(path)
    required = {"model", "features", "prediction_upper_clip"}
    missing = required - set(bundle)
    if missing:
        raise ValueError(f"TBF joblib missing keys: {sorted(missing)}")
    return bundle


def _resolve_stem(pathish: str | Path) -> Path:
    raw = Path(pathish)
    if raw.suffix in {".txt", ".json"}:
        raw = raw.with_suffix("")
    if raw.is_absolute():
        return raw
    return (config.PROJECT_ROOT / raw).resolve()


def _load_krate_ensemble_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    models = payload.get("models", [])
    if not isinstance(models, list) or not models:
        raise ValueError(f"Invalid ensemble config at {path}: missing models")
    total = 0.0
    for row in models:
        if "stem" not in row or "weight" not in row:
            raise ValueError(f"Invalid ensemble config row at {path}: {row}")
        total += float(row["weight"])
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Ensemble weights must sum to 1.0, got {total:.6f} at {path}")
    return payload


def american_odds_from_prob(p: float) -> int:
    """Convert a win probability to fair American odds (no vig)."""
    prob = float(min(max(p, 1e-6), 1.0 - 1e-6))
    if prob >= 0.5:
        return int(round(-prob / (1.0 - prob) * 100.0))
    return int(round((1.0 - prob) / prob * 100.0))


def attach_fair_american_odds(
    frame: pd.DataFrame,
    *,
    lines: Sequence[float] = PROJECTION_K_LINES,
    prefer_calibrated: bool = True,
) -> pd.DataFrame:
    """Add ``fair_amer_{line}`` from calibrated ``p_over_*_cal`` when present.

    Falls back to raw ``p_over_*``. Does not modify probability columns.
    """
    out = frame.copy()
    for line in lines:
        raw_key = p_over_col(line, calibrated=False)
        cal_key = p_over_col(line, calibrated=True)
        a_key = f"fair_amer_{line_to_stem(line)}"
        p_key = (
            cal_key
            if prefer_calibrated and cal_key in out.columns
            else raw_key
        )
        if p_key not in out.columns:
            continue
        out[a_key] = [
            american_odds_from_prob(p) if pd.notna(p) else pd.NA
            for p in out[p_key].tolist()
        ]
    return out


def line_to_stem(line: float) -> str:
    return str(line).replace(".", "_")


def score_frame(
    frame: pd.DataFrame,
    *,
    krate_stem: Path = DEFAULT_KRATE_STEM,
    tbf_joblib: Path = DEFAULT_TBF_JOBLIB,
    lines: Sequence[float] | None = None,
    calibration_path: Path | None | bool = True,
    krate_ensemble_config: Path | None | bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Score a feature frame with frozen k-rate + TBF + binomial count layer.

    ``calibration_path``:
      - ``True`` (default): load production calibrator pointer if present
      - ``Path``: load that joblib
      - ``False`` / ``None``: skip post-hoc calibration (raw ``p_over_*`` only)
    """
    line_set = tuple(lines) if lines is not None else DEFAULT_K_LINES
    k_meta: dict[str, Any] = {}
    k_hat: np.ndarray
    ensemble_used = False
    ensemble_members: list[dict[str, Any]] = []
    ensemble_path: Path | None
    if krate_ensemble_config is True:
        ensemble_path = DEFAULT_KRATE_ENSEMBLE_CONFIG
    elif krate_ensemble_config is False or krate_ensemble_config is None:
        ensemble_path = None
    else:
        ensemble_path = Path(krate_ensemble_config)

    if ensemble_path is not None and ensemble_path.exists():
        cfg = _load_krate_ensemble_config(ensemble_path)
        blend = np.zeros(len(frame), dtype=np.float64)
        for row in cfg["models"]:
            stem = _resolve_stem(str(row["stem"]))
            weight = float(row["weight"])
            booster_i, features_i, meta_i = load_krate_booster(stem)
            missing_i = [c for c in features_i if c not in frame.columns]
            if missing_i:
                raise ValueError(
                    f"frame missing ensemble k-rate features for {stem}: {missing_i[:12]}"
                )
            pred_i = np.clip(
                booster_i.predict(lightgbm_matrix(frame, features_i), num_threads=1),
                0.0,
                1.0,
            )
            blend += weight * pred_i
            ensemble_members.append(
                {
                    "stem": str(stem),
                    "weight": weight,
                    "n_features": len(features_i),
                    "registry_freeze": meta_i.get("registry_freeze"),
                }
            )
        k_hat = np.clip(blend, 0.0, 1.0)
        k_meta = {"ensemble": cfg}
        ensemble_used = True
    else:
        booster, k_features, k_meta = load_krate_booster(krate_stem)
        missing_k = [c for c in k_features if c not in frame.columns]
        if missing_k:
            raise ValueError(f"frame missing k-rate features: {missing_k[:12]}")
        k_hat = np.clip(
            booster.predict(
                lightgbm_matrix(frame, k_features),
                num_threads=1,
            ),
            0.0,
            1.0,
        )

    tbf = load_tbf_bundle(tbf_joblib)
    tbf_features = list(tbf["features"])
    missing_t = [c for c in tbf_features if c not in frame.columns]
    if missing_t:
        raise ValueError(f"frame missing TBF features: {missing_t[:12]}")
    tbf_hat = predict_nonnegative(
        tbf["model"],
        "ridge",
        frame,
        tbf_features,
        upper=float(tbf["prediction_upper_clip"]),
    )
    scored = attach_count_predictions(
        frame,
        k_rate=k_hat,
        projected_tbf=tbf_hat,
        lines=line_set,
        kappa=None,
    )

    cal_meta: dict[str, Any] = {
        "calibration_applied": False,
        "calibration_version": None,
        "calibration_path": None,
    }
    path: Path | None
    if calibration_path is True:
        path = default_bundle_path()
    elif calibration_path is False or calibration_path is None:
        path = None
    else:
        path = Path(calibration_path)

    if path is not None and path.exists():
        bundle = load_bundle(path)
        scored = apply_prob_calibration(scored, bundle, lines=line_set)
        cal_meta = {
            "calibration_applied": True,
            "calibration_version": bundle.version,
            "calibration_method": bundle.method,
            "calibration_path": str(path),
            "calibration_fit_cutoff": bundle.fit_cutoff,
        }

    scored = attach_fair_american_odds(scored, lines=line_set, prefer_calibrated=True)
    # Add pregame support gating to flag opener/piggyback-like rows before sizing.
    scored = mark_out_of_support(pl.from_pandas(scored)).to_pandas()
    report = {
        "k_rate_model": str(krate_stem.with_suffix(".txt")) if not ensemble_used else None,
        "k_rate_sha256": _sha256(krate_stem.with_suffix(".txt")) if not ensemble_used else None,
        "k_rate_n_features": len(k_features) if not ensemble_used else None,
        "k_rate_ensemble_used": ensemble_used,
        "k_rate_ensemble_config": str(ensemble_path) if ensemble_used and ensemble_path is not None else None,
        "k_rate_ensemble_members": ensemble_members if ensemble_used else [],
        "tbf_model": str(tbf_joblib),
        "tbf_sha256": _sha256(tbf_joblib),
        "tbf_n_features": len(tbf_features),
        "tbf_alpha": tbf.get("ridge_alpha"),
        "lines": list(line_set),
        "n_scored": int(len(scored)),
        "mean_k_rate_pred": float(np.mean(k_hat)),
        "mean_projected_tbf": float(np.mean(tbf_hat)),
        "mean_expected_K": float(np.mean(scored["expected_K"])),
        "n_out_of_support": int(scored["is_out_of_support"].fillna(False).sum())
        if "is_out_of_support" in scored.columns
        else 0,
        "approved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "k_rate_registry": k_meta.get("registry_freeze"),
        "out_of_support_policy": (
            "mark projected_tbf/expected_K instability and extreme rest as OOS; "
            f"days_rest>={EXTREME_REST_DAYS} always OOS"
        ),
        **cal_meta,
    }
    return scored, report


def daily_projection_board(
    scored: pd.DataFrame,
    *,
    lines: Sequence[float] = PROJECTION_K_LINES,
    preferred_only: bool = False,
) -> pl.DataFrame:
    """Readable daily board: dual RG/MLB rows stacked for the same matchup.

    Sort order groups ``(away @ home, side)`` so disagreement pairs sit on
    consecutive rows for direct comparison. Identical pitcher IDs from both
    sources are not duplicated upstream (``expand_dual_starter_slate``).
    """
    frame = scored.copy()
    if preferred_only and "is_preferred" in frame.columns:
        frame = frame.loc[frame["is_preferred"].fillna(True)].copy()
    if "fair_amer_3_5" not in frame.columns:
        frame = attach_fair_american_odds(frame, lines=lines)

    base_cols = [
        c
        for c in (
            "game_pk",
            "game_date",
            "away_team",
            "home_team",
            "is_home",
            "player_name",
            "pitcher",
            "starter_source",
            "starter_disagreement",
            "is_preferred",
            "rg_pitcher_id",
            "mlb_probable_pitcher_id",
            "expected_K",
            "projected_tbf",
            "k_rate_pred",
            "days_rest",
            "opp_lineup_size",
            "opp_lineup_k",
            "opp_lineup_k_vs_hand",
            "opp_lineup_whiff",
            "opp_lineup_swstr",
            "opp_lineup_chase",
        )
        if c in frame.columns
    ]
    line_cols: list[str] = []
    for line in lines:
        stem = str(line).replace(".", "_")
        for col in (
            f"p_over_{stem}",
            f"p_over_{stem}_cal",
            f"fair_amer_{stem}",
        ):
            if col in frame.columns:
                line_cols.append(col)
    for meta_col in (
        "calibration_version",
        "calibration_method",
        "calibration_scope",
    ):
        if meta_col in frame.columns and meta_col not in base_cols:
            base_cols.append(meta_col)

    board = pl.from_pandas(frame[base_cols + line_cols])
    if "starter_source" in board.columns:
        board = board.with_columns(
            pl.when(pl.col("starter_source") == "mlb_probable")
            .then(0)
            .when(pl.col("starter_source") == "rotogrinders")
            .then(1)
            .otherwise(2)
            .alias("_source_rank")
        )
    sort_keys = [
        c
        for c in ("game_pk", "is_home", "_source_rank", "starter_source")
        if c in board.columns
    ]
    if sort_keys:
        board = board.sort(sort_keys)
    if "_source_rank" in board.columns:
        board = board.drop("_source_rank")
    return board


def historical_training_rows(game_date: date) -> pd.DataFrame:
    """Load Level 3 rows for one calendar date (already has all features)."""
    frame = pl.read_parquet(config.PITCHER_TRAINING_PATH)
    frame = frame.with_columns(pl.col("game_date").cast(pl.Date))
    day = frame.filter(pl.col("game_date") == game_date)
    if day.is_empty():
        raise ValueError(
            f"No pitcher_training rows for {game_date}. "
            f"Rolling coverage ends {pl.read_parquet(config.PITCHER_ROLLING_PATH)['game_date'].max()}."
        )
    return day.to_pandas()


def _asof_pitcher_form(
    pitcher_ids: list[int],
    *,
    asof: date,
    rolling: pl.DataFrame,
) -> pl.DataFrame:
    """Last prior start per pitcher (form columns). Rest is recomputed later."""
    hist = rolling.filter(
        (pl.col("game_date") < asof) & pl.col("pitcher").is_in(pitcher_ids)
    )
    if hist.is_empty():
        raise ValueError(f"No pitcher_rolling history before {asof}")
    # Most recent prior start per pitcher.
    latest = (
        hist.sort(["pitcher", "game_date"])
        .group_by("pitcher", maintain_order=True)
        .agg(pl.all().last())
        .rename({"game_date": "prior_start_date"})
    )
    return latest


def _live_lineup_aggregates(
    slate: DailySlate,
    *,
    asof: date,
    batter_rolling: pl.DataFrame,
) -> pl.DataFrame:
    """Production opp-lineup means from announced batters' as-of rates."""
    lineups = slate.lineups.with_columns(
        _normalize_team_expr("team").alias("bat_team"),
        pl.col("batting_order").alias("lineup_slot"),
    )
    # As-of batter form: last game before slate date.
    br = batter_rolling.filter(pl.col("game_date") < asof)
    latest = (
        br.sort(["batter", "game_date"])
        .group_by("batter", maintain_order=True)
        .agg(pl.all().last())
    )
    needed = [
        c
        for c in (
            "batter",
            "k_rate_std",
            "k_rate_std_vL",
            "k_rate_std_vR",
            "whiff_rate_std",
            "swstr_rate_std",
            "chase_rate_std",
            "zswing_rate_P10",
            "swing_rate_P10",
            "zcontact_rate_P20",
            "bb_rate_std",
        )
        if c in latest.columns
    ]
    bat = lineups.join(latest.select(needed), on="batter", how="left")

    starters = slate.starters.with_columns(
        _normalize_team_expr("team").alias("pitch_team"),
        _normalize_team_expr("opponent").alias("opp_team"),
        pl.when(pl.col("throws").is_not_null())
        .then(pl.col("throws").str.to_uppercase())
        .otherwise(None)
        .alias("p_throws"),
    ).select("game_pk", "pitcher", "p_throws", "opp_team")

    joined = starters.join(
        bat,
        left_on=["game_pk", "opp_team"],
        right_on=["game_pk", "bat_team"],
        how="left",
    ).with_columns(
        pl.when(pl.col("p_throws") == "R")
        .then(pl.col("k_rate_std_vR"))
        .when(pl.col("p_throws") == "L")
        .then(pl.col("k_rate_std_vL"))
        .otherwise(None)
        .alias("_k_vs_hand")
    )
    aggregations = [
        pl.col("batter").count().alias("opp_lineup_size"),
        pl.col("k_rate_std").mean().alias("opp_lineup_k"),
        pl.col("_k_vs_hand").mean().alias("opp_lineup_k_vs_hand"),
        pl.col("whiff_rate_std").mean().alias("opp_lineup_whiff"),
        pl.col("swstr_rate_std").mean().alias("opp_lineup_swstr"),
        pl.col("chase_rate_std").mean().alias("opp_lineup_chase"),
    ]
    for source, output in (
        ("zswing_rate_P10", "opp_lineup_zswing_P10"),
        ("swing_rate_P10", "opp_lineup_swing_P10"),
        ("zcontact_rate_P20", "opp_lineup_zcontact_P20"),
        ("bb_rate_std", "opp_lineup_bb"),
    ):
        if source in joined.columns:
            aggregations.append(pl.col(source).mean().alias(output))
    return joined.group_by("game_pk", "pitcher").agg(aggregations)


def expand_dual_starter_slate(slate: DailySlate) -> DailySlate:
    """Score both RotoGrinders and MLB probable pitchers when they disagree.

    Emits one row per (game, source). On disagreement, ``is_preferred`` is True
    for the MLB probable (announced starter) and False for the RG projection.
    When they agree — or MLB has not announced — only the RG row is kept and
    marked preferred.
    """
    starters = slate.starters
    if starters.is_empty():
        return slate
    if "official_probable_pitcher_id" not in starters.columns:
        annotated = starters.with_columns(
            pl.lit("rotogrinders").alias("starter_source"),
            pl.lit(False).alias("starter_disagreement"),
            pl.lit(True).alias("is_preferred"),
            pl.col("pitcher").cast(pl.Int64).alias("rg_pitcher_id"),
            pl.lit(None, dtype=pl.Int64).alias("mlb_probable_pitcher_id"),
        )
        return DailySlate(lineups=slate.lineups, starters=annotated)

    try:
        name_by_id = {
            int(row["mlb_id"]): str(row["player_name"])
            for row in identity.load_player_map().iter_rows(named=True)
        }
    except Exception:  # noqa: BLE001
        name_by_id = {}

    rows: list[dict[str, Any]] = []
    for row in starters.to_dicts():
        rg_id = int(row["pitcher"])
        mlb_raw = row.get("official_probable_pitcher_id")
        mlb_id = int(mlb_raw) if mlb_raw is not None else None
        disagree = mlb_id is not None and mlb_id != rg_id

        rg_row = dict(row)
        rg_row["starter_source"] = "rotogrinders"
        rg_row["starter_disagreement"] = disagree
        rg_row["rg_pitcher_id"] = rg_id
        rg_row["mlb_probable_pitcher_id"] = mlb_id
        rg_row["is_preferred"] = not disagree
        rows.append(rg_row)

        if disagree and mlb_id is not None:
            mlb_row = dict(row)
            mlb_row["pitcher"] = mlb_id
            mlb_row["player_name"] = name_by_id.get(mlb_id, f"mlb_id:{mlb_id}")
            mlb_row["throws"] = None
            mlb_row["source_player_path"] = None
            mlb_row["starter_source"] = "mlb_probable"
            mlb_row["starter_disagreement"] = True
            mlb_row["rg_pitcher_id"] = rg_id
            mlb_row["mlb_probable_pitcher_id"] = mlb_id
            mlb_row["is_preferred"] = True
            rows.append(mlb_row)

    return DailySlate(
        lineups=slate.lineups,
        starters=pl.DataFrame(rows, infer_schema_length=len(rows)),
    )


def build_live_feature_frame(
    slate: DailySlate,
    *,
    allow_stale: bool = False,
    dual_starters: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build Level-3-shaped rows for a scraped slate (as-of yesterday history).

    When ``dual_starters`` is True (default), RotoGrinders vs MLB probable
    disagreements produce two scored rows per team with ``starter_source`` /
    ``starter_disagreement`` / ``is_preferred`` flags.
    """
    if "pitcher" not in slate.starters.columns:
        raise ValueError("slate starters missing resolved pitcher IDs")
    if dual_starters:
        slate = expand_dual_starter_slate(slate)

    asof = date.fromisoformat(str(slate.starters["game_date"][0]))
    rolling = pl.read_parquet(config.PITCHER_ROLLING_PATH).with_columns(
        pl.col("game_date").cast(pl.Date)
    )
    batter_rolling = pl.read_parquet(config.BATTER_ROLLING_PATH).with_columns(
        pl.col("game_date").cast(pl.Date)
    )
    park = pl.read_parquet(config.PARK_FACTORS_PATH)
    max_hist = rolling["game_date"].max()
    stale_days = (asof - max_hist).days if max_hist is not None else None
    if stale_days is not None and stale_days > 1 and not allow_stale:
        raise ValueError(
            f"pitcher_rolling ends {max_hist}; slate is {asof} "
            f"({stale_days} days stale). Refresh Level 1–2 through yesterday, "
            "or pass allow_stale=True for a degraded smoke run."
        )

    pitcher_ids = [int(x) for x in slate.starters["pitcher"].to_list()]
    form = _asof_pitcher_form(pitcher_ids, asof=asof, rolling=rolling)

    starters = slate.starters.with_columns(
        _normalize_team_expr("home_team").alias("home_team"),
        _normalize_team_expr("away_team").alias("away_team"),
        _normalize_team_expr("opponent").alias("opp_team"),
        _normalize_team_expr("team").alias("pitch_team"),
        pl.lit(asof.year).alias("season"),
        pl.col("game_date").cast(pl.Date),
    )

    # Drop rolling identity/context that we replace from the slate.
    drop_from_form = [
        c
        for c in (
            "game_pk",
            "game_date",
            "season",
            "home_team",
            "away_team",
            "opp_team",
            "is_home",
            "player_name",
            "prior_start_date",
            "days_rest",
            "days_rest_capped",
            "rest_is_long_gap",
            "rest_gap_severity",
            "is_season_debut",
            "is_career_mlb_debut",
        )
        if c in form.columns
    ]
    # Keep p_throws from history when available.
    form_feats = form.drop([c for c in drop_from_form if c != "prior_start_date"])

    spine = starters.join(form_feats, on="pitcher", how="left")
    # Prefer historical p_throws; fall back to scraped throws.
    throw_fallback = (
        pl.col("throws").str.to_uppercase()
        if "throws" in spine.columns
        else pl.lit(None)
    )
    if "p_throws" in spine.columns:
        spine = spine.with_columns(
            pl.coalesce(pl.col("p_throws"), throw_fallback).alias("p_throws")
        )
    else:
        spine = spine.with_columns(throw_fallback.alias("p_throws"))

    # Rest relative to slate date.
    spine = spine.with_columns(
        (pl.col("game_date") - pl.col("prior_start_date"))
        .dt.total_days()
        .alias("days_rest")
    ).with_columns(
        pl.col("days_rest").clip(1, 15).alias("days_rest_capped"),
        (pl.col("days_rest") > 15).cast(pl.Int8).alias("rest_is_long_gap"),
        pl.when(pl.col("days_rest") > 15)
        .then((pl.col("days_rest") - 15).cast(pl.Float64))
        .otherwise(0.0)
        .alias("rest_gap_severity"),
        pl.lit(0).cast(pl.Int8).alias("is_season_debut"),
        pl.lit(0).cast(pl.Int8).alias("is_career_mlb_debut"),
    )

    # Bullpen lookbacks as-of slate date.
    if config.BULLPEN_TEAM_GAMES_PATH.exists():
        bp = pl.read_parquet(config.BULLPEN_TEAM_GAMES_PATH).with_columns(
            pl.col("game_date").cast(pl.Date)
        )
        appearances = (
            pl.read_parquet(config.BULLPEN_APPEARANCES_PATH).with_columns(
                pl.col("game_date").cast(pl.Date)
            )
            if config.BULLPEN_APPEARANCES_PATH.exists()
            else None
        )
        # Drop any stale bullpen cols copied from prior start, then recompute.
        bullpen_cols = [c for c in spine.columns if c.startswith("bullpen_")]
        if bullpen_cols:
            spine = spine.drop(bullpen_cols)
        spine = add_bullpen_lookback_features(
            spine, bp, appearances=appearances
        )

    lineup = _live_lineup_aggregates(
        slate, asof=asof, batter_rolling=batter_rolling
    )
    # Replace any lineup cols from prior form.
    for col in (*_PRODUCTION_LINEUP_COLS, "opp_lineup_size"):
        if col in spine.columns:
            spine = spine.drop(col)
    spine = spine.join(lineup, on=["game_pk", "pitcher"], how="left")

    if "park_k_factor" in spine.columns:
        spine = spine.drop("park_k_factor")
    season_park = asof.year
    # Prefer exact season; if missing (e.g. early 2026), fall back to prior.
    park_seasons = set(park["season"].unique().to_list())
    use_season = season_park if season_park in park_seasons else season_park - 1
    park_dim = park.filter(pl.col("season") == use_season).select(
        "home_team", "park_k_factor"
    )
    spine = spine.join(park_dim, on="home_team", how="left")

    # Never carry prior-start labels into a pregame score frame.
    for label in ("K", "PA", "Outs", "k_rate"):
        if label in spine.columns:
            spine = spine.drop(label)

    n_disagree = (
        int(spine.filter(pl.col("starter_disagreement")).height)
        if "starter_disagreement" in spine.columns
        else 0
    )
    meta = {
        "mode": "live_asof",
        "slate_date": asof.isoformat(),
        "rolling_max_date": str(max_hist),
        "stale_days": stale_days,
        "allow_stale": allow_stale,
        "dual_starters": dual_starters,
        "n_disagreement_rows": n_disagree,
        "park_season_used": use_season,
        "n_starters": spine.height,
        "n_missing_form": int(spine.filter(pl.col("prior_start_date").is_null()).height)
        if "prior_start_date" in spine.columns
        else None,
        "n_incomplete_lineups": int(
            spine.filter(pl.col("opp_lineup_size") < 9).height
        )
        if "opp_lineup_size" in spine.columns
        else None,
        "phase_d_note": (
            "Announced starters may include openers; research metrics are "
            "conditional on PA>=9. Treat known openers as out-of-support."
        ),
        "starter_policy": (
            "Dual-score RG + MLB probable on disagreement; is_preferred=True "
            "for MLB probable when they differ, else RG."
        ),
    }
    return spine.to_pandas(), meta
