"""count-eval-v2 shared chronological comparison interface.

Implements COMPARISON_INTERFACE_SPEC.md (count-eval-v2-spec, registered
2026-10-15). One shared chronological comparison so every candidate is scored
on the SAME rows, SAME folds, SAME availability semantics, SAME metrics --
differing only in the model adapter.

Ground truth for features, windows, fitting dates and BF PMF construction:
extracted_feature_reality.md (extracted from executed code, cited file:line).
Incumbent being replayed: overnight-p2 scripts/run_ladder.py (LOG5 identity,
B_logreg 6-feature logistic, H3 8-feature logistic), which SUPERSEDES
p1-harness-v2 fit_models.py.

Synthetic-tests-first (spec section 7): harness/test_comparison.py must pass
before this runner is allowed near real inputs. No real-data fit or score is
authorized by this module alone (spec section 8). 2026 rows stay CLOSED.

Registered adapters here cover the PA lane only:
  P0_log5       full log5 identity on w150 priors + lg_rate (no fit, no scaler)
  P1_B_logreg   LogisticRegression(C=1.0, max_iter=1000) + StandardScaler
                (base_train only) on the 6 frozen B features
  P1_H3_replay  INCUMBENT REPLAY of the accepted baseline: same logistic spec
                on the 8 H3 features (reproduces the executed ladder fit
                procedure; it is not a new fit or a new search)
  P2_lgbm / B2_lgbm_catboost-style stubs / hierarchical:
                NotImplementedError stubs, registered NOT-STARTED.

BF-lane candidates (B0-B3) emit count PMFs through a different, separately
registered path (spec section 5 PMF chain); they are stubs here.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl

# ---------------------------------------------------------------------------
# Registered constants (spec sections 3, 6; run_ladder.py:45-47, 60-66)
# ---------------------------------------------------------------------------

INTERFACE_VERSION = "count-eval-v2-comparison-1.0"
SEED_BOOTSTRAP = 20261001
N_BOOT = 2000
EPS = 1e-15            # log-loss floor (run_ladder.py:45, 86-88)
LOG5_CLIP = 1e-9       # log5 input clip (run_ladder.py:77-83)

BASELINE_CANDIDATE = "P0_log5"
DEV_BLOCKS = ["block_2024H1", "block_2024H2", "block_2025H1"]
CONFIRM_BLOCK = "confirm_2025H2"

FEAT_B = [
    "p_pitcher_prior_w150", "p_batter_prior_w150", "lg_rate",
    "n_prior_pitcher", "n_prior_batter", "cold_start",
]
FEAT_H3 = FEAT_B + ["ew_pitcher", "ew_batter"]

# Fold anchors: train_end values (2023,12,31), (2024,6,30), (2024,12,31),
# (2025,6,30) and assessment windows, exactly run_ladder.py:60-66. Nominal
# calibration anchors are derived at runtime: cal_last = max game_date <=
# train_end; cal_first = cal_last - 59 days (run_ladder.py:145-151).
BLOCKS: dict[str, dict] = {
    "block_2024H1": {"train_end": (2023, 12, 31), "assess": ((2024, 1, 1), (2024, 6, 30))},
    "block_2024H2": {"train_end": (2024, 6, 30), "assess": ((2024, 7, 1), (2024, 12, 31))},
    "block_2025H1": {"train_end": (2024, 12, 31), "assess": ((2025, 1, 1), (2025, 6, 30))},
    "confirm_2025H2": {"train_end": (2025, 6, 30), "assess": ((2025, 7, 1), (2025, 9, 28))},
}
IDENTITY_COLS = ["game_pk", "at_bat_number", "batter"]


class ComparisonError(RuntimeError):
    """Base class: every interface guard fails loud."""


class DuplicateKeyError(ComparisonError):
    pass


class AvailabilityError(ComparisonError):
    pass


class AdapterContractError(ComparisonError):
    pass


class WriteOnceError(ComparisonError):
    pass


class FoldConstructionError(ComparisonError):
    pass


# ---------------------------------------------------------------------------
# sha256 helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def eval_identity_hash(keys_df: pl.DataFrame) -> str:
    """sha256 over sorted (game_pk, at_bat_number, batter) tuples, one
    'pk,ab,batter\\n' line each (definition of p1-harness-v2 fit_models.py:118-125)."""
    k = keys_df.select(IDENTITY_COLS).sort(IDENTITY_COLS)
    blob = "".join(f"{a},{b},{c}\n" for a, b, c in k.iter_rows()).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# PA-row loader (spec sections 1-2)
# ---------------------------------------------------------------------------

def load_pa_rows(
    pa_table_path: str | Path,
    features_path: str | Path,
    extra_cols: tuple[str, ...] = ("pitcher_role",),
) -> pl.DataFrame:
    """Load + join the PA-row grain: one row per completed plate appearance,
    identity (game_pk, at_bat_number, batter), unique, fail-loud on
    duplicates (build_pa_table.py:113; build_features.py:275-276).

    Default intent: p1-harness-v2 data\\pa_table.parquet + data\\features.parquet.
    NOTE the registered supersession: overnight-p2 features_v3.parquet is the
    canonical feature frame; this loader accepts any path so the canonical
    frame can be supplied. Adapters declare required columns and the join
    result is validated against them (fail loud on missing).

    Eligibility: game_date within 2023-01-01..2025-12-31; y present; 2026
    rows fail loud (spec section 8). The availability contract is enforced
    for every src_date_* / src_type_* style column present: source date
    non-null AND strictly < game_date; null source types fail
    (build_features.py:225-245).
    """
    pa = pl.read_parquet(pa_table_path)
    feat = pl.read_parquet(features_path)
    for name, df in (("pa_table", pa), ("features", feat)):
        dup = (
            df.group_by(IDENTITY_COLS).len().filter(pl.col("len") > 1)
        )
        if dup.height > 0:
            raise DuplicateKeyError(
                f"{name}: duplicate (game_pk, at_bat_number, batter) identity: "
                f"{dup.height} key(s) with >1 row (first: {dup.head(1).rows()})"
            )
        missing = [c for c in [*IDENTITY_COLS, "game_date"] if c not in df.columns]
        if missing:
            raise ComparisonError(f"{name}: missing required columns {missing}")
    if "y" not in pa.columns:
        raise ComparisonError("pa_table: label column 'y' missing")

    keep = [*IDENTITY_COLS, "game_date", "y", *extra_cols]
    keep = [c for c in keep if c in feat.columns or c in pa.columns]
    df = (
        feat.select([c for c in feat.columns if c in keep or c not in pa.columns])
        .join(pa.select([c for c in keep if c in pa.columns]), on=IDENTITY_COLS,
              how="inner", suffix="_pa")
    )
    if df.height != feat.height:
        raise ComparisonError(
            f"join dropped rows: features {feat.height} -> joined {df.height} "
            "(identity mismatch between pa_table and features)"
        )
    # deduplicate columns that came from both frames (first non-null wins is
    # not used; overlap is only allowed for columns selected from features)
    drop = [c for c in df.columns if c.endswith("_pa")]
    if drop:
        df = df.drop(drop)

    # 2026 closed; eligible frame 2023-01-01..2025-12-31 (build_pa_table.py)
    n26 = df.filter(pl.col("game_date") >= pl.date(2026, 1, 1)).height
    if n26:
        raise ComparisonError(f"2026 rows are CLOSED: {n26} row(s) present")
    df = df.filter(
        (pl.col("game_date") >= pl.date(2023, 1, 1))
        & (pl.col("game_date") <= pl.date(2025, 12, 31))
    )
    if df.filter(pl.col("y").is_null()).height:
        raise ComparisonError("null labels after eligibility filter")

    enforce_availability_guard(df)
    return df


def enforce_availability_guard(df: pl.DataFrame) -> None:
    """Binding availability contract (spec section 2; build_features.py:225-245):
    every source date non-null AND strictly < game_date; null source types
    FAIL. Applies to any column containing 'src_date' or 'src_type'. Re-run on
    eval frames at score time (adapter contract, spec section 4)."""
    date_cols = [c for c in df.columns if "src_date" in c]
    type_cols = [c for c in df.columns if "src_type" in c]
    if "game_date" not in df.columns:
        raise AvailabilityError("game_date column missing; cannot check availability")
    for c in date_cols:
        bad = df.filter(pl.col(c).is_null() | (pl.col(c) >= pl.col("game_date")))
        if bad.height:
            raise AvailabilityError(
                f"availability guard: {bad.height} row(s) with {c} null or "
                f">= game_date (no own-game updates, no same-date state)"
            )
    for c in type_cols:
        bad = df.filter(pl.col(c).is_null())
        if bad.height:
            raise AvailabilityError(
                f"availability guard: {bad.height} row(s) with null {c}"
            )


# ---------------------------------------------------------------------------
# Folds (spec section 3; run_ladder.py:60-66, 142-153)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Fold:
    name: str
    train_start: dt.date
    train_end: dt.date          # base_train is [train_start, cal_first)
    cal_first: dt.date
    cal_last: dt.date
    assess_start: dt.date
    assess_end: dt.date
    eval_identity_hash: str = ""
    n_train: int = 0
    n_cal: int = 0
    n_eval: int = 0
    n_eval_dates: int = 0

    def metadata(self) -> dict:
        return {
            "block": self.name,
            "train_window": [str(self.train_start), str(self.cal_first)],
            "calibration_span": [str(self.cal_first), str(self.cal_last)],
            "assessment_window": [str(self.assess_start), str(self.assess_end)],
            "eval_identity_sha256": self.eval_identity_hash,
            "rows": {"base_train": self.n_train, "calibration": self.n_cal,
                     "assessment": self.n_eval},
            "assessment_dates": self.n_eval_dates,
        }


def derive_folds(df: pl.DataFrame) -> dict[str, Fold]:
    """Derive the four registered folds with runtime calibration spans.

    confirm_2025H2 is present in the returned dict but is executed LAST by
    run_comparison and never pooled into dev (run_ladder.py:66, 329, 369).
    """
    folds: dict[str, Fold] = {}
    for name, spec in BLOCKS.items():
        te_y, te_m, te_d = spec["train_end"]
        a0 = dt.date(*spec["assess"][0])
        a1 = dt.date(*spec["assess"][1])
        in_train_span = df.filter(
            (pl.col("game_date") >= pl.date(2023, 1, 1))
            & (pl.col("game_date") <= pl.date(te_y, te_m, te_d))
        )
        cal_last = in_train_span["game_date"].max()
        if cal_last is None:
            raise FoldConstructionError(f"{name}: no rows on/before train_end")
        cal_first = cal_last - dt.timedelta(days=59)
        train = df.filter(
            (pl.col("game_date") >= pl.date(2023, 1, 1)) & (pl.col("game_date") < cal_first)
        )
        cal = df.filter(
            (pl.col("game_date") >= cal_first) & (pl.col("game_date") <= cal_last)
        )
        assess = df.filter(
            (pl.col("game_date") >= a0) & (pl.col("game_date") <= a1)
        )
        if train.height == 0 or cal.height == 0 or assess.height == 0:
            raise FoldConstructionError(
                f"{name}: empty partition (train={train.height}, cal={cal.height}, "
                f"eval={assess.height})"
            )
        if train.filter(pl.col("game_date") >= cal_first).height:
            raise FoldConstructionError(f"{name}: train/cal overlap")
        folds[name] = Fold(
            name=name, train_start=dt.date(2023, 1, 1), train_end=cal_last,
            cal_first=cal_first, cal_last=cal_last, assess_start=a0, assess_end=a1,
            eval_identity_hash=eval_identity_hash(assess),
            n_train=train.height, n_cal=cal.height, n_eval=assess.height,
            n_eval_dates=assess["game_date"].n_unique(),
        )
    return folds


# ---------------------------------------------------------------------------
# Adapter contract (spec section 4)
# ---------------------------------------------------------------------------

@dataclass
class FittedSpec:
    """What an adapter's fit stage stores. Logistic adapters keep the scaler
    + model; no-fit adapters keep nothing."""


class ModelAdapter:
    """Adapter contract: fit on train rows ONLY, calibrate on the calibration
    sub-block ONLY, predict RAW probabilities in [0,1] of shape (n_eval,).
    Preprocessing lives inside the adapter and is recorded in the run config.
    Fixed seeds/hyperparameters; no search."""

    name: str = "unset"
    required_features: tuple[str, ...] = ()
    status: str = "IMPLEMENTED-ADAPTER"

    def fit(self, fold_name: str, X_train: np.ndarray, y_train: np.ndarray):
        raise NotImplementedError

    def calibrate(self, fold_name: str, fitted, X_cal: np.ndarray, y_cal: np.ndarray):
        raise NotImplementedError

    def predict_proba(self, fold_name: str, calibrated, X_eval: np.ndarray) -> np.ndarray:
        raise NotImplementedError


def _check_proba(p: np.ndarray, n_expected: int, where: str) -> np.ndarray:
    p = np.asarray(p, dtype=np.float64)
    if p.ndim != 1 or p.shape[0] != n_expected:
        raise AdapterContractError(
            f"{where}: predict_proba must return shape ({n_expected},), got {p.shape}"
        )
    if not np.all(np.isfinite(p)) or np.any(p < 0.0) or np.any(p > 1.0):
        raise AdapterContractError(f"{where}: probabilities outside [0,1] or non-finite")
    return p


def log5(p_p, p_b, l, eps: float = LOG5_CLIP) -> np.ndarray:
    """Full log5 identity with league rate (run_ladder.py:77-83; identical in
    p1-harness-v2 fit_models.py:86-96), pinned by test_log5_identities.py:
    p=b=l -> q=l; p=l -> q=b; b=l -> q=p (tol 1e-12). Inputs clipped to
    [eps, 1-eps]. No fitting."""
    p = np.clip(np.asarray(p_p, dtype=np.float64), eps, 1.0 - eps)
    b = np.clip(np.asarray(p_b, dtype=np.float64), eps, 1.0 - eps)
    lg = np.clip(np.asarray(l, dtype=np.float64), eps, 1.0 - eps)
    num = p * b * (1.0 - lg)
    den = num + (1.0 - p) * (1.0 - b) * lg
    return num / den


class Log5BaselineAdapter(ModelAdapter):
    """P0: full log5 identity on w150 priors + lg_rate; no fit, no scaler
    (extracted_feature_reality.md section 2; run_ladder.py:77-83)."""

    name = "P0_log5"
    required_features = ("p_pitcher_prior_w150", "p_batter_prior_w150", "lg_rate")

    def fit(self, fold_name, X_train, y_train):
        return None

    def calibrate(self, fold_name, fitted, X_cal, y_cal):
        return None

    def predict_proba(self, fold_name, calibrated, X_eval):
        return log5(X_eval[:, 0], X_eval[:, 1], X_eval[:, 2])


class LogisticAdapter(ModelAdapter):
    """P1 family: LogisticRegression(C=1.0, max_iter=1000) on a frozen feature
    list with StandardScaler fit on base_train ONLY, one scaler per fold
    (run_ladder.py:172-181). Sigmoid calibrator (1-D unpenalized logistic of y
    on logit(p)) fit on the calibration sub-block ONLY (run_ladder.py:109-119,
    192-200); raw and calibrated lanes are kept separate.

    P1_H3_replay is the INCUMBENT REPLAY: it reproduces the accepted baseline
    fit procedure of the executed overnight-p2 H3 ladder candidate. It is not
    a new fit, not a search, and claims no new evidence."""

    def __init__(self, name: str, features: tuple[str, ...], incumbent_replay: bool = False):
        self.name = name
        self.required_features = tuple(features)
        self.incumbent_replay = incumbent_replay

    def fit(self, fold_name, X_train, y_train):
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler().fit(X_train)
        lr = LogisticRegression(C=1.0, max_iter=1000)
        lr.fit(scaler.transform(X_train), y_train)
        return {"scaler": scaler, "lr": lr, "fold": fold_name,
                "n_train": int(y_train.size)}

    def calibrate(self, fold_name, fitted, X_cal, y_cal):
        p = fitted["lr"].predict_proba(fitted["scaler"].transform(X_cal))[:, 1]
        a, b = sigmoid_fit(y_cal, p)
        return {"intercept": a, "slope": b, "n_cal": int(y_cal.size)}

    def predict_proba(self, fold_name, calibrated, X_eval):
        # stored fitted model is re-attached by the runner via `fitted_ref`
        raise RuntimeError("internal: use predict_raw/predict_cal helpers")


class _LogisticHelperMixin:
    """The runner calls these explicit hooks so raw vs calibrated lanes stay
    separate artifacts (spec section 4; run_ladder.py:280-289)."""


def _logistic_raw(adapter: LogisticAdapter, fitted, X_eval) -> np.ndarray:
    return fitted["lr"].predict_proba(fitted["scaler"].transform(X_eval))[:, 1]


def _logistic_cal(adapter: LogisticAdapter, fitted, calibrator, X_eval) -> np.ndarray:
    p_raw = _logistic_raw(adapter, fitted, X_eval)
    return sigmoid_apply(p_raw, calibrator["intercept"], calibrator["slope"])


LogisticAdapter.predict_raw = _logistic_raw          # type: ignore[attr-defined]
LogisticAdapter.predict_cal = _logistic_cal          # type: ignore[attr-defined]
LogisticAdapter.raw_lane = staticmethod(_logistic_raw)   # type: ignore[attr-defined]


class ConstantAdapter(ModelAdapter):
    """Synthetic-test adapter: constant probability; fit/calibrate are no-ops."""

    def __init__(self, name: str, p: float):
        self.name = name
        self.required_features = ()
        self._p = float(p)

    def fit(self, fold_name, X_train, y_train):
        return None

    def calibrate(self, fold_name, fitted, X_cal, y_cal):
        return None

    def predict_proba(self, fold_name, calibrated, X_eval):
        return np.full(X_eval.shape[0], self._p)


class NotImplementedAdapter(ModelAdapter):
    """Registered stub for NOT-STARTED candidates: fails loud with the
    registered candidate ID (spec section 5; execution gate section 8)."""

    def __init__(self, name: str, message: str = ""):
        self.name = name
        self.required_features = ()
        self.status = "NOT-STARTED"
        self._message = message

    def fit(self, fold_name, X_train, y_train):
        raise NotImplementedError(
            f"candidate {self.name} is registered NOT-STARTED "
            f"(COMPARISON_INTERFACE_SPEC.md section 5); no adapter implemented. "
            f"{self._message}".strip()
        )


# ---------------------------------------------------------------------------
# Calibration helpers (run_ladder.py:109-119)
# ---------------------------------------------------------------------------

def sigmoid_fit(y, p):
    z = np.log(np.clip(p, EPS, 1 - EPS) / (1 - np.clip(p, EPS, 1 - EPS)))
    from sklearn.linear_model import LogisticRegression
    lr = LogisticRegression(C=np.inf, max_iter=1000)
    lr.fit(z.reshape(-1, 1), y)
    return float(lr.intercept_[0]), float(lr.coef_[0][0])


def sigmoid_apply(p, intercept, slope):
    z = np.log(np.clip(p, EPS, 1 - EPS) / (1 - np.clip(p, EPS, 1 - EPS)))
    return 1.0 / (1.0 + np.exp(-(intercept + slope * z)))


# ---------------------------------------------------------------------------
# Metrics (spec section 6; run_ladder.py:86-106; repaired block-stratified
# bootstrap = port of market_eval.py _slate_bootstrap C3 repair, verified by
# the F-1 re-review e4de344: within each block the replicate draws exactly
# that block's original slate-date count of dates with replacement, blocks
# combined row-weighted num/den; ONE draw stream shared across candidates)
# ---------------------------------------------------------------------------

def log_loss(y, p):
    p = np.clip(np.asarray(p, dtype=np.float64), EPS, 1 - EPS)
    y = np.asarray(y, dtype=np.float64)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def brier(y, p):
    return (np.asarray(p, dtype=np.float64) - np.asarray(y, dtype=np.float64)) ** 2


def slate_date_bootstrap(values: dict, dates, blocks, n_boot: int = N_BOOT,
                         seed: int = SEED_BOOTSTRAP) -> dict:
    """Paired slate-date bootstrap, BLOCK-STRATIFIED (repaired method).

    values: name -> per-row paired metric array aligned with `dates` and
    `blocks` (blocks may be fold names or development block labels). One rng
    stream (seed 20261001); the date draws per block per resample are shared
    across ALL names, so resample indices are identical across candidates.
    Returns per-name point estimate + percentile CI on the per-row scale.
    """
    import numpy as _np
    rng = _np.random.default_rng(seed)
    names = list(values)
    mat = _np.vstack([_np.asarray(values[n], dtype=_np.float64) for n in names])
    blocks_arr = _np.asarray(blocks, dtype=object)
    num = _np.zeros((n_boot, mat.shape[0]), dtype=_np.float64)
    den = _np.zeros(n_boot, dtype=_np.float64)
    for b in sorted(set(blocks)):
        mask = _np.array([x == b for x in blocks], dtype=bool)
        row_idx = _np.nonzero(mask)[0]
        b_dates = sorted(set(dates[i] for i in row_idx))
        idx_of = {d: i for i, d in enumerate(b_dates)}
        d_idx = _np.array([idx_of[dates[i]] for i in row_idx], dtype=_np.int64)
        n_dates_b = len(b_dates)
        b_sums = _np.vstack([
            _np.bincount(d_idx, weights=mat[m][mask], minlength=n_dates_b)
            for m in range(mat.shape[0])
        ])
        b_counts = _np.bincount(d_idx, minlength=n_dates_b).astype(_np.float64)
        draws = rng.multinomial(
            n_dates_b, _np.full(n_dates_b, 1.0 / n_dates_b), size=n_boot
        )
        num += draws @ b_sums.T
        den += draws @ b_counts
    res = num / den[:, None]
    out = {}
    for j, n in enumerate(names):
        v = res[:, j]
        out[n] = {
            "point": float(mat[j].mean()),
            "ci95": [float(_np.percentile(v, 2.5)), float(_np.percentile(v, 97.5))],
        }
    out["_meta"] = {
        "method": "slate-date, block-stratified, row-weighted ratio (num/den)",
        "n_resamples": int(n_boot), "seed": int(seed),
        "unit": "game_date", "shared_draws_across_names": True,
    }
    return out


# ---------------------------------------------------------------------------
# Registered adapter set
# ---------------------------------------------------------------------------

def registered_adapters() -> dict[str, ModelAdapter]:
    """The registered PA-lane adapter set (spec section 5)."""
    return {
        "P0_log5": Log5BaselineAdapter(),
        "P1_B_logreg": LogisticAdapter("P1_B_logreg", tuple(FEAT_B)),
        "P1_H3_replay": LogisticAdapter(
            "P1_H3_replay", tuple(FEAT_H3), incumbent_replay=True),
        "P2_lgbm": NotImplementedAdapter(
            "P2_lgbm",
            "LightGBM binary classifier; monotone-constraint policy must be "
            "frozen in config BEFORE any fit."),
        "B1_ridge_bf": NotImplementedAdapter(
            "B1_ridge_bf",
            "BF-lane: Ridge replacing the BF-PMF-producing model's fit stage; "
            "must emit the identical PMF artifact shape."),
        "B2_lgbm_bf": NotImplementedAdapter(
            "B2_lgbm_bf",
            "BF-lane: LightGBM regressor in the same seam as B1."),
        "B3_exit_hazard": NotImplementedAdapter(
            "B3_exit_hazard",
            "BF-lane: discrete exit-hazard over BF 1..36; hazard vector must "
            "feed extend_overflow_with_hazard."),
        "H_hierarchical": NotImplementedAdapter(
            "H_hierarchical",
            "hierarchical placeholder: PLACEHOLDER-NOT-IMPLEMENTED."),
    }


# ---------------------------------------------------------------------------
# Runner (spec section 6: write-once outputs with run identity)
# ---------------------------------------------------------------------------

@dataclass
class RunConfig:
    pa_table_path: str
    features_path: str
    candidates: list[str] = field(default_factory=lambda: [
        "P0_log5", "P1_B_logreg", "P1_H3_replay"])
    baseline: str = BASELINE_CANDIDATE
    n_boot: int = N_BOOT
    seed: int = SEED_BOOTSTRAP
    output_root: str = "outputs"
    run_label: str = ""

    def canonical(self) -> dict:
        return {
            "interface_version": INTERFACE_VERSION,
            "pa_table_path": str(self.pa_table_path),
            "features_path": str(self.features_path),
            "candidates": list(self.candidates),
            "baseline": self.baseline,
            "n_boot": self.n_boot,
            "seed": self.seed,
            "run_label": self.run_label,
            "blocks": {k: {"train_end": v["train_end"], "assess": v["assess"]}
                       for k, v in BLOCKS.items()},
            "dev_blocks": list(DEV_BLOCKS),
        }


def _feature_matrix(part: pl.DataFrame, adapter: ModelAdapter) -> np.ndarray:
    """Feature matrix for an adapter; zero-feature adapters get an (n, 0)
    matrix so adapters can still read the row count."""
    if adapter.required_features:
        return part.select(adapter.required_features).to_numpy()
    return np.empty((part.height, 0), dtype=np.float64)


def _candidate_columns(adapter: ModelAdapter, fitted, calibrator, X: np.ndarray) -> dict:
    """Raw lane is principal; calibrated lane is a SEPARATE recorded column
    (run_ladder.py:280-289)."""
    if isinstance(adapter, (LogisticAdapter,)):
        raw = adapter.predict_raw(fitted, X)
        cal = adapter.predict_cal(fitted, calibrator, X) if calibrator else None
    else:
        raw = adapter.predict_proba(None, None, X)
        cal = None
    raw = _check_proba(raw, X.shape[0], adapter.name)
    if cal is not None:
        cal = _check_proba(cal, X.shape[0], f"{adapter.name}.cal")
    return {"pred_raw": raw, "pred_cal": cal}


def run_comparison(cfg: RunConfig) -> Path:
    """Execute every registered candidate on identical rows/folds and write
    write-once outputs under <output_root>/<run_id>/. Never overwrites a
    prior run. Returns the output directory."""
    adapters = registered_adapters()
    unknown = [c for c in cfg.candidates if c not in adapters]
    if unknown:
        raise ComparisonError(f"unregistered candidate IDs: {unknown}")

    pa_sha = sha256_file(cfg.pa_table_path)
    feat_sha = sha256_file(cfg.features_path)
    cfg_canon = cfg.canonical()
    identity = {
        "run_identity": cfg_canon,
        "input_sha256": {"pa_table": pa_sha, "features": feat_sha},
    }
    run_id = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()

    out_dir = Path(cfg.output_root) / run_id
    if out_dir.exists():
        raise WriteOnceError(
            f"write-once violation: output dir {out_dir} already exists "
            "(never overwrite a prior run; use a new config/run_label)")
    out_dir.mkdir(parents=True)

    df = load_pa_rows(cfg.pa_table_path, cfg.features_path)
    folds = derive_folds(df)
    fold_order = DEV_BLOCKS + [CONFIRM_BLOCK]

    manifest = {
        "interface_version": INTERFACE_VERSION,
        "run_id": run_id,
        "run_label": cfg.run_label,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "inputs_sha256": identity["input_sha256"],
        "config": cfg_canon,
        "versions": {
            "python": platform.python_version(),
            "polars": pl.__version__,
            "numpy": np.__version__,
        },
        "folds": {n: folds[n].metadata() for n in fold_order},
        "candidates": {},
        "execution_order_note": (
            "dev folds then confirm_2025H2 LAST; confirm never pooled into dev "
            "(run_ladder.py:66, 329, 369)"),
        "synthetic_gate": "test_comparison.py must pass before any real-data run "
                          "(spec section 7); no real-data authorization granted here",
    }

    eval_frames: dict[str, pl.DataFrame] = {}
    for fname in fold_order:
        fold = folds[fname]
        train = df.filter(
            (pl.col("game_date") >= pl.date(fold.train_start.year, fold.train_start.month, fold.train_start.day))
            & (pl.col("game_date") < pl.date(fold.cal_first.year, fold.cal_first.month, fold.cal_first.day))
        )
        cal = df.filter(
            (pl.col("game_date") >= pl.date(fold.cal_first.year, fold.cal_first.month, fold.cal_first.day))
            & (pl.col("game_date") <= pl.date(fold.cal_last.year, fold.cal_last.month, fold.cal_last.day))
        )
        eval_df = df.filter(
            (pl.col("game_date") >= pl.date(fold.assess_start.year, fold.assess_start.month, fold.assess_start.day))
            & (pl.col("game_date") <= pl.date(fold.assess_end.year, fold.assess_end.month, fold.assess_end.day))
        )
        enforce_availability_guard(eval_df)  # section 4: guard re-run on eval frame
        y_tr = train["y"].to_numpy().astype(int)
        y_ca = cal["y"].to_numpy().astype(int)
        y_ev = eval_df["y"].to_numpy().astype(int)
        eval_frames[fname] = eval_df

        per_cand_hashes = {}
        for cand in cfg.candidates:
            adapter = adapters[cand]
            missing = [c for c in adapter.required_features
                       if c not in eval_df.columns]
            if missing:
                raise ComparisonError(
                    f"candidate {cand}: required feature columns missing from "
                    f"loaded frame: {missing} (note: the canonical 8-feature H3 "
                    f"set lives in overnight-p2 data\\features_v3.parquet, which "
                    f"SUPERSEDES the p1-harness-v2 features frame)")
            X_tr = _feature_matrix(train, adapter)
            X_ca = _feature_matrix(cal, adapter)
            X_ev = _feature_matrix(eval_df, adapter)
            fitted = adapter.fit(fname, X_tr, y_tr)
            calibrator = adapter.calibrate(fname, fitted, X_ca, y_ca)
            cols = _candidate_columns(adapter, fitted, calibrator, X_ev)
            preds = eval_df.select(
                *IDENTITY_COLS, "game_date", "y",
            ).with_columns([
                pl.Series("pred_raw", cols["pred_raw"], dtype=pl.Float64),
                pl.Series(
                    "pred_cal",
                    (cols["pred_cal"] if cols["pred_cal"] is not None
                     else [None] * X_ev.shape[0]),
                    dtype=pl.Float64),
            ])
            meta = json.dumps({
                "run_id": run_id, "fold": fold.name,
                "eval_identity_sha256": fold.eval_identity_hash,
                "candidate": cand, "candidate_status": adapter.status,
                "raw_lane_only_note": "pred_raw principal; pred_cal separate lane",
            }).encode("utf-8")
            preds.write_parquet(
                out_dir / f"preds_{fname}__{cand}.parquet",
                metadata={"run_metadata": meta.decode("utf-8")},
            )
            per_cand_hashes[cand] = fold.eval_identity_hash
            manifest["candidates"].setdefault(cand, {})[fname] = {
                "eval_identity_sha256": fold.eval_identity_hash,
                "features": list(adapter.required_features),
                "status": adapter.status,
                "preds_file": f"preds_{fname}__{cand}.parquet",
            }
        if len(set(per_cand_hashes.values())) != 1:
            raise ComparisonError("eval-row identity hash differs across candidates")

    metrics = _compute_metrics(cfg, df, folds, eval_frames, adapters, out_dir)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (out_dir / "metrics.md").write_text(_metrics_md(metrics))
    manifest["metrics_files"] = ["metrics.json", "metrics.md"]
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2))
    return out_dir


def _compute_metrics(cfg, df, folds, eval_frames, adapters, out_dir) -> dict:
    base = cfg.baseline

    def fold_metrics(fname: str, cand: str) -> dict:
        p = pl.read_parquet(out_dir / f"preds_{fname}__{cand}.parquet")
        y = p["y"].to_numpy().astype(int)
        pr = p["pred_raw"].to_numpy()
        dates = p["game_date"].to_numpy()
        return {
            "n": int(y.size), "n_dates": int(_n_unique(dates)),
            "log_loss": float(log_loss(y, pr).mean()),
            "brier": float(brier(y, pr).mean()),
            "_per_row_ll": log_loss(y, pr), "_per_row_brier": brier(y, pr),
            "_dates": dates,
        }

    out: dict = {"baseline": base, "bootstrap": {
        "method": "slate-date block-stratified row-weighted ratio",
        "n_resamples": cfg.n_boot, "seed": cfg.seed},
        "per_fold": {}, "pooled_dev": {}, "confirm_separate_note":
        "confirm_2025H2 reported separately; never pooled into dev"}
    for fname in DEV_BLOCKS + [CONFIRM_BLOCK]:
        out["per_fold"][fname] = {}
        cand_stats = {c: fold_metrics(fname, c) for c in cfg.candidates}
        for c in cfg.candidates:
            s = cand_stats[c]
            out["per_fold"][fname][c] = {
                "n": s["n"], "n_dates": s["n_dates"],
                "log_loss": s["log_loss"], "brier": s["brier"],
            }
        if base in cand_stats and len(cfg.candidates) > 1:
            bs = cand_stats[base]
            ll_vals, br_vals = {}, {}
            for c in cfg.candidates:
                if c == base:
                    continue
                s = cand_stats[c]
                ll_vals[f"{c}_minus_{base}"] = s["_per_row_ll"] - bs["_per_row_ll"]
                br_vals[f"{c}_minus_{base}"] = s["_per_row_brier"] - bs["_per_row_brier"]
            dates = cand_stats[cfg.candidates[0]]["_dates"]
            blocks = [fname] * len(dates)
            out["per_fold"][fname]["paired_vs_baseline"] = {
                "log_loss": slate_date_bootstrap(ll_vals, dates, blocks, cfg.n_boot, cfg.seed),
                "brier": slate_date_bootstrap(br_vals, dates, blocks, cfg.n_boot, cfg.seed),
            }

    # pooled dev: concat dev folds ONLY (never confirm_2025H2)
    pooled_frames = {
        c: pl.concat([pl.read_parquet(out_dir / f"preds_{f}__{c}.parquet")
                      for f in DEV_BLOCKS]) for c in cfg.candidates}
    pool_blocks, pool_dates = [], []
    for f in DEV_BLOCKS:
        n = folds[f].n_eval
        pool_blocks.extend([f] * n)
    y_pool = pooled_frames[cfg.candidates[0]]["y"].to_numpy().astype(int)
    pool_dates = pooled_frames[cfg.candidates[0]]["game_date"].to_numpy()
    ll_vals, br_vals, point = {}, {}, {}
    base_raw = (pooled_frames[base]["pred_raw"].to_numpy()
                if base in pooled_frames else None)
    for c in cfg.candidates:
        pr = pooled_frames[c]["pred_raw"].to_numpy()
        point[c] = {"n": int(y_pool.size),
                    "n_dates": int(_n_unique(pool_dates)),
                    "log_loss": float(log_loss(y_pool, pr).mean()),
                    "brier": float(brier(y_pool, pr).mean())}
        if c != base and base_raw is not None:
            ll_vals[f"{c}_minus_{base}"] = log_loss(y_pool, pr) - log_loss(y_pool, base_raw)
            br_vals[f"{c}_minus_{base}"] = brier(y_pool, pr) - brier(y_pool, base_raw)
    out["pooled_dev"] = {
        "blocks_pooled": list(DEV_BLOCKS), "note":
            "dev blocks only; confirm_2025H2 never pooled (run_ladder.py:314-334)",
        "candidates": point,
    }
    if ll_vals:
        out["pooled_dev"]["paired_vs_baseline"] = {
            "log_loss": slate_date_bootstrap(ll_vals, pool_dates, pool_blocks, cfg.n_boot, cfg.seed),
            "brier": slate_date_bootstrap(br_vals, pool_dates, pool_blocks, cfg.n_boot, cfg.seed),
        }
    return out


def _n_unique(dates) -> int:
    import numpy as _np
    return int(_np.unique(dates).size)


def _metrics_md(m: dict) -> str:
    lines = ["# count-eval-v2 comparison metrics", "",
             f"Baseline: `{m['baseline']}`; bootstrap {m['bootstrap']['n_resamples']} "
             f"resamples, seed {m['bootstrap']['seed']}, block-stratified "
             f"slate-date (repaired method).", ""]
    for fold, rows in m["per_fold"].items():
        lines.append(f"## {fold}")
        lines.append("")
        lines.append("| candidate | n | dates | log loss | Brier |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for cand, s in rows.items():
            if cand == "paired_vs_baseline":
                continue
            lines.append(
                f"| {cand} | {s['n']} | {s['n_dates']} | "
                f"{s['log_loss']:.6f} | {s['brier']:.6f} |")
        lines.append("")
    pd = m["pooled_dev"]
    lines.append(f"## pooled dev ({', '.join(pd['blocks_pooled'])})")
    lines.append("")
    lines.append("| candidate | n | dates | log loss | Brier |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for cand, s in pd["candidates"].items():
        lines.append(f"| {cand} | {s['n']} | {s['n_dates']} | "
                     f"{s['log_loss']:.6f} | {s['brier']:.6f} |")
    lines.append("")
    lines.append("confirm_2025H2 is reported per-fold only and is never pooled "
                 "into dev.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(__doc__)
    sys.exit(0)
