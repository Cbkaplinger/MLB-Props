"""PA sim v4 tests: log5, TBF emergence, slot weighting, determinism."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "pa_sim",
        ROOT / "production" / "ops" / "market_research" / "pa_sim.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pa_sim"] = mod
    spec.loader.exec_module(mod)
    return mod


pa = _load()


def test_log5_known_value() -> None:
    # log5(0.30, 0.20, 0.25) = 0.24 / (0.24 + 0.7467) ≈ 0.2432.
    assert abs(pa.log5(0.30, 0.20, 0.25) - 0.2432) < 0.001
    assert pa.log5(0.25, 0.25, 0.25) == 0.25  # league-average all around


def test_tbf_emerges_and_seeds_reproduce() -> None:
    import numpy as np

    slots = [0.25] * 9
    r1 = np.random.default_rng(7)
    k1, tbf1 = pa.sim_game(r1, slots, 0.25, 0.22)
    r2 = np.random.default_rng(7)
    k2, tbf2 = pa.sim_game(r2, slots, 0.25, 0.22)
    assert (k1, tbf1) == (k2, tbf2)
    assert 9 <= tbf1 <= pa.MAX_PA  # faced at least one trip, capped
    assert pa.sim_game(r1, [0.25] * 8, 0.25, 0.22) == (0, 0)  # bad lineup


def test_top_heavy_lineup_strikes_more() -> None:
    import numpy as np

    rng = np.random.default_rng(3)
    top_heavy = [0.35, 0.33, 0.31, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15]
    bottom_heavy = [0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.35, 0.33, 0.31]
    k_top = sum(pa.sim_game(rng, top_heavy, 0.25, 0.22)[0] for _ in range(300))
    k_bot = sum(pa.sim_game(rng, bottom_heavy, 0.25, 0.22)[0] for _ in range(300))
    assert k_top > k_bot  # same nine bats, order matters


def test_better_pitcher_more_ks() -> None:
    import numpy as np

    rng = np.random.default_rng(5)
    probs_ace = pa.sim_over_probs(rng, [0.22] * 9, 0.32, 0.22, [4.5, 6.5], 2000)
    probs_avg = pa.sim_over_probs(rng, [0.22] * 9, 0.22, 0.22, [4.5, 6.5], 2000)
    assert probs_ace[4.5] > probs_avg[4.5] > 0.3
    assert probs_ace[6.5] > probs_ace[4.5] - 1.0  # sane
    assert probs_ace[6.5] < probs_ace[4.5]  # monotone tails
