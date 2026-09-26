"""Ladder sim v2 tests: posterior, chrono-safety, archetypes, monotonicity."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "ladder_sim",
        ROOT / "production" / "ops" / "market_research" / "ladder_sim.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ladder_sim"] = mod
    spec.loader.exec_module(mod)
    return mod


ls = _load()


def test_posterior_centers_on_trailing_rate() -> None:
    import numpy as np

    rng = np.random.default_rng(0)
    # 30 K in 100 PA, league prior ~22%: posterior mean between the two.
    probs = ls.sim_start_over_probs(rng, k=30.0, pa=100.0, tbf_mean=22.0,
                                    tbf_sd=3.0, a0=44.0, b0=156.0, n_sims=20000)
    # Mean K ≈ E[rate]*E[TBF] ≈ ((44+30)/(200+100)) * 22 ≈ 5.4 → P(>4.5) high.
    assert probs[4.5] > 0.5
    assert probs[9.5] < probs[8.5] < probs[6.5]  # monotone tails


def test_trailing_window_is_chrono_safe() -> None:
    rows = [{"K": float(i), "PA": 20.0} for i in range(1, 15)]
    k, pa, rates = ls.trailing_k_pa(rows, 10)
    assert pa == 200.0  # exactly the 10 prior starts (idx 0..9)
    assert k == sum(range(1, 11))
    assert len(rates) == 10
    k0, pa0, _ = ls.trailing_k_pa(rows, 0)
    assert (k0, pa0) == (0.0, 0.0)


def test_archetype_needs_rate_and_spread() -> None:
    assert ls.archetype(0.30, 0.09, 0.25, 0.05) == "power"
    assert ls.archetype(0.30, 0.01, 0.25, 0.05) == "standard"  # steady ace
    assert ls.archetype(0.18, 0.09, 0.25, 0.05) == "standard"  # wild backend


def test_empty_inputs_nan_not_crash() -> None:
    import numpy as np

    rng = np.random.default_rng(0)
    probs = ls.sim_start_over_probs(rng, k=0.0, pa=0.0, tbf_mean=0.0,
                                    tbf_sd=3.0, a0=44.0, b0=156.0, n_sims=100)
    assert all(v != v for v in probs.values())  # NaN, never raises


def test_joint_bootstrap_preserves_pairs_and_monotone() -> None:
    import numpy as np

    rng = np.random.default_rng(1)
    # Ace-ish history: 8, 9, 7 Ks over ~22 PA each.
    pairs = [(8.0, 22.0), (9.0, 23.0), (7.0, 21.0), (10.0, 24.0)]
    probs = ls.sim_start_over_probs_joint(rng, pairs, 22.0, 20000)
    assert probs[4.5] > 0.9  # an 8-K arm clears 4.5 nearly always
    assert probs[9.5] < probs[8.5] < probs[6.5]
    assert ls.sim_start_over_probs_joint(rng, [], 22.0, 100)[4.5] != \
        ls.sim_start_over_probs_joint(rng, [], 22.0, 100)[4.5]  # NaN == NaN false


def test_fixed_seed_reruns_deterministic() -> None:
    import numpy as np

    kw = dict(k=30.0, pa=100.0, tbf_mean=22.0, tbf_sd=3.0, a0=44.0,
              b0=156.0, n_sims=5000)
    a = ls.sim_start_over_probs(np.random.default_rng(11), **kw)
    b = ls.sim_start_over_probs(np.random.default_rng(11), **kw)
    assert a == b
    pairs = [(8.0, 22.0), (9.0, 23.0)]
    c = ls.sim_start_over_probs_joint(np.random.default_rng(11), pairs, 22.0, 5000)
    d = ls.sim_start_over_probs_joint(np.random.default_rng(11), pairs, 22.0, 5000)
    assert c == d
