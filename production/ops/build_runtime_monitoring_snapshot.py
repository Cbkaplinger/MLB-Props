"""Build runtime monitoring snapshots for ops/dashboard consumption.

Outputs:
- artifacts/odds_log/runtime_monitoring_snapshot.json
- artifacts/odds_log/runtime_floor_calibration.csv
- artifacts/odds_log/runtime_slippage_by_segment.csv
- artifacts/odds_log/runtime_regime_monthly.csv
- artifacts/odds_log/runtime_edge_deciles.csv
- artifacts/odds_log/runtime_decision_diagnostics.csv
- artifacts/odds_log/runtime_ops_slo_snapshot.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
ODDS_DIR = ROOT / "artifacts" / "odds_log"

LEDGER_PATH = ODDS_DIR / "ledger.parquet"
RECO_PATH = ODDS_DIR / "recommendations.parquet"
LOOP_PATH = ODDS_DIR / "daily_kpi_loop_last_run.json"
LOOP_HIST_PATH = ODDS_DIR / "daily_kpi_step_history.parquet"
WATCHER_LOG_PATH = ODDS_DIR / "close_watcher.log"
AUX_MARKET_PATH = ODDS_DIR / "watcher_aux_markets_latest.json"
AUX_QUOTES_PATH = ODDS_DIR / "watcher_aux_quotes.parquet"
SHADOW_SUMMARY_CSV = ODDS_DIR / "aux_market_shadow_summary.csv"
SHADOW_SUMMARY_JSON = ODDS_DIR / "aux_market_shadow_summary.json"

OUT_SNAPSHOT = ODDS_DIR / "runtime_monitoring_snapshot.json"
OUT_FLOOR = ODDS_DIR / "runtime_floor_calibration.csv"
OUT_SLIP = ODDS_DIR / "runtime_slippage_by_segment.csv"
OUT_MONTH = ODDS_DIR / "runtime_regime_monthly.csv"
OUT_EDGE = ODDS_DIR / "runtime_edge_deciles.csv"
OUT_DECISION = ODDS_DIR / "runtime_decision_diagnostics.csv"
OUT_SLO = ODDS_DIR / "runtime_ops_slo_snapshot.json"


def _safe_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _parse_dt(col: pl.Expr) -> pl.Expr:
    return col.cast(pl.Datetime(time_unit="us", time_zone="UTC"), strict=False)


def _watcher_health(now_utc: datetime) -> dict[str, object]:
    if not WATCHER_LOG_PATH.exists():
        return {
            "watcher_log_exists": False,
            "watcher_last_log_utc": None,
            "watcher_heartbeat_age_minutes": None,
            "watcher_healthy": False,
            "watcher_note": "missing close_watcher.log",
        }
    try:
        lines = WATCHER_LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        lines = []
    last_ts = None
    for line in reversed(lines):
        if len(line) >= 20 and line[4] == "-" and line[10] == "T":
            ts = line[:20]
            try:
                last_ts = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                break
            except Exception:
                continue
    if last_ts is None:
        return {
            "watcher_log_exists": True,
            "watcher_last_log_utc": None,
            "watcher_heartbeat_age_minutes": None,
            "watcher_healthy": False,
            "watcher_note": "log unreadable or empty",
        }
    age_min = (now_utc - last_ts).total_seconds() / 60.0
    out = {
        "watcher_log_exists": True,
        "watcher_last_log_utc": last_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "watcher_heartbeat_age_minutes": round(age_min, 2),
        "watcher_healthy": age_min <= 90.0,
        "watcher_note": "ok" if age_min <= 90.0 else "stale heartbeat",
    }
    aux = _safe_json(AUX_MARKET_PATH)
    if aux:
        out["aux_market_probe"] = aux
    if AUX_QUOTES_PATH.exists():
        try:
            aux_q = pl.read_parquet(AUX_QUOTES_PATH)
            out["aux_quote_history_rows"] = int(aux_q.height)
            if not aux_q.is_empty() and "logged_at_utc" in aux_q.columns:
                out["aux_quote_last_logged_utc"] = str(aux_q["logged_at_utc"][-1])
        except Exception:
            out["aux_quote_history_rows"] = None
    return out


def _compute_floor_table(settled: pl.DataFrame) -> pl.DataFrame:
    if settled.is_empty():
        return pl.DataFrame()
    floor_values = [0.08, 0.10, 0.12, 0.14, 0.16]
    rows: list[dict[str, object]] = []
    for floor in floor_values:
        scoped = settled.filter(pl.col("edge") >= floor)
        if scoped.is_empty():
            continue
        stake = float(scoped["stake"].sum())
        pnl = float(scoped["pnl"].sum())
        roi = (pnl / stake) if stake > 0 else None
        win_rate = float((scoped["pnl"] > 0).mean()) if scoped.height else None
        pos_clv = float((scoped["clv_pp"] > 0).mean()) if ("clv_pp" in scoped.columns and scoped.height) else None
        rows.append(
            {
                "policy_mode": "single_floor",
                "edge_floor": floor,
                "n_bets": int(scoped.height),
                "win_rate": win_rate,
                "roi": roi,
                "pnl": pnl,
                "positive_clv_share": pos_clv,
            }
        )
    dual = settled.filter(
        ((pl.col("side").cast(pl.Utf8).str.to_lowercase() == "over") & (pl.col("edge") >= 0.10))
        | ((pl.col("side").cast(pl.Utf8).str.to_lowercase() == "under") & (pl.col("edge") >= 0.08))
    )
    if not dual.is_empty():
        d_stake = float(dual["stake"].sum())
        d_pnl = float(dual["pnl"].sum())
        rows.append(
            {
                "policy_mode": "dual_side_floor",
                "edge_floor": None,
                "edge_floor_over": 0.10,
                "edge_floor_under": 0.08,
                "n_bets": int(dual.height),
                "win_rate": float((dual["pnl"] > 0).mean()),
                "roi": (d_pnl / d_stake) if d_stake > 0 else None,
                "pnl": d_pnl,
                "positive_clv_share": float((dual["clv_pp"] > 0).mean()) if "clv_pp" in dual.columns else None,
            }
        )
    return pl.DataFrame(rows).sort(["policy_mode", "edge_floor"], descending=[False, False], nulls_last=True)


def _compute_slippage_segments(settled: pl.DataFrame) -> pl.DataFrame:
    req = {"bet_price", "other_price", "close_over", "close_under", "side", "book", "minutes_to_tip_at_open"}
    if settled.is_empty() or not req.issubset(set(settled.columns)):
        return pl.DataFrame()
    scoped = settled.filter(
        pl.col("bet_price").is_not_null()
        & pl.col("other_price").is_not_null()
        & pl.col("close_over").is_not_null()
        & pl.col("close_under").is_not_null()
        & pl.col("side").is_not_null()
    ).with_columns(
        pl.when(pl.col("minutes_to_tip_at_open").cast(pl.Float64) <= 20)
        .then(pl.lit("near_tip"))
        .when(pl.col("minutes_to_tip_at_open").cast(pl.Float64) <= 90)
        .then(pl.lit("mid_window"))
        .otherwise(pl.lit("early_window"))
        .alias("maturity_bucket"),
        pl.when(pl.col("bet_price").cast(pl.Float64).abs() <= 110)
        .then(pl.lit("tight"))
        .when(pl.col("bet_price").cast(pl.Float64).abs() <= 140)
        .then(pl.lit("mid"))
        .otherwise(pl.lit("wide"))
        .alias("odds_bucket"),
        (
            pl.when(pl.col("side").cast(pl.Utf8).str.to_lowercase() == "over")
            .then(pl.col("close_over").cast(pl.Float64) - pl.col("bet_price").cast(pl.Float64))
            .otherwise(pl.col("close_under").cast(pl.Float64) - pl.col("bet_price").cast(pl.Float64))
        ).alias("price_move_to_close"),
    )
    return (
        scoped.group_by(["book", "maturity_bucket", "odds_bucket"])
        .agg(
            pl.len().alias("n"),
            pl.col("price_move_to_close").mean().alias("mean_price_move_to_close"),
            pl.col("price_move_to_close").median().alias("median_price_move_to_close"),
            (pl.col("clv_pp").cast(pl.Float64) > 0).mean().alias("positive_clv_share"),
            (pl.col("pnl").cast(pl.Float64).sum() / pl.col("stake").cast(pl.Float64).sum()).alias("roi"),
        )
        .sort(["n", "book"], descending=[True, False])
    )


def _compute_monthly_regime(settled: pl.DataFrame) -> pl.DataFrame:
    if settled.is_empty():
        return pl.DataFrame()
    return (
        settled.with_columns(
            pl.col("game_date").cast(pl.Utf8).str.slice(0, 7).alias("year_month"),
        )
        .group_by("year_month")
        .agg(
            pl.len().alias("n_bets"),
            (pl.col("pnl").sum() / pl.col("stake").sum()).alias("roi"),
            (pl.col("clv_pp") > 0).mean().alias("positive_clv_share"),
            pl.col("edge").mean().alias("mean_edge"),
            pl.col("pnl").sum().alias("pnl"),
        )
        .sort("year_month")
    )


def _compute_edge_deciles(settled: pl.DataFrame) -> pl.DataFrame:
    if settled.is_empty():
        return pl.DataFrame()
    q = settled.with_columns(
        pl.col("edge").cast(pl.Float64),
        pl.col("edge").qcut(10, labels=[f"d{i}" for i in range(1, 11)]).alias("edge_decile"),
    )
    return (
        q.group_by("edge_decile")
        .agg(
            pl.len().alias("n_bets"),
            pl.col("edge").mean().alias("mean_edge"),
            (pl.col("pnl").sum() / pl.col("stake").sum()).alias("roi"),
            (pl.col("clv_pp") > 0).mean().alias("positive_clv_share"),
            (pl.col("pnl") > 0).mean().alias("hit_rate"),
        )
        .sort("edge_decile")
    )


def _compute_decision_diagnostics(reco: pl.DataFrame, policy_cfg: dict) -> pl.DataFrame:
    if reco.is_empty():
        return pl.DataFrame()
    cols = set(reco.columns)
    need = {"player_name", "line", "book", "edge"}
    if not need.issubset(cols):
        return pl.DataFrame()
    out = reco.with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("game_date"),
        pl.col("edge").cast(pl.Float64),
        pl.when(pl.col("recommendation").cast(pl.Utf8) == "BET")
        .then(pl.lit("BET"))
        .otherwise(pl.lit("NO_BET"))
        .alias("decision"),
        pl.lit(str(policy_cfg.get("king_profile_freeze", {}).get("name", "unknown"))).alias("profile_name"),
        pl.lit(str(policy_cfg.get("king_profile_freeze", {}).get("status", "unknown"))).alias("profile_status"),
    )
    pick_cols = [c for c in ["game_date", "player_name", "book", "line", "best_side", "best_price", "edge", "decision", "oos_reason", "profile_name", "profile_status"] if c in out.columns]
    return out.select(pick_cols).sort(["decision", "edge"], descending=[False, True])


def _compute_ops_slo(now_utc: datetime, ledger: pl.DataFrame) -> dict[str, object]:
    loop = _safe_json(LOOP_PATH)
    hist = pl.read_parquet(LOOP_HIST_PATH) if LOOP_HIST_PATH.exists() else pl.DataFrame()

    out: dict[str, object] = {
        "snapshot_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "daily_loop_last_run_utc": loop.get("ran_utc"),
        "step_duration_p50_sec": {},
        "step_duration_p95_sec": {},
    }
    if not hist.is_empty() and {"step_label", "elapsed_seconds"}.issubset(set(hist.columns)):
        grouped = hist.group_by("step_label").agg(
            pl.col("elapsed_seconds").median().alias("p50"),
            pl.col("elapsed_seconds").quantile(0.95).alias("p95"),
        )
        for r in grouped.to_dicts():
            lbl = str(r["step_label"])
            out["step_duration_p50_sec"][lbl] = float(r["p50"]) if r.get("p50") is not None else None
            out["step_duration_p95_sec"][lbl] = float(r["p95"]) if r.get("p95") is not None else None

    if not ledger.is_empty() and {"logged_at_utc", "event_start_time_utc"}.issubset(set(ledger.columns)):
        l = ledger.with_columns(
            _parse_dt(pl.col("logged_at_utc")).alias("logged_dt"),
            _parse_dt(pl.col("event_start_time_utc")).alias("event_dt"),
        ).filter(pl.col("logged_dt").is_not_null() & pl.col("event_dt").is_not_null())
        if not l.is_empty():
            lag = l.with_columns(
                ((pl.col("event_dt").dt.epoch("s") - pl.col("logged_dt").dt.epoch("s")) / 60.0).alias("lead_minutes")
            )
            out["open_capture_lead_p50_min"] = float(lag["lead_minutes"].median())
            out["open_capture_lead_p95_min"] = float(lag["lead_minutes"].quantile(0.95))

    return out


def main() -> None:
    now_utc = datetime.now(timezone.utc)
    policy_cfg = _safe_json(ROOT / "production" / "ops" / "kpi_policy.json")

    if not LEDGER_PATH.exists():
        OUT_SNAPSHOT.write_text(
            json.dumps(
                {
                    "snapshot_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "status": "missing_ledger",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"wrote {OUT_SNAPSHOT}")
        return

    ledger = pl.read_parquet(LEDGER_PATH)
    settled = (
        ledger.with_columns(
            pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("game_date"),
            pl.col("edge").cast(pl.Float64),
            pl.col("stake").cast(pl.Float64),
            pl.col("pnl").cast(pl.Float64),
            pl.col("side").cast(pl.Utf8),
            pl.col("clv_pp").cast(pl.Float64),
        )
        .filter(
            (pl.col("status").cast(pl.Utf8) == "settled")
            & (pl.col("stake") > 0)
            & (pl.col("game_date") >= "2026-07-31")
        )
    )

    floor_tbl = _compute_floor_table(settled)
    slip_tbl = _compute_slippage_segments(settled)
    month_tbl = _compute_monthly_regime(settled)
    edge_tbl = _compute_edge_deciles(settled)
    reco = pl.read_parquet(RECO_PATH) if RECO_PATH.exists() else pl.DataFrame()
    decision_tbl = _compute_decision_diagnostics(reco, policy_cfg)
    slo = _compute_ops_slo(now_utc, ledger)
    watcher = _watcher_health(now_utc)

    if not floor_tbl.is_empty():
        floor_tbl.write_csv(OUT_FLOOR)
    if not slip_tbl.is_empty():
        slip_tbl.write_csv(OUT_SLIP)
    if not month_tbl.is_empty():
        month_tbl.write_csv(OUT_MONTH)
    if not edge_tbl.is_empty():
        edge_tbl.write_csv(OUT_EDGE)
    if not decision_tbl.is_empty():
        decision_tbl.write_csv(OUT_DECISION)
    OUT_SLO.write_text(json.dumps(slo, indent=2), encoding="utf-8")

    payload = {
        "snapshot_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_start": "2026-07-31",
        "settled_rows": int(settled.height),
        "watcher": watcher,
        "files": {
            "runtime_floor_calibration_csv": str(OUT_FLOOR),
            "runtime_slippage_by_segment_csv": str(OUT_SLIP),
            "runtime_regime_monthly_csv": str(OUT_MONTH),
            "runtime_edge_deciles_csv": str(OUT_EDGE),
            "runtime_decision_diagnostics_csv": str(OUT_DECISION),
            "runtime_ops_slo_snapshot_json": str(OUT_SLO),
            "aux_market_shadow_summary_csv": str(SHADOW_SUMMARY_CSV),
            "aux_market_shadow_summary_json": str(SHADOW_SUMMARY_JSON),
        },
    }
    if SHADOW_SUMMARY_JSON.exists():
        payload["aux_market_shadow"] = _safe_json(SHADOW_SUMMARY_JSON)
    OUT_SNAPSHOT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {OUT_SNAPSHOT}")
    print(f"wrote {OUT_SLO}")
    if not floor_tbl.is_empty():
        print(f"wrote {OUT_FLOOR}")
    if not slip_tbl.is_empty():
        print(f"wrote {OUT_SLIP}")
    if not month_tbl.is_empty():
        print(f"wrote {OUT_MONTH}")
    if not edge_tbl.is_empty():
        print(f"wrote {OUT_EDGE}")
    if not decision_tbl.is_empty():
        print(f"wrote {OUT_DECISION}")


if __name__ == "__main__":
    main()

