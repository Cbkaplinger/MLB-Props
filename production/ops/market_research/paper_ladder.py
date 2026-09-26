"""Paper ladder tracker v1: rung feasibility from RESULTS (research, no live change).

Owner 2026-09-24: the ladder question is feasibility, not pipeline. No model
changes, no ingestion changes, no board changes. Answer with settled history:
for every taken BET, which neighboring rungs existed on Kalshi and how often
would they have hit? Compare hit rates against breakeven prices (+150 → 40%,
+200 → 33.3%, +300 → 25%) — if alt rungs can't clear breakeven on RESULTS
alone, no pricing model saves them.

Inputs: cloud/local ledger (settled, staked, family-deduped) + Kalshi
  k_ladder history (rung/result per game; prices IGNORED v1 — provenance
  murky, results are facts).
Method: for each taken BET (player, line, side, actual K), map Kalshi rungs
  at line±1 and line±2 (rung N = over N-0.5); rung hits if actual clears it
  on the bet side. Coverage = share of BETs with ≥1 mapped rung.
Writes: artifacts/odds_log/paper_ladder_report.json.

Usage:
  python production/ops/market_research/paper_ladder.py [--ledger PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
K_LADDER = ROOT / "data" / "Odds-Historical" / "kalshi" / "k_ladder.parquet"
OUT = ROOT / "artifacts" / "odds_log" / "paper_ladder_report.json"

BREAKEVEN = {"+150": 0.40, "+200": 1.0 / 3.0, "+300": 0.25, "+400": 0.20}


def _norm(name: object) -> str:
    s = " ".join(str(name or "").lower().split())
    if "," in s:
        last, _, first = s.partition(",")
        s = f"{first.strip()} {last.strip()}".strip()
    return s


def rung_hits(actual_k: float, line: float, side: str) -> bool:
    """Did rung `line` (over line) hit for side, given actual Ks."""
    return (actual_k > line) if side == "over" else (actual_k < line)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", default="",
                    help="Ledger parquet (default: live ledger path).")
    args = ap.parse_args()
    from Python.odds_ledger import (  # noqa: E402
        LEDGER_PATH, dedupe_ledger_props, settled_bets)

    ledger = pl.read_parquet(args.ledger) if args.ledger else pl.read_parquet(LEDGER_PATH)
    bets = dedupe_ledger_props(
        settled_bets(ledger).filter(pl.col("stake").fill_null(0.0) > 0))
    ladder = pl.scan_parquet(K_LADDER).select(
        ["game_date", "player_norm", "rung"]).collect()
    ladder = ladder.with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gd"),
        (pl.col("rung").cast(pl.Float64) - 0.5).alias("line"))

    n_bets, covered, rungs = 0, 0, {}
    for r in bets.to_dicts():
        try:
            actual = float(r["settle_strikeouts"])
            line = float(r["line"])
        except (TypeError, ValueError, KeyError):
            continue
        side = str(r.get("side") or "").lower()
        if side not in ("over", "under"):
            continue
        n_bets += 1
        key = _norm(r.get("player_name"))
        gd = str(r.get("game_date") or "")[:10]
        alt_lines = [line - 2.0, line - 1.0, line + 1.0, line + 2.0]
        rows = ladder.filter(
            (pl.col("gd") == gd)
            & (pl.col("player_norm").map_elements(
                _norm, return_dtype=pl.Utf8) == key)
            & (pl.col("line").is_in(alt_lines)))
        if rows.is_empty():
            continue
        covered += 1
        for lr in rows.to_dicts():
            slot = "up" if float(lr["line"]) > line else "down"
            hit = rung_hits(actual, float(lr["line"]), side)
            cell = rungs.setdefault(f"{side}/{slot}", {"n": 0, "hits": 0})
            cell["n"] += 1
            cell["hits"] += int(hit)
    summary = {}
    for cell, v in sorted(rungs.items()):
        rate = v["hits"] / v["n"] if v["n"] else 0.0
        summary[cell] = {"n": v["n"], "hits": v["hits"],
                         "hit_rate": round(rate, 4),
                         "beats_+150": bool(rate >= BREAKEVEN["+150"]),
                         "beats_+200": bool(rate >= BREAKEVEN["+200"])}
    rep = {"built": "paper_ladder v1", "n_bets": n_bets,
           "coverage": round(covered / max(n_bets, 1), 4), "rungs": summary}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=2, default=str))
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
