"""Live strikeout recommendation board (model × SharpAPI odds).

Terminal prints **BET only** (≥ edge floor, in-support).
Full matched slate (BET + skip + OOS) is always written for monitoring / curves.

Examples:
    python production/odds/odds_board.py --unit 50
    python production/odds/odds_board.py --show-all
    python production/odds/odds_board.py --open-html
    python production/odds/odds_board.py --quality-gate

Writes (full slate every run — single file, overwritten):
  artifacts/odds_log/recommendations.parquet
  artifacts/odds_log/recommendations.html
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.env_load import load_project_dotenv  # noqa: E402
from Python.market import DEFAULT_EDGE_FLOOR  # noqa: E402
from Python.odds_board import (  # noqa: E402
    build_recommendations,
    write_recommendations,
)


def _print_table(frame: pl.DataFrame, *, bets_only: bool) -> None:
    if frame.is_empty():
        print("No matched rows.")
        return
    view = frame
    if bets_only:
        if "recommendation" in view.columns:
            view = view.filter(pl.col("recommendation") == "BET")
        elif "passes_floor" in view.columns:
            view = view.filter(pl.col("passes_floor") == True)  # noqa: E712
        if view.is_empty():
            print("No BET rows at current floor (full slate still written to parquet/HTML).")
            return
    cols = [
        c
        for c in (
            "recommendation",
            "pitcher_team",
            "player_name",
            "expected_K",
            "book",
            "line",
            "best_side",
            "best_price",
            "edge",
            "units",
            "stake",
            "oos_reason",
        )
        if c in view.columns
    ]
    rows = view.select(cols).to_dicts()
    hdr = (
        f"{'rec':4} {'tm':3} {'pitcher':18} {'expK':>5} {'book':10} "
        f"{'line':>4} {'side':5} {'price':>5} {'edge':>7} {'u':>5} {'$':>6}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        price = int(r["best_price"])
        print(
            f"{r['recommendation']:4} {str(r.get('pitcher_team') or '?'):3} "
            f"{str(r['player_name'])[:18]:18} {float(r['expected_K']):5.2f} "
            f"{str(r['book']):10} {float(r['line']):4.1f} {r['best_side']:5} "
            f"{price:+5d} {float(r['edge'])*100:+6.1f}% "
            f"{float(r['units']):5.2f} {float(r['stake']):6.2f}"
            + (f"  [{r['oos_reason']}]" if r.get("oos_reason") else "")
        )


def main() -> None:
    load_project_dotenv()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", type=date.fromisoformat, default=None)
    p.add_argument("--unit", type=float, default=50.0)
    p.add_argument("--edge-floor", type=float, default=DEFAULT_EDGE_FLOOR)
    p.add_argument("--book", type=str, default=None, help="draftkings|fanduel")
    p.add_argument("--all-starters", action="store_true")
    p.add_argument(
        "--all-books",
        action="store_true",
        help="Keep DK and FD per pitcher (default: best book only)",
    )
    p.add_argument(
        "--show-all",
        action="store_true",
        help="Print BET+skip+OOS (default: BET only)",
    )
    p.add_argument("--open-html", action="store_true")
    p.add_argument("--no-write", action="store_true")
    p.add_argument(
        "--quality-gate",
        action="store_true",
        help="Mark risky BET rows as HOLD based on latest diagnostics.",
    )
    p.add_argument(
        "--kpi-policy",
        type=str,
        default=None,
        help="Optional path to KPI/gate policy JSON (default: production/ops/kpi_policy.json).",
    )
    p.add_argument(
        "--apply-line-price-correction",
        action="store_true",
        help="Apply line/price calibration offsets before recommendation scoring.",
    )
    p.add_argument(
        "--apply-line-floors",
        action="store_true",
        help="Apply line-aware edge floors from market research policy.",
    )
    p.add_argument(
        "--apply-deploy-matrix-filter",
        action="store_true",
        help="Allow only ON segments from calibration deploy matrix.",
    )
    p.add_argument(
        "--roi-mode",
        choices=["aggressive", "balanced", "conservative", "profit_lock"],
        default=None,
        help="Preset risk mode: enables correction/floors/deploy-filter and sets edge floor.",
    )
    args = p.parse_args()

    edge_floor = args.edge_floor
    apply_line_price_correction = args.apply_line_price_correction
    apply_line_floors = args.apply_line_floors
    apply_deploy_matrix_filter = args.apply_deploy_matrix_filter
    if args.roi_mode is not None:
        roi_floors = {
            "aggressive": 0.14,
            "balanced": 0.16,
            "conservative": 0.18,
            "profit_lock": 0.18,
        }
        edge_floor = roi_floors[args.roi_mode]
        apply_line_price_correction = True
        apply_line_floors = True
        apply_deploy_matrix_filter = True
    side_edge_floors = None
    if args.roi_mode == "profit_lock":
        side_edge_floors = {"over": 0.22, "under": 0.18}

    frame, meta = build_recommendations(
        slate=args.date,
        preferred_only=not args.all_starters,
        unit_dollars=args.unit,
        edge_floor=edge_floor,
        sportsbook=args.book,
        best_book_only=not args.all_books,
        quality_gate=args.quality_gate,
        kpi_policy_path=args.kpi_policy,
        apply_line_price_correction=apply_line_price_correction,
        apply_line_floors=apply_line_floors,
        apply_deploy_matrix_filter=apply_deploy_matrix_filter,
        side_edge_floors=side_edge_floors,
    )
    print(
        f"slate={meta['slate_date']}  board={meta['n_board']}  "
        f"quotes={meta['n_quotes']}  matched={meta['n_matched']}"
        f"/{meta.get('n_matched_raw', meta['n_matched'])}  "
        f"BET={meta['n_bet']}  HOLD={meta.get('n_hold', 0)}  unmatched={meta['n_unmatched']}"
        + ("  (best book/pitcher)" if meta.get("best_book_only") else "  (all books)")
    )
    if meta.get("quality_gate_enabled"):
        print(
            f"quality_gate: n_warn={meta.get('quality_gate_n_warn')} "
            f"min_edge={meta.get('quality_gate_min_edge', args.edge_floor):.2f} "
            f"holds={meta.get('quality_gate_n_hold', 0)}"
        )
    if meta.get("line_price_correction_applied"):
        print(
            f"line_price_correction: segments={meta.get('line_price_correction_segments', 0)}"
        )
    if meta.get("line_floor_policy_applied"):
        print(
            f"line_floor_policy: segments={meta.get('line_floor_policy_segments', 0)}"
        )
    if meta.get("deploy_matrix_filter_applied"):
        print(
            f"deploy_matrix_filter: segments_on={meta.get('deploy_matrix_segments_on', 0)} "
            f"segments_off={meta.get('deploy_matrix_segments_off', 0)} "
            f"filtered_rows={meta.get('n_segment_filtered', 0)}"
        )
    if args.roi_mode:
        print(f"roi_mode: {args.roi_mode} (edge_floor={edge_floor:.2f})")
    if meta.get("side_edge_floors_applied"):
        print(
            "side_edge_floors:",
            f"over>={meta.get('side_edge_floor_over'):.2f}",
            f"under>={meta.get('side_edge_floor_under'):.2f}",
        )
    if meta.get("unmatched_sample"):
        print("unmatched e.g.", ", ".join(meta["unmatched_sample"][:8]))
    if meta.get("preferred_missing_quote"):
        print(
            f"preferred with no scored quote ({meta.get('n_preferred_missing_quote')}):",
            ", ".join(meta["preferred_missing_quote"][:8]),
        )
    print()
    _print_table(frame, bets_only=not args.show_all)

    if not args.no_write:
        pq, html = write_recommendations(frame, meta)
        print()
        print(f"Wrote {pq}  (full slate n={0 if frame.is_empty() else frame.height})")
        print(f"Wrote {html}")
        if args.open_html:
            webbrowser.open(html.resolve().as_uri())


if __name__ == "__main__":
    main()
