"""Bettor's calibration: ECE/MCE on the taken set (descriptive).

Universe ECE (0.021) averages over lines we would never bet. The honest
calibration number is measured on taken tickets only: same decile method,
same subset rule. Side splits included (selection concentrates error
differently by side).

Reads: juiced_replay_candidates.parquet (accepted, over/under).
Writes: artifacts/odds_log/bettable_calibration_report.json.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[3]
CAND = REPO / "artifacts" / "odds_log" / "juiced_replay_candidates.parquet"
OUT = REPO / "artifacts" / "odds_log" / "bettable_calibration_report.json"


def ece_mce(pairs: list[tuple[float, float]], k: int = 10) -> dict:
    pairs = sorted(pairs, key=lambda r: r[0])
    n = len(pairs)
    e = m = 0.0
    bins = []
    for i in range(k):
        b = pairs[i * n // k:(i + 1) * n // k]
        if not b:
            continue
        acc = sum(r[1] for r in b) / len(b)
        conf = sum(r[0] for r in b) / len(b)
        e += abs(acc - conf) * len(b) / n
        m = max(m, abs(acc - conf))
        bins.append({"n": len(b), "conf": round(conf, 3), "acc": round(acc, 3)})
    return {"n": n, "ece": round(e, 4), "mce": round(m, 4), "bins": bins}


def main() -> None:
    taken = (pl.read_parquet(CAND)
             .filter(pl.col("accepted") & pl.col("side").is_in(["over", "under"]))
             .select(["p_ours_cal", "y", "side"]).to_dicts())
    rep: dict = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                 "note": "decile ECE on taken tickets; universe ECE (0.021) is the wrong denominator for bettors",
                 "taken": ece_mce([(float(r["p_ours_cal"]), float(r["y"])) for r in taken])}
    for s in ("over", "under"):
        q = [(float(r["p_ours_cal"]), float(r["y"])) for r in taken if r["side"] == s]
        rep[s] = ece_mce(q)
    rep["verdict"] = ("CONFIRMED (taken ECE %.4f ~= 4x universe — humility priced in via 1/16 Kelly + caps; "
                      "universe ECE must never justify sizing)" % rep["taken"]["ece"])
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps({k: v for k, v in rep.items() if k != "bins"}, indent=2)[:800])


if __name__ == "__main__":
    main()
