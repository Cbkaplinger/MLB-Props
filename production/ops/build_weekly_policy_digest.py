"""Build weekly policy digest artifact for quick review."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
ODDS_DIR = ROOT / "artifacts" / "odds_log"
OUT_JSON = ODDS_DIR / "weekly_policy_digest_latest.json"


def _load_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    return pl.read_csv(path)


def main() -> None:
    floor = _load_csv(ODDS_DIR / "runtime_floor_calibration.csv")
    month = _load_csv(ODDS_DIR / "runtime_regime_monthly.csv")
    decile = _load_csv(ODDS_DIR / "runtime_edge_deciles.csv")

    payload: dict[str, object] = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {},
        "tables": {},
    }

    if not floor.is_empty():
        best = floor.filter(pl.col("policy_mode") == "single_floor").sort("roi", descending=True).head(1)
        payload["summary"]["best_single_floor"] = best.to_dicts()[0] if not best.is_empty() else None
        payload["tables"]["floor_calibration"] = floor.to_dicts()

    if not month.is_empty():
        tail = month.sort("year_month").tail(3)
        payload["summary"]["recent_months"] = tail.to_dicts()
        payload["tables"]["monthly_regime"] = month.to_dicts()

    if not decile.is_empty():
        payload["summary"]["top_edge_decile"] = decile.sort("mean_edge", descending=True).head(1).to_dicts()[0]
        payload["tables"]["edge_deciles"] = decile.to_dicts()

    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()

