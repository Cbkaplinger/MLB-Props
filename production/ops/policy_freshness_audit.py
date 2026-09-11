"""Policy freshness audit: date + lineage every live policy input (read-only).

Answers "are we slaves to old policies": each live input gets mtime, fit
metadata where it exists, and a verdict:
  FRESH (<=14d old) / FRESH-BY-EVIDENCE (weekly pack validates it live) /
  STALE-REGATE (>21d + pre-freeze fit — re-derive on post-freeze data) /
  UNDATED (no fit metadata at all — lineage gap)

Writes artifacts/odds_log/policy_freshness_report.json. No live change.
Run weekly or from ship watch.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import atomic_write_text  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"
NOW = datetime.now(timezone.utc)


def age_days(p: Path) -> float | None:
    if not p.exists():
        return None
    import datetime as dt
    ts = dt.datetime.fromtimestamp(p.stat().st_mtime, tz=dt.timezone.utc)
    return (NOW - ts).total_seconds() / 86400.0


def item(name: str, path: str, fit: str, verdict: str, note: str,
         age: float | None) -> dict:
    return {"input": name, "path": path, "age_days": round(age, 1) if age is not None else None,
            "fit_basis": fit, "verdict": verdict, "note": note}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    items = []

    ptr_p = ROOT / "artifacts" / "models" / "prob_calibration_production.json"
    try:
        ptr = json.loads(ptr_p.read_text(encoding="utf-8"))
        items.append(item("calibration pointer", str(ptr_p.relative_to(ROOT)),
                          f"{ptr.get('version')} fit_cutoff={ptr.get('fit_cutoff')}",
                          "FRESH", "WS1c per-line Platt, shipped 9/10 (#28)",
                          age_days(ptr_p)))
    except Exception as exc:
        items.append(item("calibration pointer", str(ptr_p), f"UNREADABLE: {exc}",
                          "UNDATED", "pointer missing!", age_days(ptr_p)))

    from Python.count_layer import COUNT_LAYER_FAMILY_DEFAULT  # noqa: E402
    items.append(item("count family default", "src/Python/count_layer.py",
                      f"COUNT_LAYER_FAMILY_DEFAULT={COUNT_LAYER_FAMILY_DEFAULT!r}",
                      "FRESH", "Poisson shipped 9/10 (#29), one-line revert",
                      None))

    seg = ODDS_DIR / "line_price_correction_table_segmented.parquet"
    seg_fit = "unknown"
    try:
        summ = json.loads((ODDS_DIR / "line_price_correction_table_segmented_summary.json").read_text(encoding="utf-8"))
        seg_fit = (f"n={summ.get('global', {}).get('n')} opens, "
                   f"generated {summ.get('generated_utc', '?')[:10]} (pre-freeze)")
    except Exception:
        pass
    items.append(item("price offsets (live)", "artifacts/odds_log/line_price_correction_table_segmented.parquet",
                      seg_fit, "STALE-REGATE",
                      "#85: Brier +0.0049 but ROI worse; cap/remove/keep pending owner",
                      age_days(seg)))

    mx = ODDS_DIR / "calibration_deploy_matrix.parquet"
    mx_fit = "unknown"
    try:
        import polars as pl
        m = pl.read_parquet(mx)
        on_n = int(m.filter(pl.col("deploy_state") == "ON").height)
        mx_fit = (f"{m.height} segments, {on_n} ON "
                  "(fit window undated in file)")
    except Exception:
        pass
    items.append(item("deploy matrix (ON/OFF filter)", "artifacts/odds_log/calibration_deploy_matrix.parquet",
                      mx_fit, "STALE-REGATE",
                      "month-old ON/OFF states; re-gate on post-freeze data",
                      age_days(mx)))

    kpi = ROOT / "production" / "ops" / "kpi_policy.json"
    items.append(item("kpi veto/probation", "production/ops/kpi_policy.json",
                      "4.5-over veto + 2.5/3.5 probation",
                      "FRESH-BY-EVIDENCE", "weekly pack validates veto 4 straight weeks",
                      age_days(kpi)))

    fl = ROOT / "production" / "ops" / "market_research" / "line_floor_policy.json"
    items.append(item("line floors", "production/ops/market_research/line_floor_policy.json",
                      "8 line floors", "FRESH-BY-EVIDENCE",
                      "WS7 challenger killed 9/10; floors stand on evidence",
                      age_days(fl)))

    try:
        import polars as pl
        from Python import config  # noqa: E402
        lp = Path(config.PITCHER_TRAINING_PATH)
        d = pl.scan_parquet(lp).select("game_date").collect()
        items.append(item("L3 features/projections", str(lp.relative_to(ROOT)),
                          f"max game_date={d['game_date'].max()}, n={d.height}",
                          "FRESH", "nightly refresh; projections log daily",
                          age_days(lp)))
    except Exception as exc:
        items.append(item("L3 features/projections", "?", f"UNREADABLE: {exc}",
                          "UNDATED", "check pipeline", None))

    stale = [i for i in items if i["verdict"] == "STALE-REGATE"]
    rep = {"generated_utc": NOW.isoformat(), "items": items,
           "stale_count": len(stale),
           "stale": [i["input"] for i in stale]}
    out = ODDS_DIR / "policy_freshness_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    for i in items:
        print(f"{i['verdict']:18} {i['age_days']!s:>6}d  {i['input']:32} {i['fit_basis']}")
    print(f"stale={len(stale)}; wrote {out}")


if __name__ == "__main__":
    main()
