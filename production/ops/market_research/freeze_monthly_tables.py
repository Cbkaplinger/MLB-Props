"""Freeze rule-versioned monthly grading tables (offseason audit, no live change).

Recomputes family-graded monthly tables from the ledger with the CURRENT
dedupe rule stamped as the rule version, so future rule changes never
silently rewrite history. Writes versioned JSON + parquet snapshots.

Usage:
  python production/ops/market_research/freeze_monthly_tables.py [--ledger PATH] [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from Python.odds_ledger import (  # noqa: E402
    dedupe_ledger_props,
    settled_bets,
)

RULE_VERSION = "family-earliest-v1"


def month_table(frame: pl.DataFrame, month: str) -> dict:
    sub = frame.filter(pl.col("game_date").cast(pl.Utf8).str.slice(0, 7) == month)
    if sub.is_empty():
        return {"month": month, "n": 0}
    pnl = float(sub["pnl"].fill_null(0.0).sum())
    stake = float(sub["stake"].fill_null(0.0).sum())
    out: dict = {"month": month, "n": int(sub.height),
                 "stake": round(stake, 2), "pnl": round(pnl, 2),
                 "roi": round(pnl / stake, 4) if stake else None,
                 "wr": round(float((sub["result"] == "win").mean()), 4)
                 if "result" in sub.columns else None}
    for dim in ("side", "book", "line"):
        if dim in sub.columns:
            out[f"by_{dim}"] = [
                {"k": str(r[dim]), "n": int(r["len"]),
                 "pnl": round(float(r["pnl"]), 2)}
                for r in sub.group_by(dim).agg(
                    pl.len().alias("len"),
                    pl.col("pnl").fill_null(0.0).sum().alias("pnl")
                ).sort(dim).to_dicts()]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", default="")
    ap.add_argument("--out-dir", default="")
    args = ap.parse_args()
    from Python.odds_ledger import LEDGER_PATH  # noqa: E402

    ledger = pl.read_parquet(args.ledger) if args.ledger else pl.read_parquet(LEDGER_PATH)
    graded = dedupe_ledger_props(
        settled_bets(ledger).filter(pl.col("stake").fill_null(0.0) > 0))
    months = sorted({str(d)[:7] for d in graded["game_date"].cast(pl.Utf8).to_list()})
    out_dir = Path(args.out_dir) if args.out_dir else (
        ROOT / "artifacts" / "odds_log")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    tables = [month_table(graded, m) for m in months]
    payload = {"rule_version": RULE_VERSION, "built_utc": datetime.now(timezone.utc).isoformat(),
               "ledger_rows": int(ledger.height),
               "graded_slips": int(graded.height), "months": tables}
    blob = json.dumps(payload, indent=1, default=str)
    sha = hashlib.sha256(blob.encode()).hexdigest()[:12]
    path = out_dir / f"monthly_tables_{RULE_VERSION}_{stamp}_{sha}.json"
    path.write_text(blob, encoding="utf-8")
    frame = pl.DataFrame([{"month": t["month"], "n": t["n"],
                           "pnl": t.get("pnl"), "roi": t.get("roi")}
                          for t in tables])
    frame.write_parquet(out_dir / f"monthly_tables_{RULE_VERSION}_{stamp}_{sha}.parquet")
    print(f"froze {len(tables)} months -> {path.name} (sha {sha})")
    for t in tables:
        print(f"  {t['month']}: n={t['n']} pnl={t.get('pnl')} roi={t.get('roi')}")


if __name__ == "__main__":
    main()
