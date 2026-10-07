"""BF workload distribution: discrete termination-hazard utilities.

Implements frozen design preregistration
`research/offseason_2026/bf-distribution-design-prereg.md`.
Pure functions over injected frames/arrays; NO file I/O, NO real-data
fitting or scoring at import or in these helpers. The `run_diagnostic`
entry point operates on caller-supplied synthetic frames only; real-data
execution requires a separate one-run authorization.

Conventions (frozen):
- PMF vectors have length N_MAX + 1 = 37: index 0 holds P(N=1), ...,
  index 35 holds P(N=36), index 36 holds P(N>=37) overflow mass.
- A completed short outing is an observed outcome, never censored.
- Truncated/corrupt observations raise loudly; they never become
  benign missingness.
"""

from __future__ import annotations

import numpy as np

N_MAX = 36
N_CATEGORIES = N_MAX + 1  # 1..36 plus overflow bucket
SHORT_OUTING_THRESHOLD = 9
NLL_CLIP = 1e-12
MASS_TOLERANCE = 1e-9


def check_pmf(pmf: np.ndarray) -> None:
    pmf = np.asarray(pmf, dtype=float)
    if pmf.shape != (N_CATEGORIES,):
        raise ValueError("pmf must have length %d" % N_CATEGORIES)
    if bool((pmf < 0.0).any()):
        raise ValueError("pmf has negative mass")
    if abs(float(pmf.sum()) - 1.0) > MASS_TOLERANCE:
        raise ValueError("pmf mass sums to %r, not 1" % float(pmf.sum()))


def hazard_to_pmf(hazards: np.ndarray) -> np.ndarray:
    """Termination hazards h_1..h_36 to the 37-category PMF.

    P(N=n) = h_n * prod_{j<n}(1-h_j); overflow = prod_{j<=36}(1-h_j).
    """
    hazards = np.asarray(hazards, dtype=float)
    if hazards.shape != (N_MAX,):
        raise ValueError("hazards must have length %d" % N_MAX)
    if bool(((hazards < 0.0) | (hazards > 1.0)).any()):
        raise ValueError("hazards must lie in [0, 1]")
    survival = 1.0
    pmf = np.empty(N_CATEGORIES)
    for n in range(N_MAX):
        pmf[n] = hazards[n] * survival
        survival *= 1.0 - hazards[n]
    pmf[N_MAX] = survival
    return pmf


def pmf_to_cdf(pmf: np.ndarray) -> np.ndarray:
    check_pmf(pmf)
    return np.cumsum(pmf)


def _category(k: int) -> int:
    """Realized BF to PMF category (overflow bucket absorbs >= 37)."""
    if k < 1:
        raise ValueError("BF outcome below support: %r" % (k,))
    return min(int(k) - 1, N_MAX)


def rps_score(pmf: np.ndarray, k: int) -> float:
    """Discrete CRPS over categories 0..37 (overflow = category 37)."""
    cdf = pmf_to_cdf(pmf)
    hit = _category(k)
    return float(sum((cdf[t] - (1.0 if t >= hit else 0.0)) ** 2
                     for t in range(N_CATEGORIES)))


def count_nll(pmf: np.ndarray, k: int,
              clip: float = NLL_CLIP) -> tuple[float, bool]:
    mass = float(pmf[_category(k)])
    clipped = mass < clip
    return float(-np.log(max(mass, clip))), clipped


def short_outing_brier(pmf: np.ndarray, k: int,
                       threshold: int = SHORT_OUTING_THRESHOLD) -> float:
    """Brier score on the event {BF < threshold}."""
    check_pmf(pmf)
    prob = float(pmf[:threshold - 1].sum())
    return float((prob - (1.0 if k < threshold else 0.0)) ** 2)


