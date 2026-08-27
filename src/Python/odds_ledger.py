"""Append-only odds / paper-bet ledger (product layer; not model features).

Canonical path: ``artifacts/odds_log/ledger.parquet``
See ``docs/reference/market_clv_gates.md``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from Python import config
from Python.projection_support import projection_oos_reason
from Python.market import (
    DEFAULT_EDGE_FLOOR,
    DEFAULT_KELLY_FRACTION,
    bet_pnl,
    clv_pp_from_americans,
    evaluate_side,
    settle_side,
    size_in_units,
    threshold_curve,
)

ODDS_DIR = config.OUTPUT_DIR / "odds_log"
LEDGER_PATH = ODDS_DIR / "ledger.parquet"
META_PATH = ODDS_DIR / "last_ledger.json"
CURVE_PATH = ODDS_DIR / "threshold_curve.parquet"

LEDGER_COLUMNS: list[str] = [
    "ticket_id",
    "logged_at_utc",
    "closed_at_utc",
    "event_id",
    "event_start_time_utc",
    "minutes_to_tip_at_open",
    "minutes_to_tip_at_close",
    "game_date",
    "game_pk",
    "pitcher",
    "player_name",
    "market",
    "line",
    "book",
    "snapshot",  # open | bet | close
    "side",
    "bet_price",
    "other_price",
    "over_price",
    "under_price",
    "p_model",
    "p_market",
    "edge",
    "passes_floor",
    "units",
    "unit_dollars",
    "stake",
    "bankroll",
    "kelly_frac",
    "status",  # open | settled | void
    "close_over",
    "close_under",
    "clv_pp",
    "close_status",  # null | ok | ok_cross_book | unavailable
    "settle_value",
    "settle_ip",
    "settle_outs",
    "settle_hits_allowed",
    "settle_walks_allowed",
    "settle_strikeouts",
    "result",  # win | loss | null
    "pnl",
    "source",
    "note",
]


def ensure_odds_dir() -> Path:
    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    return ODDS_DIR


def norm_player_name(s: str) -> str:
    return re.sub(r"[^a-z ]", "", (s or "").lower()).strip()


def parse_event_start_utc(raw: str | None) -> datetime | None:
    """Parse SharpAPI / ISO tip times into timezone-aware UTC."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def minutes_to_tip(
    tip: datetime | None,
    *,
    as_of: datetime | None = None,
) -> float | None:
    if tip is None:
        return None
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (tip - now.astimezone(timezone.utc)).total_seconds() / 60.0


def open_dedupe_key(
    *,
    game_date: str,
    player_name: str,
    book: str,
    line: float,
) -> str:
    """One open ticket per slate pitcher × book × line (side ignored)."""
    return (
        f"{str(game_date)[:10]}|{norm_player_name(player_name)}|"
        f"{str(book or '').lower()}|{float(line):g}"
    )


def stable_ticket_id(
    *,
    game_date: str,
    player_name: str,
    line: float,
    book: str,
    side: str,
) -> str:
    """Deterministic id (no wall-clock) so re-opens can be detected."""
    return (
        f"{str(game_date)[:10]}_{norm_player_name(player_name)}_"
        f"{float(line):g}_{str(book or '').lower()}_{side}"
    )


def load_ledger(path: Path = LEDGER_PATH) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    return pl.read_parquet(path)


