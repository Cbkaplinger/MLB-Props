"""Report all-vs-core impact from exit anomaly tags.

Outputs a compact JSON report at:
  artifacts/projection_log/exit_anomaly_impact_report.json
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OVERRIDE_PATH = ROOT / "production" / "ops" / "exit_anomaly_overrides.csv"
MASK_PATH = ROOT / "artifacts" / "projection_log" / "exit_anomaly_training_mask.parquet"
GRADED_PATH = ROOT / "artifacts" / "projection_log" / "graded.parquet"
LEDGER_PATH = ROOT / "artifacts" / "odds_log" / "ledger.parquet"
OUT_PATH = ROOT / "artifacts" / "projection_log" / "exit_anomaly_impact_report.json"
ANOMALY_RATE_WARN = 0.05


def _regression_metrics(df: pl.DataFrame) -> dict[str, float | int | None]:
    if df.is_empty():
        return {"n": 0, "mae": None, "rmse": None, "r2": None}
    y = df["actual_K"].cast(pl.Float64)
    yhat = df["expected_K"].cast(pl.Float64)
    err = yhat - y
    mae = float(err.abs().mean())
    rmse = float((err.pow(2).mean()) ** 0.5)
    ybar = float(y.mean())
    ss_res = float(err.pow(2).sum())
    ss_tot = float((y - ybar).pow(2).sum())
    r2 = None if ss_tot == 0 else float(1.0 - (ss_res / ss_tot))
    return {"n": int(df.height), "mae": mae, "rmse": rmse, "r2": r2}


def _settled_metrics(df: pl.DataFrame) -> dict[str, float | int | None]:
    if df.is_empty():
        return {"n": 0, "stake": 0.0, "pnl": 0.0, "roi": None, "mean_clv_pp": None}
    stake = float(df["stake"].cast(pl.Float64).sum())
    pnl = float(df["pnl"].cast(pl.Float64).sum())
    roi = None if stake == 0.0 else pnl / stake
    clv = float(df["clv_pp"].cast(pl.Float64).mean()) if "clv_pp" in df.columns else None
    return {
        "n": int(df.height),
        "stake": stake,
        "pnl": pnl,
        "roi": roi,
        "mean_clv_pp": clv,
    }


def _delta(all_m: dict, core_m: dict) -> dict:
    out: dict[str, float | int | None] = {}
    for k, v in all_m.items():
        cv = core_m.get(k)
        if isinstance(v, (int, float)) and isinstance(cv, (int, float)):
            out[f"{k}_delta_core_minus_all"] = float(cv) - float(v)
    return out


def _filter_last_n_days(df: pl.DataFrame, col: str, n_days: int) -> pl.DataFrame:
    if col not in df.columns or n_days <= 0:
        return df
    max_d = df.select(pl.col(col).str.to_date(strict=False).max()).item()
    if max_d is None:
        return df
    start_d = max_d - timedelta(days=n_days - 1)
    return df.filter(pl.col(col).str.to_date(strict=False) >= pl.lit(start_d))


def main() -> None:
    if not OVERRIDE_PATH.exists() or not MASK_PATH.exists():
        raise FileNotFoundError("Missing override/mask artifacts; build them first.")

    overrides = pl.read_csv(OVERRIDE_PATH).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10),
        pl.col("game_pk").cast(pl.Int64, strict=False),
        pl.col("pitcher").cast(pl.Int64, strict=False),
    )
    mask = pl.read_parquet(MASK_PATH).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10),
        pl.col("game_pk").cast(pl.Int64, strict=False),
        pl.col("pitcher").cast(pl.Int64, strict=False),
        pl.col("exit_anomaly_flag").fill_null(False).cast(pl.Boolean),
    )
    keys = ["game_pk", "pitcher", "game_date"]
    anomaly_keys = mask.filter(pl.col("exit_anomaly_flag")).select(keys).unique()

    graded = pl.read_parquet(GRADED_PATH).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10)
    )
    graded_keys = graded.select(keys).unique()
    graded = graded.join(
        anomaly_keys.with_columns(pl.lit(True).alias("exit_anomaly_flag")),
        on=keys,
        how="left",
    ).with_columns(pl.col("exit_anomaly_flag").fill_null(False))
    graded = graded.filter(
        pl.col("actual_K").is_not_null() & pl.col("expected_K").is_not_null()
    )

    ledger = pl.read_parquet(LEDGER_PATH).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10)
    )
    settled = ledger.filter((pl.col("status") == "settled") & (pl.col("stake").fill_null(0) > 0))
    settled = settled.join(
        anomaly_keys.with_columns(pl.lit(True).alias("exit_anomaly_flag")),
        on=keys,
        how="left",
    ).with_columns(pl.col("exit_anomaly_flag").fill_null(False))

    windows = {"all": 0, "last_30d": 30, "last_7d": 7}
    graded_report: dict[str, dict] = {}
    settled_report: dict[str, dict] = {}

    for label, ndays in windows.items():
        g_src = _filter_last_n_days(graded, "game_date", ndays)
        s_src = _filter_last_n_days(settled, "game_date", ndays)

        g_all = _regression_metrics(g_src)
        g_core = _regression_metrics(g_src.filter(~pl.col("exit_anomaly_flag")))
        graded_report[label] = {"all": g_all, "core": g_core, "delta": _delta(g_all, g_core)}

        s_all = _settled_metrics(s_src)
        s_core = _settled_metrics(s_src.filter(~pl.col("exit_anomaly_flag")))
        settled_report[label] = {"all": s_all, "core": s_core, "delta": _delta(s_all, s_core)}

    report = {
        "as_of": date.today().isoformat(),
        "override_rows": int(overrides.height),
        "override_breakdown": (
            overrides.group_by(
                ["exit_anomaly_type", "exit_anomaly_confidence", "exit_anomaly_source"]
            )
            .agg(pl.len().alias("n"))
            .sort("n", descending=True)
            .to_dicts()
        ),
        "mask_counts": (
            mask.group_by("include_for_training")
            .agg(pl.len().alias("n"))
            .sort("include_for_training")
            .to_dicts()
        ),
        "graded_impact": graded_report,
        "settled_impact": settled_report,
    }
    unmatched = overrides.join(graded_keys, on=keys, how="anti")
    mask_counts = {str(r["include_for_training"]).lower(): int(r["n"]) for r in report["mask_counts"]}
    excluded_n = int(mask_counts.get("false", 0))
    total_n = excluded_n + int(mask_counts.get("true", 0))
    anomaly_rate = float(excluded_n / total_n) if total_n else 0.0
    status_reasons: list[str] = []
    if unmatched.height > 0:
        status_reasons.append(f"unmatched_override_rows={unmatched.height}")
    if anomaly_rate >= ANOMALY_RATE_WARN:
        status_reasons.append(f"anomaly_rate {anomaly_rate:.2%} >= {ANOMALY_RATE_WARN:.2%}")
    report["quality_checks"] = {
        "status": "WARN" if status_reasons else "PASS",
        "status_reasons": status_reasons,
        "unmatched_override_rows": int(unmatched.height),
        "excluded_rows": excluded_n,
        "total_rows": total_n,
        "anomaly_rate": anomaly_rate,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print(json.dumps(report["graded_impact"]["all"], indent=2))
    print(json.dumps(report["settled_impact"]["all"], indent=2))


if __name__ == "__main__":
    main()
