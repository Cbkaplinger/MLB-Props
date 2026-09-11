"""Ship-lift compare: frozen universe panel vs live-config rescore (post hoc).

Common-subset (gd, key, line) compare of p_ours_cal frozen (binomial raw +
isotonic cal, pre-ships) vs live (poisson + WS1c-Platt). Same book closes.
MEASUREMENT ONLY per #80 contract: no kill, evidence for ship-lift at scale
+ fresh per-line cells for the offseason program.

Writes artifacts/odds_log/rescore_shiplift_report.json. No live change.
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

from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.prob_calibration import expected_calibration_error  # noqa: E402
from join_keys import ODDS_DIR  # noqa: E402

FROZEN = ODDS_DIR / "universe_panel.parquet"
LIVE = ODDS_DIR / "universe_panel_live.parquet"


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    fz = pl.read_parquet(FROZEN).select(
        ["gd", "key", "line", "y", "expected_K", "p_ours_cal", "p_book_close"])
    lv = pl.read_parquet(LIVE).select(
        ["gd", "key", "line", "p_ours_cal", "p_book_close"])
    print(f"frozen rows {fz.height} / live rows {lv.height}")
    j = fz.join(lv, on=["gd", "key", "line"], how="inner",
                suffix="_live").filter(
        pl.col("p_ours_cal").is_not_null()
        & pl.col("p_ours_cal_live").is_not_null()
        & pl.col("y").is_not_null())
    print(f"common subset (any): {j.height}")
    jm = j.filter(pl.col("p_book_close").is_not_null())
    print(f"common subset (close-matched): {jm.height}")

    def arm(d: pl.DataFrame, col: str) -> dict:
        y = d["y"].to_numpy().astype(float)
        p = d[col].to_numpy().astype(float)
        out = {"n": int(d.height), "brier": brier(p, y)}
        e, _ = expected_calibration_error(y, p)
        out["ece"] = float(e)
        return out

    rep: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_common_any": int(j.height),
        "n_common_close": int(jm.height),
        "pooled_any": {"frozen": arm(j, "p_ours_cal"),
                       "live": arm(j, "p_ours_cal_live")},
        "pooled_close": {"frozen": arm(jm, "p_ours_cal"),
                         "live": arm(jm, "p_ours_cal_live"),
                         "book": arm(jm, "p_book_close")},
    }
    for name, d in (("any", j), ("close", jm)):
        pf = rep[f"pooled_{name}"]["frozen"]["brier"]
        plv = rep[f"pooled_{name}"]["live"]["brier"]
        rep[f"pooled_{name}"]["shiplift"] = float(pf - plv)
    cells = []
    for ln in sorted(set(jm["line"].to_list())):
        sub = jm.filter(pl.col("line") == ln)
        y = sub["y"].to_numpy().astype(float)
        cells.append({"line": float(ln), "n": int(sub.height),
                      "brier_frozen": brier(sub["p_ours_cal"].to_numpy().astype(float), y),
                      "brier_live": brier(sub["p_ours_cal_live"].to_numpy().astype(float), y),
                      "brier_book": brier(sub["p_book_close"].to_numpy().astype(float), y)})
    rep["per_line_close"] = cells
    rep["cells_sum_n"] = int(sum(c["n"] for c in cells))
    out = ODDS_DIR / "rescore_shiplift_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(json.dumps({"n_common_any": rep["n_common_any"],
                      "n_common_close": rep["n_common_close"],
                      "pooled_any": rep["pooled_any"],
                      "pooled_close": rep["pooled_close"]}, indent=2))
    print(f"cells_sum_n={rep['cells_sum_n']} (must equal n_common_close)")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