def central_interval(pmf: np.ndarray,
                     level: float) -> tuple[int, int, int]:
    """Central interval at `level`: (loBF, hiBF, width) with equal tails."""
    if not 0.0 < level < 1.0:
        raise ValueError("level must lie in (0, 1)")
    cdf = pmf_to_cdf(pmf)
    tail = (1.0 - level) / 2.0
    lo = int(np.searchsorted(cdf, tail, side="left"))
    hi = int(np.searchsorted(cdf, 1.0 - tail, side="left"))
    lo = min(lo, N_MAX)
    hi = min(hi, N_MAX)
    return lo + 1 if lo < N_MAX else N_MAX + 1, hi + 1, hi - lo + 1


def interval_covered(interval: tuple[int, int, int], k: int) -> bool:
    lo, hi, _ = interval
    return bool(lo <= k <= hi) if k <= N_MAX else bool(lo <= N_MAX + 1)


def empirical_baseline(counts: np.ndarray,
                       laplace: float = 1.0) -> np.ndarray:
    """Train-only empirical PMF over the 37 categories (add-one default).

    `counts`: observed per-category counts for the training partition.
    Laplace smoothing keeps every log score finite; the smoothing
    strength is frozen, not tuned.
    """
    counts = np.asarray(counts, dtype=float)
    if counts.shape != (N_CATEGORIES,):
        raise ValueError("counts must have length %d" % N_CATEGORIES)
    if bool((counts < 0).any()):
        raise ValueError("counts must be nonnegative")
    if float(counts.sum()) <= 0.0:
        raise ValueError("empty training counts")
    pmf = (counts + laplace) / (counts.sum() + laplace * N_CATEGORIES)
    check_pmf(pmf)
    return pmf


def counts_from_outcomes(outcomes: list[int]) -> np.ndarray:
    counts = np.zeros(N_CATEGORIES)
    for k in outcomes:
        counts[_category(k)] += 1.0
    return counts


def _fit_preprocess(train_matrix: np.ndarray) -> dict:
    """Training-only median imputation + standardization parameters."""
    train_matrix = np.asarray(train_matrix, dtype=float)
    if train_matrix.size == 0:
        raise ValueError("empty training matrix")
    if bool(np.isnan(train_matrix).all(axis=0).any()):
        raise ValueError("imputation baseline undefined: all-null column")
    with np.errstate(all="ignore"):
        medians = np.nanmedian(train_matrix, axis=0)
    filled = np.where(np.isnan(train_matrix), medians, train_matrix)
    means = filled.mean(axis=0)
    scales = filled.std(axis=0)
    scales[scales == 0.0] = 1.0
    return {"medians": medians, "means": means, "scales": scales}


def _apply_preprocess(stats: dict, matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=float)
    filled = np.where(np.isnan(matrix), stats["medians"], matrix)
    return (filled - stats["means"]) / stats["scales"]


def build_risk_rows(n_values: np.ndarray,
                    max_n: int = N_MAX) -> tuple[np.ndarray, np.ndarray]:
    """Expand start-level outcomes to start-by-index Bernoulli rows.

    Returns (row_index, y) with y_j = 1{N == j} for j <= min(N, max_n).
    Starts with N > max_n contribute all-zero rows (overflow mass).
    N < 1 raises: below-support outcomes are corrupt input, not data.
    """
    n_values = np.asarray(n_values, dtype=int)
    if bool((n_values < 1).any()):
        raise ValueError("BF outcomes below support")
    rows, labels = [], []
    for i, n in enumerate(n_values):
        for j in range(1, min(int(n), max_n) + 1):
            rows.append((i, j))
            labels.append(1.0 if int(n) == j else 0.0)
    return np.array(rows, dtype=int), np.array(labels, dtype=float)


