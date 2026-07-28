"""Binomial / beta-binomial likelihood helpers for Step 5 rate modeling.

Historical games are treated as ``K`` successes in ``PA`` trials. Same-game
``PA`` and ``K`` enter the response likelihood only — never the feature matrix.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import betaln, gammaln

from Python.features import TARGET

try:
    import statsmodels.api as sm
except ImportError:  # pragma: no cover - research extra
    sm = None


def binomial_nll(
    k: np.ndarray | pd.Series,
    pa: np.ndarray | pd.Series,
    probability: np.ndarray,
    *,
    eps: float = 1e-12,
) -> dict[str, float]:
    """Binomial negative log-likelihood summaries for predicted rates."""
    k_arr = np.asarray(k, dtype=np.float64)
    pa_arr = np.asarray(pa, dtype=np.float64)
    p = np.clip(np.asarray(probability, dtype=np.float64), eps, 1.0 - eps)
    if k_arr.shape != pa_arr.shape or k_arr.shape != p.shape:
        raise ValueError("k, pa, and probability must share the same shape")
    if (pa_arr <= 0).any():
        raise ValueError("PA trials must be strictly positive")
    if ((k_arr < 0) | (k_arr > pa_arr)).any():
        raise ValueError("K must lie in [0, PA]")

    nll_per_game = -(k_arr * np.log(p) + (pa_arr - k_arr) * np.log(1.0 - p))
    total_nll = float(nll_per_game.sum())
    total_pa = float(pa_arr.sum())
    return {
        "binomial_nll_sum": total_nll,
        "binomial_nll_per_game": float(nll_per_game.mean()),
        "binomial_nll_per_pa": total_nll / total_pa,
    }


def beta_binomial_nll(
    k: np.ndarray | pd.Series,
    pa: np.ndarray | pd.Series,
    probability: np.ndarray,
    kappa: float,
    *,
    eps: float = 1e-12,
) -> dict[str, float]:
    """Beta-binomial NLL with mean ``probability`` and concentration ``kappa``.

    Parameterization: ``alpha = mu * kappa``, ``beta = (1 - mu) * kappa``.
    Large ``kappa`` approaches the ordinary binomial.
    """
    k_arr = np.asarray(k, dtype=np.float64)
    pa_arr = np.asarray(pa, dtype=np.float64)
    mu = np.clip(np.asarray(probability, dtype=np.float64), eps, 1.0 - eps)
    if k_arr.shape != pa_arr.shape or k_arr.shape != mu.shape:
        raise ValueError("k, pa, and probability must share the same shape")
    if (pa_arr <= 0).any():
        raise ValueError("PA trials must be strictly positive")
    if ((k_arr < 0) | (k_arr > pa_arr)).any():
        raise ValueError("K must lie in [0, PA]")
    if not np.isfinite(kappa) or kappa <= 0:
        raise ValueError("kappa must be a positive finite concentration")

    alpha = mu * kappa
    beta = (1.0 - mu) * kappa
    # log C(n,k) + betaln(alpha+k, beta+n-k) - betaln(alpha, beta)
    log_pmf = (
        gammaln(pa_arr + 1.0)
        - gammaln(k_arr + 1.0)
        - gammaln(pa_arr - k_arr + 1.0)
        + betaln(alpha + k_arr, beta + pa_arr - k_arr)
        - betaln(alpha, beta)
    )
    nll_per_game = -log_pmf
    total_nll = float(nll_per_game.sum())
    total_pa = float(pa_arr.sum())
    return {
        "beta_binomial_nll_sum": total_nll,
        "beta_binomial_nll_per_game": float(nll_per_game.mean()),
        "beta_binomial_nll_per_pa": total_nll / total_pa,
        "kappa": float(kappa),
    }


def fit_beta_binomial_kappa(
    k: np.ndarray | pd.Series,
    pa: np.ndarray | pd.Series,
    probability: np.ndarray,
    *,
    kappa_bounds: tuple[float, float] = (1.0, 1.0e6),
) -> float:
    """MLE concentration given fixed per-game means (two-stage BB)."""

    def objective(log_kappa: float) -> float:
        kappa = float(np.exp(log_kappa))
        return beta_binomial_nll(k, pa, probability, kappa)["beta_binomial_nll_sum"]

    lower, upper = kappa_bounds
    result = minimize_scalar(
        objective,
        bounds=(np.log(lower), np.log(upper)),
        method="bounded",
    )
    if not result.success:
        raise RuntimeError(f"kappa MLE failed: {result.message}")
    return float(np.exp(result.x))


def rate_and_likelihood_metrics(
    frame: pd.DataFrame,
    prediction: np.ndarray,
    *,
    kappa: float | None = None,
) -> dict[str, float]:
    """Game-level rate metrics plus binomial (and optional beta-binomial) NLL."""
    from Python.training import metrics, resolve_sample_weights

    pa_weights = resolve_sample_weights(frame, "pa")
    assert pa_weights is not None
    clipped = np.clip(prediction, 0.0, 1.0)
    unweighted = metrics(frame[TARGET], clipped)
    weighted = metrics(frame[TARGET], clipped, pa_weights)
    nll = binomial_nll(frame["K"], frame["PA"], clipped)
    report = {
        "unweighted_mae": unweighted["mae"],
        "unweighted_rmse": unweighted["rmse"],
        "unweighted_r2": unweighted["r2"],
        "pa_weighted_mae": weighted["mae"],
        "pa_weighted_rmse": weighted["rmse"],
        "pa_weighted_r2": weighted["r2"],
        **nll,
    }
    if kappa is not None:
        report.update(beta_binomial_nll(frame["K"], frame["PA"], clipped, kappa))
    return report


class BinomialGLM:
    """L2-regularized binomial GLM for pregame strikeout probability.

    Uses median imputation and standardization fit on training rows only.
    Regularization is required: the production allow-list is wide relative to
    starter-game counts, so an unpenalized GLM is poorly conditioned.
    """

    def __init__(self, *, alpha: float = 1.0) -> None:
        if sm is None:
            raise ImportError(
                "BinomialGLM requires statsmodels: pip install -e \".[research]\""
            )
        if alpha < 0:
            raise ValueError("alpha must be non-negative")
        self.alpha = float(alpha)
        self._imputer = None
        self._scaler = None
        self._result = None

    def _design(self, frame: pd.DataFrame, features: list[str], *, fit: bool) -> np.ndarray:
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler

        values = frame[features].to_numpy(dtype=np.float64)
        if fit:
            self._imputer = SimpleImputer(strategy="median")
            self._scaler = StandardScaler()
            values = self._imputer.fit_transform(values)
            values = self._scaler.fit_transform(values)
        else:
            if self._imputer is None or self._scaler is None:
                raise RuntimeError("BinomialGLM must be fit before transform")
            values = self._imputer.transform(values)
            values = self._scaler.transform(values)
        return sm.add_constant(values, has_constant="add")

    def fit(self, frame: pd.DataFrame, features: list[str]) -> BinomialGLM:
        if not {"K", "PA"}.issubset(frame.columns):
            raise ValueError("BinomialGLM requires K and PA label columns")
        design = self._design(frame, features, fit=True)
        endog = np.column_stack(
            [
                frame["K"].to_numpy(dtype=np.float64),
                (frame["PA"] - frame["K"]).to_numpy(dtype=np.float64),
            ]
        )
        model = sm.GLM(endog, design, family=sm.families.Binomial())
        # L1_wt=0 -> ridge-like penalty on standardized coefficients.
        self._result = model.fit_regularized(
            method="elastic_net",
            alpha=self.alpha,
            L1_wt=0.0,
            maxiter=200,
        )
        return self

    def predict_proba(self, frame: pd.DataFrame, features: list[str]) -> np.ndarray:
        if self._result is None:
            raise RuntimeError("BinomialGLM must be fit before predict")
        design = self._design(frame, features, fit=False)
        return np.clip(np.asarray(self._result.predict(design), dtype=np.float64), 0.0, 1.0)


class BetaBinomialModel:
    """Two-stage beta-binomial: fixed mean model + MLE concentration.

    Stage 1 fits per-game strikeout probability ``mu`` (default: L2 binomial
    GLM). Stage 2 estimates a global concentration ``kappa`` on training rows
    only. Prediction returns ``mu``; ``kappa`` is used for likelihood scoring.
    """

    def __init__(
        self,
        *,
        alpha: float = 1.0,
        mean_model: str = "binomial_glm",
    ) -> None:
        if mean_model not in {"binomial_glm"}:
            raise ValueError(f"unsupported mean_model {mean_model!r}")
        self.alpha = float(alpha)
        self.mean_model = mean_model
        self.kappa: float | None = None
        self._mean: BinomialGLM | None = None

    def fit(self, frame: pd.DataFrame, features: list[str]) -> BetaBinomialModel:
        self._mean = BinomialGLM(alpha=self.alpha).fit(frame, features)
        train_mu = self._mean.predict_proba(frame, features)
        self.kappa = fit_beta_binomial_kappa(frame["K"], frame["PA"], train_mu)
        return self

    def predict_proba(self, frame: pd.DataFrame, features: list[str]) -> np.ndarray:
        if self._mean is None or self.kappa is None:
            raise RuntimeError("BetaBinomialModel must be fit before predict")
        return self._mean.predict_proba(frame, features)
