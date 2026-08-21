"""Reconcile board recommendations against open-ledger execution rows.

Outputs:
- artifacts/odds_log/board_ledger_reconciliation_latest.json
- artifacts/odds_log/board_ledger_reconciliation_latest.csv
- artifacts/odds_log/board_ledger_reconciliation_history.parquet
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
ODDS_DIR = ROOT / "artifacts" / "odds_log"
REC_PATH = ODDS_DIR / "recommendations.parquet"
LEDGER_PATH = ODDS_DIR / "ledger.parquet"
OUT_JSON = ODDS_DIR / "board_ledger_reconciliation_latest.json"
OUT_CSV = ODDS_DIR / "board_ledger_reconciliation_latest.csv"
OUT_HIST = ODDS_DIR / "board_ledger_reconciliation_history.parquet"


def _safe_int(v: object) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def _reason_counts(df: pl.DataFrame, col: str) -> dict[str, int]:
    if df.is_empty() or col not in df.columns:
        return {}
    out = (
        df.with_columns(pl.col(col).cast(pl.Utf8).fill_null("").alias("_reason"))
        .group_by("_reason")
        .agg(pl.len().alias("n"))
        .sort("n", descending=True)
        .to_dicts()
    )
    return {str(r["_reason"]): int(r["n"]) for r in out if str(r["_reason"]) != ""}


def main() -> None:
    strict = "--no-strict" not in sys.argv
    snap = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not REC_PATH.exists() or not LEDGER_PATH.exists():
        payload = {
            "snapshot_utc": snap,
            "status": "missing_inputs",
            "recommendations_exists": REC_PATH.exists(),
            "ledger_exists": LEDGER_PATH.exists(),
        }
        OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        pl.DataFrame([payload]).write_csv(OUT_CSV)
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_CSV}")
        return

    rec = pl.read_parquet(REC_PATH)
    led = pl.read_parquet(LEDGER_PATH)
    if rec.is_empty() or led.is_empty():
        payload = {
            "snapshot_utc": snap,
            "status": "empty_inputs",
            "recommendations_rows": int(rec.height),
            "ledger_rows": int(led.height),
        }
        OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        pl.DataFrame([payload]).write_csv(OUT_CSV)
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_CSV}")
        return

    rec = rec.with_columns(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gdate"))
    slate = rec.select(pl.col("gdate").max()).item()
    rec_slate = rec.filter(pl.col("gdate") == slate)

    open_led = (
        led.with_columns(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gdate"))
        .filter((pl.col("status") == "open") & (pl.col("gdate") == slate))
    )

    board_bet = rec_slate.filter(pl.col("recommendation") == "BET")
    led_bet = open_led.filter(pl.col("passes_floor") == True)  # noqa: E712
    board_hold = rec_slate.filter(pl.col("recommendation") == "HOLD")
    led_hold = open_led.filter(
        pl.col("note").cast(pl.Utf8).fill_null("").str.contains("hold=", literal=False)
        | pl.col("note").cast(pl.Utf8).fill_null("").str.contains("segment_off", literal=True)
    )

    payload = {
        "snapshot_utc": snap,
        "slate_date": slate,
        "board_rows": int(rec_slate.height),
        "board_bet": int(board_bet.height),
        "board_hold": int(board_hold.height),
        "ledger_open_rows": int(open_led.height),
        "ledger_bet_rows": int(led_bet.height),
        "ledger_hold_rows": int(led_hold.height),
        "bet_delta": int(led_bet.height - board_bet.height),
        "hold_delta": int(led_hold.height - board_hold.height),
        "board_skip_rows": int(rec_slate.filter(pl.col("recommendation") == "skip").height),
        "ledger_skip_like_rows": int(open_led.height - led_bet.height - led_hold.height),
        "board_policy_reason_counts": _reason_counts(rec_slate, "policy_reason"),
        "ledger_note_reason_counts": _reason_counts(open_led, "note"),
    }
    has_delta_alert = bool(payload["bet_delta"] != 0 or payload["hold_delta"] != 0)
    payload["delta_alert"] = has_delta_alert
    payload["delta_alert_level"] = "ERROR" if has_delta_alert else "OK"
    csv_row = dict(payload)
    csv_row["board_policy_reason_counts"] = json.dumps(
        payload["board_policy_reason_counts"], sort_keys=True
    )
    csv_row["ledger_note_reason_counts"] = json.dumps(
        payload["ledger_note_reason_counts"], sort_keys=True
    )

    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    pl.DataFrame([csv_row]).write_csv(OUT_CSV)
    snap_df = pl.DataFrame([csv_row])
    if OUT_HIST.exists():
        hist = pl.read_parquet(OUT_HIST)
        out = pl.concat([hist, snap_df], how="diagonal_relaxed")
    else:
        out = snap_df
    out.write_parquet(OUT_HIST)

    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_CSV}")
    print(f"wrote {OUT_HIST}")
    print(
        "reconciliation:",
        f"slate={slate}",
        f"board_bet={payload['board_bet']}",
        f"ledger_bet={payload['ledger_bet_rows']}",
        f"delta={payload['bet_delta']}",
    )
    if strict and has_delta_alert:
        raise SystemExit(
            "reconciliation_delta_alert: board/ledger bet or hold counts differ"
        )


if __name__ == "__main__":
    main()
