"""Post-hoc calibration of count-layer ``p_over_*`` probabilities.

Maps raw binomial/Poisson prop probabilities to calibrated probabilities
without retraining k-rate or TBF. Fits are chrono-safe: calibrators see only
prior-date outcomes.

Production apply keeps generative ``p_over_*`` intact and writes
``p_over_*_cal`` (+ metadata columns). Downstream edge / fair American odds
prefer calibrated columns when present.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

import joblib
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from Python import config
from Python.count_layer import DEFAULT_K_LINES, PROJECTION_K_LINES, over_threshold

MethodName = Literal["isotonic", "platt", "identity"]

EPS = 1e-6
MIN_LINE_N = 200
MIN_GLOBAL_N = 400
DEFAULT_CALIBRATION_LINES: tuple[float, ...] = DEFAULT_K_LINES  # 3.5…7.5

# Nearest trained line for board lines outside the fit set.
_NEAREST_LINE: dict[float, float] = {
    2.5: 3.5,
    8.5: 7.5,
    9.5: 7.5,
}


def line_to_stem(line: float) -> str:
    return str(line).replace(".", "_")


def p_over_col(line: float, *, calibrated: bool = False) -> str:
    stem = line_to_stem(line)
    return f"p_over_{stem}_cal" if calibrated else f"p_over_{stem}"


def clip_prob(p: np.ndarray | float) -> np.ndarray:
    return np.clip(np.asarray(p, dtype=np.float64), EPS, 1.0 - EPS)


def logit(p: np.ndarray) -> np.ndarray:
    p = clip_prob(p)
    return np.log(p / (1.0 - p))


def sigmoid(z: np.ndarray) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64)
    return 1.0 / (1.0 + np.exp(-np.clip(z, -50.0, 50.0)))


def outcome_over(actual_k: np.ndarray, line: float) -> np.ndarray:
    """Binary over-hit labels (half-lines: K > line)."""
    k = np.asarray(actual_k, dtype=np.float64)
    return (k >= over_threshold(line)).astype(np.float64)


def expected_calibration_error(
    y: np.ndarray,
    p: np.ndarray,
    *,
    n_bins: int = 10,
) -> tuple[float, list[dict[str, float]]]:
    """Equal-width probability bins; ECE = Σ |acc − conf| × weight."""
    y = np.asarray(y, dtype=np.float64)
    p = clip_prob(p)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[dict[str, float]] = []
    ece = 0.0
    n = len(y)
    if n == 0:
        return float("nan"), bins
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p <= hi) if i == n_bins - 1 else (p >= lo) & (p < hi)
        count = int(mask.sum())
        if count == 0:
            bins.append(
                {
                    "bin": i,
                    "lo": float(lo),
                    "hi": float(hi),
                    "n": 0,
                    "mean_prob": float("nan"),
                    "empirical": float("nan"),
                    "gap": float("nan"),
                }
            )
            continue
        mean_p = float(p[mask].mean())
        emp = float(y[mask].mean())
        gap = abs(emp - mean_p)
        ece += gap * (count / n)
        bins.append(
            {
                "bin": i,
                "lo": float(lo),
                "hi": float(hi),
                "n": count,
                "mean_prob": mean_p,
                "empirical": emp,
                "gap": gap,
            }
        )
    return float(ece), bins


def scoring_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float | None]:
    y = np.asarray(y, dtype=np.float64)
    p = clip_prob(p)
    out: dict[str, float | None] = {"n": float(len(y))}
    if len(y) < 5 or y.min() == y.max():
        out.update(
            {"brier": None, "log_loss": None, "auc": None, "ece": None, "bias_pp": None}
        )
        return out
    out["brier"] = float(brier_score_loss(y, p))
    out["log_loss"] = float(log_loss(y, p, labels=[0, 1]))
    try:
        out["auc"] = float(roc_auc_score(y, p))
    except ValueError:
        out["auc"] = None
    ece, _ = expected_calibration_error(y, p)
    out["ece"] = ece
    out["bias_pp"] = float(100.0 * (p.mean() - y.mean()))
    out["emp_rate"] = float(y.mean())
    out["mean_p"] = float(p.mean())
    return out


@dataclass
class LineCalibrator:
    """One-line or global probability map."""

    method: MethodName
    scope: str  # e.g. "line_4.5" or "global"
    line: float | None
    n_fit: int
    # Platt
    platt_a: float | None = None
    platt_b: float | None = None
    # Isotonic (parallel arrays)
    iso_x: list[float] = field(default_factory=list)
    iso_y: list[float] = field(default_factory=list)

    def transform(self, p_raw: np.ndarray) -> np.ndarray:
        p = clip_prob(p_raw)
        if self.method == "identity" or self.n_fit <= 0:
            return p
        if self.method == "platt":
            if self.platt_a is None or self.platt_b is None:
                return p
            return clip_prob(sigmoid(self.platt_a * logit(p) + self.platt_b))
        if self.method == "isotonic":
            if len(self.iso_x) < 2:
                return p
            return clip_prob(
                np.interp(p, np.asarray(self.iso_x), np.asarray(self.iso_y))
            )
        raise ValueError(f"unknown method {self.method!r}")


@dataclass
class ProbCalibrationBundle:
    """Versioned multi-line calibrator for production apply."""

    version: str
    method: MethodName
    fit_cutoff: str
    fit_source: str
    lines: list[float]
    min_line_n: int
    min_global_n: int
    created_utc: str
    line_maps: dict[str, LineCalibrator]  # keyed by line stem or "global"
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def resolve(self, line: float) -> tuple[LineCalibrator, str]:
        """Return (calibrator, scope_used) with fallback hierarchy."""
        stem = line_to_stem(line)
        if stem in self.line_maps:
            return self.line_maps[stem], f"line_{line}"
        nearest = _NEAREST_LINE.get(line)
        if nearest is not None:
            nstem = line_to_stem(nearest)
            if nstem in self.line_maps:
                return self.line_maps[nstem], f"nearest_{nearest}"
        if "global" in self.line_maps:
            return self.line_maps["global"], "global"
        # Identity fallback
        identity = LineCalibrator(
            method="identity", scope="identity", line=line, n_fit=0
        )
        return identity, "identity"


def fit_platt(p_raw: np.ndarray, y: np.ndarray) -> LineCalibrator:
    p = clip_prob(p_raw)
    y = np.asarray(y, dtype=np.float64)
    x = logit(p).reshape(-1, 1)
    # sklearn LogisticRegression on logit(p): P(y=1) = σ(A·logit(p)+B)
    clf = LogisticRegression(solver="lbfgs", max_iter=1000)
    clf.fit(x, y)
    a = float(clf.coef_.ravel()[0])
    b = float(clf.intercept_.ravel()[0])
    return LineCalibrator(
        method="platt",
        scope="fit",
        line=None,
        n_fit=int(len(y)),
        platt_a=a,
        platt_b=b,
    )


def fit_isotonic(p_raw: np.ndarray, y: np.ndarray) -> LineCalibrator:
    p = clip_prob(p_raw)
    y = np.asarray(y, dtype=np.float64)
    iso = IsotonicRegression(y_min=EPS, y_max=1.0 - EPS, out_of_bounds="clip")
    iso.fit(p, y)
    # Persist via thresholds for joblib-free transform reproducibility
    x_th = np.asarray(iso.X_thresholds_, dtype=np.float64)
    y_th = np.asarray(iso.y_thresholds_, dtype=np.float64)
    return LineCalibrator(
        method="isotonic",
        scope="fit",
        line=None,
        n_fit=int(len(y)),
        iso_x=x_th.tolist(),
        iso_y=y_th.tolist(),
    )


def fit_line_calibrator(
    p_raw: np.ndarray,
    y: np.ndarray,
    *,
    method: MethodName,
    line: float | None,
    scope: str,
) -> LineCalibrator:
    if method == "identity":
        return LineCalibrator(method="identity", scope=scope, line=line, n_fit=0)
    if method == "platt":
        cal = fit_platt(p_raw, y)
    elif method == "isotonic":
        cal = fit_isotonic(p_raw, y)
    else:
        raise ValueError(f"unsupported method {method!r}")
    cal.scope = scope
    cal.line = line
    return cal


def fit_bundle_from_arrays(
    *,
    method: MethodName,
    line_data: Mapping[float, tuple[np.ndarray, np.ndarray]],
    fit_cutoff: date | str,
    fit_source: str,
    version: str | None = None,
    min_line_n: int = MIN_LINE_N,
    min_global_n: int = MIN_GLOBAL_N,
    metrics: dict[str, Any] | None = None,
    notes: Sequence[str] | None = None,
) -> ProbCalibrationBundle:
    """Fit per-line maps (+ global) from ``{line: (p_raw, y)}`` dicts."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    version = version or f"prob_calibration_{method}_{stamp}"
    maps: dict[str, LineCalibrator] = {}
    lines_fit: list[float] = []
    note_list = list(notes or [])

    # Global pool
    all_p: list[np.ndarray] = []
    all_y: list[np.ndarray] = []
    for line, (p, y) in sorted(line_data.items()):
        p = np.asarray(p, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        if len(p) != len(y):
            raise ValueError(f"line {line}: p/y length mismatch")
        all_p.append(p)
        all_y.append(y)
        if len(y) >= min_line_n and y.min() != y.max():
            cal = fit_line_calibrator(
                p, y, method=method, line=line, scope=f"line_{line}"
            )
            maps[line_to_stem(line)] = cal
            lines_fit.append(float(line))
        else:
            note_list.append(
                f"line {line}: n={len(y)} < {min_line_n} or single-class — skip line map"
            )

    if all_p:
        gp = np.concatenate(all_p)
        gy = np.concatenate(all_y)
        if len(gy) >= min_global_n and gy.min() != gy.max():
            maps["global"] = fit_line_calibrator(
                gp, gy, method=method, line=None, scope="global"
            )
        else:
            note_list.append(
                f"global: n={len(gy)} insufficient or single-class — identity fallback"
            )
            maps["global"] = LineCalibrator(
                method="identity", scope="global", line=None, n_fit=int(len(gy))
            )

    cutoff = (
        fit_cutoff.isoformat() if isinstance(fit_cutoff, date) else str(fit_cutoff)
    )
    return ProbCalibrationBundle(
        version=version,
        method=method,
        fit_cutoff=cutoff,
        fit_source=fit_source,
        lines=lines_fit,
        min_line_n=min_line_n,
        min_global_n=min_global_n,
        created_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        line_maps=maps,
        metrics=dict(metrics or {}),
        notes=note_list,
    )


def transform_line(
    bundle: ProbCalibrationBundle,
    line: float,
    p_raw: np.ndarray,
) -> tuple[np.ndarray, str]:
    cal, scope = bundle.resolve(line)
    return cal.transform(p_raw), scope


def apply_prob_calibration(
    frame: Any,
    bundle: ProbCalibrationBundle,
    *,
    lines: Sequence[float] | None = None,
    inplace: bool = False,
) -> Any:
    """Add ``p_over_*_cal`` columns; leave raw ``p_over_*`` unchanged.

    Accepts pandas DataFrame (live scoring path).
    """
    import pandas as pd

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("apply_prob_calibration expects a pandas DataFrame")
    out = frame if inplace else frame.copy()
    line_set = tuple(lines) if lines is not None else PROJECTION_K_LINES
    scopes: list[str] = []
    for line in line_set:
        raw_col = p_over_col(line, calibrated=False)
        cal_col = p_over_col(line, calibrated=True)
        if raw_col not in out.columns:
            continue
        raw = out[raw_col].to_numpy(dtype=np.float64)
        cal, scope = transform_line(bundle, float(line), raw)
        out[cal_col] = cal
        scopes.append(f"{line}:{scope}")
    out["calibration_version"] = bundle.version
    out["calibration_method"] = bundle.method
    out["calibration_scope"] = ";".join(scopes) if scopes else "none"
    return out


def save_bundle(bundle: ProbCalibrationBundle, path: Path) -> tuple[Path, Path]:
    """Persist joblib + JSON sidecar under ``path`` stem."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib_path = path if path.suffix == ".joblib" else path.with_suffix(".joblib")
    json_path = joblib_path.with_suffix(".json")

    payload = {
        "version": bundle.version,
        "method": bundle.method,
        "fit_cutoff": bundle.fit_cutoff,
        "fit_source": bundle.fit_source,
        "lines": bundle.lines,
        "min_line_n": bundle.min_line_n,
        "min_global_n": bundle.min_global_n,
        "created_utc": bundle.created_utc,
        "metrics": bundle.metrics,
        "notes": bundle.notes,
        "line_maps": {
            key: asdict(cal) for key, cal in bundle.line_maps.items()
        },
    }
    joblib.dump(bundle, joblib_path)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return joblib_path, json_path


def load_bundle(path: Path) -> ProbCalibrationBundle:
    path = Path(path)
    joblib_path = path if path.suffix == ".joblib" else path.with_suffix(".joblib")
    obj = joblib.load(joblib_path)
    if isinstance(obj, ProbCalibrationBundle):
        return obj
    raise TypeError(f"unexpected calibrator type in {joblib_path}: {type(obj)}")


def default_bundle_path() -> Path | None:
    """Latest production pointer if present."""
    pointer = config.MODEL_DIR / "prob_calibration_production.json"
    if pointer.exists():
        meta = json.loads(pointer.read_text(encoding="utf-8"))
        stem = meta.get("joblib")
        if stem:
            path = Path(stem)
            if not path.is_absolute():
                path = config.MODEL_DIR / path
            if path.exists():
                return path
    cands = sorted(config.MODEL_DIR.glob("prob_calibration_*.joblib"))
    return cands[-1] if cands else None


def set_production_pointer(joblib_path: Path, *, meta: dict[str, Any] | None = None) -> Path:
    pointer = config.MODEL_DIR / "prob_calibration_production.json"
    payload = {
        "joblib": joblib_path.name,
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **(meta or {}),
    }
    pointer.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return pointer


def band_metrics(
    y: np.ndarray,
    p: np.ndarray,
    bands: Sequence[tuple[float, float, str]] | None = None,
) -> list[dict[str, Any]]:
    """Scoring within probability bands (e.g. 0.5–0.6, 0.6–0.7)."""
    if bands is None:
        bands = (
            (0.5, 0.6, "50-60"),
            (0.6, 0.7, "60-70"),
            (0.65, 0.75, "65-75"),
        )
    y = np.asarray(y, dtype=np.float64)
    p = clip_prob(p)
    rows = []
    for lo, hi, name in bands:
        mask = (p >= lo) & (p < hi)
        if mask.sum() < 5:
            rows.append({"band": name, "n": int(mask.sum())})
            continue
        m = scoring_metrics(y[mask], p[mask])
        m["band"] = name
        rows.append(m)
    return rows
