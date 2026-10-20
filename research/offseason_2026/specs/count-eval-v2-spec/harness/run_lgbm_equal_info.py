# run_lgbm_equal_info.py -- EXECUTABLE FROZEN RUNNER for lgbm-equal-info-v1
# (freeze_lgbm_equal_info_v1.json amendment-1, 2026-10-15).
#
# D-1: this runner is the frozen LightGBM command. It invokes the SHARED
# tracking wrapper (track_and_verify.py: compare -> save -> log(MLflow) ->
# verify) after its canonical outputs finalize; it never hand-replicates
# logging calls.
#
# D-2: BEFORE any fitting, verify_registered_identities() re-derives every
# registered identity from disk (freeze config hash, pa_table / features_v3 /
# start_metrics sha256s, adapter file + config hashes, builder-worktree
# harness comparison.py sha, wrapper/runner self-hashes) and fails loud on
# any mismatch. start_metrics_outcome_source is registered PATH+HASH ONLY:
# it is NOT read and NOT joined by this command (the join is a later,
# separately registered step).
#
# D-3: predictions use best_iteration (predict_raw calls booster.predict
# with num_iteration=booster.best_iteration); there is NO refit on the full
# training fold anywhere in this batch.
#
# Execution gate: refuses to run without
# --i-accept-real-data-execution (the --i-accept-outcome-scoring
# equivalent: this batch scores realized outcomes on the registered dev
# folds). confirm_2025H2 and 2026 rows are excluded (EXCLUDED - NOT
# SCORED / CLOSED). Real-data execution additionally requires the owner
# readiness gate; this file alone authorizes nothing.
#
# ASCII-only (cp1252 consoles).
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import comparison as cmp  # noqa: E402  (executed harness; registered by sha)
import track_and_verify as tv  # noqa: E402  (shared D-1 wrapper)

ACCEPT_FLAG = "--i-accept-real-data-execution"
RUN_NAME = "lgbm-equal-info-v1"


