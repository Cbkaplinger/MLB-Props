"""Build a preferred-board × live strikeout-odds recommendation table.

Joins logged projections to SharpAPI main-line K props, scores both sides with
local de-vig / edge / unit sizing. Product layer only.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

import polars as pl

from Python import config
from Python.kpi_policy import load_kpi_policy
from Python.count_layer import p_strikeouts_ge
from Python.market import (
    DEFAULT_EDGE_FLOOR,
    evaluate_side,
    size_in_units,
)
from Python.odds_ledger import ODDS_DIR, norm_player_name
from Python.projection_support import row_oos_reason
from Python.sharp_odds import StrikeoutQuote, fetch_mlb_strikeout_quotes

LOG_PATH = config.OUTPUT_DIR / "projection_log" / "projections.parquet"
BOARD_PARQUET = ODDS_DIR / "recommendations.parquet"
BOARD_HTML = ODDS_DIR / "recommendations.html"
BOARD_META = ODDS_DIR / "recommendations_meta.json"
SCORECARD_DAILY = ODDS_DIR / "model_health_scorecard_daily.parquet"
LINE_PRICE_CORR_PATH = ODDS_DIR / "line_price_correction_table.parquet"
LINE_PRICE_CORR_APPROVED_PATH = ODDS_DIR / "line_price_correction_table_approved.parquet"
CALIBRATION_DEPLOY_MATRIX_PATH = ODDS_DIR / "calibration_deploy_matrix.parquet"
LINE_FLOOR_POLICY_PATH = (
    config.PROJECT_ROOT
    / "production"
    / "ops"
    / "market_research"
    / "line_floor_policy.json"
)


def _norm_name(s: str) -> str:
    return norm_player_name(s)


def _line_to_col(line: float) -> str:
    return f"p_over_{int(line)}_{int(round((line - int(line)) * 10))}"


def _line_key(line: float) -> str:
    return f"{float(line):.1f}"


def _load_line_floor_map() -> dict[str, float]:
    if not LINE_FLOOR_POLICY_PATH.exists():
        return {}
    try:
        payload = json.loads(LINE_FLOOR_POLICY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    raw = payload.get("line_edge_floors", {}) if isinstance(payload, dict) else {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def _price_bucket(price: float) -> str:
    p = float(price)
    if p <= -170:
        return "fav_le_-170"
    if p <= -140:
        return "fav_-169_to_-140"
    if p <= -115:
        return "fav_-139_to_-115"
    if p <= -105:
        return "coin_-114_to_-105"
    if p <= 105:
        return "coin_-104_to_+105"
    if p <= 130:
        return "dog_+106_to_+130"
    if p <= 160:
        return "dog_+131_to_+160"
    return "dog_gt_+160"


def _load_line_price_offsets() -> dict[tuple[float, str], float]:
    """Collapsed correction offsets keyed by (line, over_price_bucket)."""
    use_path = (
        LINE_PRICE_CORR_APPROVED_PATH
        if LINE_PRICE_CORR_APPROVED_PATH.exists()
        else LINE_PRICE_CORR_PATH
    )
    if not use_path.exists():
        return {}
    table = pl.read_parquet(use_path)
    if table.is_empty():
        return {}
    offset_col = "prob_offset_final" if "prob_offset_final" in table.columns else "prob_offset"
    collapsed = (
        table.group_by(["line", "over_price_bucket"])
        .agg(
            ((pl.col(offset_col) * pl.col("n")).sum() / pl.col("n").sum()).alias(
                "prob_offset"
            )
        )
        .to_dicts()
    )
    out: dict[tuple[float, str], float] = {}
    for r in collapsed:
        out[(float(r["line"]), str(r["over_price_bucket"]))] = float(r["prob_offset"])
    return out


def _load_deploy_segment_states() -> dict[tuple[float, str, str], str]:
    if not CALIBRATION_DEPLOY_MATRIX_PATH.exists():
        return {}
    table = pl.read_parquet(CALIBRATION_DEPLOY_MATRIX_PATH)
    if table.is_empty() or "deploy_state" not in table.columns:
        return {}
    return {
        (
            float(r["line"]),
            str(r["over_price_bucket"]),
            str(r["maturity_bucket"]),
        ): str(r["deploy_state"])
        for r in table.select(
            "line", "over_price_bucket", "maturity_bucket", "deploy_state"
        ).to_dicts()
    }


def _bucket_from_starts(starts: int) -> str:
    if starts < 10:
        return "early_lt10"
    if starts < 20:
        return "mid_10_19"
    return "mature_20_plus"


@lru_cache(maxsize=32)
def _historical_starts_by_pitcher(game_date_iso: str) -> dict[str, int]:
    """Approx prior starts from logged projection history before game date."""
    if not LOG_PATH.exists():
        return {}
    try:
        cutoff = date.fromisoformat(str(game_date_iso))
        hist = pl.read_parquet(LOG_PATH)
    except Exception:
        return {}
    if hist.is_empty() or "game_date" not in hist.columns or "player_name" not in hist.columns:
        return {}
    try:
        counts = (
            hist.with_columns(
                pl.col("game_date").cast(pl.Date).alias("game_date"),
                pl.col("player_name")
                .cast(pl.Utf8)
                .map_elements(_norm_name, return_dtype=pl.Utf8)
                .alias("player_norm"),
            )
            .filter(pl.col("game_date") < pl.lit(cutoff))
            .group_by("player_norm")
            .agg(pl.col("game_date").n_unique().alias("prior_starts_in_season"))
            .to_dicts()
        )
    except Exception:
        return {}
    return {
        str(r["player_norm"]): int(r["prior_starts_in_season"])
        for r in counts
        if r.get("player_norm") is not None and r.get("prior_starts_in_season") is not None
    }


def _maturity_bucket(board_row: dict[str, Any]) -> str:
    raw = board_row.get("maturity_bucket")
    if raw is not None:
        raw_str = str(raw).strip().lower()
        if raw_str not in {"", "unknown", "none", "null", "nan"}:
            return str(raw)
    starts = board_row.get("prior_starts_in_season")
    try:
        return _bucket_from_starts(int(starts))
    except (TypeError, ValueError):
        pass
    gdate = board_row.get("game_date")
    pname = board_row.get("player_name")
    if gdate is None or pname is None:
        return "unknown"
    try:
        gdate_iso = str(gdate)[:10]
        key = _norm_name(str(pname))
        prior = _historical_starts_by_pitcher(gdate_iso).get(key)
        if prior is not None:
            return _bucket_from_starts(int(prior))
    except Exception:
        return "unknown"
    return "unknown"


def p_model_over_for_line(board_row: dict[str, Any], line: float) -> float | None:
    """Model P(over) at ``line`` from logged probs (prefer calibrated).

    Preference order:
      1. ``p_over_*_cal`` (post-hoc calibrated)
      2. ``p_over_*`` (raw count-layer)
      3. binomial fallback from ``k_rate_pred`` × ``projected_tbf``
    """
    col = _line_to_col(line)
    cal_col = f"{col}_cal"
    for key in (cal_col, col):
        raw = board_row.get(key)
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass

    rate = board_row.get("k_rate_pred")
    tbf = board_row.get("projected_tbf")
    if rate is None or tbf is None:
        ek = board_row.get("expected_K")
        if ek is not None and tbf is not None and float(tbf) > 0:
            rate = float(ek) / float(tbf)
        else:
            return None
    try:
        p = p_strikeouts_ge(
            float(line),
            k_rate=[float(rate)],
            projected_tbf=[float(tbf)],
            family="binomial",
        )
    except (TypeError, ValueError):
        return None
    return float(p[0])


def load_projection_board(
    slate: date | None = None,
    *,
    preferred_only: bool = True,
) -> pl.DataFrame:
    if not LOG_PATH.exists():
        raise FileNotFoundError(
            f"Missing {LOG_PATH}. Run production/projections/log_projections.py first."
        )
    df = pl.read_parquet(LOG_PATH)
    if df["game_date"].dtype == pl.Datetime:
        df = df.with_columns(pl.col("game_date").dt.date().alias("game_date"))
    else:
        df = df.with_columns(pl.col("game_date").cast(pl.Date))
    dates = sorted(df["game_date"].unique().to_list())
    use = slate if slate is not None else dates[-1]
    board = df.filter(pl.col("game_date") == use)
    if preferred_only and "is_preferred" in board.columns:
        board = board.filter(pl.col("is_preferred"))
    if board.is_empty():
        raise ValueError(f"No projection rows for {use}; logged={dates}")
    if "is_home" in board.columns and "away_team" in board.columns:
        board = board.with_columns(
            pl.when(pl.col("is_home"))
            .then(pl.col("home_team"))
            .otherwise(pl.col("away_team"))
            .alias("pitcher_team"),
            pl.when(pl.col("is_home"))
            .then(pl.lit("home"))
            .otherwise(pl.lit("away"))
            .alias("venue"),
        )
    return board


def _match_row(board: pl.DataFrame, player_name: str) -> dict[str, Any] | None:
    key = _norm_name(player_name)
    hits = [
        r
        for r in board.to_dicts()
        if _norm_name(str(r.get("player_name"))) == key
    ]
    if len(hits) == 1:
        return hits[0]
    last = key.split()[-1] if key else ""
    if last:
        hits = [
            r
            for r in board.to_dicts()
            if last in _norm_name(str(r.get("player_name")))
        ]
        if len(hits) == 1:
            return hits[0]
    return None


def score_quote_against_board(
    board_row: dict[str, Any],
    quote: StrikeoutQuote,
    *,
    unit_dollars: float = 50.0,
    edge_floor: float = DEFAULT_EDGE_FLOOR,
    prob_offset_map: dict[tuple[float, str], float] | None = None,
    line_floor_map: dict[str, float] | None = None,
    deploy_segment_states: dict[tuple[float, str, str], str] | None = None,
) -> dict[str, Any] | None:
    col = _line_to_col(quote.line)
    p_over = p_model_over_for_line(board_row, quote.line)
    if p_over is None:
        return None
    over_price_bucket = _price_bucket(float(quote.over_american))
    maturity_bucket = _maturity_bucket(board_row)
    correction_key = (float(quote.line), over_price_bucket)
    offset = (
        float(prob_offset_map.get(correction_key, 0.0))
        if prob_offset_map is not None
        else 0.0
    )
    p_over = min(max(float(p_over) + offset, 1e-6), 1.0 - 1e-6)
    effective_floor = (
        float(line_floor_map.get(_line_key(quote.line), edge_floor))
        if line_floor_map is not None
        else float(edge_floor)
    )
    segment_key = (
        float(quote.line),
        over_price_bucket,
        maturity_bucket,
    )
    segment_state = "UNSPECIFIED"
    segment_allowed = True
    if deploy_segment_states is not None and len(deploy_segment_states) > 0:
        segment_state = str(deploy_segment_states.get(segment_key, "UNSPECIFIED"))
        segment_allowed = segment_state != "OFF"
    over_ev = evaluate_side(p_over, quote.over_american, quote.under_american, "over")
    under_ev = evaluate_side(
        1.0 - p_over, quote.over_american, quote.under_american, "under"
    )
    best = over_ev if over_ev["edge"] >= under_ev["edge"] else under_ev
    sizing = size_in_units(
        float(best["p_model"]),
        float(best["price_american"]),
        edge=float(best["edge"]),
        edge_floor=effective_floor,
        unit_dollars=unit_dollars,
    )
    fair_key = col.replace("p_over_", "fair_amer_", 1)
    oos = row_oos_reason(board_row)
    in_support = oos is None
    passes = bool(sizing["passes_floor"]) and in_support and segment_allowed
    return {
        "game_date": str(board_row.get("game_date")),
        "game_pk": board_row.get("game_pk"),
        "pitcher_team": board_row.get("pitcher_team"),
        "player_name": board_row.get("player_name"),
        "pitcher": board_row.get("pitcher"),
        "venue": board_row.get("venue"),
        "away_team": board_row.get("away_team"),
        "home_team": board_row.get("home_team"),
        "expected_K": round(float(board_row["expected_K"]), 2)
        if board_row.get("expected_K") is not None
        else None,
        "projected_tbf": board_row.get("projected_tbf"),
        "days_rest": board_row.get("days_rest"),
        "opp_lineup_k_vs_hand": board_row.get("opp_lineup_k_vs_hand"),
        "book": quote.sportsbook,
        "line": float(quote.line),
        "maturity_bucket": maturity_bucket,
        "over_price_bucket": over_price_bucket,
        "over_price": float(quote.over_american),
        "under_price": float(quote.under_american),
        "fair_amer_model": board_row.get(fair_key),
        "p_model_over": round(p_over, 3),
        "prob_correction_offset": round(offset, 5),
        "best_side": best["side"],
        "best_price": float(best["price_american"]),
        "p_model": round(float(best["p_model"]), 3),
        "p_market": round(float(best["p_market"]), 3),
        "edge": round(float(best["edge"]), 4),
        "edge_floor_effective": round(float(effective_floor), 4),
        "passes_floor": passes,
        "segment_allowed": segment_allowed,
        "segment_state": segment_state,
        "policy_reason": ""
        if segment_allowed
        else "segment_disabled_by_deploy_matrix",
        "units": round(float(sizing["units"]), 2) if in_support else 0.0,
        "stake": round(float(sizing["stake"]), 2) if in_support else 0.0,
        "over_edge": round(float(over_ev["edge"]), 4),
        "under_edge": round(float(under_ev["edge"]), 4),
        "event_start_time": quote.event_start_time,
        "oos_reason": oos,
        "recommendation": "BET" if passes else ("OOS" if oos else "skip"),
    }


def latest_scorecard_warns() -> int | None:
    """Read latest model-health warning count if available."""
    if not SCORECARD_DAILY.exists():
        return None
    try:
        df = pl.read_parquet(SCORECARD_DAILY)
    except Exception:
        return None
    if df.is_empty() or "n_warn" not in df.columns:
        return None
    sort_col = "snapshot_utc" if "snapshot_utc" in df.columns else df.columns[0]
    row = df.sort(sort_col).tail(1).to_dicts()
    if not row:
        return None
    try:
        return int(row[0].get("n_warn"))
    except (TypeError, ValueError):
        return None


def apply_quality_gate(
    frame: pl.DataFrame,
    *,
    enabled: bool,
    kpi_policy_path: str | Path | None = None,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Apply a conservative quality gate to BET rows and annotate reasons.

    This does not alter model probabilities. It changes recommendation labels
    from BET -> HOLD when risk rules trigger.
    """
    if frame.is_empty():
        return frame, {
            "quality_gate_enabled": enabled,
            "quality_gate_n_hold": 0,
            "quality_gate_n_warn": None,
        }

    base = frame.with_columns(
        pl.col("recommendation").alias("recommendation_pre_gate"),
        pl.lit(False).alias("quality_gate_block"),
        pl.lit("").alias("quality_gate_reason"),
    )
    if not enabled:
        return base, {
            "quality_gate_enabled": False,
            "quality_gate_n_hold": 0,
            "quality_gate_n_warn": latest_scorecard_warns(),
        }

    policy = load_kpi_policy(kpi_policy_path)
    qg = policy.get("quality_gate", {})
    dyn = qg.get("dynamic_min_edge", {})
    rules = qg.get("rules", {})
    n_warn = latest_scorecard_warns()
    min_edge = float(dyn.get("base", 0.12))
    elevated = float(dyn.get("elevated", 0.14))
    elevated_when = int(dyn.get("elevated_when_n_warn_gte", 2))
    if n_warn is not None and n_warn >= elevated_when:
        min_edge = elevated

    gated = base
    if "opp_lineup_k_vs_hand" in gated.columns:
        try:
            gated = gated.with_columns(
                pl.col("opp_lineup_k_vs_hand")
                .qcut(
                    3,
                    labels=["weak_matchup", "avg_matchup", "favorable_matchup"],
                    allow_duplicates=True,
                )
                .alias("matchup_tier")
            )
        except Exception:
            gated = gated.with_columns(pl.lit(None).alias("matchup_tier"))
    else:
        gated = gated.with_columns(pl.lit(None).alias("matchup_tier"))

    cond_core = pl.col("recommendation_pre_gate") == "BET"
    side_col = "best_side" if "best_side" in gated.columns else "side"
    blocked_tiers = rules.get("matchup_tiers_blocked", ["avg_matchup", "favorable_matchup"])
    cond_matchup = (
        cond_core
        & pl.lit(bool(rules.get("block_matchup_tier", True)))
        & pl.col("matchup_tier").is_in(blocked_tiers)
    )
    long_rest_min_days = float(rules.get("under_long_rest_min_days", 10))
    cond_rest = (
        cond_core
        & pl.lit(bool(rules.get("block_under_long_rest", True)))
        & pl.col(side_col).eq("under")
        & pl.col("days_rest").is_not_null()
        & (pl.col("days_rest") >= long_rest_min_days)
    )
    any_long_rest_min_days = float(rules.get("any_long_rest_min_days", 10))
    cond_rest_any = (
        cond_core
        & pl.lit(bool(rules.get("block_any_long_rest", False)))
        & pl.col("days_rest").is_not_null()
        & (pl.col("days_rest") >= any_long_rest_min_days)
    )
    low_tbf_min = float(rules.get("low_projected_tbf_min", 15.0))
    if "projected_tbf" in gated.columns:
        cond_low_tbf = (
            cond_core
            & pl.lit(bool(rules.get("block_low_projected_tbf", False)))
            & pl.col("projected_tbf").is_not_null()
            & (pl.col("projected_tbf") < low_tbf_min)
        )
    else:
        cond_low_tbf = pl.lit(False)
    cond_edge = (
        cond_core
        & pl.lit(bool(rules.get("block_edge_below_min", True)))
        & (pl.col("edge") < float(min_edge))
    )

    gated = gated.with_columns(
        (cond_matchup | cond_rest | cond_rest_any | cond_low_tbf | cond_edge).alias("quality_gate_block")
    )
    gated = gated.with_columns(
        pl.when(pl.col("quality_gate_block"))
        .then(
            pl.concat_str(
                [
                    pl.when(cond_matchup)
                    .then(pl.lit("matchup_tier_risk"))
                    .otherwise(pl.lit("")),
                    pl.when(cond_rest)
                    .then(pl.lit("under_long_rest_risk"))
                    .otherwise(pl.lit("")),
                    pl.when(cond_rest_any)
                    .then(pl.lit("any_long_rest_risk"))
                    .otherwise(pl.lit("")),
                    pl.when(cond_low_tbf)
                    .then(pl.lit("low_projected_tbf_risk"))
                    .otherwise(pl.lit("")),
                    pl.when(cond_edge)
                    .then(pl.lit("edge_below_dynamic_min"))
                    .otherwise(pl.lit("")),
                ],
                separator=";",
            )
            .str.replace_all(r"(;)+", ";")
            .str.strip_chars(";")
        )
        .otherwise(pl.lit(""))
        .alias("quality_gate_reason")
    )
    gated = gated.with_columns(
        pl.when(
            pl.col("quality_gate_block") & pl.col("recommendation_pre_gate").eq("BET")
        )
        .then(pl.lit("HOLD"))
        .otherwise(pl.col("recommendation_pre_gate"))
        .alias("recommendation")
    )

    n_hold = int(
        gated.filter(
            pl.col("recommendation_pre_gate").eq("BET") & pl.col("recommendation").eq("HOLD")
        ).height
    )
    return gated, {
        "quality_gate_enabled": True,
        "quality_gate_n_hold": n_hold,
        "quality_gate_n_warn": n_warn,
        "quality_gate_min_edge": min_edge,
    }


