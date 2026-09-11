"""Deploy-matrix regate: re-derive ON/OFF states on post-freeze data.

The live deploy matrix (calibration_deploy_matrix.parquet, 24d old, fit
window undated) gates live tickets OFF by (line, price-bucket, maturity)
— it held Fried/Jones to skip today. This re-measures per-segment Brier
gain (live offset arm vs raw arm, #85 inversion method) on the bettable
panel and recommends states. MEASUREMENT ONLY (#95): acting needs sign-off.

Recommend ON iff segment Brier gain >= 0.0005 AND n >= 30, else OFF
(UNRATED when n < 30). Churn vs current 14-ON states reported.

Writes artifacts/odds_log/deploy_regate_report.json. No live change.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.odds_board import (  # noqa: E402
    _load_line_price_offsets,
    _maturity_bucket,
    _price_bucket,
)
from Python.odds_ledger import atomic_write_text  # noqa: E402
from join_keys import ODDS_DIR, read_consensus_cache, sorted_key  # noqa: E402

LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
MATRIX = ODDS_DIR / "calibration_deploy_matrix.parquet"
MIN_N = 30
BAR = 0.0005


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    offsets = _load_line_price_offsets()
    mx = pl.read_parquet(MATRIX).select(
        ["line", "over_price_bucket", "maturity_bucket", "deploy_state"])
    cur = {(float(r["line"]), str(r["over_price_bucket"]), str(r["maturity_bucket"])):
           str(r["deploy_state"]) for r in mx.to_dicts()}
    n_on = sum(1 for v in cur.values() if v == "ON")
    print(f"matrix segments={len(cur)} currently ON={n_on}")

    cc = read_consensus_cache("pitcher_strikeouts", "close").filter(
        (pl.col("n_books") >= 2) & pl.col("fair").is_not_null())
    led = pl.read_parquet(ODDS_DIR / "ledger.parquet").filter(
        (pl.col("status") == "settled") & pl.col("settle_value").is_not_null()).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gd"),
        pl.col("player_name").map_elements(
            lambda s: sorted_key(str(s)), return_dtype=pl.Utf8).alias("key"))
    led = led.drop([c for c in ("close_over", "close_under", "close_status",
                                "closed_at_utc", "minutes_to_tip_at_close")
                    if c in led.columns])
    j = led.join(cc.select(["gd", "key", "line", "fair"]).rename({"fair": "close_over"}),
                 on=["gd", "key", "line"], how="inner")
    jj = j.filter(pl.col("p_model").is_not_null()
                  & pl.col("over_price").is_not_null()
                  & pl.col("line").is_in(LINES))
    print(f"gated panel: {jj.height}")

    segs: dict[tuple, dict] = {}
    for r in jj.to_dicts():
        ln = float(r["line"])
        side = str(r["side"])
        y_over = 1.0 if float(r["settle_value"]) > ln else 0.0
        stored = float(r["p_model"])
        lo = stored if side == "over" else 1.0 - stored
        op = float(r["over_price"])
        key = (ln, _price_bucket(op),
               _maturity_bucket({"game_date": r.get("game_date"),
                                 "player_name": str(r.get("player_name"))}))
        off = float(offsets.get(key, offsets.get((ln, _price_bucket(op), "*"), 0.0)))
        bo = float(np.clip(lo - off, 1e-6, 1.0 - 1e-6))
        y = y_over if side == "over" else 1.0 - y_over
        p_raw = bo if side == "over" else 1.0 - bo
        p_live = lo if side == "over" else 1.0 - lo
        s = segs.setdefault(key, {"n": 0, "se_raw": 0.0, "se_live": 0.0})
        s["n"] += 1
        s["se_raw"] += (p_raw - y) ** 2
        s["se_live"] += (p_live - y) ** 2
    rows = []
    flips = 0
    for key, s in sorted(segs.items(), key=lambda kv: -kv[1]["n"]):
        gain = (s["se_raw"] - s["se_live"]) / s["n"]
        rec = ("UNRATED" if s["n"] < MIN_N
               else ("ON" if gain >= BAR else "OFF"))
        now = cur.get(key, "ABSENT")
        if rec in ("ON", "OFF") and now in ("ON", "OFF") and rec != now:
            flips += 1
        rows.append({"line": key[0], "bucket": key[1], "maturity": key[2],
                     "n": s["n"], "brier_raw": s["se_raw"] / s["n"],
                     "brier_live": s["se_live"] / s["n"], "gain": gain,
                     "current": now, "recommended": rec})
    rated = [x for x in rows if x["recommended"] in ("ON", "OFF")]
    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "n": int(jj.height), "segments": rows,
           "rated_segments": len(rated), "flips_vs_current": flips,
           "recommend_on": sum(1 for x in rated if x["recommended"] == "ON"),
           "recommend_off": sum(1 for x in rated if x["recommended"] == "OFF"),
           "unrated_thin": sum(1 for x in rows if x["recommended"] == "UNRATED")}
    out = ODDS_DIR / "deploy_regate_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"n={rep['n']} rated={rep['rated_segments']} on={rep['recommend_on']} "
          f"off={rep['recommend_off']} thin={rep['unrated_thin']} flips={flips}")
    for x in rows[:15]:
        print("  line=%.1f %-16s %-12s n=%4d gain=%+.5f cur=%-6s rec=%s" % (
            x["line"], x["bucket"], x["maturity"], x["n"], x["gain"],
            x["current"], x["recommended"]))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
