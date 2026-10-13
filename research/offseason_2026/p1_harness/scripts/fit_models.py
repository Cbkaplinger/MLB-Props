"""P1 harness v2 step 4+5: model adapters, fit on TRAIN, evaluate DEV + EVAL.

v2 corrections vs v1 (owner rulings 2026-10-13):
  4. All reported probabilities are RAW (uncalibrated); the v1 "CAL" split is
     relabeled "DEV_VALIDATION" (development/validation); NO calibration is
     fitted anywhere.
  5. LOG5 uses the full identity with league rate:
         q = (p*b/l) / (p*b/l + (1-p)*(1-b)/(1-l))
     checked by test_log5_identities.py (p=b=l -> q=l; p=l -> q=b; b=l -> q=p;
     tolerance 1e-12). Inputs are clipped to [EPS, 1-EPS] to avoid 0/0.
  6. Same three candidates + log5 reference, SAME rows/features as v1, metrics
     recomputed on the corrected table.
  7. Versioned identities: reports/manifest.json carries sha256 of scripts,
     data artifacts, timestamp, model names, split dates, and the row-identity
     hash of the EVAL keys (and of the DEV keys). BOTH dev and EVAL predictions
     are saved (data/dev_predictions.parquet, data/eval_predictions.parquet).

Candidates:
  A_reference                  shrunk pitcher rate (w=150) alone as the probability
  B_logreg                     LogisticRegression(C=1.0, max_iter=1000) on
                               [p_pitcher_prior, p_batter_prior, lg_rate, n_prior_pitcher,
                               n_prior_batter, cold_start]  (w=150 priors)
  C_two_shrinkage_placeholder  two-shrinkage pooling PLACEHOLDER, not hierarchical:
                               logistic on the w=150 AND w=500 shrunk pitcher/batter
                               rates + lg_rate + supports + cold_start
  LOG5_reference               pitcher-batter log5 with league rate, from the same
                               w=150 priors + lg_rate; nothing is fit, just computed.

Outputs:
  reports/metrics.md + reports/metrics.json
  reports/reliability_<split>_<model>.csv (deciles, diagnosis only)
  data/eval_predictions.parquet + data/dev_predictions.parquet
  reports/run_metadata.json + reports/manifest.json
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

HARNESS = Path(__file__).resolve().parent.parent
DATA = HARNESS / "data"
REPORTS = HARNESS / "reports"

EPS = 1e-9

FEATURES_B = [
    "p_pitcher_prior_w150",
    "p_batter_prior_w150",
    "lg_rate",
    "n_prior_pitcher",
    "n_prior_batter",
    "cold_start",
]
FEATURES_C = [
    "p_pitcher_prior_w150",
    "p_pitcher_prior_w500",
    "p_batter_prior_w150",
    "p_batter_prior_w500",
    "lg_rate",
    "n_prior_pitcher",
    "n_prior_batter",
    "cold_start",
]
MODELS = ["A_reference", "B_logreg", "C_two_shrinkage_placeholder", "LOG5_reference"]
C_MODEL = "C_two_shrinkage_placeholder"
C_DESCRIPTION = "two-shrinkage pooling PLACEHOLDER, not hierarchical"

SPLIT_DATES = {
    "TRAIN": "game_date < 2025-01-01",
    "DEV_VALIDATION": "2025-01-01 <= game_date < 2025-07-01 (development/validation; "
    "v1 'CALIBRATION' relabeled; NO calibration fitted)",
    "EVAL": "2025-07-01 <= game_date <= 2026-12-31; 2026 rows reserved "
    "(retrospective validation, NOT an untouched holdout)",
}


def log5(p_p: np.ndarray, p_b: np.ndarray, l: np.ndarray | float) -> np.ndarray:
    """Pitcher-batter log5 with league rate l (event-weighted league K prior):
        q = (p*b/l) / (p*b/l + (1-p)*(1-b)/(1-l))
    algebraically q = p*b*(1-l) / (p*b*(1-l) + (1-p)*(1-b)*l).
    Inputs clipped to [EPS, 1-EPS] to avoid 0/0. No fitting: pure formula."""
    p = np.clip(np.asarray(p_p, dtype=np.float64), EPS, 1.0 - EPS)
    b = np.clip(np.asarray(p_b, dtype=np.float64), EPS, 1.0 - EPS)
    lg = np.clip(np.asarray(l, dtype=np.float64), EPS, 1.0 - EPS)
    num = p * b * (1.0 - lg)
    den = num + (1.0 - p) * (1.0 - b) * lg
    return num / den


def fit_lightgbm(X, y):  # pragma: no cover - reserved adapter
    raise NotImplementedError("LightGBM adapter reserved for a later harness stage")


def fit_catboost(X, y):  # pragma: no cover - reserved adapter
    raise NotImplementedError("CatBoost adapter reserved for a later harness stage")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_hash() -> dict[str, str]:
    out = {}
    for f in sorted(HARNESS.glob("scripts/*.py")):
        out[f.name] = sha256_file(f)
    return out


def eval_identity_hash(keys_df: pl.DataFrame) -> str:
    """sha256 over the UTF-8 bytes of the (game_pk, at_bat_number, batter)
    tuples sorted ascending, each as f'{game_pk},{at_bat_number},{batter}\\n'."""
    k = keys_df.select("game_pk", "at_bat_number", "batter").sort(
        ["game_pk", "at_bat_number", "batter"]
    )
    blob = "".join(f"{a},{b},{c}\n" for a, b, c in k.iter_rows()).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def decile_reliability(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> pl.DataFrame:
    """Equal-count predicted-probability deciles vs observed frequency."""
    order = np.argsort(np.argsort(p, kind="stable"), kind="stable")
    bin_idx = np.minimum(order * n_bins // p.size, n_bins - 1)
    rows = []
    for b in range(n_bins):
        m = bin_idx == b
        if m.any():
            rows.append(
                {
                    "decile": b + 1,
                    "n": int(m.sum()),
                    "mean_pred": float(p[m].mean()),
                    "obs_rate": float(y[m].mean()),
                }
            )
    return pl.DataFrame(rows)


def main() -> None:
    feat = pl.read_parquet(DATA / "features.parquet")
    pa = pl.read_parquet(DATA / "pa_table.parquet").select(
        "game_pk", "at_bat_number", "batter", "y"
    )
    df = feat.join(pa, on=["game_pk", "at_bat_number", "batter"], how="inner")
    assert df.height == feat.height, "feature/PA key mismatch"

    train = df.filter(pl.col("split") == "TRAIN")
    dev = df.filter(pl.col("split") == "DEV_VALIDATION")
    ev = df.filter(pl.col("split") == "EVAL")
    assert train.height > 0 and dev.height > 0 and ev.height > 0

    y_train = train["y"].to_numpy()
    y_dev = dev["y"].to_numpy()
    y_ev = ev["y"].to_numpy()

    # (b) and (c): logistic regression
    lr_b = LogisticRegression(C=1.0, max_iter=1000)
    lr_b.fit(train.select(FEATURES_B).to_numpy(), y_train)
    lr_c = LogisticRegression(C=1.0, max_iter=1000)
    lr_c.fit(train.select(FEATURES_C).to_numpy(), y_train)

    # RAW uncalibrated probabilities for both evaluation splits
    preds: dict[str, dict[str, np.ndarray]] = {}
    for name, split_df in [
        ("DEV", dev),
        ("EVAL", ev),
    ]:
        X_b = split_df.select(FEATURES_B).to_numpy()
        X_c = split_df.select(FEATURES_C).to_numpy()
        preds[name] = {
            "A_reference": split_df["p_pitcher_prior_w150"].to_numpy(),
            "B_logreg": lr_b.predict_proba(X_b)[:, 1],
            C_MODEL: lr_c.predict_proba(X_c)[:, 1],
            "LOG5_reference": log5(
                split_df["p_pitcher_prior_w150"].to_numpy(),
                split_df["p_batter_prior_w150"].to_numpy(),
                split_df["lg_rate"].to_numpy(),
            ),
        }

    metrics = {}
    reliability_frames = []
    for name in MODELS:
        metrics[name] = {}
        for split, y in [("DEV", y_dev), ("EVAL", y_ev)]:
            p = preds[split][name]
            metrics[name][split] = {
                "n": int(y.size),
                "log_loss": float(log_loss(y, p)),
                "brier": float(brier_score_loss(y, p)),
            }
            rel = decile_reliability(y, p).with_columns(
                pl.lit(name).alias("model"), pl.lit(split).alias("split")
            )
            reliability_frames.append(rel)

    rel_df = pl.concat(reliability_frames)
    rel_df.write_csv(REPORTS / "reliability_all.csv")

    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    run_meta = {
        "run_version": "p1-harness-v2",
        "timestamp_utc": timestamp,
        "code_sha256": code_hash(),
        "split_definition": SPLIT_DATES,
        "library_versions": {
            "python": sys.version.split()[0],
            "polars": pl.__version__,
            "numpy": np.__version__,
            "scikit-learn": sklearn.__version__,
        },
        "models": {
            "A_reference": "shrunk pitcher K rate w=150 alone (RAW, uncalibrated)",
            "B_logreg": f"LogisticRegression(C=1.0, max_iter=1000) on {FEATURES_B} (RAW, uncalibrated)",
            C_MODEL: C_DESCRIPTION
            + ": LogisticRegression(C=1.0, max_iter=1000) on " + str(FEATURES_C)
            + " (RAW, uncalibrated)",
            "LOG5_reference": "pitcher-batter log5 with league rate from w=150 shrunk priors; "
            "no fit; q = (p*b/l) / (p*b/l + (1-p)*(1-b)/(1-l))",
        },
        "calibration_note": "NO calibration fitted anywhere in v2; all probabilities are "
        "raw. DEV_VALIDATION (v1 'CALIBRATION') is development/validation only.",
        "corrections_vs_v1": {
            "1": "truncated_pa rows excluded from the completed-PA table",
            "2": "2022-04-07 league prior = fixed 0.2245 (external_fixed_prior), "
            "v1 same-date backward fill removed",
            "3": "all-pitchers policy kept; pitcher_role slices tagged",
            "4": "raw probabilities reported; CAL relabeled DEV_VALIDATION",
            "5": "log5 corrected to full league-rate identity",
            "6": "metrics recomputed on the corrected table",
            "7": "versioned manifest with artifact hashes + identity hashes",
        },
    }

    keys = ["game_pk", "at_bat_number", "batter", "game_date", "y"]
    dev_pred = dev.select(
        *keys,
        pl.col("p_pitcher_prior_w150").alias("pred_A_reference"),
        pl.lit(preds["DEV"]["B_logreg"]).alias("pred_B_logreg"),
        pl.lit(preds["DEV"][C_MODEL]).alias("pred_" + C_MODEL),
        pl.lit(preds["DEV"]["LOG5_reference"]).alias("pred_LOG5_reference"),
    )
    ev_pred = ev.select(
        *keys,
        pl.col("p_pitcher_prior_w150").alias("pred_A_reference"),
        pl.lit(preds["EVAL"]["B_logreg"]).alias("pred_B_logreg"),
        pl.lit(preds["EVAL"][C_MODEL]).alias("pred_" + C_MODEL),
        pl.lit(preds["EVAL"]["LOG5_reference"]).alias("pred_LOG5_reference"),
    )
    meta_json = json.dumps(run_meta).encode("utf-8")
    dev_pred.write_parquet(DATA / "dev_predictions.parquet", metadata={"run_metadata": meta_json.decode("utf-8")})
    ev_pred.write_parquet(DATA / "eval_predictions.parquet", metadata={"run_metadata": meta_json.decode("utf-8")})
    (REPORTS / "run_metadata.json").write_text(json.dumps(run_meta, indent=2))
    (REPORTS / "metrics.json").write_text(json.dumps(metrics, indent=2))

    # versioned manifest: scripts/configs/data hashes, timestamp, model names,
    # split dates, row-identity hashes of EVAL and DEV keys
    data_hashes = {}
    for f in sorted(DATA.glob("*.parquet")):
        data_hashes[f.name] = sha256_file(f)
    manifest = {
        "run_version": "p1-harness-v2",
        "timestamp_utc": timestamp,
        "model_names": MODELS,
        "split_dates": SPLIT_DATES,
        "scripts_sha256": run_meta["code_sha256"],
        "config_sha256": {
            "split_definition_inline_in_build_features.py": "see scripts_sha256; "
            "no external config file (split dates + hyperparameters are in code)"
        },
        "data_sha256": data_hashes,
        "eval_key_identity_sha256": eval_identity_hash(ev),
        "dev_key_identity_sha256": eval_identity_hash(dev),
        "eval_key_identity_definition": "sha256 over UTF-8 bytes of the "
        "(game_pk, at_bat_number, batter) tuples sorted ascending by all three "
        "fields, each serialized as f'{game_pk},{at_bat_number},{batter}\\n'",
        "row_counts": {
            "TRAIN": train.height,
            "DEV_VALIDATION": dev.height,
            "EVAL": ev.height,
        },
        "library_versions": run_meta["library_versions"],
    }
    (REPORTS / "manifest.json").write_text(json.dumps(manifest, indent=2))

    lines = ["| model | split | n | log loss | brier |", "|---|---|---|---|---|"]
    for name in MODELS:
        for split in ["DEV", "EVAL"]:
            m = metrics[name][split]
            lines.append(
                f"| {name} | {split} | {m['n']:,} | {m['log_loss']:.5f} | {m['brier']:.5f} |"
            )
    table = "\n".join(lines)
    (REPORTS / "metrics_v2.md").write_text(table + "\n")
    (REPORTS / "metrics.md").write_text(table + "\n")
    print(table)
    print("\nmanifest hashes:")
    print(json.dumps({k: v for k, v in manifest.items() if k.endswith(("_sha256",)) or k in ("timestamp_utc", "eval_key_identity_sha256", "dev_key_identity_sha256")}, indent=2))
    print("\nreliability (DEV):")
    print(rel_df.filter(pl.col("split") == "DEV").drop("split").to_pandas().to_string(index=False))
    print("\nreliability (EVAL):")
    print(rel_df.filter(pl.col("split") == "EVAL").drop("split").to_pandas().to_string(index=False))


if __name__ == "__main__":
    main()