def _write_meta(path: Path, n_rows: int) -> None:
    META_PATH.write_text(
        json.dumps(
            {
                "path": str(path),
                "n_rows": n_rows,
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def append_rows(rows: Iterable[dict[str, Any]], *, path: Path = LEDGER_PATH) -> pl.DataFrame:
    ensure_odds_dir()
    batch = pl.DataFrame(list(rows))
    if path.exists():
        prev = pl.read_parquet(path)
        frame = pl.concat([prev, batch], how="diagonal_relaxed")
    else:
        frame = batch
    frame.write_parquet(path)
    _write_meta(path, frame.height)
    return frame


def existing_open_keys(ledger: pl.DataFrame) -> set[str]:
    if ledger.is_empty():
        return set()
    keys: set[str] = set()
    for r in ledger.to_dicts():
        keys.add(
            open_dedupe_key(
                game_date=str(r.get("game_date") or ""),
                player_name=str(r.get("player_name") or ""),
                book=str(r.get("book") or ""),
                line=float(r.get("line") or 0.0),
            )
        )
    return keys


def append_open_rows(
    rows: Iterable[dict[str, Any]],
    *,
    path: Path = LEDGER_PATH,
) -> tuple[pl.DataFrame, int, int]:
    """Append open tickets, skipping keys already present (idempotent open).

    Returns ``(frame, n_appended, n_skipped)``.
    """
    ensure_odds_dir()
    ledger = load_ledger(path)
    seen = existing_open_keys(ledger)
    fresh: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        key = open_dedupe_key(
            game_date=str(row.get("game_date") or ""),
            player_name=str(row.get("player_name") or ""),
            book=str(row.get("book") or ""),
            line=float(row.get("line") or 0.0),
        )
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        fresh.append(row)
    if not fresh:
        return ledger, 0, skipped
    if ledger.is_empty():
        frame = pl.DataFrame(fresh)
    else:
        frame = pl.concat([ledger, pl.DataFrame(fresh)], how="diagonal_relaxed")
    frame.write_parquet(path)
    _write_meta(path, frame.height)
    return frame, len(fresh), skipped


def replace_open_slate(
    rows: Iterable[dict[str, Any]],
    *,
    slate: str,
    path: Path = LEDGER_PATH,
) -> tuple[pl.DataFrame, int, int]:
    """Replace *unclosed* open tickets for one slate date with ``rows``.

    Keeps: other dates, settled rows, and same-day rows that already have
    ``clv_pp`` (close already filled). Dedupes the incoming batch by open key.

    Returns ``(frame, n_written, n_removed)``.
    """
    ensure_odds_dir()
    slate_s = str(slate)[:10]
    ledger = load_ledger(path)
    removed = 0
    if not ledger.is_empty() and "game_date" in ledger.columns:
        g = pl.col("game_date").cast(pl.Utf8).str.slice(0, 10)
        is_slate = g == slate_s
        is_open = (
            (pl.col("status") == "open")
            if "status" in ledger.columns
            else pl.lit(True)
        )
        no_clv = (
            pl.col("clv_pp").is_null()
            if "clv_pp" in ledger.columns
            else pl.lit(True)
        )
        drop = is_slate & is_open & no_clv
        removed = int(ledger.filter(drop).height)
        ledger = ledger.filter(~drop)

    # Dedupe incoming batch (SharpAPI / double books).
    seen: set[str] = set()
    fresh: list[dict[str, Any]] = []
    for row in rows:
        key = open_dedupe_key(
            game_date=str(row.get("game_date") or slate_s),
            player_name=str(row.get("player_name") or ""),
            book=str(row.get("book") or ""),
            line=float(row.get("line") or 0.0),
        )
        if key in seen:
            continue
        seen.add(key)
        fresh.append(row)

    if ledger.is_empty() and not fresh:
        frame = pl.DataFrame()
    elif ledger.is_empty():
        frame = pl.DataFrame(fresh)
    elif not fresh:
        frame = ledger
    else:
        frame = pl.concat([ledger, pl.DataFrame(fresh)], how="diagonal_relaxed")
    frame.write_parquet(path)
    _write_meta(path, frame.height)
    return frame, len(fresh), removed

def score_quote_to_row(
    *,
    game_date: str,
    game_pk: int | None,
    pitcher: int | None,
    player_name: str,
    line: float,
    over_price: float,
    under_price: float,
    p_model_over: float,
    book: str,
    unit_dollars: float = 50.0,
    edge_floor: float = DEFAULT_EDGE_FLOOR,
    kelly_frac: float = DEFAULT_KELLY_FRACTION,
    source: str = "manual",
    note: str = "",
    ticket_id: str | None = None,
    event_id: str | None = None,
    event_start_time: str | None = None,
    logged_at: datetime | None = None,
    projected_tbf: float | None = None,
    days_rest: float | None = None,
    expected_K: float | None = None,
) -> dict[str, Any]:
    """Build one ledger row for the best side of an over/under quote."""
    over_ev = evaluate_side(
        float(p_model_over),
        over_price,
        under_price,
        "over",
        edge_floor=edge_floor,
        kelly_frac=kelly_frac,
    )
    under_ev = evaluate_side(
        1.0 - float(p_model_over),
        over_price,
        under_price,
        "under",
        edge_floor=edge_floor,
        kelly_frac=kelly_frac,
    )
    best = over_ev if over_ev["edge"] >= under_ev["edge"] else under_ev
    side = str(best["side"])
    sizing = size_in_units(
        float(best["p_model"]),
        float(best["price_american"]),
        edge=float(best["edge"]),
        edge_floor=edge_floor,
        unit_dollars=unit_dollars,
        kelly_frac=kelly_frac,
    )
    oos = projection_oos_reason(
        projected_tbf=projected_tbf,
        days_rest=days_rest,
        expected_K=expected_K,
    )
    in_support = oos is None
    passes = bool(sizing["passes_floor"]) and in_support
    as_of = logged_at or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    ts = as_of.astimezone(timezone.utc).isoformat()
    tip = parse_event_start_utc(event_start_time)
    tip_iso = tip.isoformat() if tip is not None else (
        str(event_start_time).strip() if event_start_time else None
    )
    tid = ticket_id or stable_ticket_id(
        game_date=game_date,
        player_name=player_name,
        line=line,
        book=book,
        side=side,
    )
    note_out = note
    if oos:
        note_out = (f"{note} | oos={oos}" if note else f"oos={oos}").strip(" |")
    return {
        "ticket_id": tid,
        "logged_at_utc": ts,
        "closed_at_utc": None,
        "event_id": event_id,
        "event_start_time_utc": tip_iso,
        "minutes_to_tip_at_open": minutes_to_tip(tip, as_of=as_of),
        "minutes_to_tip_at_close": None,
        "game_date": game_date,
        "game_pk": game_pk,
        "pitcher": pitcher,
        "player_name": player_name,
        "market": "pitcher_strikeouts",
        "line": float(line),
        "book": book,
        "snapshot": "bet",
        "side": side,
        "bet_price": float(best["price_american"]),
        "other_price": float(under_price if side == "over" else over_price),
        "over_price": float(over_price),
        "under_price": float(under_price),
        "p_model": float(best["p_model"]),
        "p_market": float(best["p_market"]),
        "edge": float(best["edge"]),
        "passes_floor": passes,
        "units": float(sizing["units"]) if in_support else 0.0,
        "unit_dollars": float(unit_dollars),
        "stake": float(sizing["stake"]) if in_support else 0.0,
        "bankroll": float(sizing["bankroll"]),
        "kelly_frac": float(sizing["kelly_frac"]),
        "status": "open",
        "close_over": None,
        "close_under": None,
        "clv_pp": None,
        "close_status": None,
        "settle_value": None,
        "settle_ip": None,
        "settle_outs": None,
        "settle_hits_allowed": None,
        "settle_walks_allowed": None,
        "settle_strikeouts": None,
        "result": None,
        "pnl": None,
        "source": source,
        "note": note_out,
    }


def apply_close(
    ledger: pl.DataFrame,
    *,
    ticket_id: str,
    close_over: float,
    close_under: float,
    closed_at: datetime | None = None,
    overwrite: bool = False,
    close_status: str = "ok",
) -> pl.DataFrame:
    """Fill close prices + CLV for one open ticket (idempotent unless overwrite)."""
    as_of = closed_at or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    closed_iso = as_of.astimezone(timezone.utc).isoformat()
    mask = pl.col("ticket_id") == ticket_id
    tgt = ledger.filter(mask).head(1)
    if tgt.is_empty():
        return ledger
    row = tgt.row(0, named=True)
    side = row["side"]
    bet_price = float(row["bet_price"])
    if side == "over":
        clv = clv_pp_from_americans(
            float(close_over),
            bet_price,
            close_other=float(close_under),
            bet_other=row.get("under_price"),
        )
    else:
        clv = clv_pp_from_americans(
            float(close_under),
            bet_price,
            close_other=float(close_over),
            bet_other=row.get("over_price"),
        )
    tip = parse_event_start_utc(row.get("event_start_time_utc"))
    note = str(row.get("note") or "")
    if close_status == "ok_cross_book" and "close_cross_book=" not in note:
        note = f"{note} | close_cross_book=1".strip(" |")

    # Idempotent unless overwrite: never clobber an already-filled close.
    already = pl.col("clv_pp").is_not_null()
    set_mask = mask & (pl.lit(overwrite) | ~already)
    return ledger.with_columns(
        pl.when(set_mask)
        .then(_float_literal(close_over))
        .otherwise(pl.col("close_over"))
        .alias("close_over"),
        pl.when(set_mask)
        .then(_float_literal(close_under))
        .otherwise(pl.col("close_under"))
        .alias("close_under"),
        pl.when(set_mask)
        .then(_float_literal(clv))
        .otherwise(pl.col("clv_pp"))
        .alias("clv_pp"),
        pl.when(set_mask)
        .then(pl.lit(close_status))
        .otherwise(pl.col("close_status"))
        .alias("close_status"),
        pl.when(set_mask)
        .then(pl.lit(closed_iso))
        .otherwise(pl.col("closed_at_utc"))
        .alias("closed_at_utc"),
        pl.when(set_mask)
        .then(_float_literal(minutes_to_tip(tip, as_of=as_of)))
        .otherwise(pl.col("minutes_to_tip_at_close"))
        .alias("minutes_to_tip_at_close"),
        pl.when(set_mask).then(pl.lit(note)).otherwise(pl.col("note")).alias("note"),
    )


def mark_close_unavailable(
    ledger: pl.DataFrame,
    *,
    ticket_id: str,
    reason: str,
) -> pl.DataFrame:
    """Stop retrying close for a ticket (market gone / window exhausted)."""
    mask = pl.col("ticket_id") == ticket_id
    tgt = ledger.filter(mask).head(1)
    if tgt.is_empty():
        return ledger
    row = tgt.row(0, named=True)
    note = str(row.get("note") or "")
    tag = f"close_unavailable={reason}"
    if tag not in note:
        note = f"{note} | {tag}".strip(" |")
    already = pl.col("clv_pp").is_not_null()
    set_mask = mask & ~already
    return ledger.with_columns(
        pl.when(set_mask)
        .then(pl.lit("unavailable"))
        .otherwise(pl.col("close_status"))
        .alias("close_status"),
        pl.when(set_mask).then(pl.lit(note)).otherwise(pl.col("note")).alias("note"),
    )


def _float_literal(value: Any) -> pl.Expr:
    """A Float64 polars literal, or an explicit null literal for ``None``."""
    if value is None:
        return pl.lit(None, dtype=pl.Float64)
    return pl.lit(float(value), dtype=pl.Float64)


def _settle_keep(col: str, value: Any) -> pl.Expr:
    """Use the provided settle value when given; otherwise keep prior state."""
    if value is None:
        return pl.col(col)
    return _float_literal(value)


def apply_settle(
    ledger: pl.DataFrame,
    *,
    ticket_id: str,
    settle_value: float,
    settle_context: dict[str, Any] | None = None,
) -> pl.DataFrame:
    """Mark win/loss + pnl from final K (or other settle_value).

    Polars-native and vectorized so column dtypes stay stable. The previous
    implementation rebuilt the frame from a Python list of dicts, and polars'
    schema inference crashed whenever a settle column that was all-null in the
    first sampled rows received its first non-null value mid-stream
    (``ComputeError: could not append value``), which broke ``--auto-settle-api``.
    """
    ctx = settle_context or {}
    mask = pl.col("ticket_id") == ticket_id
    tgt = ledger.filter(mask).head(1)
    if tgt.is_empty():
        return ledger
    row = tgt.row(0, named=True)
    won = settle_side(row["side"], float(row["line"]), settle_value)
    pnl = bet_pnl(float(row["stake"]), float(row["bet_price"]), won=won)
    return ledger.with_columns(
        pl.when(mask)
        .then(_float_literal(settle_value))
        .otherwise(pl.col("settle_value"))
        .alias("settle_value"),
        pl.when(mask)
        .then(_settle_keep("settle_ip", ctx.get("ip")))
        .otherwise(pl.col("settle_ip"))
        .alias("settle_ip"),
        pl.when(mask)
        .then(_settle_keep("settle_outs", ctx.get("outs")))
        .otherwise(pl.col("settle_outs"))
        .alias("settle_outs"),
        pl.when(mask)
        .then(_settle_keep("settle_hits_allowed", ctx.get("hits_allowed")))
        .otherwise(pl.col("settle_hits_allowed"))
        .alias("settle_hits_allowed"),
        pl.when(mask)
        .then(_settle_keep("settle_walks_allowed", ctx.get("walks_allowed")))
        .otherwise(pl.col("settle_walks_allowed"))
        .alias("settle_walks_allowed"),
        pl.when(mask)
        .then(_settle_keep("settle_strikeouts", ctx.get("strikeouts")))
        .otherwise(pl.col("settle_strikeouts"))
        .alias("settle_strikeouts"),
        pl.when(mask).then(pl.lit("win" if won else "loss")).otherwise(pl.col("result")).alias("result"),
        pl.when(mask).then(_float_literal(pnl)).otherwise(pl.col("pnl")).alias("pnl"),
        pl.when(mask).then(pl.lit("settled")).otherwise(pl.col("status")).alias("status"),
    )


def apply_void(
    ledger: pl.DataFrame,
    *,
    ticket_id: str,
    reason: str = "no_action",
) -> pl.DataFrame:
    """Mark a ticket void/no-action (pitcher scratched, game postponed, etc.).

    No pnl impact: stake is treated as refunded, so voided tickets are excluded
    from ``settled_bets``/CLV and threshold-curve stats.
    """
    mask = pl.col("ticket_id") == ticket_id
    tgt = ledger.filter(mask).head(1)
    if tgt.is_empty():
        return ledger
    row = tgt.row(0, named=True)
    note = str(row.get("note") or "")
    tag = f"void={reason}"
    if tag not in note:
        note = f"{note} | {tag}".strip(" |")
    return ledger.with_columns(
        pl.when(mask).then(pl.lit("void")).otherwise(pl.col("status")).alias("status"),
        pl.when(mask).then(pl.lit("void")).otherwise(pl.col("result")).alias("result"),
        pl.when(mask).then(pl.lit(0.0)).otherwise(pl.col("pnl")).alias("pnl"),
        pl.when(mask).then(pl.lit(note)).otherwise(pl.col("note")).alias("note"),
    )


def save_ledger(frame: pl.DataFrame, path: Path = LEDGER_PATH) -> None:
    ensure_odds_dir()
    frame.write_parquet(path)
    _write_meta(path, frame.height)


def settled_bets(ledger: pl.DataFrame) -> pl.DataFrame:
    if ledger.is_empty() or "status" not in ledger.columns:
        return ledger
    return ledger.filter(pl.col("status") == "settled")


def dedupe_ledger_props(ledger: pl.DataFrame) -> pl.DataFrame:
    """One ticket per prop for skill stats / curves (no DK+FD double count).

    Prop key: ``(game_date, pitcher|player_name, line)``.

    Keeps the book you'd paper-bet: highest ``edge``, then ``units``.
    Ties break toward same-book close (``ok``) over ``ok_cross_book``.

    The per-book detail table can still show every ticket; call this only for
    summary statistics, histograms, and threshold curves.
    """
    if ledger.is_empty():
        return ledger

    df = ledger
    if "game_date" in df.columns:
        df = df.with_columns(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("_prop_d"))
    else:
        df = df.with_columns(pl.lit("").alias("_prop_d"))

    if "pitcher" in df.columns:
        pid = (
            pl.when(pl.col("pitcher").is_not_null())
            .then(pl.col("pitcher").cast(pl.Utf8))
            .otherwise(pl.col("player_name").str.to_lowercase())
            .alias("_prop_pid")
        )
    elif "player_name" in df.columns:
        pid = pl.col("player_name").str.to_lowercase().alias("_prop_pid")
    else:
        return ledger

    close_rank = (
        pl.when(pl.col("close_status") == "ok")
        .then(0)
        .when(pl.col("close_status") == "ok_cross_book")
        .then(1)
        .when(pl.col("close_status").is_null())
        .then(2)
        .otherwise(3)
        .alias("_close_rank")
        if "close_status" in df.columns
        else pl.lit(2).alias("_close_rank")
    )

    ranked = df.with_columns(pid, close_rank)
    sort_keys = ["_prop_d", "_prop_pid"]
    sort_desc: list[bool] = [False, False]
    if "line" in ranked.columns:
        sort_keys.append("line")
        sort_desc.append(False)
    if "edge" in ranked.columns:
        sort_keys.append("edge")
        sort_desc.append(True)
    if "units" in ranked.columns:
        sort_keys.append("units")
        sort_desc.append(True)
    sort_keys.append("_close_rank")
    sort_desc.append(False)

    ranked = ranked.sort(sort_keys, descending=sort_desc)
    subset = ["_prop_d", "_prop_pid"] + (["line"] if "line" in ranked.columns else [])
    out = ranked.unique(subset=subset, keep="first")
    return out.drop([c for c in ("_prop_d", "_prop_pid", "_close_rank") if c in out.columns])


def run_threshold_curve(
    ledger: pl.DataFrame,
    *,
    thresholds: list[float] | None = None,
    write: bool = True,
    dedupe_props: bool = True,
) -> pl.DataFrame:
    """Exploratory accept/deny curve on settled rows with pnl.

    By default dedupes to one ticket per prop (best edge) so DK+FD pairs
    are not double-counted.
    """
    s = settled_bets(ledger)
    if dedupe_props and not s.is_empty():
        s = dedupe_ledger_props(s)
    if s.is_empty() or "pnl" not in s.columns:
        return pl.DataFrame()
    s = s.filter(pl.col("pnl").is_not_null() & pl.col("edge").is_not_null())
    if s.is_empty():
        return pl.DataFrame()
    edges = s["edge"].to_list()
    pnls = s["pnl"].to_list()
    stakes = s["stake"].to_list()
    clvs = s["clv_pp"].to_list() if "clv_pp" in s.columns else None
    curve = threshold_curve(edges, pnls, stakes, clvs=clvs, thresholds=thresholds)
    frame = pl.DataFrame(curve)
    if write:
        ensure_odds_dir()
        frame.write_parquet(CURVE_PATH)
    return frame
