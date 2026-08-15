"""Simulate edge-floor and recommendation policy scenarios.

Outputs:
- artifacts/odds_log/policy_scenario_sweep.parquet
- artifacts/odds_log/policy_scenario_sweep_latest.csv
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import load_ledger  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"
REC_PATH = ODDS_DIR / "recommendations.parquet"
OUT_SWEEP = ODDS_DIR / "policy_scenario_sweep.parquet"
OUT_LATEST_CSV = ODDS_DIR / "policy_scenario_sweep_latest.csv"
OUT_PROFILE_SCAN = ODDS_DIR / "policy_side_profile_scan.parquet"
OUT_PROFILE_SCAN_LATEST = ODDS_DIR / "policy_side_profile_scan_latest.csv"


def _parse_thresholds(raw: str) -> list[float]:
    vals: list[float] = []
    for piece in raw.split(","):
        text = piece.strip()
        if not text:
            continue
        vals.append(float(text))
    if not vals:
        raise ValueError("No thresholds parsed from --thresholds.")
    return sorted(set(vals))


def _parse_side_threshold_map(raw: str) -> dict[str, float]:
    side_map: dict[str, float] = {}
    for piece in raw.split(","):
        text = piece.strip()
        if not text:
            continue
        if ":" not in text:
            raise ValueError(
                "Invalid --side-thresholds entry. Use format 'over:0.14,under:0.10'."
            )
        side_raw, val_raw = text.split(":", 1)
        side = side_raw.strip().lower()
        if side not in {"over", "under"}:
            raise ValueError(f"Invalid side '{side}'. Allowed: over, under.")
        side_map[side] = float(val_raw.strip())
    if not side_map:
        raise ValueError("No side thresholds parsed from --side-thresholds.")
    return side_map


def _safe_rate(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return float(num) / float(den)


def _latest_recommendation_counts(slate_date: str | None = None) -> pl.DataFrame:
    if not REC_PATH.exists():
        return pl.DataFrame()
    rec = pl.read_parquet(REC_PATH)
    if rec.is_empty():
        return rec

    if "game_date" in rec.columns:
        rec = rec.with_columns(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("game_date"))
        if slate_date:
            rec = rec.filter(pl.col("game_date") == slate_date)
        else:
            latest = rec.select(pl.col("game_date").max()).item()
            if latest is not None:
                rec = rec.filter(pl.col("game_date") == latest)

    group_cols: list[str] = ["recommendation"] if "recommendation" in rec.columns else []
    if "oos_reason" in rec.columns:
        group_cols.append("oos_reason")
    if not group_cols:
        return pl.DataFrame()

    return rec.group_by(group_cols).agg(pl.len().alias("n")).sort("n", descending=True)


def _scenario_rows(
    settled: pl.DataFrame,
    thresholds: list[float],
    *,
    side: str | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    scope = settled
    if side in {"over", "under"} and "side" in scope.columns:
        scope = scope.filter(pl.col("side") == side)

    if scope.is_empty():
        return rows

    for floor in thresholds:
        sel = scope.filter(pl.col("edge").cast(pl.Float64) >= floor)
        n = int(sel.height)
        wins = int(sel.filter(pl.col("result") == "win").height) if "result" in sel.columns else 0
        losses = int(sel.filter(pl.col("result") == "loss").height) if "result" in sel.columns else 0
        pnl = float(sel["pnl"].cast(pl.Float64).sum()) if "pnl" in sel.columns and n else 0.0
        stake = float(sel["stake"].cast(pl.Float64).sum()) if "stake" in sel.columns and n else 0.0
        avg_edge = float(sel["edge"].cast(pl.Float64).mean()) if n else None
        avg_clv = (
            float(sel["clv_pp"].cast(pl.Float64).mean())
            if n and "clv_pp" in sel.columns and sel.filter(pl.col("clv_pp").is_not_null()).height > 0
            else None
        )
        rows.append(
            {
                "snapshot_utc": datetime.now(timezone.utc).isoformat(),
                "scope": side or "all",
                "edge_floor": floor,
                "n_bets": n,
                "wins": wins,
                "losses": losses,
                "win_rate": _safe_rate(wins, wins + losses),
                "total_pnl": pnl,
                "roi": (pnl / stake) if stake > 0 else None,
                "avg_edge": avg_edge,
                "avg_clv_pp": avg_clv,
                "total_stake": stake,
            }
        )
    return rows


def _scenario_rows_dual_floor(
    settled: pl.DataFrame, side_thresholds: dict[str, float]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if settled.is_empty() or "side" not in settled.columns:
        return rows

    floor_over = side_thresholds.get("over")
    floor_under = side_thresholds.get("under")
    if floor_over is None or floor_under is None:
        return rows

    sel = settled.filter(
        ((pl.col("side") == "over") & (pl.col("edge").cast(pl.Float64) >= floor_over))
        | ((pl.col("side") == "under") & (pl.col("edge").cast(pl.Float64) >= floor_under))
    )
    n = int(sel.height)
    wins = int(sel.filter(pl.col("result") == "win").height) if "result" in sel.columns else 0
    losses = int(sel.filter(pl.col("result") == "loss").height) if "result" in sel.columns else 0
    pnl = float(sel["pnl"].cast(pl.Float64).sum()) if "pnl" in sel.columns and n else 0.0
    stake = float(sel["stake"].cast(pl.Float64).sum()) if "stake" in sel.columns and n else 0.0
    avg_edge = float(sel["edge"].cast(pl.Float64).mean()) if n else None
    avg_clv = (
        float(sel["clv_pp"].cast(pl.Float64).mean())
        if n and "clv_pp" in sel.columns and sel.filter(pl.col("clv_pp").is_not_null()).height > 0
        else None
    )
    rows.append(
        {
            "snapshot_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "all_dual_floor",
            "edge_floor": None,
            "edge_floor_over": floor_over,
            "edge_floor_under": floor_under,
            "n_bets": n,
            "wins": wins,
            "losses": losses,
            "win_rate": _safe_rate(wins, wins + losses),
            "total_pnl": pnl,
            "roi": (pnl / stake) if stake > 0 else None,
            "avg_edge": avg_edge,
            "avg_clv_pp": avg_clv,
            "total_stake": stake,
        }
    )
    return rows


def _parse_opt_thresholds(raw: str | None) -> list[float] | None:
    if raw is None:
        return None
    vals = _parse_thresholds(raw)
    return vals if vals else None


def _dual_floor_profile_scan(
    settled: pl.DataFrame,
    *,
    over_floors: list[float],
    under_floors: list[float],
    min_bets: int = 20,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    if settled.is_empty() or "side" not in settled.columns:
        return pl.DataFrame(rows)
    for over_floor in over_floors:
        for under_floor in under_floors:
            sel = settled.filter(
                ((pl.col("side") == "over") & (pl.col("edge").cast(pl.Float64) >= over_floor))
                | ((pl.col("side") == "under") & (pl.col("edge").cast(pl.Float64) >= under_floor))
            )
            if sel.is_empty():
                continue
            n = int(sel.height)
            stake = float(sel["stake"].cast(pl.Float64).sum())
            pnl = float(sel["pnl"].cast(pl.Float64).sum())
            clv_mean = (
                float(sel.filter(pl.col("clv_pp").is_not_null())["clv_pp"].cast(pl.Float64).mean())
                if sel.filter(pl.col("clv_pp").is_not_null()).height > 0
                else None
            )
            over = sel.filter(pl.col("side") == "over")
            under = sel.filter(pl.col("side") == "under")
            rows.append(
                {
                    "snapshot_utc": datetime.now(timezone.utc).isoformat(),
                    "edge_floor_over": float(over_floor),
                    "edge_floor_under": float(under_floor),
                    "n_bets": n,
                    "stake": stake,
                    "pnl": pnl,
                    "roi": (pnl / stake) if stake > 0 else None,
                    "mean_clv_pp": clv_mean,
                    "over_n": int(over.height),
                    "under_n": int(under.height),
                    "over_roi": (float(over["pnl"].cast(pl.Float64).sum()) / float(over["stake"].cast(pl.Float64).sum()))
                    if over.height and float(over["stake"].cast(pl.Float64).sum()) > 0
                    else None,
                    "under_roi": (float(under["pnl"].cast(pl.Float64).sum()) / float(under["stake"].cast(pl.Float64).sum()))
                    if under.height and float(under["stake"].cast(pl.Float64).sum()) > 0
                    else None,
                    "is_eligible": bool(n >= min_bets),
                }
            )
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).sort(["roi", "n_bets"], descending=[True, True])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--thresholds",
        type=str,
        default="0.08,0.10,0.12,0.14,0.16,0.18",
        help="Comma-separated edge floors to test (edge units, not percent).",
    )
    parser.add_argument(
        "--side-thresholds",
        type=str,
        default=None,
        help="Optional side-specific floor map, e.g. 'over:0.14,under:0.10'.",
    )
    parser.add_argument("--slate-date", type=str, default=None, help="Optional YYYY-MM-DD for rec count snapshot.")
    parser.add_argument(
        "--profile-over-floors",
        type=str,
        default=None,
        help="Optional comma-separated over-side floors for dual-floor profile scan.",
    )
    parser.add_argument(
        "--profile-under-floors",
        type=str,
        default=None,
        help="Optional comma-separated under-side floors for dual-floor profile scan.",
    )
    parser.add_argument(
        "--profile-min-bets",
        type=int,
        default=20,
        help="Minimum historical bet count to treat profile as eligible.",
    )
    args = parser.parse_args()

    thresholds = _parse_thresholds(args.thresholds)
    side_thresholds = _parse_side_threshold_map(args.side_thresholds) if args.side_thresholds else None
    profile_over = _parse_opt_thresholds(args.profile_over_floors)
    profile_under = _parse_opt_thresholds(args.profile_under_floors)

    led = load_ledger()
    settled = (
        led.filter(
            (pl.col("status") == "settled")
            & (pl.col("stake").cast(pl.Float64).fill_null(0.0) > 0)
        )
        if not led.is_empty()
        else led
    )
    settled = settled.filter(pl.col("edge").is_not_null()) if not settled.is_empty() else settled

    scenario_rows: list[dict[str, object]] = []
    for scope in (None, "over", "under"):
        scenario_rows.extend(_scenario_rows(settled, thresholds, side=scope))
    if side_thresholds is not None:
        scenario_rows.extend(_scenario_rows_dual_floor(settled, side_thresholds))
    scenario = pl.DataFrame(scenario_rows) if scenario_rows else pl.DataFrame()
    profile_scan = pl.DataFrame()
    if profile_over is not None and profile_under is not None:
        profile_scan = _dual_floor_profile_scan(
            settled,
            over_floors=profile_over,
            under_floors=profile_under,
            min_bets=max(1, int(args.profile_min_bets)),
        )

    if OUT_SWEEP.exists() and not scenario.is_empty():
        hist = pl.read_parquet(OUT_SWEEP)
        out = pl.concat([hist, scenario], how="diagonal_relaxed")
    else:
        out = scenario
    if not out.is_empty():
        out.write_parquet(OUT_SWEEP)
        scenario.write_csv(OUT_LATEST_CSV)
    if not profile_scan.is_empty():
        if OUT_PROFILE_SCAN.exists():
            prof_hist = pl.read_parquet(OUT_PROFILE_SCAN)
            prof_out = pl.concat([prof_hist, profile_scan], how="diagonal_relaxed")
        else:
            prof_out = profile_scan
        prof_out.write_parquet(OUT_PROFILE_SCAN)
        profile_scan.write_csv(OUT_PROFILE_SCAN_LATEST)

    rec_counts = _latest_recommendation_counts(args.slate_date)
    if not rec_counts.is_empty():
        print("--- latest recommendation mix ---")
        for row in rec_counts.to_dicts():
            print(row)
    if scenario.is_empty():
        print("No settled rows with stake>0 and edge available; scenario sweep not updated.")
        return

    print(f"wrote {OUT_SWEEP}")
    print(f"wrote {OUT_LATEST_CSV}")
    print("--- latest scenario rows ---")
    for row in scenario.sort(["scope", "edge_floor"]).to_dicts():
        print(row)
    if not profile_scan.is_empty():
        best = profile_scan.filter(pl.col("is_eligible"))
        if not best.is_empty():
            pick = best.sort(["roi", "mean_clv_pp", "n_bets"], descending=[True, True, True]).head(1)
            print("--- best eligible side profile ---")
            print(pick.to_dicts()[0])
        else:
            print("--- side profile scan ---")
            print("No profile met --profile-min-bets eligibility.")


if __name__ == "__main__":
    main()
