"""Ledger promotion gate — Poisson + WS1c vs bundle on the BETTABLE panel.

Same n=1049 close-joined ledger panel as WS1 (apples-to-apples with the
blend verdict). Per ticket, in over-frame: bundle p_over (raw binomial),
Poisson p_over (mu=xK via graded k_rate/TBF join), WS1c Platt p_over
(per-line a/b from ws1c_report), consensus fair-over. Brier on taken side.

Writes artifacts/odds_log/ledger_gate_report.json. No live change.
Promote rule: challenger beats bundle by >=0.0005 here AND weekly-pack
confirm AND sign-off. Otherwise stays shadow.
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

from Python.count_layer import over_threshold  # noqa: E402
from Python.odds_ledger import atomic_write_text, norm_player_name  # noqa: E402
from Python.prob_calibration import clip_prob, sigmoid, logit  # noqa: E402
from scipy.stats import poisson as _pois  # noqa: E402
from analyze_book_skill import build_consensus  # noqa: E402
from join_keys import ODDS_DIR, load_event_date_map, sorted_key  # noqa: E402

LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args()
    evdate = load_event_date_map()

    cons = build_consensus(2).with_columns(
        pl.col("event_id").map_elements(lambda e: evdate.get(e, ""), return_dtype=pl.Utf8).alias("gd"),
        pl.col("player_norm").map_elements(sorted_key, return_dtype=pl.Utf8).alias("key"))
    led = pl.read_parquet(ODDS_DIR / "ledger.parquet").filter(
        (pl.col("status") == "settled") & pl.col("settle_value").is_not_null()).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gd"),
        pl.col("player_name").map_elements(
            lambda s: sorted_key(str(s)), return_dtype=pl.Utf8).alias("key"))
    j = led.join(cons, left_on=["gd", "key", "line"],
                 right_on=["gd", "key", "line"], how="inner")
    print(f"ledger-consensus join: {j.height}")

    gr = pl.scan_parquet(ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet").select(
        ["gd", "key_sorted", "k_rate_pred", "projected_tbf"]).collect()
    jj = j.join(gr, left_on=["gd", "key"], right_on=["gd", "key_sorted"], how="left")
    print(f"with k_rate/TBF: {jj.filter(pl.col('k_rate_pred').is_not_null()).height} / {jj.height}")

    ws1c = {float(e["line"]): (e["platt_a"], e["platt_b"])
            for e in json.loads((ODDS_DIR / "ws1c_report.json").read_text())["per_line"]}
    rows = jj.to_dicts()
    se: dict[str, float] = {}
    nn: dict[str, int] = {}
    for r in rows:
        if r.get("p_model") is None or r.get("consensus_over") is None:
            continue
        ln = float(r["line"])
        y_over = 1.0 if float(r["settle_value"]) > ln else 0.0
        y_side = y_over if r["side"] == "over" else 1.0 - y_over
        p_over = float(r["p_model"]) if r["side"] == "over" else 1.0 - float(r["p_model"])
        co = float(r["consensus_over"]) if r["side"] == "over" else 1.0 - float(r["consensus_over"])
        cands = {"bundle": p_over, "consensus": co}
        if r.get("k_rate_pred") is not None and r.get("projected_tbf") is not None and ln in LINES:
            mu = max(float(r["k_rate_pred"]) * float(r["projected_tbf"]), 1e-9)
            p_pois = float(_pois.sf(over_threshold(ln) - 1, mu))
            cands["poisson"] = p_pois if r["side"] == "over" else 1.0 - p_pois
        if ln in ws1c:
            a, b = ws1c[ln]
            p_w = float(clip_prob(sigmoid(a * logit(np.array([p_over])) + b))[0])
            cands["ws1c"] = p_w if r["side"] == "over" else 1.0 - p_w
        for k, p in cands.items():
            se[k] = se.get(k, 0.0) + (p - y_side) ** 2
            nn[k] = nn.get(k, 0) + 1
        if all(k in cands for k in ("bundle", "poisson", "ws1c", "consensus")):
            for k, p in cands.items():
                se["common_" + k] = se.get("common_" + k, 0.0) + (p - y_side) ** 2
            nn["common"] = nn.get("common", 0) + 1
    # Apples-to-apples: head-to-head on COMMON subsets only.
    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n": nn,
           "brier": {k: se[k] / nn[k] for k in se if not k.startswith("common_")},
           "brier_common_subset": {k[7:]: se[k] / nn["common"] for k in se if k.startswith("common_")},
           "n_common": nn.get("common", 0)}
    out = ODDS_DIR / "ledger_gate_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(json.dumps(rep, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
