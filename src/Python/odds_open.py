"""Shared open-snapshot quote matching (SharpAPI → ledger tickets).

Used by ``production/odds/poll_odds.py --snapshot open`` and by
``production/odds/close_watcher.py``'s late-open sweep, which re-polls for
starters whose markets weren't posted yet at the morning open snapshot.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from Python.market import DEFAULT_EDGE_FLOOR
from Python.odds_board import (
    _line_key,
    _load_deploy_segment_states,
    _load_line_floor_map,
    _load_line_price_offsets,
    _maturity_bucket,
    _price_bucket,
    p_model_over_for_line,
    quality_gate_hold_reason,
)
from Python.odds_close import dedupe_quotes
from Python.odds_ledger import norm_player_name, score_quote_to_row
from Python.sharp_odds import fetch_mlb_strikeout_quotes


def match_board_row(board: pl.DataFrame, player_name: str) -> dict | None:
    key = norm_player_name(player_name)
    hits = board.filter(
        pl.col("player_name").map_elements(norm_player_name, return_dtype=pl.Utf8) == key
    )
    if hits.is_empty():
        last = key.split()[-1] if key else ""
        if last:
            hits = board.filter(
                pl.col("player_name")
                .map_elements(norm_player_name, return_dtype=pl.Utf8)
                .str.contains(last, literal=True)
            )
    if hits.is_empty() or hits.height > 1:
        return None
    return hits.to_dicts()[0]


def poll_open_tickets(
    board: pl.DataFrame,
    *,
    unit: float = 50.0,
    edge_floor: float = DEFAULT_EDGE_FLOOR,
    book: str | None = None,
    quotes: list | None = None,
    quality_gate: bool = False,
    kpi_policy_path: str | None = None,
    apply_line_price_correction: bool = False,
    apply_line_floors: bool = False,
    apply_deploy_matrix_filter: bool = False,
    side_edge_floors: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], list[str], int]:
    """Fetch (or reuse) open quotes and score them against ``board``.

    Returns ``(rows, unmatched, n_quotes)``. Does not touch the ledger.
    """
    if quotes is None:
        quotes, _ = dedupe_quotes(
            fetch_mlb_strikeout_quotes(sportsbook=book, main_only=True, is_live=False)
        )
    prob_offset_map = _load_line_price_offsets() if apply_line_price_correction else None
    line_floor_map = _load_line_floor_map() if apply_line_floors else None
    deploy_segment_states = (
        _load_deploy_segment_states() if apply_deploy_matrix_filter else None
    )
    rows: list[dict[str, Any]] = []
    unmatched: list[str] = []
    for q in quotes:
        brow = match_board_row(board, q.player_name)
        if brow is None:
            unmatched.append(q.player_name)
            continue
        col_p = p_model_over_for_line(brow, q.line)
        if col_p is None:
            unmatched.append(f"{q.player_name} line={q.line}")
            continue
        p_model_over = float(col_p)
        over_price_bucket = _price_bucket(float(q.over_american))
        maturity_bucket = _maturity_bucket(brow)
        if prob_offset_map is not None:
            offset_key = (float(q.line), over_price_bucket)
            p_model_over = min(
                max(p_model_over + float(prob_offset_map.get(offset_key, 0.0)), 1e-6),
                1.0 - 1e-6,
            )
        effective_floor = (
            float(line_floor_map.get(_line_key(q.line), edge_floor))
            if line_floor_map is not None
            else float(edge_floor)
        )

        ticket = score_quote_to_row(
            game_date=str(brow["game_date"]),
            game_pk=brow.get("game_pk"),
            pitcher=brow.get("pitcher"),
            player_name=brow["player_name"],
            line=q.line,
            over_price=q.over_american,
            under_price=q.under_american,
            p_model_over=p_model_over,
            book=q.sportsbook,
            unit_dollars=unit,
            edge_floor=effective_floor,
            source="sharpapi",
            event_id=q.event_id,
            event_start_time=q.event_start_time,
            projected_tbf=brow.get("projected_tbf"),
            days_rest=brow.get("days_rest"),
            expected_K=brow.get("expected_K"),
            note="",
        )
        if deploy_segment_states is not None and len(deploy_segment_states) > 0:
            segment_key = (float(q.line), over_price_bucket, maturity_bucket)
            seg_state = str(deploy_segment_states.get(segment_key, "UNSPECIFIED"))
            if seg_state == "OFF":
                ticket["passes_floor"] = False
                ticket["units"] = 0.0
                ticket["stake"] = 0.0
                note = str(ticket.get("note") or "")
                ticket["note"] = (
                    f"{note} | deploy_filter_hold=segment_off".strip(" |")
                )
        if side_edge_floors:
            side = str(ticket.get("side") or "")
            side_floor = side_edge_floors.get(side)
            if side_floor is not None and float(ticket.get("edge") or 0.0) < float(
                side_floor
            ):
                ticket["passes_floor"] = False
                ticket["units"] = 0.0
                ticket["stake"] = 0.0
                note = str(ticket.get("note") or "")
                ticket["note"] = (
                    f"{note} | side_floor_hold={side}_lt_{float(side_floor):.2f}".strip(
                        " |"
                    )
                )
        if quality_gate and ticket.get("passes_floor"):
            tier = None
            try:
                okv = brow.get("opp_lineup_k_vs_hand")
                if okv is not None:
                    v = float(okv)
                    if v >= 0.23:
                        tier = "favorable_matchup"
                    elif v >= 0.20:
                        tier = "avg_matchup"
                    else:
                        tier = "weak_matchup"
            except (TypeError, ValueError):
                tier = None
            hold_reason = quality_gate_hold_reason(
                edge=float(ticket.get("edge") or 0.0),
                side=str(ticket.get("side") or ""),
                days_rest=(float(brow.get("days_rest")) if brow.get("days_rest") is not None else None),
                projected_tbf=(
                    float(brow.get("projected_tbf"))
                    if brow.get("projected_tbf") is not None
                    else None
                ),
                matchup_tier=tier,
                kpi_policy_path=kpi_policy_path,
            )
            if hold_reason:
                ticket["passes_floor"] = False
                ticket["units"] = 0.0
                ticket["stake"] = 0.0
                note = str(ticket.get("note") or "")
                tag = f"quality_gate_hold={hold_reason}"
                ticket["note"] = f"{note} | {tag}".strip(" |")
        rows.append(ticket)
    return rows, unmatched, len(quotes)


def board_players_missing_open(board: pl.DataFrame, ledger_open_names: set[str]) -> list[str]:
    """Board (preferred-slate) player names with no open ticket yet."""
    if board.is_empty():
        return []
    out = []
    for name in board["player_name"].to_list():
        if norm_player_name(name) not in ledger_open_names:
            out.append(name)
    return out
