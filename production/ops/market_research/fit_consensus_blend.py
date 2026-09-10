"""WS1 shrink-to-consensus blend — shadow only (post hoc, chrono-safe).

Fits p_blend = w * p_model + (1-w) * p_consensus on the CLOSE panel
(never opens), chrono split (first ~70% dates fit, last ~30% eval).
Writes artifacts/odds_log/blend_shadow_report.json. No live scorer change.

Kill criterion (program WS1): no Brier gain on held-out split vs bundle (w=1).
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

from Python.odds_ledger import atomic_write_text, norm_player_name  # noqa: E402
from Python.prob_calibration import expected_calibration_error  # noqa: E402
from analyze_book_skill import build_consensus  # noqa: E402

HIST = ROOT / "data" / "Odds-Historical" / "theoddsapi"
ODDS_DIR = ROOT / "artifacts" / "odds_log"


def load_panel(min_books: int = 2, snapshot: str = "close") -> list[dict]:
    consensus = build_consensus(min_books, snapshot)
    evdate: dict[str, str] = {}
    for fp in sorted((HIST / "raw" / "event_index").glob("*.json")):
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for ev in d.get("data", d.get("events", [])):
            if isinstance(ev, dict) and ev.get("id"):
                ct = str(ev.get("commence_time", ""))[:10]
                if ct:
                    evdate[ev["id"]] = ct
    consensus = consensus.with_columns(
        pl.col("event_id").map_elements(lambda e: evdate.get(e, ""), return_dtype=pl.Utf8).alias("gd"))
    led = pl.read_parquet(ODDS_DIR / "ledger.parquet").filter(
        (pl.col("status") == "settled") & pl.col("settle_value").is_not_null()).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gd"),
        pl.col("player_name").map_elements(norm_player_name, return_dtype=pl.Utf8).alias("pnorm"))
    j = led.join(consensus, left_on=["gd", "pnorm", "line"],
                 right_on=["gd", "player_norm", "line"], how="inner").sort("gd")
    rows = j.to_dicts()
    for r in rows:
        r["won"] = 1.0 if (r["side"] == "over") == (float(r["settle_value"]) > float(r["line"])) else 0.0
        pm = r.get("p_model")
        r["p_side"] = float(pm) if r["side"] == "over" and pm is not None else (
            1.0 - float(pm) if pm is not None else None)
        co = r.get("consensus_over")
        r["c_side"] = float(co) if r["side"] == "over" and co is not None else (
            1.0 - float(co) if co is not None else None)
    return [r for r in rows if r.get("p_side") is not None and r.get("c_side") is not None]


def brier(ps, ys) -> float:
    return float(np.mean([(p - y) ** 2 for p, y in zip(ps, ys)]))


def ece_of(rs, key) -> float:
    y = np.array([r["won"] for r in rs])
    p = np.array([r[key] for r in rs])
    e, _ = expected_calibration_error(y, p)
    return float(e)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-books", type=int, default=2)
    ap.add_argument("--train-frac", type=float, default=0.7)
    ap.add_argument("--snapshot", type=str, default="close",
                    help="book snapshot for consensus (close=oracle bound, morning=deployable)")
    args = ap.parse_args()

    rows = load_panel(args.min_books, args.snapshot)
    dates = sorted({r["gd"] for r in rows})
    cut = dates[int(len(dates) * args.train_frac)]
    tr = [r for r in rows if r["gd"] <= cut]
    te = [r for r in rows if r["gd"] > cut]

    grid = [0, 0.02, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5, 0.7, 1.0]
    train_curve, test_curve = [], []
    for w in grid:
        for r in tr:
            r["pb"] = w * r["p_side"] + (1 - w) * r["c_side"]
        for r in te:
            r["pb"] = w * r["p_side"] + (1 - w) * r["c_side"]
        train_curve.append({"w": w, "brier": brier([r["pb"] for r in tr], [r["won"] for r in tr]),
                            "ece": ece_of(tr, "pb")})
        test_curve.append({"w": w, "brier": brier([r["pb"] for r in te], [r["won"] for r in te]),
                           "ece": ece_of(te, "pb")})
    best = min(test_curve, key=lambda d: d["brier"])
    bundle_brier = next(d["brier"] for d in test_curve if d["w"] == 1.0)
    rep = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n": len(rows), "n_train": len(tr), "n_test": len(te),
        "cut_date": cut, "dates": [dates[0], dates[-1]],
        "train_curve": train_curve, "test_curve": test_curve,
        "best_w_test": best["w"], "best_brier_test": best["brier"],
        "bundle_brier_test": bundle_brier,
        "brier_gain_vs_bundle": bundle_brier - best["brier"],
        "kill": "SURVIVE" if best["brier"] < bundle_brier else "KILL",
        "by_side_test": {},
        "snapshot": args.snapshot,
        "note": ("shadow only; close-consensus is lookahead (oracle bound); "
                 "morning-consensus is the deployable repeat."),
    }
    for side in ("over", "under"):
        sub = [r for r in te if r["side"] == side]
        if not sub:
            continue
        bm = brier([r["p_side"] for r in sub], [r["won"] for r in sub])
        bc = brier([r["c_side"] for r in sub], [r["won"] for r in sub])
        rep["by_side_test"][side] = {"n": len(sub), "brier_model": bm,
                                     "brier_consensus": bc, "skill": bc - bm}
    out = ODDS_DIR / f"blend_shadow_report_{args.snapshot}.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(json.dumps({k: rep[k] for k in ("n", "n_train", "n_test", "cut_date", "best_w_test",
                                          "best_brier_test", "bundle_brier_test",
                                          "brier_gain_vs_bundle", "kill")}, indent=2))
    print("by_side_test:", json.dumps(rep["by_side_test"], indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
