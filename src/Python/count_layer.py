"""Strikeout count layer: rate × projected TBF → expected_K and P(K ≥ line).

Frozen inputs:
- ``k_rate`` from the Step-7 LightGBM production model
- ``projected_tbf`` from the Ridge TBF spine (thin bullpen)

Same-game ``PA`` / ``K`` are labels for evaluation only. Prop probabilities use
**projected** TBF as the trial count, never same-game PA.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd
from scipy.stats import betabinom, binom, poisson

from Python.likelihoods import fit_beta_binomial_kappa

DEFAULT_K_LINES: tuple[float, ...] = (3.5, 4.5, 5.5, 6.5, 7.5)
# Live / notebook / odds board (covers soft 2.5 through long 9.5 mains).
PROJECTION_K_LINES: tuple[float, ...] = (2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5)

# Above this concentration, beta-binomial ≈ binomial for prop work.
BINOMIAL_KAPPA_FLOOR: float = 1.0e5


def expected_strikeouts(
    k_rate: np.ndarray | pd.Series,
    projected_tbf: np.ndarray | pd.Series,
) -> np.ndarray:
    """Point estimate ``E[K] = k_rate × projected_tbf`` (pregame only)."""
    rate = np.clip(np.asarray(k_rate, dtype=np.float64), 0.0, 1.0)
    tbf = np.asarray(projected_tbf, dtype=np.float64)
    if rate.shape != tbf.shape:
        raise ValueError("k_rate and projected_tbf must share the same shape")
    if (tbf < 0).any():
        raise ValueError("projected_tbf must be non-negative")
    return rate * tbf


def trials_from_projected_tbf(
    projected_tbf: np.ndarray | pd.Series,
    *,
    minimum: int = 1,
) -> np.ndarray:
    """Integer trial counts for binomial / beta-binomial prop probabilities."""
    tbf = np.asarray(projected_tbf, dtype=np.float64)
    if (tbf < 0).any():
        raise ValueError("projected_tbf must be non-negative")
    trials = np.maximum(np.rint(tbf).astype(np.int64), minimum)
    return trials


def over_threshold(line: float) -> int:
    """Smallest integer K that wins the over at ``line`` (e.g. 4.5 → 5)."""
    if not np.isfinite(line):
        raise ValueError("line must be finite")
    return int(np.floor(line) + 1)


def p_strikeouts_ge(
    line: float,
    *,
    k_rate: np.ndarray | pd.Series,
    projected_tbf: np.ndarray | pd.Series,
    family: str = "binomial",
    kappa: float | None = None,
) -> np.ndarray:
    """``P(K ≥ over_threshold(line) | projected TBF, k_rate)``.

    Families:
    - ``binomial``: ``Binomial(n=round(TBF), p=k_rate)``
    - ``beta_binomial``: mean ``k_rate``, concentration ``kappa``
    - ``poisson``: ``Poisson(mu=k_rate × TBF)`` (ignores integer-n rounding)
    """
    rate = np.clip(np.asarray(k_rate, dtype=np.float64), 1e-12, 1.0 - 1e-12)
    tbf = np.asarray(projected_tbf, dtype=np.float64)
    if rate.shape != tbf.shape:
        raise ValueError("k_rate and projected_tbf must share the same shape")
    threshold = over_threshold(line)
    family = family.lower()

    if family == "poisson":
        mu = expected_strikeouts(rate, tbf)
        return poisson.sf(threshold - 1, mu)

    trials = trials_from_projected_tbf(tbf)
    if family == "binomial":
        return binom.sf(threshold - 1, trials, rate)

    if family == "beta_binomial":
        if kappa is None or not np.isfinite(kappa) or kappa <= 0:
            raise ValueError("beta_binomial requires a positive kappa")
        if kappa >= BINOMIAL_KAPPA_FLOOR:
            return binom.sf(threshold - 1, trials, rate)
        alpha = rate * kappa
        beta = (1.0 - rate) * kappa
        return betabinom.sf(threshold - 1, trials, alpha, beta)

    raise ValueError(
        f"unsupported family {family!r}; expected binomial, beta_binomial, or poisson"
    )


def count_point_metrics(
    actual_k: np.ndarray | pd.Series,
    expected_k: np.ndarray | pd.Series,
) -> dict[str, float]:
    """MAE / RMSE / R² for expected strikeout counts vs actual K."""
    from Python.training import metrics

    return metrics(
        actual_k,
        np.asarray(expected_k, dtype=float),
        clip_to_unit_interval=False,
    )


def line_market_metrics(
    actual_k: np.ndarray | pd.Series,
    prob_over: np.ndarray | pd.Series,
    line: float,
) -> dict[str, float]:
    """Brier / log-loss / accuracy for one over/under line."""
    from sklearn.metrics import brier_score_loss, log_loss

    y = (np.asarray(actual_k, dtype=np.float64) >= over_threshold(line)).astype(int)
    p = np.clip(np.asarray(prob_over, dtype=np.float64), 1e-12, 1.0 - 1e-12)
    pick_over = (p >= 0.5).astype(int)
    return {
        "line": float(line),
        "base_rate": float(y.mean()),
        "mean_prob": float(p.mean()),
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "accuracy": float((pick_over == y).mean()),
        "n": int(y.size),
    }


def evaluate_count_layer(
    frame: pd.DataFrame,
    *,
    k_rate: np.ndarray,
    projected_tbf: np.ndarray,
    lines: Sequence[float] = DEFAULT_K_LINES,
    kappa: float | None = None,
    families: Iterable[str] = ("binomial", "beta_binomial", "poisson"),
) -> dict:
    """Point + line metrics for one partition (validation or test)."""
    if "K" not in frame.columns:
        raise ValueError("frame requires actual K for evaluation")
    expected = expected_strikeouts(k_rate, projected_tbf)
    report: dict = {
        "expected_k": count_point_metrics(frame["K"], expected),
        "projected_tbf_mean": float(np.mean(projected_tbf)),
        "k_rate_mean": float(np.mean(k_rate)),
        "actual_k_mean": float(frame["K"].mean()),
        "lines": {},
    }
    family_list = list(families)
    if kappa is None:
        family_list = [f for f in family_list if f != "beta_binomial"]

    for family in family_list:
        report["lines"][family] = {}
        for line in lines:
            prob = p_strikeouts_ge(
                line,
                k_rate=k_rate,
                projected_tbf=projected_tbf,
                family=family,
                kappa=kappa,
            )
            report["lines"][family][str(line)] = line_market_metrics(
                frame["K"], prob, line
            )
    if kappa is not None:
        report["kappa"] = float(kappa)
    return report


def fit_count_layer_kappa(
    *,
    k: np.ndarray | pd.Series,
    pa: np.ndarray | pd.Series,
    k_rate: np.ndarray | pd.Series,
) -> float:
    """Train-only BB concentration using historical PA trials + predicted rate.

    Same two-stage protocol as Step 5: mean is fixed; ``kappa`` is MLE on train.
    At score time, trial counts switch to projected TBF.
    """
    return fit_beta_binomial_kappa(k, pa, np.clip(np.asarray(k_rate), 1e-12, 1 - 1e-12))


def attach_count_predictions(
    frame: pd.DataFrame,
    *,
    k_rate: np.ndarray,
    projected_tbf: np.ndarray,
    lines: Sequence[float] = DEFAULT_K_LINES,
    kappa: float | None = None,
) -> pd.DataFrame:
    """Return a copy with ``projected_tbf``, ``expected_K``, and line probs."""
    out = frame.copy()
    out["k_rate_pred"] = np.asarray(k_rate, dtype=np.float64)
    out["projected_tbf"] = np.asarray(projected_tbf, dtype=np.float64)
    out["expected_K"] = expected_strikeouts(k_rate, projected_tbf)
    for line in lines:
        key = f"p_over_{str(line).replace('.', '_')}"
        out[key] = p_strikeouts_ge(
            line,
            k_rate=k_rate,
            projected_tbf=projected_tbf,
            family="binomial",
        )
        if kappa is not None:
            out[f"{key}_bb"] = p_strikeouts_ge(
                line,
                k_rate=k_rate,
                projected_tbf=projected_tbf,
                family="beta_binomial",
                kappa=kappa,
            )
    return out
