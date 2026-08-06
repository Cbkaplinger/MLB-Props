"""Build a preferred-board × live strikeout-odds recommendation table.

Joins logged projections to SharpAPI main-line K props, scores both sides with
local de-vig / edge / unit sizing. Product layer only.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from Python import config
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


def _norm_name(s: str) -> str:
    return norm_player_name(s)


def _line_to_col(line: float) -> str:
    return f"p_over_{int(line)}_{int(round((line - int(line)) * 10))}"


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
            f"Missing {LOG_PATH}. Run production/log_projections.py first."
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
) -> dict[str, Any] | None:
    col = _line_to_col(quote.line)
    p_over = p_model_over_for_line(board_row, quote.line)
    if p_over is None:
        return None
    over_ev = evaluate_side(p_over, quote.over_american, quote.under_american, "over")
    under_ev = evaluate_side(
        1.0 - p_over, quote.over_american, quote.under_american, "under"
    )
    best = over_ev if over_ev["edge"] >= under_ev["edge"] else under_ev
    sizing = size_in_units(
        float(best["p_model"]),
        float(best["price_american"]),
        edge=float(best["edge"]),
        edge_floor=edge_floor,
        unit_dollars=unit_dollars,
    )
    fair_key = col.replace("p_over_", "fair_amer_", 1)
    oos = row_oos_reason(board_row)
    in_support = oos is None
    passes = bool(sizing["passes_floor"]) and in_support
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
        "book": quote.sportsbook,
        "line": float(quote.line),
        "over_price": float(quote.over_american),
        "under_price": float(quote.under_american),
        "fair_amer_model": board_row.get(fair_key),
        "p_model_over": round(p_over, 3),
        "best_side": best["side"],
        "best_price": float(best["price_american"]),
        "p_model": round(float(best["p_model"]), 3),
        "p_market": round(float(best["p_market"]), 3),
        "edge": round(float(best["edge"]), 4),
        "passes_floor": passes,
        "units": round(float(sizing["units"]), 2) if in_support else 0.0,
        "stake": round(float(sizing["stake"]), 2) if in_support else 0.0,
        "over_edge": round(float(over_ev["edge"]), 4),
        "under_edge": round(float(under_ev["edge"]), 4),
        "event_start_time": quote.event_start_time,
        "oos_reason": oos,
        "recommendation": "BET" if passes else ("OOS" if oos else "skip"),
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
    for q in quotes:
        brow = _match_row(board, q.player_name)
        if brow is None:
            unmatched.append(q.player_name)
            continue
        scored = score_quote_against_board(
            brow, q, unit_dollars=unit_dollars, edge_floor=edge_floor
        )
        if scored is None:
            unmatched.append(f"{q.player_name}@{q.line}")
            continue
        rows.append(scored)

    frame = pl.DataFrame(rows) if rows else pl.DataFrame()
    n_matched_raw = frame.height
    if not frame.is_empty():
        if best_book_only:
            frame = keep_best_book_per_pitcher(frame)
        else:
            frame = frame.sort(["passes_floor", "edge"], descending=[True, True])

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
        "n_bet": int(frame.filter(pl.col("passes_floor")).height)
        if not frame.is_empty() and "passes_floor" in frame.columns
        else 0,
        "n_unmatched": len(unmatched),
        "unmatched_sample": unmatched[:12],
        "n_preferred_missing_quote": len(missing_quotes),
        "preferred_missing_quote": missing_quotes[:12],
        "unit_dollars": unit_dollars,
        "edge_floor": edge_floor,
        "sportsbook_filter": sportsbook,
        "best_book_only": best_book_only,
    }
    return frame, meta


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
