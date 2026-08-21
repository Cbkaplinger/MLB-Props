"""Poll SharpAPI MLB pitcher strikeouts into the odds ledger.

Morning (open / bet-time snapshot):
    python production/odds/poll_odds.py --snapshot open --unit 50

Near first pitch (or use the tip-aware watcher):
    python production/odds/poll_odds.py --snapshot close
    python production/odds/close_watcher.py

Requires ``SHARPAPI_KEY`` in repo-root ``.env``. Free tier = DraftKings + FanDuel.
Open replaces unclosed same-day tickets by default (``--append`` to keep).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402
from Python.env_load import load_project_dotenv  # noqa: E402
from Python.kpi_policy import load_kpi_policy  # noqa: E402
from Python.market import DEFAULT_EDGE_FLOOR  # noqa: E402
from Python.odds_close import fill_closes  # noqa: E402
from Python.odds_ledger import (  # noqa: E402
    LEDGER_PATH,
    append_open_rows,
    minutes_to_tip,
    parse_event_start_utc,
    replace_open_slate,
    stable_ticket_id,
)
from Python.odds_open import poll_open_tickets  # noqa: E402

LOG_PATH = config.OUTPUT_DIR / "projection_log" / "projections.parquet"
REC_PATH = config.OUTPUT_DIR / "odds_log" / "recommendations.parquet"
REC_META_PATH = config.OUTPUT_DIR / "odds_log" / "recommendations_meta.json"
POLICY_LOG_PATH = config.OUTPUT_DIR / "odds_log" / "policy_change_log.jsonl"
POLICY_STATE_PATH = config.OUTPUT_DIR / "odds_log" / "policy_current_state.json"


def _apply_exposure_controls(
    rows: list[dict],
    *,
    kpi_policy: str | None,
) -> tuple[list[dict], dict[str, float]]:
    policy = load_kpi_policy(kpi_policy)
    cfg = policy.get("exposure_controls", {})
    max_daily = float(cfg.get("max_daily_total_stake", 500.0))
    max_line = float(cfg.get("max_stake_per_line", 150.0))
    max_game = float(cfg.get("max_stake_per_game", 200.0))

    keep: list[dict] = []
    stake_total = 0.0
    by_line: dict[tuple[str, float], float] = {}
    by_game: dict[object, float] = {}
    for ticket in sorted(rows, key=lambda x: float(x.get("edge") or 0.0), reverse=True):
        stake = float(ticket.get("stake") or 0.0)
        if stake <= 0:
            keep.append(ticket)
            continue
        line_key = (str(ticket.get("player_name") or ""), float(ticket.get("line") or 0.0))
        game_key = ticket.get("game_pk") or str(ticket.get("game_date") or "")
        line_after = by_line.get(line_key, 0.0) + stake
        game_after = by_game.get(game_key, 0.0) + stake
        total_after = stake_total + stake
        reasons: list[str] = []
        if total_after > max_daily:
            reasons.append("max_daily_total_stake")
        if line_after > max_line:
            reasons.append("max_stake_per_line")
        if game_after > max_game:
            reasons.append("max_stake_per_game")
        if reasons:
            ticket["passes_floor"] = False
            ticket["units"] = 0.0
            ticket["stake"] = 0.0
            note = str(ticket.get("note") or "")
            tag = "exposure_hold=" + ",".join(reasons)
            ticket["note"] = f"{note} | {tag}".strip(" |")
            keep.append(ticket)
            continue
        by_line[line_key] = line_after
        by_game[game_key] = game_after
        stake_total = total_after
        keep.append(ticket)
    return keep, {
        "max_daily_total_stake": max_daily,
        "max_stake_per_line": max_line,
        "max_stake_per_game": max_game,
        "accepted_total_stake": stake_total,
    }


def _policy_signature(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _log_policy_change_if_needed(policy_payload: dict) -> tuple[str, bool]:
    sig = _policy_signature(policy_payload)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prior_sig = None
    if POLICY_STATE_PATH.exists():
        try:
            prior = json.loads(POLICY_STATE_PATH.read_text(encoding="utf-8"))
            prior_sig = prior.get("policy_signature")
        except Exception:
            prior_sig = None
    changed = prior_sig != sig
    POLICY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    POLICY_STATE_PATH.write_text(
        json.dumps(
            {
                "updated_utc": now,
                "policy_signature": sig,
                "policy_payload": policy_payload,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if changed:
        entry = {
            "changed_utc": now,
            "policy_signature": sig,
            "prior_policy_signature": prior_sig,
            "policy_payload": policy_payload,
        }
        with POLICY_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    return sig, changed


def _stamp_policy_on_rows(rows: list[dict], *, policy_signature: str, policy_label: str) -> list[dict]:
    for row in rows:
        note = str(row.get("note") or "")
        tags = [f"policy_sig={policy_signature}", f"policy_label={policy_label}"]
        if note:
            row["note"] = f"{note} | " + " | ".join(tags)
        else:
            row["note"] = " | ".join(tags)
    return rows


def _load_recommendations_meta() -> dict:
    if not REC_META_PATH.exists():
        return {}
    try:
        return json.loads(REC_META_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_board(slate: date | None, preferred_only: bool) -> pl.DataFrame:
    if not LOG_PATH.exists():
        raise SystemExit(
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
        raise SystemExit(f"No projection rows for {use}; logged={dates}")
    return board


def _poll_open(
    board: pl.DataFrame,
    *,
    unit: float,
    edge_floor: float,
    book: str | None,
    dry_run: bool,
    replace: bool,
    quality_gate: bool,
    kpi_policy: str | None,
    single_ticket_per_prop: bool,
    apply_line_price_correction: bool,
    apply_line_floors: bool,
    apply_deploy_matrix_filter: bool,
    side_edge_floors: dict[str, float] | None,
    policy_signature: str,
    policy_label: str,
) -> None:
    rows, unmatched, n_quotes = poll_open_tickets(
        board,
        unit=unit,
        edge_floor=edge_floor,
        book=book,
        quality_gate=quality_gate,
        kpi_policy_path=kpi_policy,
        apply_line_price_correction=apply_line_price_correction,
        apply_line_floors=apply_line_floors,
        apply_deploy_matrix_filter=apply_deploy_matrix_filter,
        side_edge_floors=side_edge_floors,
    )
    if single_ticket_per_prop and rows:
        # Keep one morning ticket per prop (pitcher/line/side), selecting the
        # best available book by edge, then payout price, then stake.
        rf = pl.DataFrame(rows)
        key_cols = [
            c
            for c in ("game_date", "player_name", "line", "side")
            if c in rf.columns
        ]
        if key_cols:
            sort_cols: list[str] = []
            sort_desc: list[bool] = []
            if "edge" in rf.columns:
                sort_cols.append("edge")
                sort_desc.append(True)
            if "bet_price" in rf.columns:
                sort_cols.append("bet_price")
                sort_desc.append(True)
            if "stake" in rf.columns:
                sort_cols.append("stake")
                sort_desc.append(True)
            if sort_cols:
                rf = rf.sort(sort_cols, descending=sort_desc)
            before_n = rf.height
            rf = rf.unique(subset=key_cols, keep="first")
            dropped = before_n - rf.height
            if dropped > 0:
                print(
                    f"single-ticket mode: kept {rf.height}/{before_n} rows "
                    f"(dropped {dropped} duplicate book entries)"
                )
            rows = rf.to_dicts()

    rows, exp_meta = _apply_exposure_controls(rows, kpi_policy=kpi_policy)
    rows = _stamp_policy_on_rows(
        rows, policy_signature=policy_signature, policy_label=policy_label
    )

    print(f"SharpAPI paired quotes: {n_quotes}")
    for ticket in rows:
        note = str(ticket.get("note") or "")
        if "quality_gate_hold=" in note:
            flag = "HOLD"
        elif "exposure_hold=" in note:
            flag = "HOLD"
        elif ticket["passes_floor"]:
            flag = "BET"
        elif "oos=" in note:
            flag = "OOS"
        else:
            flag = "skip"
        tip_m = ticket.get("minutes_to_tip_at_open")
        tip_s = f"  tip-{tip_m:.0f}m" if tip_m is not None else ""
        print(
            f"[{flag}] {ticket['book']:10} {ticket['player_name']:20} "
            f"{ticket['side']} {ticket['line']} @ {ticket['bet_price']:+.0f}  "
            f"edge={ticket['edge']:+.1%}  {ticket['units']:.2f}u{tip_s}"
        )

    n_bet = sum(1 for r in rows if r["passes_floor"])
    n_hold = sum(
        1
        for r in rows
        if (
            "quality_gate_hold=" in str(r.get("note") or "")
            or "exposure_hold=" in str(r.get("note") or "")
        )
    )
    print(f"Matched={len(rows)}  BET={n_bet}  HOLD={n_hold}  unmatched_or_bad_line={len(unmatched)}")
    print(
        "exposure caps:",
        f"daily<={exp_meta['max_daily_total_stake']:.0f}",
        f"line<={exp_meta['max_stake_per_line']:.0f}",
        f"game<={exp_meta['max_stake_per_game']:.0f}",
        f"accepted=${exp_meta['accepted_total_stake']:.2f}",
    )
    if unmatched[:8]:
        print("  e.g.", ", ".join(unmatched[:8]))
    if dry_run:
        print("dry-run: not writing ledger")
        return
    if not rows:
        print("Nothing to append.")
        return
    slate = str(board["game_date"][0])
    if replace:
        _, n_written, n_removed = replace_open_slate(rows, slate=slate)
        print(
            f"Replaced slate {slate}: wrote {n_written}, removed {n_removed} "
            f"prior unclosed opens -> {LEDGER_PATH}"
        )
    else:
        _, n_appended, n_skipped = append_open_rows(rows)
        print(
            f"Appended {n_appended} (skipped {n_skipped} already-open) -> {LEDGER_PATH}"
        )


def _rows_from_recommendations(*, slate: str, unit_dollars: float) -> list[dict]:
    if not REC_PATH.exists():
        raise SystemExit(
            f"Missing {REC_PATH}. Run production/odds/odds_board.py first."
        )
    rec = pl.read_parquet(REC_PATH)
    if rec.is_empty():
        return []
    rec = rec.with_columns(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gdate"))
    rec = rec.filter(pl.col("gdate") == str(slate)[:10])
    if rec.is_empty():
        return []
    # Ensure deterministic one-row-per-prop behavior, preferring BET rows on duplicates.
    rec = (
        rec.with_columns(
            (pl.col("recommendation") == "BET").cast(pl.Int8).alias("_bet_rank"),
            pl.col("edge").cast(pl.Float64).fill_null(-1e9).alias("_edge_sort"),
        )
        .sort(["_bet_rank", "_edge_sort"], descending=[True, True])
        .unique(subset=["gdate", "player_name", "book", "line"], keep="first")
        .drop(["_bet_rank", "_edge_sort"])
    )
    now = datetime.now(timezone.utc)
    rows: list[dict] = []
    for r in rec.to_dicts():
        side = str(r.get("best_side") or "")
        if side not in {"over", "under"}:
            continue
        line = float(r.get("line") or 0.0)
        book = str(r.get("book") or "")
        player_name = str(r.get("player_name") or "")
        over_price = float(r.get("over_price") or 0.0)
        under_price = float(r.get("under_price") or 0.0)
        bet_price = float(r.get("best_price") or (over_price if side == "over" else under_price))
        other_price = float(under_price if side == "over" else over_price)
        event_start = r.get("event_start_time")
        tip = parse_event_start_utc(str(event_start) if event_start is not None else None)
        note_parts: list[str] = []
        rec_label = str(r.get("recommendation") or "")
        if rec_label in {"HOLD", "skip", "OOS"}:
            note_parts.append(f"board_rec={rec_label}")
        for key in ("quality_gate_reason", "policy_reason", "oos_reason"):
            val = r.get(key)
            if val is not None and str(val).strip():
                note_parts.append(f"{key}={str(val).strip()}")
        note = " | ".join(note_parts).strip(" |")
        passes_floor = rec_label == "BET"
        units = float(r.get("units") or 0.0) if passes_floor else 0.0
        stake = float(r.get("stake") or 0.0) if passes_floor else 0.0
        rows.append(
            {
                "ticket_id": stable_ticket_id(
                    game_date=str(slate),
                    player_name=player_name,
                    line=line,
                    book=book,
                    side=side,
                ),
                "logged_at_utc": now.isoformat(),
                "closed_at_utc": None,
                "event_id": r.get("event_id"),
                "event_start_time_utc": tip.isoformat() if tip is not None else (str(event_start) if event_start is not None else None),
                "minutes_to_tip_at_open": minutes_to_tip(tip, as_of=now),
                "minutes_to_tip_at_close": None,
                "game_date": str(slate),
                "game_pk": r.get("game_pk"),
                "pitcher": r.get("pitcher"),
                "player_name": player_name,
                "market": "pitcher_strikeouts",
                "line": line,
                "book": book,
                "snapshot": "bet",
                "side": side,
                "bet_price": bet_price,
                "other_price": other_price,
                "over_price": over_price,
                "under_price": under_price,
                "p_model": float(r.get("p_model") or 0.0),
                "p_market": float(r.get("p_market") or 0.0),
                "edge": float(r.get("edge") or 0.0),
                "passes_floor": bool(passes_floor),
                "units": units,
                "unit_dollars": float(unit_dollars),
                "stake": stake,
                "bankroll": None,
                "kelly_frac": None,
                "status": "open",
                "close_over": None,
                "close_under": None,
                "clv_pp": None,
                "close_status": None,
                "settle_value": None,
                "result": None,
                "pnl": None,
                "source": "board_artifact",
                "note": note,
            }
        )
    return rows


def _open_from_recommendations(
    board: pl.DataFrame,
    *,
    unit: float,
    dry_run: bool,
    replace: bool,
    policy_signature: str,
    policy_label: str,
) -> None:
    slate = str(board["game_date"][0])
    rows = _rows_from_recommendations(slate=slate, unit_dollars=unit)
    rows = _stamp_policy_on_rows(
        rows, policy_signature=policy_signature, policy_label=policy_label
    )
    n_bet = sum(1 for r in rows if bool(r.get("passes_floor")))
    print(f"board-artifact rows={len(rows)}  BET={n_bet}  non-BET={len(rows)-n_bet}")
    if dry_run:
        print("dry-run: not writing ledger")
        return
    if replace:
        _, n_written, n_removed = replace_open_slate(rows, slate=slate)
        print(
            f"Replaced slate {slate}: wrote {n_written}, removed {n_removed} "
            f"prior unclosed opens -> {LEDGER_PATH}"
        )
    else:
        _, n_appended, n_skipped = append_open_rows(rows)
        print(
            f"Appended {n_appended} (skipped {n_skipped} already-open) -> {LEDGER_PATH}"
        )


def _poll_close(
    board: pl.DataFrame,
    *,
    book: str | None,
    dry_run: bool,
) -> None:
    slate = str(board["game_date"][0])
    result = fill_closes(slate=slate, book=book, dry_run=dry_run)
    if result["n_need"] == 0:
        print(f"No open tickets needing close for {slate}")
        return
    print(
        f"SharpAPI paired quotes: {result['n_quotes']}"
        + (
            f" (dropped {result.get('n_dupes_dropped', 0)} dupes)"
            if result.get("n_dupes_dropped")
            else ""
        )
    )
    for miss in result.get("misses") or []:
        print(f"MISS close {miss}")
    print(
        f"Updated closes: {result['n_upd']}/{result['n_need']}  "
        f"miss={result['n_miss']}  line_fallback={result['n_line_fallback']}"
    )
    if dry_run:
        print("dry-run: not writing")
        return
    if result.get("updated"):
        print(f"Wrote {LEDGER_PATH}")
    elif result["n_upd"] == 0:
        print("Nothing written.")


def main() -> None:
    load_project_dotenv()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--snapshot",
        choices=("open", "close"),
        required=True,
        help="open=bet-time quotes; close=fill CLV on today's open tickets",
    )
    p.add_argument("--date", type=date.fromisoformat, default=None)
    p.add_argument("--unit", type=float, default=50.0)
    p.add_argument("--edge-floor", type=float, default=DEFAULT_EDGE_FLOOR)
    p.add_argument(
        "--book",
        type=str,
        default=None,
        help="Optional sportsbook filter (draftkings|fanduel).",
    )
    p.add_argument("--all-starters", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--quality-gate",
        action="store_true",
        help="Apply diagnostics-driven HOLD gate to open-ticket sizing.",
    )
    p.add_argument(
        "--append",
        action="store_true",
        help="Open only: keep existing same-day opens (default: replace)",
    )
    p.add_argument(
        "--kpi-policy",
        type=str,
        default=None,
        help="Optional path to KPI/gate policy JSON (default: production/ops/kpi_policy.json).",
    )
    p.add_argument(
        "--multi-book",
        action="store_true",
        help="Open only: keep multiple books per prop (default: single-ticket best line).",
    )
    p.add_argument(
        "--apply-line-price-correction",
        action="store_true",
        help="Open only: apply line/price calibration offsets before scoring.",
    )
    p.add_argument(
        "--apply-line-floors",
        action="store_true",
        help="Open only: apply line-aware edge floors from policy.",
    )
    p.add_argument(
        "--apply-deploy-matrix-filter",
        action="store_true",
        help="Open only: allow only ON segments from deploy matrix.",
    )
    p.add_argument(
        "--roi-mode",
        choices=["aggressive", "balanced", "conservative", "profit_lock"],
        default=None,
        help="Open only: risk mode that sets floor and deploy controls consistently with odds_board.",
    )
    p.add_argument(
        "--from-recommendations",
        action="store_true",
        help="Open only: write open ledger rows directly from recommendations.parquet (source-of-truth execution mode).",
    )
    args = p.parse_args()

    edge_floor = float(args.edge_floor)
    apply_line_price_correction = bool(args.apply_line_price_correction)
    apply_line_floors = bool(args.apply_line_floors)
    apply_deploy_matrix_filter = bool(args.apply_deploy_matrix_filter)
    side_edge_floors: dict[str, float] | None = None
    if args.roi_mode is not None:
        roi_floors = {
            "aggressive": 0.14,
            "balanced": 0.16,
            "conservative": 0.18,
            "profit_lock": 0.18,
        }
        edge_floor = float(roi_floors[args.roi_mode])
        apply_line_price_correction = True
        apply_line_floors = True
        apply_deploy_matrix_filter = True
        if args.roi_mode == "profit_lock":
            side_edge_floors = {"over": 0.22, "under": 0.18}
    policy_signature = "n/a"
    policy_label = "close_snapshot"
    if args.snapshot == "open":
        rec_meta = _load_recommendations_meta() if args.from_recommendations else {}
        policy_payload = {
            "snapshot": args.snapshot,
            "from_recommendations": bool(args.from_recommendations),
            "roi_mode": args.roi_mode,
            "edge_floor": float(rec_meta.get("edge_floor", edge_floor)),
            "quality_gate": bool(args.quality_gate),
            "apply_line_price_correction": bool(
                rec_meta.get("line_price_correction_applied", apply_line_price_correction)
            ),
            "apply_line_floors": bool(
                rec_meta.get("line_floor_policy_applied", apply_line_floors)
            ),
            "apply_deploy_matrix_filter": bool(
                rec_meta.get("deploy_matrix_filter_applied", apply_deploy_matrix_filter)
            ),
            "side_edge_floors": side_edge_floors or {},
            "kpi_policy_path": args.kpi_policy or "default",
            "unit_dollars": float(args.unit),
        }
        policy_signature, policy_changed = _log_policy_change_if_needed(policy_payload)
        policy_label = (
            args.roi_mode
            if args.roi_mode is not None
            else ("board_artifact" if args.from_recommendations else "custom")
        )
        print(
            "policy regime:",
            f"label={policy_label}",
            f"sig={policy_signature}",
            f"changed={policy_changed}",
        )

    board = _load_board(args.date, preferred_only=not args.all_starters)
    print(
        f"slate={board['game_date'][0]}  board_n={board.height}  "
        f"snapshot={args.snapshot}  unit=${args.unit:.0f}"
    )
    if args.snapshot == "open":
        if args.from_recommendations:
            _open_from_recommendations(
                board,
                unit=args.unit,
                dry_run=args.dry_run,
                replace=not args.append,
                policy_signature=policy_signature,
                policy_label=policy_label,
            )
        else:
            _poll_open(
                board,
                unit=args.unit,
                edge_floor=edge_floor,
                book=args.book,
                dry_run=args.dry_run,
                replace=not args.append,
                quality_gate=args.quality_gate,
                kpi_policy=args.kpi_policy,
                single_ticket_per_prop=not args.multi_book,
                apply_line_price_correction=apply_line_price_correction,
                apply_line_floors=apply_line_floors,
                apply_deploy_matrix_filter=apply_deploy_matrix_filter,
                side_edge_floors=side_edge_floors,
                policy_signature=policy_signature,
                policy_label=policy_label,
            )
    else:
        _poll_close(board, book=args.book, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
