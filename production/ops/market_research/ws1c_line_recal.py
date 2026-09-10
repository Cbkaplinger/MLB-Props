"""WS1c per-line mean correction (post hoc, research).

Bins first, calibrate second: per-line Platt maps (reuse prob_calibration.fit_platt)
fit on universe TRAIN dates, evaluated on HELD-OUT dates vs raw / live-isotonic /
book-close. Direct answer to the monotonic line-bias (+4.8pp @2.5 -> -14.5pp @9.5)
and isotonic losses at 5.5/6.5.

Writes artifacts/odds_log/ws1c_report.json. No live change.
Kill: no held-out Brier gain vs live-isotonic (keep bundle).
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
from Python.prob_calibration import expected_calibration_error, fit_platt  # noqa: E402
from join_keys import ODDS_DIR  # noqa: E402

PANEL = ODDS_DIR / "universe_panel.parquet"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train-frac", type=float, default=0.7)
    args = ap.parse_args()

    p = pl.read_parquet(PANEL).filter(
        pl.col("p_ours").is_not_null() & pl.col("p_ours_cal").is_not_null()
        & pl.col("p_book_close").is_not_null()).sort("gd")
    dates = sorted(set(p["gd"].to_list()))
    cut = dates[int(len(dates) * args.train_frac)]
    tr, te = p.filter(pl.col("gd") <= cut), p.filter(pl.col("gd") > cut)
    print(f"train {tr.height} / test {te.height} points, cut {cut}")

    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(),
                 "cut": cut, "per_line": []}
    for ln in LINES:
        strn, ste = tr.filter(pl.col("line") == ln), te.filter(pl.col("line") == ln)
        if strn.height < 200 or ste.height < 50:
            continue
        cal = fit_platt(strn["p_ours"].to_numpy(), strn["y"].to_numpy())
        y = ste["y"].to_numpy()
        preds = {"raw": ste["p_ours"].to_numpy(), "isotonic": ste["p_ours_cal"].to_numpy(),
                 "ws1c": cal.transform(ste["p_ours"].to_numpy()),
                 "book": ste["p_book_close"].to_numpy()}
        entry: dict = {"line": ln, "n_train": strn.height, "n_test": ste.height,
                       "platt_a": cal.platt_a, "platt_b": cal.platt_b}
        for name, pr in preds.items():
            entry[name] = {"brier": float(np.mean((pr - y) ** 2))}
        e, _ = expected_calibration_error(y, preds["ws1c"])
        entry["ws1c"]["ece"] = float(e)
        rep["per_line"].append(entry)
        print("line=%.1f nte=%d raw=%.4f iso=%.4f ws1c=%.4f book=%.4f (a=%.2f b=%+.2f)" % (
            ln, ste.height, entry["raw"]["brier"], entry["isotonic"]["brier"],
            entry["ws1c"]["brier"], entry["book"]["brier"], cal.platt_a or 0, cal.platt_b or 0))
    keys = ["raw", "isotonic", "ws1c", "book"]
    means = {k: float(np.mean([e[k]["brier"] for e in rep["per_line"]])) for k in keys}
    rep["means"] = means
    print(means)
    rep["kill"] = ("SURVIVE-challenger" if means["ws1c"] < means["isotonic"] - 0.0005
                   else "KILL-keep-bundle")
    out = ODDS_DIR / "ws1c_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
