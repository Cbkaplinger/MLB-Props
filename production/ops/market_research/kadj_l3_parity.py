"""kAdj L3 parity check (post hoc, research; backlog #60).

Runs the pipeline `_join_kadj_features` on the real L3 frame and compares
behavioral aggregates against the validated probe
(`ws8_kadj_report.json`): coverage ~93%, pitcher-season-mean YoY r ~0.75.
No retraining here — the member test is the next script.

Writes artifacts/model_quality/kadj_parity/report.json. No live change.
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

from Python.config import PITCHER_TRAINING_PATH  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.pipeline.training import _join_kadj_features  # noqa: E402

SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
PROBE_REP = ROOT / "artifacts" / "odds_log" / "ws8_kadj_report.json"
OUT_DIR = ROOT / "artifacts" / "model_quality" / "kadj_parity"


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 10:
        return float("nan")
    return float(np.corrcoef(a[m], b[m])[0, 1])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    l3 = pl.scan_parquet(PITCHER_TRAINING_PATH).select(
        ["game_pk", "pitcher", "game_date", "season"]).collect()
    print(f"L3 rows: {l3.height}")
    out = _join_kadj_features(l3)
    assert out.height == l3.height
    coverage = 1.0 - out["kadj"].null_count() / out.height

    scored_pks = set(pl.scan_parquet(SCORED).select("game_pk").collect()["game_pk"].to_list())
    overlap = out.filter(pl.col("game_pk").is_in(scored_pks))
    n_overlap = overlap.height
    # Same-population comparison: the probe scored 2025-2026 starts (rich
    # history); full-L3 coverage is lower because 2023 rows lack priors.
    coverage = 1.0 - overlap["kadj"].null_count() / max(n_overlap, 1)
    coverage_all = 1.0 - out["kadj"].null_count() / out.height
    d = out.filter(pl.col("kadj").is_not_null()).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 4).alias("season"))
    seas = (d.group_by(["pitcher", "season"])
            .agg(pl.col("kadj").mean().alias("mk"), pl.len().alias("n"))
            .filter(pl.col("n") >= 10))
    piv = seas.pivot(on="season", index="pitcher", values="mk")
    yoy = _corr(piv["2025"].to_numpy().astype(float), piv["2026"].to_numpy().astype(float)) \
        if "2025" in piv.columns and "2026" in piv.columns else float("nan")

    probe = json.loads(PROBE_REP.read_text(encoding="utf-8"))
    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "l3_rows": l3.height, "scored_overlap": n_overlap,
           "coverage": coverage, "coverage_all_l3": coverage_all,
           "coverage_probe": probe["coverage"],
           "yoy_r": yoy, "yoy_probe": probe["stability"]["yoy_r"],
           "parity": bool(abs(coverage - probe["coverage"]) < 0.02
                          and abs(yoy - probe["stability"]["yoy_r"]) < 0.10)}
    print(f"coverage L3={coverage:.3f} probe={probe['coverage']:.3f} | "
          f"YoY L3={yoy:.3f} probe={probe['stability']['yoy_r']:.3f} | "
          f"parity={rep['parity']}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(OUT_DIR / "report.json", json.dumps(rep, indent=2, default=str))
    print(f"wrote {OUT_DIR / 'report.json'}")
    if not rep["parity"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
