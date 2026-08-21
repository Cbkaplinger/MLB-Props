"""Build A/B recommendation diff: base vs corrected scoring in one run."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
import sys

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.env_load import load_project_dotenv  # noqa: E402
from Python.market import DEFAULT_EDGE_FLOOR  # noqa: E402
from Python.odds_board import build_recommendations  # noqa: E402
from Python.sharp_odds import fetch_mlb_strikeout_quotes  # noqa: E402

OUT_DIR = ROOT / "artifacts" / "odds_log"
OUT_PATH = OUT_DIR / "recommendations_ab_diff.parquet"
OUT_SUMMARY = OUT_DIR / "recommendations_ab_diff_summary.json"


def _key_cols(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    return frame.with_columns(
        pl.concat_str(
            [
                pl.col("player_name").cast(pl.Utf8),
                pl.col("book").cast(pl.Utf8),
                pl.col("line").cast(pl.Float64).round(1).cast(pl.Utf8),
            ],
            separator="|",
        ).alias("row_key")
    )


def main() -> None:
    load_project_dotenv()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", type=date.fromisoformat, default=None)
    p.add_argument("--unit", type=float, default=50.0)
    p.add_argument("--edge-floor", type=float, default=DEFAULT_EDGE_FLOOR)
    p.add_argument("--book", type=str, default=None, help="draftkings|fanduel")
    p.add_argument("--all-starters", action="store_true")
    p.add_argument("--all-books", action="store_true")
    p.add_argument("--quality-gate", action="store_true")
    p.add_argument("--kpi-policy", type=str, default=None)
    args = p.parse_args()

    quotes = fetch_mlb_strikeout_quotes(sportsbook=args.book, main_only=True, is_live=False)
    base, meta_base = build_recommendations(
        slate=args.date,
        preferred_only=not args.all_starters,
        unit_dollars=args.unit,
        edge_floor=args.edge_floor,
        sportsbook=args.book,
        best_book_only=not args.all_books,
        quality_gate=args.quality_gate,
        kpi_policy_path=args.kpi_policy,
        apply_line_price_correction=False,
        quotes=quotes,
    )
    corr, meta_corr = build_recommendations(
        slate=args.date,
        preferred_only=not args.all_starters,
        unit_dollars=args.unit,
        edge_floor=args.edge_floor,
        sportsbook=args.book,
        best_book_only=not args.all_books,
        quality_gate=args.quality_gate,
        kpi_policy_path=args.kpi_policy,
        apply_line_price_correction=True,
        quotes=quotes,
    )

    base = _key_cols(base).select(
        "row_key", "recommendation", "edge", "units", "stake", "p_model", "p_model_over"
    ).rename(
        {
            "recommendation": "recommendation_base",
            "edge": "edge_base",
            "units": "units_base",
            "stake": "stake_base",
            "p_model": "p_model_base",
            "p_model_over": "p_model_over_base",
        }
    )
    corr = _key_cols(corr)
    keep_corr = [
        c
        for c in (
            "row_key",
            "game_date",
            "player_name",
            "book",
            "line",
            "best_side",
            "best_price",
            "recommendation",
            "edge",
            "units",
            "stake",
            "p_model",
            "p_model_over",
            "prob_correction_offset",
        )
        if c in corr.columns
    ]
    corr = corr.select(keep_corr).rename(
        {
            "recommendation": "recommendation_corr",
            "edge": "edge_corr",
            "units": "units_corr",
            "stake": "stake_corr",
            "p_model": "p_model_corr",
            "p_model_over": "p_model_over_corr",
        }
    )
    out = corr.join(base, on="row_key", how="left").with_columns(
        (pl.col("recommendation_base") != pl.col("recommendation_corr")).alias("recommendation_changed"),
        (pl.col("units_corr") - pl.col("units_base")).alias("units_delta"),
        (pl.col("edge_corr") - pl.col("edge_base")).alias("edge_delta"),
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_parquet(OUT_PATH)

    changed = out.filter(pl.col("recommendation_changed"))
    summary = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "slate_date": meta_corr.get("slate_date"),
        "quotes_fetched": len(quotes),
        "n_rows": int(out.height),
        "n_recommendation_changed": int(changed.height),
        "counts": {
            "base_bet": int(base.filter(pl.col("recommendation_base") == "BET").height)
            if not base.is_empty()
            else 0,
            "corr_bet": int(corr.filter(pl.col("recommendation_corr") == "BET").height)
            if not corr.is_empty()
            else 0,
        },
        "changed_examples": changed.select(
            [c for c in ("player_name", "book", "line", "recommendation_base", "recommendation_corr", "edge_base", "edge_corr", "prob_correction_offset") if c in changed.columns]
        ).head(12).to_dicts(),
        "output": str(OUT_PATH),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print(f"wrote {OUT_SUMMARY}")
    print(summary)


if __name__ == "__main__":
    main()