def _dedupe_quotes(quotes: list[StrikeoutQuote]) -> list[StrikeoutQuote]:
    """Keep first SharpAPI row per (player, book, line)."""
    seen: set[tuple[str, str, float]] = set()
    out: list[StrikeoutQuote] = []
    for q in quotes:
        key = (_norm_name(q.player_name), q.sportsbook.lower(), float(q.line))
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def keep_best_book_per_pitcher(frame: pl.DataFrame) -> pl.DataFrame:
    """One row per pitcher: highest edge (then units, then price)."""
    if frame.is_empty() or "player_name" not in frame.columns:
        return frame
    # Stable sort so group first() is deterministic: edge desc, units desc.
    ranked = frame.sort(
        ["player_name", "edge", "units", "best_price"],
        descending=[False, True, True, True],
    )
    return ranked.unique(subset=["player_name"], keep="first").sort(
        ["passes_floor", "edge"], descending=[True, True]
    )


def build_recommendations(
    *,
    slate: date | None = None,
    preferred_only: bool = True,
    unit_dollars: float = 50.0,
    edge_floor: float = DEFAULT_EDGE_FLOOR,
    sportsbook: str | None = None,
    quotes: list[StrikeoutQuote] | None = None,
    best_book_only: bool = True,
    quality_gate: bool = False,
    kpi_policy_path: str | Path | None = None,
    apply_line_price_correction: bool = False,
    apply_line_floors: bool = False,
    apply_deploy_matrix_filter: bool = False,
    side_edge_floors: dict[str, float] | None = None,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Return recommendation frame + meta (fetches SharpAPI unless quotes given).

    By default keeps the single best book per pitcher (highest edge). Pass
    ``best_book_only=False`` to see every matched DK/FD quote.
    """
    board = load_projection_board(slate, preferred_only=preferred_only)
    if quotes is None:
        quotes = fetch_mlb_strikeout_quotes(
            sportsbook=sportsbook, main_only=True, is_live=False
        )
    quotes = _dedupe_quotes(quotes)
    rows: list[dict[str, Any]] = []
    unmatched: list[str] = []
    prob_offset_map = _load_line_price_offsets() if apply_line_price_correction else None
    line_floor_map = _load_line_floor_map() if apply_line_floors else None
    deploy_segment_states = (
        _load_deploy_segment_states() if apply_deploy_matrix_filter else None
    )
    for q in quotes:
        brow = _match_row(board, q.player_name)
        if brow is None:
            unmatched.append(q.player_name)
            continue
        scored = score_quote_against_board(
            brow,
            q,
            unit_dollars=unit_dollars,
            edge_floor=edge_floor,
            prob_offset_map=prob_offset_map,
            line_floor_map=line_floor_map,
            deploy_segment_states=deploy_segment_states,
        )
        if scored is None:
            unmatched.append(f"{q.player_name}@{q.line}")
            continue
        rows.append(scored)

    frame = pl.DataFrame(rows) if rows else pl.DataFrame()
    n_matched_raw = frame.height
    if not frame.is_empty():
        if side_edge_floors:
            over_floor = float(side_edge_floors.get("over", edge_floor))
            under_floor = float(side_edge_floors.get("under", edge_floor))
            side_min_edge = (
                pl.when(pl.col("best_side") == "over")
                .then(pl.lit(over_floor))
                .otherwise(pl.lit(under_floor))
            )
            frame = frame.with_columns(
                side_min_edge.alias("side_min_edge_floor"),
                (pl.col("edge") >= side_min_edge).alias("passes_side_floor"),
            ).with_columns(
                (
                    pl.col("passes_floor")
                    & pl.col("passes_side_floor")
                    & pl.col("segment_allowed")
                ).alias("passes_floor"),
                pl.when(
                    pl.col("recommendation").eq("BET")
                    & (~pl.col("passes_side_floor"))
                )
                .then(pl.lit("skip"))
                .otherwise(pl.col("recommendation"))
                .alias("recommendation"),
                pl.when(
                    pl.col("policy_reason").eq("")
                    & (~pl.col("passes_side_floor"))
                )
                .then(pl.lit("below_side_floor"))
                .otherwise(pl.col("policy_reason"))
                .alias("policy_reason"),
            )

        if best_book_only:
            frame = keep_best_book_per_pitcher(frame)
        else:
            frame = frame.sort(["passes_floor", "edge"], descending=[True, True])

        frame, gate_meta = apply_quality_gate(
            frame,
            enabled=quality_gate,
            kpi_policy_path=kpi_policy_path,
        )
    else:
        gate_meta = {
            "quality_gate_enabled": quality_gate,
            "quality_gate_n_hold": 0,
            "quality_gate_n_warn": latest_scorecard_warns(),
        }

    matched_names = {
        _norm_name(str(n))
        for n in (frame["player_name"].to_list() if not frame.is_empty() else [])
    }
    missing_quotes = [
        str(r["player_name"])
        for r in board.to_dicts()
        if _norm_name(str(r.get("player_name"))) not in matched_names
    ]

    meta = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "slate_date": str(board["game_date"][0]),
        "n_board": board.height,
        "n_quotes": len(quotes),
        "n_matched_raw": n_matched_raw,
        "n_matched": frame.height,
        "n_bet": int(frame.filter(pl.col("recommendation") == "BET").height)
        if not frame.is_empty() and "recommendation" in frame.columns
        else 0,
        "n_hold": int(frame.filter(pl.col("recommendation") == "HOLD").height)
        if not frame.is_empty() and "recommendation" in frame.columns
        else 0,
        "n_unmatched": len(unmatched),
        "unmatched_sample": unmatched[:12],
        "n_preferred_missing_quote": len(missing_quotes),
        "preferred_missing_quote": missing_quotes[:12],
        "unit_dollars": unit_dollars,
        "edge_floor": edge_floor,
        "sportsbook_filter": sportsbook,
        "best_book_only": best_book_only,
        "line_price_correction_applied": bool(apply_line_price_correction),
        "line_price_correction_segments": len(prob_offset_map or {}),
        "line_floor_policy_applied": bool(apply_line_floors),
        "line_floor_policy_segments": len(line_floor_map or {}),
        "deploy_matrix_filter_applied": bool(apply_deploy_matrix_filter),
        "deploy_matrix_segments_tracked": len(deploy_segment_states or {}),
        "deploy_matrix_segments_on": int(
            sum(
                1
                for state in (deploy_segment_states or {}).values()
                if str(state) == "ON"
            )
        ),
        "deploy_matrix_segments_off": int(
            sum(
                1
                for state in (deploy_segment_states or {}).values()
                if str(state) == "OFF"
            )
        ),
        "side_edge_floors_applied": bool(side_edge_floors),
        "side_edge_floor_over": float(side_edge_floors.get("over"))
        if side_edge_floors and "over" in side_edge_floors
        else None,
        "side_edge_floor_under": float(side_edge_floors.get("under"))
        if side_edge_floors and "under" in side_edge_floors
        else None,
        "n_segment_filtered": int(
            frame.filter(~pl.col("segment_allowed")).height
            if not frame.is_empty() and "segment_allowed" in frame.columns
            else 0
        ),
        **gate_meta,
    }
    return frame, meta


def quality_gate_hold_reason(
    *,
    edge: float,
    side: str,
    days_rest: float | None,
    projected_tbf: float | None = None,
    matchup_tier: str | None,
    n_warn: int | None = None,
    kpi_policy_path: str | Path | None = None,
) -> str | None:
    """Return semicolon-joined hold reasons for a single ticket context."""
    policy = load_kpi_policy(kpi_policy_path)
    qg = policy.get("quality_gate", {})
    dyn = qg.get("dynamic_min_edge", {})
    rules = qg.get("rules", {})
    warns = latest_scorecard_warns() if n_warn is None else n_warn
    min_edge = float(dyn.get("base", 0.12))
    elevated = float(dyn.get("elevated", 0.14))
    elevated_when = int(dyn.get("elevated_when_n_warn_gte", 2))
    if warns is not None and warns >= elevated_when:
        min_edge = elevated
    reasons: list[str] = []
    blocked_tiers = set(rules.get("matchup_tiers_blocked", ["avg_matchup", "favorable_matchup"]))
    if bool(rules.get("block_matchup_tier", True)) and matchup_tier in blocked_tiers:
        reasons.append("matchup_tier_risk")
    long_rest_min_days = float(rules.get("under_long_rest_min_days", 10))
    if (
        bool(rules.get("block_under_long_rest", True))
        and side == "under"
        and days_rest is not None
        and float(days_rest) >= long_rest_min_days
    ):
        reasons.append("under_long_rest_risk")
    any_long_rest_min_days = float(rules.get("any_long_rest_min_days", 10))
    if (
        bool(rules.get("block_any_long_rest", False))
        and days_rest is not None
        and float(days_rest) >= any_long_rest_min_days
    ):
        reasons.append("any_long_rest_risk")
    low_tbf_min = float(rules.get("low_projected_tbf_min", 15.0))
    if (
        bool(rules.get("block_low_projected_tbf", False))
        and projected_tbf is not None
        and float(projected_tbf) < low_tbf_min
    ):
        reasons.append("low_projected_tbf_risk")
    if bool(rules.get("block_edge_below_min", True)) and float(edge) < min_edge:
        reasons.append("edge_below_dynamic_min")
    return ";".join(reasons) if reasons else None


def recommendations_to_html(frame: pl.DataFrame, meta: dict[str, Any]) -> str:
    """Simple scrollable HTML table (open in browser)."""
    if frame.is_empty():
        body = "<p>No matched recommendations.</p>"
    else:
        show = [
            c
            for c in (
                "recommendation",
                "pitcher_team",
                "player_name",
                "venue",
                "expected_K",
                "book",
                "line",
                "best_side",
                "best_price",
                "over_price",
                "under_price",
                "edge",
                "units",
                "stake",
                "p_model",
                "p_market",
                "away_team",
                "home_team",
            )
            if c in frame.columns
        ]
        pdf = frame.select(show).to_pandas()
        # highlight BET rows via styler-less class
        rows_html = []
        cols = list(pdf.columns)
        rows_html.append(
            "<tr>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr>"
        )
        for rec in pdf.to_dict(orient="records"):
            cls = "bet" if rec.get("recommendation") == "BET" else "skip"
            tds = []
            for c in cols:
                v = rec[c]
                if c == "edge" and v is not None:
                    tds.append(f"<td>{float(v):+.1%}</td>")
                elif c in ("best_price", "over_price", "under_price") and v is not None:
                    x = int(v)
                    tds.append(f"<td>{'+' if x > 0 else ''}{x}</td>")
                elif c in ("p_model", "p_market") and v is not None:
                    tds.append(f"<td>{float(v):.0%}</td>")
                else:
                    tds.append(f"<td>{v}</td>")
            rows_html.append(f'<tr class="{cls}">' + "".join(tds) + "</tr>")
        body = (
            '<div class="wrap"><table>'
            + "".join(rows_html)
            + "</table></div>"
        )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"/>
<title>K prop recommendations {meta.get('slate_date')}</title>
<style>
 body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; background:#111; color:#eee; }}
 h1 {{ font-size: 20px; margin: 0 0 8px; }}
 .meta {{ color:#aaa; font-size: 13px; margin-bottom: 16px; }}
 .wrap {{ overflow: auto; max-height: 80vh; border: 1px solid #333; border-radius: 8px; }}
 table {{ border-collapse: collapse; width: max-content; min-width: 100%; font-size: 13px; }}
 th {{ position: sticky; top: 0; background: #1b1b1b; text-align: left; padding: 8px 10px; }}
 td {{ padding: 6px 10px; white-space: nowrap; border-top: 1px solid #2a2a2a; }}
 tr.bet {{ background: #14301f; }}
 tr.skip {{ background: transparent; }}
</style></head><body>
<h1>Strikeout recommendations</h1>
<div class="meta">
 slate={meta.get('slate_date')} · matched={meta.get('n_matched')} ·
 BET={meta.get('n_bet')} · floor={meta.get('edge_floor')} ·
 unit=${meta.get('unit_dollars')} · built={meta.get('built_at_utc')}
</div>
{body}
</body></html>
"""


def write_recommendations(
    frame: pl.DataFrame,
    meta: dict[str, Any],
    *,
    parquet_path: Path = BOARD_PARQUET,
    html_path: Path = BOARD_HTML,
) -> tuple[Path, Path]:
    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(parquet_path)
    html_path.write_text(recommendations_to_html(frame, meta), encoding="utf-8")
    import json

    BOARD_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return parquet_path, html_path
