"""Build weekly KPI artifact summary (parquet + markdown)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import dedupe_ledger_props, load_ledger  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"
SCORECARD_PATH = ODDS_DIR / "model_health_scorecard_daily.parquet"
GATE_PATH = ODDS_DIR / "gate_next_n_comparison.parquet"
PROJ_PATH = ROOT / "artifacts" / "projection_log" / "projections.parquet"
OUT_PARQUET = ODDS_DIR / "weekly_kpi_summary.parquet"
OUT_MD = ODDS_DIR / "weekly_kpi_summary.md"


def _slate_size_bucket(n_pitchers: int) -> str:
    if n_pitchers >= 24:
        return "full_24_plus"
    if n_pitchers >= 16:
        return "mid_16_23"
    return "light_0_15"


def _bet_volume_by_slate_size() -> pl.DataFrame:
    if not PROJ_PATH.exists():
        return pl.DataFrame(
            {"slate_size_bucket": [], "n_days": [], "total_bets": [], "avg_bets_per_day": []}
        )

    proj = pl.read_parquet(PROJ_PATH).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("game_date")
    )
    by_day = proj.group_by("game_date").agg(pl.col("player_name").n_unique().alias("n_pitchers"))
    by_day = by_day.with_columns(
        pl.col("n_pitchers")
        .map_elements(_slate_size_bucket, return_dtype=pl.Utf8)
        .alias("slate_size_bucket")
    )

    led = dedupe_ledger_props(load_ledger())
    if led.is_empty():
        return by_day.group_by("slate_size_bucket").agg(
            pl.len().alias("n_days"),
            pl.lit(0).alias("total_bets"),
            pl.lit(0.0).alias("avg_bets_per_day"),
        )

    bets = led.filter(
        pl.col("stake").cast(pl.Float64).fill_null(0.0) > 0
    ).with_columns(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("game_date"))
    bets_by_day = bets.group_by("game_date").agg(pl.len().alias("n_bets"))
    merged = by_day.join(bets_by_day, on="game_date", how="left").with_columns(
        pl.col("n_bets").fill_null(0)
    )
    return (
        merged.group_by("slate_size_bucket")
        .agg(
            pl.len().alias("n_days"),
            pl.col("n_bets").sum().alias("total_bets"),
            pl.col("n_bets").mean().round(3).alias("avg_bets_per_day"),
        )
        .sort("slate_size_bucket")
    )


def main() -> None:
    if not SCORECARD_PATH.exists():
        raise SystemExit(f"Missing {SCORECARD_PATH}. Run results dashboard Section 20 first.")

    score = pl.read_parquet(SCORECARD_PATH).sort("snapshot_utc")
    if score.is_empty():
        raise SystemExit("Scorecard artifact is empty.")

    latest = score.tail(1)
    gate_latest = pl.DataFrame()
    if GATE_PATH.exists():
        gate = pl.read_parquet(GATE_PATH).sort("snapshot_utc")
        if not gate.is_empty():
            gate_latest = gate.tail(1)

    row = {
        "snapshot_utc": datetime.now(timezone.utc).isoformat(),
        "scorecard_snapshots": int(score.height),
        "n_warn_latest": int(latest["n_warn"][0]),
        "mae_err_k_rate_latest": float(latest["mae_err_k_rate"][0]),
        "under_bias_tbf_latest": float(latest["under_bias_tbf"][0]),
        "mae_err_k_rate_change": None,
        "under_bias_tbf_change": None,
        "gate_pnl_delta_latest": None,
    }
    if score.height >= 2:
        prev = score.slice(score.height - 2, 1)
        row["mae_err_k_rate_change"] = float(latest["mae_err_k_rate"][0]) - float(prev["mae_err_k_rate"][0])
        row["under_bias_tbf_change"] = float(latest["under_bias_tbf"][0]) - float(prev["under_bias_tbf"][0])
    if not gate_latest.is_empty() and "gate_pnl_delta" in gate_latest.columns:
        row["gate_pnl_delta_latest"] = (
            float(gate_latest["gate_pnl_delta"][0]) if gate_latest["gate_pnl_delta"][0] is not None else None
        )

    summary = pl.DataFrame([row])
    if OUT_PARQUET.exists():
        hist = pl.read_parquet(OUT_PARQUET)
        out = pl.concat([hist, summary], how="diagonal_relaxed")
    else:
        out = summary
    out.write_parquet(OUT_PARQUET)

    volume = _bet_volume_by_slate_size()
    md_lines = [
        "# Weekly KPI Summary",
        "",
        f"- Snapshot UTC: {row['snapshot_utc']}",
        f"- Latest `n_warn`: {row['n_warn_latest']}",
        f"- Latest `mae_err_k_rate`: {row['mae_err_k_rate_latest']:.4f}",
        f"- Latest `under_bias_tbf`: {row['under_bias_tbf_latest']:.3f}",
        f"- Latest `gate_pnl_delta`: {row['gate_pnl_delta_latest']}",
        "",
        "## Bet Volume by Slate Size",
        "",
        "| Bucket | Days | Total Bets | Avg Bets/Day |",
        "|---|---:|---:|---:|",
    ]
    for r in volume.to_dicts():
        md_lines.append(
            f"| {r['slate_size_bucket']} | {int(r['n_days'])} | "
            f"{int(r['total_bets'])} | {float(r['avg_bets_per_day']):.2f} |"
        )
    OUT_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"wrote {OUT_PARQUET}")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()

