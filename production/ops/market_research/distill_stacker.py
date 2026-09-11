"""Distillation stacker v1 (post hoc, research, shadow only).

The only unbuilt learn-from-books idea (#72 brief): morning consensus as
teacher, but fit to OUTCOMES (not to the teacher) so the student can beat
the book instead of becoming it. A 4-param logistic overlay
  logit(p) = b0 + b1*logit(p_model) + b2*logit(p_cons_morning) + b3*line
fit on universe TRAIN dates, judged on HELD-OUT dates.

Why this is not WS1-redux: WS1's linear blend (w=0, pure consensus) wins
Brier by surrendering edge (CLV~0 minus vig). The stacker instead asks
whether model + morning-consensus jointly predict outcomes better than
EITHER alone — conditional trust (e.g. consensus mid-curve, model tails).

Vehicle discipline (#66 closure respected): overlay only — no retrain, no
live change, no bundle. Same vehicle class as the kadj overlay (#62).

Panel: universe_panel main-morning-matched rows (p_book_morning not null,
SOP main-vs-alt rule). Frozen-config caveat: p_ours_cal is isotonic-era
(pre-Poisson/WS1c ships); judged as the model arm regardless, same subset.

Writes artifacts/odds_log/distill_stacker_report.json. No live change.
KILL: no held-out Brier gain >= 0.0005 vs BOTH model and morning-consensus.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.prob_calibration import expected_calibration_error  # noqa: E402
from join_keys import ODDS_DIR  # noqa: E402

PANEL = ODDS_DIR / "universe_panel.parquet"
EPS = 1e-4
BAR = 0.0005


def logit(p: np.ndarray) -> np.ndarray:
    pc = np.clip(p, EPS, 1.0 - EPS)
    return np.log(pc / (1.0 - pc))


def expit(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train-frac", type=float, default=0.7)
    args = ap.parse_args()

    df = (
        pl.read_parquet(PANEL)
        .filter(
            pl.col("p_ours_cal").is_not_null()
            & pl.col("p_book_morning").is_not_null()
            & pl.col("y").is_not_null()
        )
        .sort("gd")
    )
    dates = sorted(set(df["gd"].to_list()))
    cut = dates[int(len(dates) * args.train_frac)]
    tr = df.filter(pl.col("gd") <= cut)
    te = df.filter(pl.col("gd") > cut)

    def feats(d: pl.DataFrame) -> np.ndarray:
        return np.column_stack(
            [
                logit(d["p_ours_cal"].to_numpy()),
                logit(d["p_book_morning"].to_numpy()),
                d["line"].to_numpy().astype(float),
            ]
        )

    Xtr, ytr = feats(tr), tr["y"].to_numpy().astype(float)
    Xte, yte = feats(te), te["y"].to_numpy().astype(float)
    pm_te = tr.shape  # placeholder to fail loud if misused below
    del pm_te

    clf = LogisticRegression(C=1.0, solver="lbfgs")
    clf.fit(Xtr, ytr)
    p_stack = clf.predict_proba(Xte)[:, 1]
    p_model = te["p_ours_cal"].to_numpy().astype(float)
    p_morn = te["p_book_morning"].to_numpy().astype(float)

    has_close = te["p_book_close"].is_not_null().to_numpy()
    p_close = te["p_book_close"].to_numpy().astype(float)

    rep: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n": df.height,
        "n_train": tr.height,
        "n_test": te.height,
        "cut": cut,
        "dates": [dates[0], dates[-1]],
        "coef": {"b0": float(clf.intercept_[0]), "b1_model": float(clf.coef_[0][0]),
                 "b2_morn": float(clf.coef_[0][1]), "b3_line": float(clf.coef_[0][2])},
        "held_out": {
            "brier_model": brier(p_model, yte),
            "brier_morning_cons": brier(p_morn, yte),
            "brier_stacker": brier(p_stack, yte),
        },
        "frozen_config_note": ("p_ours_cal is isotonic-era (pre-Poisson/WS1c ships); "
                               "all arms scored on the same subset regardless."),
    }
    h = rep["held_out"]
    h["gain_vs_model"] = h["brier_model"] - h["brier_stacker"]
    h["gain_vs_morning"] = h["brier_morning_cons"] - h["brier_stacker"]
    if int(has_close.sum()) > 100:
        mc = has_close
        rep["reference_close_oracle"] = {
            "n": int(mc.sum()),
            "brier_close": brier(p_close[mc], yte[mc]),
            "brier_stacker_same_subset": brier(p_stack[mc], yte[mc]),
        }
    e_mod, _ = expected_calibration_error(yte, p_model)
    e_morn, _ = expected_calibration_error(yte, p_morn)
    e_stack, _ = expected_calibration_error(yte, p_stack)
    rep["held_out"].update(
        {"ece_model": float(e_mod), "ece_morning": float(e_morn), "ece_stacker": float(e_stack)}
    )

    # Per-line cells (must sum to n_test — #62 lesson).
    cells = []
    for ln in sorted(set(te["line"].to_list())):
        sub = te.filter(pl.col("line") == ln)
        ys = sub["y"].to_numpy().astype(float)
        idx = np.where(te["line"].to_numpy() == ln)[0]
        cells.append(
            {
                "line": float(ln),
                "n": int(sub.height),
                "brier_model": brier(p_model[idx], ys),
                "brier_morning": brier(p_morn[idx], ys),
                "brier_stacker": brier(p_stack[idx], ys),
            }
        )
    rep["per_line"] = cells
    rep["cells_sum_n"] = int(sum(c["n"] for c in cells))

    # Descriptive guardrails (not gates): how much idiosyncrasy survives,
    # and implied shadow-edge beat-close (descriptive until fills, #21).
    rep["descriptive"] = {
        "mean_abs_stacker_minus_morning": float(np.mean(np.abs(p_stack - p_morn))),
        "mean_abs_stacker_minus_model": float(np.mean(np.abs(p_stack - p_model))),
    }

    survives = (h["gain_vs_model"] >= BAR) and (h["gain_vs_morning"] >= BAR)
    rep["kill"] = "SURVIVE-challenger" if survives else "KILL"
    out = ODDS_DIR / "distill_stacker_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(json.dumps({"n": rep["n"], "n_train": rep["n_train"], "n_test": rep["n_test"],
                      "cut": cut, "coef": rep["coef"], "held_out": h,
                      "kill": rep["kill"]}, indent=2))
    print(f"cells_sum_n={rep['cells_sum_n']} (must equal n_test={rep['n_test']})")
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
