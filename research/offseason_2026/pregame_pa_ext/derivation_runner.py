"""Historical derivation/overlap execution entry point (thin runner).

RESEARCH-ONLY, write-once outputs, SYNTHETIC-TESTED ONLY. This module
adds NO statistical machinery: it is the exact I/O procedure around the
existing registered functions
    starter_outcomes.derive_start_outcomes
    starter_outcomes.validate_against_registered
whose starter/BF/K definitions and fail-loud guards are reused
unchanged. Real-source execution still requires its applicable
authorization (a separate procedural requirement; the acknowledgement
below is a technical gate only).

Checked for reuse before creation: no existing wrapper performs
derive + 2024H2 overlap validation I/O (count_pmf_calibration_runner
is the calibration experiment's own registered entry point; adapter.py
holds shared file/frame helpers only). This module follows that
runner's receipt/failure conventions.

Sequence (run_derivation_overlap, and the CLI main() wrapper):
    0. Execution-acknowledgement gate (technical gate only; before any
       input read, validation, or output creation).
    1. Write-once output destination check (must not exist).
    2. receipt_initial: code identity + config + EXPECTED input file
       identities, written BEFORE validation so failure evidence
       always references it.
    3. Verify actual input file SHA-256 identities against the
       caller-declared expected values; refuse on mismatch.
    4. PA source: read, verify schema (required fields present),
       select ONLY the required columns, keep ONLY the declared
       2023-01-01..2024-12-31 training window (out-of-window rows are
       counted and excluded, never scored, never carried forward).
    5. Registered artifact: read, verify schema, select keys +
       outcomes + game_date, keep ONLY the 2024-07-01..2024-12-31
       (block_2024H2) overlap window on BOTH sides.
    6. derive_start_outcomes on the selected frame (all registered
       guards preserved; no opener rule invented).
    7. validate_against_registered on the two 2024H2 slices.
    8. Outputs: derived_start_outcomes_v1.parquet (full derived
       2023-2024 window), overlap_report.json, receipt_final.json.
    9. A DISCREPANCIES_REQUIRE_EXPLANATION verdict is recorded and
       returned verbatim and the CLI exits 3: a discrepancy is NEVER
       presented as validated success ("validated" is true only for
       the IDENTICAL verdict).
   10. Any exception after receipt_initial writes failure_record.json
       (stage, error, initial-receipt sha) and re-raises: failure
       evidence is preserved, nothing is silently retried or patched.

Generated outcome parquets and receipts are written ONLY to the
caller-supplied output directory in the designated research-data area
(the owner's MLB-Props-Research lake); they are never committed to the
repository, and no private paths are hardcoded here.

Registered invocation (after independent review + explicit owner
authorization; synthetic tests only until then):

    python research/offseason_2026/pregame_pa_ext/derivation_runner.py \
        --pa-source <registered PA parquet> \
        --registered-starts <existing start artifact parquet> \
        --expected-pa-sha256 <sha256 of PA parquet bytes> \
        --expected-registered-sha256 <sha256 of artifact bytes> \
        --out-dir <fresh dir under the research-data area> \
        --execution-ack EXECUTE-BASELINE-V2-DERIVATION-V1

Exit codes: 0 derived + overlap IDENTICAL; 2 execution acknowledgement
refused (no side effects); 3 overlap discrepancies (evidence written);
nonzero on fail-loud guards (failure_record.json preserved).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import starter_outcomes as so  # noqa: E402

# Technical execution-acceptance token, following the reviewed
# count_pmf_calibration_runner convention. Presenting it is a
# TECHNICAL GATE ONLY; it is NOT evidence of owner authorization.
EXECUTION_ACK_TOKEN = "EXECUTE-BASELINE-V2-DERIVATION-V1"

PA_COLUMNS = ["game_pk", "game_date", "pitcher", "y",
              "pitcher_role", "inning_topbot", "at_bat_number"]
REGISTERED_COLUMNS = ["game_pk", "side", "pitcher", "game_date",
                      "realized_bf", "realized_k"]
KEYS = ["game_pk", "side", "pitcher"]
# Declared v2 training window (starter_outcomes.V2_TRAIN_START/END).
TRAIN_START = so.V2_TRAIN_START
TRAIN_END = so.V2_TRAIN_END
# Overlap window = block_2024H2 bounds (the v1 estimation window).
OVERLAP_START = "2024-07-01"
OVERLAP_END = "2024-12-31"


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _date_filter(frame: "pl.DataFrame", lo: str, hi: str
                 ) -> "pl.DataFrame":
    return frame.filter(
        (pl.col("game_date") >= pl.date(*map(int, lo.split("-"))))
        & (pl.col("game_date") <= pl.date(*map(int, hi.split("-")))))


def _require_columns(frame: "pl.DataFrame", required: list,
                     source_name: str) -> None:
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise so.DerivationError(
            f"{source_name}: missing field(s) {missing} (field/schema "
            "gap); expected columns: {required}".replace("{required}",
                                                         str(required)))
    for c in required:
        n = frame[c].null_count()
        if n:
            raise so.DerivationError(
                f"{source_name}: null values in required field "
                f"'{c}': {n} rows")


def run_derivation_overlap(pa_path, registered_path, out_dir, *,
                           expected_pa_sha256: str,
                           expected_registered_sha256: str,
                           execution_ack: str,
                           ack_route: str = "direct-call") -> dict:
    """Execute the historical derivation + 2024H2 overlap validation.

    pa_path: registered PA source parquet (pa_table lineage).
    registered_path: existing start artifact parquet carrying
        game_pk, side, pitcher, game_date, realized_bf, realized_k.
    out_dir: fresh write-once output directory (research-data area).
    expected_*_sha256: caller-declared SHA-256 of each input FILE's
        bytes; verified before any frame is read.
    execution_ack: REQUIRED technical gate token; checked before any
        input handling or output creation.
    """
    if execution_ack != EXECUTION_ACK_TOKEN:
        raise ValueError(
            "execution acknowledgement missing or invalid: refusing "
            "to run before loading input, deriving, validating, or "
            "creating output; supply the registered "
            "EXECUTION_ACK_TOKEN (technical gate only, not owner "
            "authorization)")
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)
    initial_path = out_dir / "receipt_initial.json"
    failure_path = out_dir / "failure_record.json"

    code_identity = {
        "runner_sha256": _file_sha(Path(__file__)),
        "starter_outcomes_sha256": _file_sha(Path(so.__file__)),
    }
    config = {
        "train_window": [TRAIN_START, TRAIN_END],
        "overlap_window": [OVERLAP_START, OVERLAP_END],
        "pa_columns": PA_COLUMNS,
        "registered_columns": REGISTERED_COLUMNS,
        "overlap_keys": KEYS,
        "derivation_contract": so.DERIVED_CONTRACT,
        "derivation_contract_sha": so.contract_sha(),
    }
    initial = {
        "execution_acknowledgement": {
            "route": ack_route,
            "token": execution_ack,
            "note": ("technical execution-acceptance gate only; NOT "
                     "proof of owner authorization, which remains a "
                     "separate procedural requirement"),
        },
        "code_identity": code_identity,
        "config": config,
        "expected_input_identities": {
            "pa_source_sha256": expected_pa_sha256,
            "registered_starts_sha256": expected_registered_sha256,
        },
        "actual_input_identities": None,  # populated after verification
        "counts": None,  # populated after window selection
    }
    initial_path.write_text(json.dumps(initial, indent=1, sort_keys=True),
                            encoding="utf-8")
    initial_sha = ad.sha256_file(initial_path)

    try:
        # ---- verify input file identities BEFORE reading frames -----
        pa_path = Path(pa_path)
        registered_path = Path(registered_path)
        actual = {"pa_source_sha256": _file_sha(pa_path),
                  "registered_starts_sha256": _file_sha(registered_path)}
        # The initial receipt is IMMUTABLE once written: the verified
        # actual identities are recorded in the final receipt, not by
        # rewriting the initial one.
        if actual["pa_source_sha256"] != expected_pa_sha256:
            raise ValueError(
                f"PA source identity mismatch: "
                f"actual={actual['pa_source_sha256']} "
                f"expected={expected_pa_sha256}")
        if (actual["registered_starts_sha256"]
                != expected_registered_sha256):
            raise ValueError(
                f"registered start artifact identity mismatch: "
                f"actual={actual['registered_starts_sha256']} "
                f"expected={expected_registered_sha256}")

        # ---- PA source: schema, column selection, window narrowing --
        pa_full = pl.read_parquet(pa_path)
        _require_columns(pa_full, PA_COLUMNS, "PA source")
        n_source_rows = pa_full.height
        pa_sel = pa_full.select(PA_COLUMNS)
        pa_train = _date_filter(pa_sel, TRAIN_START, TRAIN_END)
        n_pa_rows_excluded_out_of_window = n_source_rows - pa_train.height

        # ---- registered artifact: schema, selection, overlap window -
        reg_full = pl.read_parquet(registered_path)
        _require_columns(reg_full, REGISTERED_COLUMNS,
                         "registered start artifact")
        reg_all = reg_full.select(REGISTERED_COLUMNS)
        n_registered_rows_total = reg_all.height
        reg_h2 = _date_filter(reg_all, OVERLAP_START, OVERLAP_END)
        n_registered_excluded_out_of_window = (
            n_registered_rows_total - reg_h2.height)

        # ---- derivation (registered functions, guards unchanged) ----
        derived_res = so.derive_start_outcomes(pa_train)
        derived = derived_res["start_outcomes"]

        # ---- explicit 2024H2 overlap selection on BOTH sides --------
        derived_h2 = _date_filter(derived, OVERLAP_START, OVERLAP_END)
        report = so.validate_against_registered(derived_h2, reg_h2)

        # ---- write outputs (write-once) -----------------------------
        derived_path = out_dir / "derived_start_outcomes_v1.parquet"
        derived.write_parquet(derived_path)
        overlap_payload = {
            "windows": {"train": [TRAIN_START, TRAIN_END],
                        "overlap": [OVERLAP_START, OVERLAP_END]},
            "counts": {
                "pa_source_rows": n_source_rows,
                "pa_rows_in_train_window": pa_train.height,
                "pa_rows_excluded_out_of_window":
                    n_pa_rows_excluded_out_of_window,
                "registered_rows_total": n_registered_rows_total,
                "registered_rows_in_overlap_window": reg_h2.height,
                "registered_rows_excluded_out_of_window":
                    n_registered_excluded_out_of_window,
                "derived_starts_total": derived.height,
                "derived_starts_in_overlap_window": derived_h2.height,
            },
            "derivation_meta": derived_res["meta"],
            "overlap_report": report,
        }
        overlap_path = out_dir / "overlap_report.json"
        overlap_path.write_text(json.dumps(overlap_payload, indent=1,
                                           sort_keys=True,
                                           default=str),
                                encoding="utf-8")
        outputs = {
            "derived_start_outcomes_v1.parquet":
                ad.sha256_file(derived_path),
            "overlap_report.json": ad.sha256_file(overlap_path),
        }

        # ---- verdict: discrepancy is NEVER validated success --------
        validated = report["verdict"] == "IDENTICAL"
        final = dict(initial)
        final["actual_input_identities"] = actual
        final["counts"] = overlap_payload["counts"]
        final["outputs"] = outputs
        final["overlap_verdict"] = report["verdict"]
        final["validated"] = validated
        final["acceptance"] = {"receipt_chain": initial_sha}
        final_path = out_dir / "receipt_final.json"
        final_path.write_text(json.dumps(final, indent=1, sort_keys=True,
                                         default=str),
                              encoding="utf-8")
        if ad.sha256_file(initial_path) != initial_sha:
            raise ValueError("IMMUTABLE initial receipt modified")
    except Exception as exc:
        failure = {"stage": "baseline_v2_derivation", "failure": True,
                   "error": repr(exc),
                   "initial_receipt_sha256": initial_sha}
        failure_path.write_text(json.dumps(failure, indent=1,
                                           sort_keys=True),
                                encoding="utf-8")
        raise

    return {"out_dir": str(out_dir),
            "verdict": report["verdict"],
            "validated": validated,
            "overlap_report": report,
            "counts": overlap_payload["counts"],
            "outputs": outputs,
            "receipt_initial_sha256": initial_sha}


def main(argv=None) -> int:
    """Registered CLI entry point. The acknowledgement gate runs before
    the input parquets are read and before any output is created;
    without a valid --execution-ack the CLI exits 2 with no side
    effects. A DISCREPANCIES_REQUIRE_EXPLANATION verdict exits 3 after
    writing all evidence; it is never reported as success."""
    p = argparse.ArgumentParser(
        description=("Historical starter-outcome derivation + 2024H2 "
                     "overlap validation (registered, write-once). "
                     "Requires an explicit execution acknowledgement "
                     "token; the token is a technical gate only and is "
                     "NOT proof of owner authorization."))
    p.add_argument("--pa-source", required=True,
                   help="registered PA source parquet (pa_table lineage)")
    p.add_argument("--registered-starts", required=True,
                   help="existing start artifact parquet (keys + "
                        "realized_bf/realized_k + game_date)")
    p.add_argument("--expected-pa-sha256", required=True,
                   help="SHA-256 of the PA parquet file bytes")
    p.add_argument("--expected-registered-sha256", required=True,
                   help="SHA-256 of the start artifact file bytes")
    p.add_argument("--out-dir", required=True,
                   help="fresh write-once output directory under the "
                        "designated research-data area")
    p.add_argument("--execution-ack", required=True,
                   help="registered EXECUTION_ACK_TOKEN")
    args = p.parse_args(argv)

    if args.execution_ack != EXECUTION_ACK_TOKEN:
        print("EXECUTION REFUSED: missing or invalid execution "
              "acknowledgement (--execution-ack). No input was read, "
              "nothing was derived or validated, and no output was "
              "created. The acknowledgement token gates the technical "
              "run only; owner authorization is a separate procedural "
              "requirement.", file=sys.stderr)
        return 2

    result = run_derivation_overlap(
        args.pa_source, args.registered_starts, args.out_dir,
        expected_pa_sha256=args.expected_pa_sha256,
        expected_registered_sha256=args.expected_registered_sha256,
        execution_ack=args.execution_ack, ack_route="cli")
    print(json.dumps({"verdict": result["verdict"],
                      "validated": result["validated"],
                      "out_dir": result["out_dir"],
                      "outputs": result["outputs"]},
                     indent=1, sort_keys=True))
    return 0 if result["validated"] else 3


if __name__ == "__main__":
    sys.exit(main())
