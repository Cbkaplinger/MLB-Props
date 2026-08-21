"""Evaluate strikeout count props: frozen k-rate × projected TBF.

Fits / loads:
- LightGBM production k-rate (frozen booster when available, else refit)
- Ridge projected TBF (thin bullpen; always fit on the train partition)

Baselines for ``expected_K``:
- ``k_rate × projected_tbf`` (primary)
- ``k_rate × PA_P5``
- ``k_rate × train_mean_PA``

Example:
    python models/Strikeout-Model/score_count_layer.py
    python models/Strikeout-Model/score_count_layer.py --k-rate-model artifacts/models/lightgbm_krate_20260727_204342.txt
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from Python.config import (
    MODEL_DIR,
    OUTPUT_DIR,
    PITCHER_TRAINING_PATH,
    TRAIN_SEASONS,
    ensure_output_directories,
)
from Python.count_layer import (
    DEFAULT_K_LINES,
    attach_count_predictions,
    count_point_metrics,
    evaluate_count_layer,
    expected_strikeouts,
    fit_count_layer_kappa,
)
from Python.registries import resolve_feature_names
from Python.tbf import (
    TBF_DEFAULT_FEATURE_SET,
    TBF_TARGET,
    assert_tbf_label_not_in_features,
    tbf_feature_names,
)
from Python.training import (
    assert_pa_not_in_features,
    build_model,
    chronological_split,
    fit_regressor,
    lightgbm_matrix,
    predict_clipped,
    predict_nonnegative,
)

try:
    import lightgbm as lgb
except ImportError:  # pragma: no cover
    lgb = None

_DEFAULT_KRATE = MODEL_DIR / "lightgbm_krate_20260803_155401.txt"
_COUNT_DIR = OUTPUT_DIR / "count_layer"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_frame() -> pd.DataFrame:
    if not PITCHER_TRAINING_PATH.exists():
        raise FileNotFoundError(
            f"Missing {PITCHER_TRAINING_PATH}. Run the three pipeline stages first."
        )
    frame = pd.read_parquet(PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.loc[frame["season"].isin(TRAIN_SEASONS)]
        .dropna(subset=["k_rate", "K", "PA", "game_date"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    observed = tuple(sorted(frame["season"].unique()))
    if observed != TRAIN_SEASONS:
        raise ValueError(f"expected {TRAIN_SEASONS}, got {observed}")
    return frame


def _load_frozen_krate(model_path: Path) -> tuple[object, list[str]]:
    if lgb is None:
        raise ImportError('LightGBM required: pip install -e ".[research]"')
    meta_path = model_path.with_suffix(".json")
    if not model_path.exists():
        raise FileNotFoundError(model_path)
    if not meta_path.exists():
        raise FileNotFoundError(meta_path)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    features = list(meta["features"])
    booster = lgb.Booster(model_file=str(model_path))
    return booster, features


def _predict_krate(model, model_name: str, frame: pd.DataFrame, features: list[str]):
    if model_name == "booster":
        return np.clip(
            model.predict(lightgbm_matrix(frame, features)),
            0.0,
            1.0,
        )
    return predict_clipped(model, model_name, frame, features)


def _fit_or_load_krate(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    *,
    model_path: Path | None,
) -> tuple[object, str, list[str]]:
    if model_path is not None and model_path.exists():
        booster, features = _load_frozen_krate(model_path)
        missing = [c for c in features if c not in train.columns]
        if missing:
            raise ValueError(f"training frame missing k-rate features: {missing[:8]}")
        assert_pa_not_in_features(features)
        return booster, "booster", features

    features = list(resolve_feature_names(train, "production"))
    assert_pa_not_in_features(features)
    model = build_model("lightgbm", lightgbm_verbosity=-1)
    fit_regressor(
        model,
        "lightgbm",
        lightgbm_matrix(train, features),
        train["k_rate"],
        validation_features=lightgbm_matrix(validation, features),
        validation_target=validation["k_rate"],
        early_stopping_rounds=200,
        log_evaluation_period=None,
    )
    return model, "lightgbm", features


def _fit_tbf_ridge(
    train: pd.DataFrame,
    feature_set: str = TBF_DEFAULT_FEATURE_SET,
) -> tuple[object, list[str], float]:
    features = list(tbf_feature_names(train, feature_set))
    assert_tbf_label_not_in_features(features)
    model = build_model("ridge")
    fit_regressor(model, "ridge", train[features], train[TBF_TARGET])
    upper = float(train[TBF_TARGET].quantile(0.999))
    return model, features, upper


def _baseline_report(
    frame: pd.DataFrame,
    k_rate: np.ndarray,
    *,
    projected_tbf: np.ndarray,
    pa_p5: np.ndarray,
    mean_pa: float,
) -> dict[str, dict[str, float]]:
    return {
        "k_rate_x_projected_tbf": count_point_metrics(
            frame["K"], expected_strikeouts(k_rate, projected_tbf)
        ),
        "k_rate_x_PA_P5": count_point_metrics(
            frame["K"], expected_strikeouts(k_rate, pa_p5)
        ),
        "k_rate_x_train_mean_PA": count_point_metrics(
            frame["K"],
            expected_strikeouts(k_rate, np.full_like(k_rate, mean_pa)),
        ),
    }


def main(
    *,
    k_rate_model: Path | None = _DEFAULT_KRATE,
    feature_set: str = TBF_DEFAULT_FEATURE_SET,
    write_predictions: bool = True,
) -> dict:
    frame = load_frame()
    train, validation, test = chronological_split(frame)

    k_model, k_name, k_features = _fit_or_load_krate(
        train, validation, model_path=k_rate_model
    )
    tbf_model, tbf_features, tbf_upper = _fit_tbf_ridge(train, feature_set=feature_set)

    parts = {"train": train, "validation": validation, "test": test}
    preds: dict[str, dict[str, np.ndarray]] = {}
    for name, part in parts.items():
        k_hat = _predict_krate(k_model, k_name, part, k_features)
        tbf_hat = predict_nonnegative(
            tbf_model, "ridge", part, tbf_features, upper=tbf_upper
        )
        preds[name] = {"k_rate": k_hat, "projected_tbf": tbf_hat}

    kappa = fit_count_layer_kappa(
        k=train["K"],
        pa=train["PA"],
        k_rate=preds["train"]["k_rate"],
    )
    mean_pa = float(train["PA"].mean())

    report = {
        "k_rate_source": (
            str(k_rate_model) if k_rate_model and k_rate_model.exists() else "refit_lightgbm"
        ),
        "tbf_model": "ridge",
        "tbf_feature_set": feature_set,
        "tbf_features": len(tbf_features),
        "k_rate_features": len(k_features),
        "kappa_train": kappa,
        "train_mean_PA": mean_pa,
        "rows": {name: len(part) for name, part in parts.items()},
        "cutoffs": {
            "train_end": str(train["game_date"].max().date()),
            "validation_start": str(validation["game_date"].min().date()),
            "validation_end": str(validation["game_date"].max().date()),
            "test_start": str(test["game_date"].min().date()),
        },
        "partitions": {},
    }

    for name in ("validation", "test"):
        part = parts[name]
        k_hat = preds[name]["k_rate"]
        tbf_hat = preds[name]["projected_tbf"]
        pa_p5 = part["PA_P5"].to_numpy(dtype=np.float64)
        # Early-career null PA_P5: fall back to train mean for the baseline only.
        pa_p5 = np.where(np.isfinite(pa_p5), pa_p5, mean_pa)
        report["partitions"][name] = {
            "baselines_expected_K": _baseline_report(
                part,
                k_hat,
                projected_tbf=tbf_hat,
                pa_p5=pa_p5,
                mean_pa=mean_pa,
            ),
            "count_layer": evaluate_count_layer(
                part,
                k_rate=k_hat,
                projected_tbf=tbf_hat,
                lines=DEFAULT_K_LINES,
                kappa=kappa,
            ),
        }

    print(json.dumps(report, indent=2))

    ensure_output_directories()
    _COUNT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_json = _COUNT_DIR / f"count_layer_{stamp}.json"
    payload = {
        "evaluation": report,
        "training_artifact": str(PITCHER_TRAINING_PATH),
        "training_artifact_sha256": _sha256(PITCHER_TRAINING_PATH),
        "approved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes": (
            "Count layer: expected_K = frozen_k_rate × Ridge projected_tbf. "
            "Line probs use projected TBF trials (not same-game PA). "
            "kappa fit on train with historical PA trials (Step 5 two-stage)."
        ),
    }
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_json}")

    if write_predictions:
        scored = []
        for name, part in parts.items():
            scored.append(
                attach_count_predictions(
                    part.assign(partition=name),
                    k_rate=preds[name]["k_rate"],
                    projected_tbf=preds[name]["projected_tbf"],
                    lines=DEFAULT_K_LINES,
                    kappa=kappa,
                )
            )
        pred_path = _COUNT_DIR / f"count_layer_predictions_{stamp}.parquet"
        pd.concat(scored, ignore_index=True).to_parquet(pred_path)
        print(f"Wrote {pred_path}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--k-rate-model",
        type=Path,
        default=_DEFAULT_KRATE,
        help="Frozen LightGBM .txt (sidecar .json required). Missing → refit.",
    )
    parser.add_argument(
        "--tbf-feature-set",
        default=TBF_DEFAULT_FEATURE_SET,
        help="TBF feature set (default: frozen thin bullpen).",
    )
    parser.add_argument(
        "--no-predictions",
        action="store_true",
        help="Skip writing the scored parquet.",
    )
    args = parser.parse_args()
    path = args.k_rate_model
    main(
        k_rate_model=path if path.exists() else None,
        feature_set=args.tbf_feature_set,
        write_predictions=not args.no_predictions,
    )