def fit_hazard(train_features: np.ndarray, train_n: np.ndarray,
               feature_names: list[str],
               candidate_index_levels: int = N_MAX,
               l2_c: float = 1.0) -> dict:
    """Fit the frozen L2 logistic termination hazard (synthetic/test use).

    Index one-hots (1..levels) + caller features; L2 C frozen. Real-data
    fitting requires the separately authorized scored diagnostic.
    """
    from sklearn.linear_model import LogisticRegression

    train_features = np.asarray(train_features, dtype=float)
    train_n = np.asarray(train_n, dtype=int)
    if len(train_features) != len(train_n):
        raise ValueError("features/outcomes length mismatch")
    if candidate_index_levels != N_MAX:
        raise ValueError("index levels must equal frozen N_MAX")
    stats = _fit_preprocess(train_features)
    standardized = _apply_preprocess(stats, train_features)
    rows, y = build_risk_rows(train_n)
    blocks = []
    for i, j in rows:
        one_hot = np.zeros(N_MAX)
        one_hot[j - 1] = 1.0
        blocks.append(np.concatenate([one_hot, standardized[i]]))
    design = np.array(blocks)
    model = LogisticRegression(C=l2_c, max_iter=5000)
    model.fit(design, y)
    return {"model": model, "preprocess": stats,
            "feature_names": list(feature_names), "l2_c": float(l2_c),
            "n_train_starts": int(len(train_n))}


def predict_pmf(bundle: dict, features: np.ndarray) -> np.ndarray:
    """Per-row 37-category PMFs from a fitted bundle (features only)."""
    features = np.asarray(features, dtype=float)
    standardized = _apply_preprocess(bundle["preprocess"], features)
    model = bundle["model"]
    out = np.empty((len(features), N_CATEGORIES))
    for r in range(len(features)):
        hazards = np.empty(N_MAX)
        for j in range(1, N_MAX + 1):
            one_hot = np.zeros(N_MAX)
            one_hot[j - 1] = 1.0
            row = np.concatenate([one_hot, standardized[r]])
            hazards[j - 1] = model.predict_proba(row.reshape(1, -1))[0, 1]
        out[r] = hazard_to_pmf(hazards)
    for r in range(len(features)):
        check_pmf(out[r])
    return out


def run_diagnostic(train_features: np.ndarray,
                   train_n: np.ndarray,
                   eval_features: np.ndarray,
                   eval_n: np.ndarray,
                   feature_names: list[str]) -> dict:
    """End-to-end synthetic diagnostic (injected frames only, no files).

    Fits the hazard + empirical baseline on train rows, scores eval
    rows, and returns metrics with mass/coverage checks. No real-data
    use; the scored real diagnostic needs separate authorization.
    """
    bundle = fit_hazard(train_features, train_n, feature_names)
    pmfs = predict_pmf(bundle, np.asarray(eval_features, dtype=float))
    eval_n = np.asarray(eval_n, dtype=int)
    base_counts = counts_from_outcomes(
        [int(v) for v in np.asarray(train_n, dtype=int)])
    base_pmf = empirical_baseline(base_counts)
    rps = [rps_score(p, int(k)) for p, k in zip(pmfs, eval_n)]
    nlls, clipped = zip(*[count_nll(p, int(k)) for p, k in zip(pmfs, eval_n)])
    briers = [short_outing_brier(p, int(k)) for p, k in zip(pmfs, eval_n)]
    base_rps = [rps_score(base_pmf, int(k)) for k in eval_n]
    intervals = [central_interval(p, 0.80) for p in pmfs]
    covered = [interval_covered(iv, int(k))
               for iv, k in zip(intervals, eval_n)]
    widths = [iv[2] for iv in intervals]
    return {
        "n_train": int(len(train_n)), "n_eval": int(len(eval_n)),
        "mean_rps": float(np.mean(rps)),
        "mean_nll": float(np.mean(nlls)),
        "nll_clipped": int(sum(clipped)),
        "mean_short_outing_brier": float(np.mean(briers)),
        "baseline_mean_rps": float(np.mean(base_rps)),
        "coverage_80": float(np.mean(covered)),
        "mean_width_80": float(np.mean(widths)),
        "mass_checks": True,
    }
