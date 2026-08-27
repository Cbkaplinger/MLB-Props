"""Build shadow scoring diagnostics for non-K pitcher props.

Uses watcher-collected quote history (outs/hits/walks) and settled pitcher box
stats captured in the strikeout ledger to estimate CLV and blind-side ROI for
these markets before any production modeling/promotion.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from Python.market import bet_pnl, clv_pp_from_americans, settle_side

ROOT = Path(__file__).resolve().parents[2]
ODDS_DIR = ROOT / "artifacts" / "odds_log"
LEDGER_PATH = ODDS_DIR / "ledger.parquet"
AUX_QUOTES_PATH = ODDS_DIR / "watcher_aux_quotes.parquet"

OUT_PROP = ODDS_DIR / "aux_market_shadow_prop_level.parquet"
OUT_SUMMARY_CSV = ODDS_DIR / "aux_market_shadow_summary.csv"
OUT_SUMMARY_JSON = ODDS_DIR / "aux_market_shadow_summary.json"

STAT_TO_SETTLE_COL = {
    "outs": "settle_outs",
    "hits_allowed": "settle_hits_allowed",
    "walks_allowed": "settle_walks_allowed",
}


def _empty_outputs(reason: str) -> None:
    payload = {"status": "empty", "reason": reason}
    OUT_SUMMARY_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {OUT_SUMMARY_JSON}")


def _build_settle_map(ledger: pl.DataFrame) -> pl.DataFrame:
    req = {
        "status",
        "player_name",
        "game_date",
        "settle_outs",
        "settle_hits_allowed",
        "settle_walks_allowed",
    }
    if ledger.is_empty() or not req.issubset(set(ledger.columns)):
        return pl.DataFrame()
    return (
        ledger.filter(pl.col("status") == "settled")
        .with_columns(
            pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("game_date"),
            pl.col("player_name").cast(pl.Utf8).str.to_lowercase().alias("player_key"),
            pl.col("settle_outs").cast(pl.Float64),
            pl.col("settle_hits_allowed").cast(pl.Float64),
            pl.col("settle_walks_allowed").cast(pl.Float64),
        )
        .group_by(["game_date", "player_key"])
        .agg(
            pl.col("settle_outs").max().alias("settle_outs"),
            pl.col("settle_hits_allowed").max().alias("settle_hits_allowed"),
            pl.col("settle_walks_allowed").max().alias("settle_walks_allowed"),
        )
    )


def _pair_quotes(aux: pl.DataFrame) -> pl.DataFrame:
    req = {
        "logged_at_utc",
        "market_stat",
        "event_id",
        "event_start_time",
        "player_name",
        "sportsbook",
        "selection_type",
        "line",
        "odds_american",
    }
    if aux.is_empty() or not req.issubset(set(aux.columns)):
        return pl.DataFrame()
    a = aux.with_columns(
        pl.col("logged_at_utc").cast(pl.Utf8),
        pl.col("event_start_time").cast(pl.Utf8),
        pl.col("market_stat").cast(pl.Utf8),
        pl.col("event_id").cast(pl.Utf8),
        pl.col("player_name").cast(pl.Utf8),
        pl.col("sportsbook").cast(pl.Utf8),
        pl.col("selection_type").cast(pl.Utf8).str.to_lowercase(),
        pl.col("line").cast(pl.Float64),
        pl.col("odds_american").cast(pl.Float64),
    ).with_columns(
        pl.col("event_start_time").str.slice(0, 10).alias("game_date"),
        pl.col("player_name").str.to_lowercase().alias("player_key"),
    )
    pivot = (
        a.group_by(
            [
                "logged_at_utc",
                "market_stat",
                "event_id",
                "event_start_time",
                "game_date",
                "player_name",
                "player_key",
                "sportsbook",
                "line",
            ]
        )
        .agg(
            pl.col("odds_american")
            .filter(pl.col("selection_type") == "over")
            .max()
            .alias("over_price"),
            pl.col("odds_american")
            .filter(pl.col("selection_type") == "under")
            .max()
            .alias("under_price"),
        )
        .filter(pl.col("over_price").is_not_null() & pl.col("under_price").is_not_null())
    )
    if pivot.is_empty():
        return pivot
    keyed = [
        "market_stat",
        "event_id",
        "event_start_time",
        "game_date",
        "player_name",
        "player_key",
        "sportsbook",
        "line",
    ]
    return (
        pivot.sort("logged_at_utc")
        .group_by(keyed)
        .agg(
            pl.col("logged_at_utc").first().alias("open_logged_at_utc"),
            pl.col("logged_at_utc").last().alias("close_logged_at_utc"),
            pl.col("over_price").first().alias("open_over"),
            pl.col("under_price").first().alias("open_under"),
            pl.col("over_price").last().alias("close_over"),
            pl.col("under_price").last().alias("close_under"),
            pl.len().alias("n_snapshots"),
        )
    )


def _score_props(props: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for r in props.to_dicts():
        stat = str(r.get("market_stat") or "")
        settle_val = r.get("settle_stat_value")
        if settle_val is None:
            rows.append({**r, "scored": False})
            continue
        line = float(r["line"])
        open_over = float(r["open_over"])
        open_under = float(r["open_under"])
        close_over = float(r["close_over"])
        close_under = float(r["close_under"])
        settle_f = float(settle_val)

        over_win = settle_side("over", line, settle_f)
        under_win = settle_side("under", line, settle_f)
        over_pnl = float(bet_pnl(1.0, open_over, won=over_win))
        under_pnl = float(bet_pnl(1.0, open_under, won=under_win))
        over_clv = float(clv_pp_from_americans(close_over, open_over, close_other=close_under, bet_other=open_under))
        under_clv = float(clv_pp_from_americans(close_under, open_under, close_other=close_over, bet_other=open_over))

        rows.append(
            {
                **r,
                "scored": True,
                "settle_stat_value": settle_f,
                "over_win": over_win,
                "under_win": under_win,
                "over_pnl_1u": over_pnl,
                "under_pnl_1u": under_pnl,
                "over_clv_pp": over_clv,
                "under_clv_pp": under_clv,
                "better_open_side": "over" if over_clv >= under_clv else "under",
                "better_clv_pp": over_clv if over_clv >= under_clv else under_clv,
                "better_pnl_1u": over_pnl if over_clv >= under_clv else under_pnl,
                "stat_family": stat,
            }
        )
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def main() -> None:
    if not AUX_QUOTES_PATH.exists():
        _empty_outputs("missing_aux_quotes")
        return
    if not LEDGER_PATH.exists():
        _empty_outputs("missing_ledger")
        return

    aux = pl.read_parquet(AUX_QUOTES_PATH)
    ledger = pl.read_parquet(LEDGER_PATH)
    pairs = _pair_quotes(aux)
    if pairs.is_empty():
        _empty_outputs("no_paired_quotes")
        return

    settle_map = _build_settle_map(ledger)
    joined = pairs
    if not settle_map.is_empty():
        joined = joined.join(settle_map, on=["game_date", "player_key"], how="left")
    else:
        joined = joined.with_columns(
            pl.lit(None).cast(pl.Float64).alias("settle_outs"),
            pl.lit(None).cast(pl.Float64).alias("settle_hits_allowed"),
            pl.lit(None).cast(pl.Float64).alias("settle_walks_allowed"),
        )

    joined = joined.with_columns(
        pl.when(pl.col("market_stat") == "outs")
        .then(pl.col("settle_outs"))
        .when(pl.col("market_stat") == "hits_allowed")
        .then(pl.col("settle_hits_allowed"))
        .when(pl.col("market_stat") == "walks_allowed")
        .then(pl.col("settle_walks_allowed"))
        .otherwise(None)
        .cast(pl.Float64)
        .alias("settle_stat_value")
    )

    scored_all = _score_props(joined)
    if scored_all.is_empty():
        _empty_outputs("no_rows_after_scoring")
        return
    scored = scored_all.filter(pl.col("scored") == True)  # noqa: E712
    scored_all.write_parquet(OUT_PROP)
    if scored.is_empty():
        payload = {
            "status": "empty",
            "reason": "no_scored_rows",
            "rows_prop_level": int(scored_all.height),
            "rows_scored": 0,
            "coverage_note": "Need settled rows with captured outs/hits/walks for matching player/date.",
            "files": {"prop_level_parquet": str(OUT_PROP)},
        }
        OUT_SUMMARY_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {OUT_PROP}")
        print(f"wrote {OUT_SUMMARY_JSON}")
        return
    summary = (
        scored.group_by("market_stat")
        .agg(
            pl.len().alias("n_props"),
            pl.col("scored").cast(pl.Int64).sum().alias("n_scored"),
            pl.col("n_snapshots").mean().alias("mean_snapshots"),
            pl.col("over_clv_pp").mean().alias("mean_over_clv_pp"),
            pl.col("under_clv_pp").mean().alias("mean_under_clv_pp"),
            (pl.col("over_clv_pp") > 0).mean().alias("over_positive_clv_share"),
            (pl.col("under_clv_pp") > 0).mean().alias("under_positive_clv_share"),
            pl.col("over_pnl_1u").mean().alias("mean_over_pnl_1u"),
            pl.col("under_pnl_1u").mean().alias("mean_under_pnl_1u"),
            pl.col("better_pnl_1u").mean().alias("mean_better_side_pnl_1u"),
            (pl.col("better_pnl_1u") > 0).mean().alias("better_side_hit_rate"),
        )
        .sort("market_stat")
    )
    summary.write_csv(OUT_SUMMARY_CSV)

    payload = {
        "status": "ok",
        "rows_prop_level": int(scored_all.height),
        "rows_scored": int(scored.height),
        "rows_summary": int(summary.height),
        "files": {
            "prop_level_parquet": str(OUT_PROP),
            "summary_csv": str(OUT_SUMMARY_CSV),
        },
        "coverage_note": "Scoring currently requires settle stats from strikeout ledger rows for same player/date.",
    }
    OUT_SUMMARY_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PROP}")
    print(f"wrote {OUT_SUMMARY_CSV}")
    print(f"wrote {OUT_SUMMARY_JSON}")


if __name__ == "__main__":
    main()

