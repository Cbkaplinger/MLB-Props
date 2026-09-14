"""September cohort check (descriptive, no live change).

September brings expanded rosters + rookie arms (dilution hypothesis).
Compares September starts vs rest: MAE_K, bias, n — residual = K - xK with
xK = k_rate_pred * projected_tbf from frozen historical scores joined to
L3 actuals. 2025 + 2026 pooled (regular season only).

Reads: historical_scores_2025_2026 + pitcher_training (K).
Writes: artifacts/odds_log/september_cohort_report.json.
FLAG bar: |MAE gap| >= 0.05 or |September bias| >= 0.20.
"""

from __future__ import annotations

import datetime as dt
import importlib.util as _ilu
import json
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[3]

_JK = REPO / "production" / "ops" / "market_research" / "join_keys.py"
_spec = _ilu.spec_from_file_location("join_keys", _JK)
assert _spec and _spec.loader
_jk = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_jk)

OUT = REPO / "artifacts" / "odds_log" / "september_cohort_report.json"


def main() -> None:
    sc = (pl.scan_parquet(REPO / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet")
          .select(["game_date", "pitcher_name", "k_rate_pred", "projected_tbf"])
          .collect().to_dicts())
    actual: dict[tuple, float] = {}
    for r in pl.read_parquet(REPO / "data" / "processed" / "pitcher_training.parquet").select(
            ["game_date", "pitcher_name", "K"]).to_dicts():
        actual[(str(r["game_date"])[:10], _jk.sorted_key(r["pitcher_name"]))] = float(r["K"])
    cohorts: dict[str, list] = {"september": [], "rest": []}
    unmapped = 0
    for s in sc:
        try:
            xk = float(s["k_rate_pred"]) * float(s["projected_tbf"])
        except (TypeError, ValueError):
            continue
        gd = str(s["game_date"])[:10]
        k = actual.get((gd, _jk.sorted_key(s["pitcher_name"])))
        if k is None:
            unmapped += 1
            continue
        cohorts["september" if int(gd[5:7]) == 9 else "rest"].append((k, xk))
    rep: dict = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                 "unmapped": unmapped}
    for name, pts in cohorts.items():
        n = len(pts)
        rep[name] = {"n": n,
                     "mae_K": round(sum(abs(k - x) for k, x in pts) / n, 3),
                     "bias_x_minus_k": round(sum(x - k for k, x in pts) / n, 3)}
    rep["mae_gap_sep_minus_rest"] = round(
        rep["september"]["mae_K"] - rep["rest"]["mae_K"], 4)
    rep["verdict"] = ("FLAG (September harder -- dilution real, gate September separately in October)"
                      if abs(rep["mae_gap_sep_minus_rest"]) >= 0.05
                      or abs(rep["september"]["bias_x_minus_k"]) >= 0.20
                      else "CLEAR (no September effect on frozen-projection errors)")
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
