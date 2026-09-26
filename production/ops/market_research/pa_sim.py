"""PA-level game sim v4 (paper research, no live change).

Owner 2026-09-24: aggregate lineup K% hides that each slot approaches the
plate differently. Answer: sim every PA with SLOT-SPECIFIC batter rates —
no pair-level noise (batter season rates over ~600 PA are stable; the
pitcher-vs-specific-batter interaction is what's noise, and we never touch
it). Order weight emerges naturally (top slots bat more).

Per PA: p(K) = log5(batter slot rate, pitcher rate, league rate). Pulls via
the hook table (v1 constants). TBF is an OUTPUT (PAs faced), never an input
— one fewer model to be wrong about.

Inputs per sim: slot_rates[9] (batter K% vs hand), p_pitcher, p_league.
Usage is paper-only (ladder pricing research, archetype tails v2).
"""

from __future__ import annotations

import numpy as np

PITCHES_PER_PA = 3.85
MAX_PA = 45


def log5(p_batter: float, p_pitcher: float, p_league: float) -> float:
    """Classic matchup blend (pure, testable)."""
    pb = min(max(p_batter, 1e-4), 1.0 - 1e-4)
    pp = min(max(p_pitcher, 1e-4), 1.0 - 1e-4)
    pl = min(max(p_league, 1e-4), 1.0 - 1e-4)
    num = pb * pp / pl
    den = num + (1.0 - pb) * (1.0 - pp) / (1.0 - pl)
    return num / den if den > 0 else pl


def sim_game(rng: np.random.Generator, slot_rates: list[float],
             p_pitcher: float, p_league: float,
             pull_prob: float = 0.10) -> tuple[int, int]:
    """One game: (strikeouts, TBF faced). TBF emerges from pulls."""
    rates = [min(max(float(r), 1e-4), 1.0 - 1e-4) for r in slot_rates]
    if len(rates) != 9 or not (0.0 < p_pitcher < 1.0):
        return 0, 0
    ks, pa, pitches, tto = 0, 0, 0, 0
    for _ in range(MAX_PA):
        slot = pa % 9
        if pa > 0 and slot == 0:
            tto += 1
        p = log5(rates[slot], p_pitcher, p_league)
        if rng.random() < p:
            ks += 1
        pa += 1
        pitches += PITCHES_PER_PA
        if tto >= 2 and rng.random() < pull_prob:
            break
        if pitches >= 110:
            break
    return ks, pa


def sim_over_probs(rng: np.random.Generator, slot_rates: list[float],
                   p_pitcher: float, p_league: float, rungs: list[float],
                   n_sims: int, pull_prob: float = 0.10) -> dict[float, float]:
    """P(K > rung) over n_sims games (pure, testable)."""
    ks = np.array([sim_game(rng, slot_rates, p_pitcher, p_league,
                            pull_prob)[0] for _ in range(max(n_sims, 1))])
    return {r: float((ks > r).mean()) for r in rungs}
