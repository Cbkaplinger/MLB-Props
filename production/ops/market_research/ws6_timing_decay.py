"""WS6 timing-decay — where does the edge live intraday? (post hoc, research).

Same line-points, three book timestamps: friend_open (-12h), book_morning
(-5h), book_close (-5min). Ours (cal) vs each: Brier skill + bias.
Also open->close steam direction vs our error (does steam correct us?).

Writes artifacts/odds_log/ws6_timing_report.json. No live change.
Kill: flat skill across timestamps (timing is not edge; park WS6).
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

from Python.odds_ledger import atomic_write_text  # noqa: E402
from join_keys import ODDS_DIR  # noqa: E402

PANEL = ODDS_DIR / "universe_panel.parquet"


def sk(y, p, b) -> tuple[float, float]:
    return float(np.mean((p - y) ** 2)), float(np.mean((b - y) ** 2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args()
    p = pl.read_parquet(PANEL)
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "stamps": {}}
    cols = {"friend_open": "p_friend_open", "book_morning": "p_book_morning", "book_close": "p_book_close"}
    common = p.filter(pl.col("p_ours_cal").is_not_null() & pl.col("p_friend_open").is_not_null()
                      & pl.col("p_book_morning").is_not_null() & pl.col("p_book_close").is_not_null())
    rep["n_common"] = common.height
    y = common["y"].to_numpy()
    po = common["p_ours_cal"].to_numpy()
    for name, col in cols.items():
        pb = common[col].to_numpy()
        bo, bb = sk(y, po, pb)
        rep["stamps"][name] = {"n": common.height, "brier_ours": bo, "brier_book": bb,
                               "skill": bb - bo,
                               "bias_ours_pp": float(100 * (po.mean() - y.mean())),
                               "bias_book_pp": float(100 * (pb.mean() - y.mean()))}
        print(f"{name}: skill={bb - bo:+.4f} (ours {bo:.4f} book {bb:.4f})")
    # steam test: on points where open->close moved toward outcome, did we already know?
    fo = common["p_friend_open"].to_numpy()
    fc = common["p_book_close"].to_numpy()
    moved_right = np.sign(fc - fo) == np.sign(y - fo)
    err_o = np.abs(po - y)
    rep["steam"] = {"n": int(common.height),
                    "moved_right_rate": float(moved_right.mean()),
                    "our_mae_when_steam_right": float(err_o[moved_right].mean()),
                    "our_mae_when_steam_wrong": float(err_o[~moved_right].mean())}
    print(json.dumps(rep["steam"], indent=1))
    s = [rep["stamps"][k]["skill"] for k in ("friend_open", "book_morning", "book_close")]
    rep["kill"] = "SURVIVE" if max(s) - min(s) > 0.005 else "KILL"
    out = ODDS_DIR / "ws6_timing_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