def import_adapter(path: str):
    spec = importlib.util.spec_from_file_location(
        "lgbm_equal_info_adapter", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_real_folds(df: pl.DataFrame, feature_names: tuple) -> list[dict]:
    """Build the fold dicts for the adapter from the loaded PA frame, using
    the executed comparison.py fold derivation (runtime calibration spans).
    DEV BLOCKS ONLY: confirm_2025H2 is EXCLUDED - NOT SCORED."""
    folds = cmp.derive_folds(df)
    out: list[dict] = []
    for name in cmp.DEV_BLOCKS:
        f = folds[name]

        def win(d0, d1):
            return df.filter(
                (pl.col("game_date") >= pl.date(d0.year, d0.month, d0.day))
                & (pl.col("game_date") <= pl.date(d1.year, d1.month, d1.day)))

        train = win(f.train_start, f.cal_first - dt.timedelta(days=1))
        cal = win(f.cal_first, f.cal_last)
        eval_df = win(f.assess_start, f.assess_end)
        cmp.enforce_availability_guard(eval_df)
        if train.height == 0 or cal.height == 0 or eval_df.height == 0:
            raise cmp.FoldConstructionError(
                f"{name}: empty real-data partition "
                f"(train={train.height}, cal={cal.height}, "
                f"eval={eval_df.height})")
        out.append({
            "name": name,
            "X_train": train.select(list(feature_names)).to_numpy(),
            "y_train": train["y"].to_numpy().astype(int),
            # datetime.date objects (not np.datetime64): the adapter's inner
            # split and the slate-date bootstrap group by plain date objects
            "dates_train": np.array(train["game_date"].to_list(),
                                    dtype=object),
            "X_cal": cal.select(list(feature_names)).to_numpy(),
            "y_cal": cal["y"].to_numpy().astype(int),
            "X_eval": eval_df.select(list(feature_names)).to_numpy(),
            "y_eval": eval_df["y"].to_numpy().astype(int),
            "dates_eval": np.array(eval_df["game_date"].to_list(),
                                   dtype=object),
            "blocks_eval": np.array([name] * eval_df.height),
        })
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Frozen lgbm-equal-info-v1 command (D-1/D-2/D-3).")
    p.add_argument("--freeze", required=True,
                   help="path to freeze_lgbm_equal_info_v1.json")
    p.add_argument("--tracking-uri", default=None,
                   help="override the registered MLflow tracking URI")
    p.add_argument(ACCEPT_FLAG, dest="accept_real_data_execution",
                   action="store_true",
                   help="the --i-accept-outcome-scoring equivalent: "
                        "acknowledge this batch scores realized outcomes "
                        "on the registered dev folds")
    args = p.parse_args(argv)
    if not args.accept_real_data_execution:
        print(f"REFUSED: real-data execution requires {ACCEPT_FLAG} "
              "(the --i-accept-outcome-scoring equivalent). Nothing was "
              "read, fitted, scored, or written.")
        return 2

    freeze = json.loads(Path(args.freeze).read_text(encoding="utf-8"))
    cfg = freeze["config"]

    # D-2: registered identity verification BEFORE any fitting.
    ad = import_adapter(cfg["adapter"]["path"])
    ident = tv.verify_registered_identities(args.freeze, adapter_module=ad,
                                            runner_path=__file__)
    inputs = cfg["registered_inputs"]

    run_identity = {
        "batch_id": freeze["batch_id"],
        "freeze_config_sha256": freeze["config_sha256"],
        "input_sha256": {k: inputs[k]["sha256"]
                         for k in ("pa_table", "features_v3")},
        "adapter_file_sha256": cfg["adapter"]["file_sha256"],
        "comparison_sha256":
            cfg["builder_worktree_harness"]["comparison_sha256"],
        "wrapper_file_sha256": cfg["tracking_wrapper"]["file_sha256"],
    }
    run_id = hashlib.sha256(
        json.dumps(run_identity, sort_keys=True).encode("utf-8")
    ).hexdigest()

    out_dir = Path(cfg["output_destination"]) / run_id
    if out_dir.exists():
        raise cmp.WriteOnceError(
            f"write-once violation: output dir {out_dir} already exists "
            "(never overwrite a prior run)")
    out_dir.mkdir(parents=True)

    df = cmp.load_pa_rows(inputs["pa_table"]["path"],
                          inputs["features_v3"]["path"])
    feature_names = tuple(cfg["equal_information_contract"]["features"])
    fold_dicts = build_real_folds(df, feature_names)

    def compare_fn():
        return ad.compare_on_synthetic_folds(fold_dicts)

    tracking_uri = args.tracking_uri or cfg["tracking"]["tracking_uri"]
    status = tv.track_and_verify(
        compare_fn, out_dir, tracking_uri,
        experiment=cfg["tracking"]["experiment"], run_name=RUN_NAME)

    manifest = {
        "run_id": run_id,
        "batch_id": freeze["batch_id"],
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "freeze_path": str(Path(args.freeze).resolve()),
        "freeze_config_sha256": freeze["config_sha256"],
        "run_identity": run_identity,
        "identity_verification": {"ok": True,
                                  "checked": ident["checked"]},
        "folds_executed": [fd["name"] for fd in fold_dicts],
        "confirm_block_status": "EXCLUDED - NOT SCORED (dev blocks only)",
        "final_fit_declaration": cfg["final_fit_declaration"],
        "tracking": {
            "wrapper": "track_and_verify.track_and_verify (shared D-1 "
                       "wrapper: compare -> save -> log -> verify)",
            "tracking_uri": tracking_uri,
            "experiment": cfg["tracking"]["experiment"],
            "status": status["status"],
            "run_id": status["run_id"],
        },
        "start_metrics_outcome_source": {
            **inputs["start_metrics_outcome_source"],
            "join_status": "REGISTERED-PATH-ONLY - not read, not joined "
                           "by this command"},
    }
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"run_id": run_id, "output_dir": str(out_dir),
                      "tracking_status": status["status"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
