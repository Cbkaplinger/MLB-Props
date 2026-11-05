"""Unit tests for band-grid v2 (synthetic-first; equivalence on published sets)."""

import importlib.util
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "production" / "ops" / "market_research"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_v2 = _load("band_grid_v2", "production/ops/market_research/band_grid_v2.py")
_sel = _load("select_2025_champion", "production/ops/market_research/select_2025_champion.py")

CAND = ROOT / "artifacts" / "odds_log" / "juiced_replay_candidates.parquet"


def _keyset(t: pl.DataFrame) -> set:
    return set(zip(t["gd"].cast(pl.String).to_list(), t["player_name"].to_list(),
                   t["line"].to_list(), t["side"].to_list(), t["book"].to_list()))


def test_grid_size_and_superset() -> None:
    n = len(_v2.FLOOR_OPTS) * len(_v2.CAPS) * len(_v2.SIDES) * len(_v2.BOOKS)
    assert n == 80
    names = [_v2.cfg_name(fm, fv, c, s, b)
             for fm, fv in _v2.FLOOR_OPTS for c in _v2.CAPS
             for s in _v2.SIDES for b in _v2.BOOKS]
    assert len(set(names)) == 80
    # every old-36 config is contained
    for fl in (0.08, 0.10, 0.12):
        for cap in (0.18, 0.20, 0.24):
            for side in ("both", "lean"):
                for book in ("next", "dkfd"):
                    assert _v2.cfg_name("uniform", fl, cap, side, book) in names


def test_take_v2_matches_selector_on_overlap() -> None:
    # Published 2025 slice only (no new peek): identical row sets.
    df = pl.read_parquet(CAND).filter(pl.col("yr").cast(pl.String) == "2025")
    for fl, cap, side, book in [(0.12, 0.24, "lean", "dkfd"),
                                (0.10, 0.20, "both", "next"),
                                (0.08, None, "both", "dkfd")]:
        cap_v = 9.0 if cap is None else cap
        a = _sel.apply_config(df, fl, cap_v, side, book)
        b = _v2.take_v2(df, "uniform", fl, cap, side, book)
        assert _keyset(a) == _keyset(b), (fl, cap, side, book)
        assert float(a["pnl"].sum()) == float(b["pnl"].sum())


def test_peek_gate_refuses() -> None:
    try:
        _v2.run(select_from="2026-01-01", allow_peeked=False, n_boot=10)
    except _v2.PeekRefused:
        return
    raise AssertionError("peeked selection without flag must refuse")


def test_empty_slice_valid() -> None:
    rep = _v2.run(select_from="2026-09-28", allow_peeked=False, n_boot=10)
    assert rep["champion"] is None and rep["promotable"] is True
    assert rep["n_configs"] in (0, 80)


def test_file_floors_map() -> None:
    fm = _v2.file_floors()
    assert fm[2.5] == 0.20 and fm[4.5] == 0.14 and fm[9.5] == 0.16


def test_white_lite_bounds() -> None:
    import numpy as np
    rng = np.random.default_rng(0)
    fam = {}
    for i in range(3):
        n = 60
        fam[f"leg{i}"] = pl.DataFrame({
            "gd": [f"2026-09-{28 + (j % 2)}" for j in range(n)],
            "pnl": list(rng.normal(2.0, 40.0, n)),
        })
    w = _v2.white_lite(fam, ["2026-09-28", "2026-09-29"], 0.05,
                        n_boot=50, seed=1)
    assert 0.0 <= w["p_value"] <= 1.0 and w["n_configs"] == 3
