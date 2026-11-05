"""Champion monthly/probcurve smoke: selector-exact set reconciles to the grade."""

import importlib.util
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from conftest import artifact_path  # noqa: E402


def _load_mod(name, rel):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_champion_monthly_reconciles_to_grade() -> None:
    cand = artifact_path("artifacts", "odds_log", "juiced_replay_candidates.parquet")
    grade = artifact_path("artifacts", "odds_log", "champion_2026_grade.json")
    import json

    curves = _load_mod(
        "monthly_prob_curves",
        "production/ops/market_research/monthly_prob_curves.py")
    df = pl.read_parquet(cand).filter(pl.col("yr").cast(pl.String) == "2026")
    sel = _load_mod(
        "select_2025_champion",
        "production/ops/market_research/select_2025_champion.py")
    taken = sel.apply_config(df, 0.12, 0.24, "lean", "dkfd")
    months = taken.with_columns(
        pl.col("gd").cast(pl.String).str.slice(0, 7).alias("month"))
    by_m = months.group_by("month").len().sort("month")
    g = json.loads(Path(grade).read_text(encoding="utf-8"))
    assert by_m["len"].sum() == g["n"] == 460
    assert set(by_m["month"].to_list()) == set(g["monthly"])
    assert curves is not None
