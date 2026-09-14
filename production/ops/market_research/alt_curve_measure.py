"""Alt-line curve measurement at universe scale (descriptive, no live change).

Scores the frozen live config (Poisson + WS1c) at alt lines 0.5..14.5 for
every scored 2025-2026 start, joins book alt-close probs + actual-K outcomes.
Answers where the curve shape breaks beyond the main 2.5-9.5 grid.
Book alt is over-only, vig-loaded (no devig possible) -- labeled everywhere.
WS1c maps exist for 2.5-9.5 only; outside, the nearest map is reused
(documented approximation -- tails descriptive, never gates).

Reads: historical_scores, L3 actuals, book_lines_pitcher alt closes.
Writes: artifacts/odds_log/alt_curve_report.json.
"""

from __future__ import annotations

import datetime as dt
import importlib.util as _ilu
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import polars as pl

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

from Python.count_layer import p_strikeouts_ge  # noqa: E402
from Python.market import american_to_implied_prob  # noqa: E402

_JK = REPO / "production" / "ops" / "market_research" / "join_keys.py"
_spec = _ilu.spec_from_file_location("join_keys", _JK)
assert _spec and _spec.loader
_jk = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_jk)

SCORED = REPO / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
L3 = REPO / "data" / "processed" / "pitcher_training.parquet"
CALIB = REPO / "artifacts" / "models" / "prob_calibration_ws1c_platt_20260910_012559.joblib"
OUT = REPO / "artifacts" / "odds_log" / "alt_curve_report.json"

ALT_LINES = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5, 14.5]
MAIN_MAP = {"2_5": 2.5, "3_5": 3.5, "4_5": 4.5, "5_5": 5.5, "6_5": 6.5, "7_5": 7.5, "8_5": 8.5, "9_5": 9.5}


def main() -> None:
    bundle = joblib.load(CALIB)
    maps = {ln: bundle.line_maps[k] for k, ln in MAIN_MAP.items()}

    def cal(kr: float, tbf: float, ln: float) -> float:
        raw = float(p_strikeouts_ge(ln, k_rate=np.array([kr]),
                                    projected_tbf=np.array([tbf]), family="poisson")[0])
        anchor = min(MAIN_MAP.values(), key=lambda m: abs(m - ln))
        return float(maps[anchor].transform(np.array([raw]))[0])

    sc = (pl.scan_parquet(SCORED).select(
        ["game_pk", "pitcher_name", "game_date", "k_rate_pred", "projected_tbf"])
        .collect().to_dicts())
    actual: dict[tuple, float] = {}
    for r in pl.read_parquet(L3).select(["game_date", "pitcher_name", "K"]).to_dicts():
        actual[(str(r["game_date"])[:10], _jk.sorted_key(r["pitcher_name"]))] = float(r["K"])

    evdate = _jk.load_event_date_map()
    book: dict[tuple, list[float]] = {}
    for r in (pl.read_parquet(REPO / "data" / "Odds-Historical" / "theoddsapi" / "book_lines_pitcher.parquet")
              .filter((pl.col("market") == "pitcher_strikeouts") & (pl.col("snapshot") == "close"))
              .to_dicts()):
        if r.get("side") != "over":
            continue
        try:
            ln = float(r["line"])
            p = american_to_implied_prob(float(r["price"]))
        except (TypeError, ValueError):
            continue
        book.setdefault((evdate.get(str(r["event_id"]), ""), _jk.sorted_key(r["player"]), ln), []).append(p)
    book_med = {k: sorted(v)[len(v) // 2] for k, v in book.items()}

    cells: dict[str, dict] = {}
    n_starts = n_mapped = 0
    for s in sc:
        try:
            kr = float(np.clip(float(s["k_rate_pred"]), 0.02, 0.5))
            tbf = float(s["projected_tbf"])
        except (TypeError, ValueError):
            continue
        gd = str(s["game_date"])[:10]
        skey = _jk.sorted_key(s.get("pitcher_name") or "")
        k = actual.get((gd, skey))
        if k is None:
            continue
        n_starts += 1
        hit_any = False
        for ln in ALT_LINES:
            b = book_med.get((gd, skey, ln))
            if b is None:
                continue
            hit_any = True
            y = 1.0 if k > ln else 0.0
            p = cal(kr, tbf, ln)
            c = cells.setdefault(str(ln), {"n": 0, "se_o": 0.0, "se_b": 0.0, "bias_o": 0.0})
            c["n"] += 1
            c["se_o"] += (p - y) ** 2
            c["se_b"] += (b - y) ** 2
            c["bias_o"] += p - y
        n_mapped += 1 if hit_any else 0

    rep = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "n_starts": n_starts, "n_starts_with_alt": n_mapped,
           "book_note": "alt over-only, vig-loaded implied (no devig); ws1c nearest-map outside 2.5-9.5",
           "lines": {}}
    for ln in ALT_LINES:
        c = cells.get(str(ln))
        if not c or not c["n"]:
            rep["lines"][str(ln)] = {"n": 0}
            continue
        rep["lines"][str(ln)] = {"n": c["n"],
                                 "brier_ours": round(c["se_o"] / c["n"], 4),
                                 "brier_book": round(c["se_b"] / c["n"], 4),
                                 "skill": round((c["se_b"] - c["se_o"]) / c["n"], 4),
                                 "bias_pp": round(100 * c["bias_o"] / c["n"], 2)}
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
