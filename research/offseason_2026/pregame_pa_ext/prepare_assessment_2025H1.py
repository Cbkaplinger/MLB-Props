"""Stage-1 assessment preparation for pregame_multiclass_baseline_v1.

PREPARATION ONLY: derives the 2025H1 actual-PA assessment input. No
model fitting, no scoring, no forecast computation.

Contract (architect-approved):
  1. Verify PA/lineup input hashes BEFORE decoding (mandatory pins).
  2. Restrict projected-lineup requests to the declared assessment
     window BEFORE deriving request keys.
  3. Preserve EVERY completed PA of the requested starters - including
     replacement batters and repeated encounters. No projected-batter
     or projected-slot filter (an inner join there would delete
     replacement PAs before starter K totals are derived).
  4. Labels via the registered m0.map_statcast_events: recognized
     events -> class_label 0..3; UNRECOGNIZED/null events are preserved
     with class_label = -1 and counted, and INVALID-LABEL REFUSAL fires
     before any assessment output is written (preparation evidence
     preserved; unknowns are never classified as non-K).
  5. Duplicate actual-PA identities are counted correctly and refuse.
  6. Missing/unrequested starts are computed with actual anti-joins on
     the key sets (never manufactured from counts).
  7. Fresh preparation destination: refused if it exists; accounting and
     failure evidence are written there durably (never console-only).

Outputs (write-once destination): assessment_2025H1_v1.parquet +
preparation_receipt.json (+ failure_record.json on any refusal). The
receipt records the resolved imported module paths and code identities
of the checkout that produced the file.
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
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402

PREPARATION_ID = "pregame_multiclass_baseline_v1_assessment_prep"
EXECUTION_ACK_TOKEN = "PREPARE-ASSESSMENT-2025H1-V1"
REQ_KEYS = ["game_pk", "side", "pitcher"]
PA_COLUMNS = ["game_date", "game_pk", "at_bat_number", "pitcher",
              "batter", "events"]


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _frame_sha(frame: pl.DataFrame) -> str:
    import io
    buf = io.BytesIO()
    frame.write_parquet(buf)
    return hashlib.sha256(buf.getvalue()).hexdigest()


def prepare_assessment(pa: pl.DataFrame, lineups: pl.DataFrame,
                       out_dir, *, assessment_start: str,
                       assessment_end: str,
                       execution_ack: str,
                       ack_route: str = "direct-call") -> dict:
    """Derive the 2025H1 actual-PA assessment frame per the contract."""
    if execution_ack != EXECUTION_ACK_TOKEN:
        raise ValueError(
            "preparation acknowledgement missing or invalid: refusing "
            "before any input handling (technical gate only)")
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"write-once violation: {out_dir} exists")
    out_dir.mkdir(parents=True)
    failure_path = out_dir / "failure_record.json"

    code_identity = {
        "preparation_script_sha256": _sha_file(Path(__file__)),
        "m0_multiclass_resolved_path": str(Path(m0.__file__)),
        "m0_multiclass_sha256": _sha_file(Path(m0.__file__)),
        "adapter_resolved_path": str(Path(ad.__file__)),
        "adapter_sha256": _sha_file(Path(ad.__file__)),
    }
    lo = pl.date(*map(int, assessment_start.split("-")))
    hi = pl.date(*map(int, assessment_end.split("-")))

    try:
        # ---- requests: restricted to the assessment window BEFORE keys
        _require_columns(lineups, REQ_KEYS + ["game_date", "nine_distinct"]
                         + [f"u_slot_{i}" for i in range(1, 10)],
                         "projected lineups")
        long, n_uncovered = ad.projected_long(lineups)
        long_dev = long.filter(
            (pl.col("game_date") >= lo) & (pl.col("game_date") <= hi))
        if long_dev.height == 0:
            raise ValueError(
                "no projected-lineup requests within the declared "
                "assessment window; refusing")
        req_keys = long_dev.select(*REQ_KEYS).unique()

        # ---- actual PAs: preserve EVERY completed PA of requested
        # starters (no projected-batter or slot filter) ------------------
        _require_columns(pa, ["game_date", "game_pk", "pitcher", "batter",
                             "events"], "PA source")
        sub = pa.join(req_keys, on=REQ_KEYS, how="semi")
        sub = sub.filter((pl.col("game_date") >= lo)
                         & (pl.col("game_date") <= hi))
        if sub.height == 0:
            raise ValueError(
                "no completed PAs for the requested starters within the "
                "declared assessment window; refusing")
        out = sub.with_columns(
            m0.map_statcast_events(pl.col("events")).alias("class_label")
        ).select("game_pk", "side", "pitcher", "at_bat_number", "batter",
                 "class_label")

        # ---- invalid-label refusal BEFORE any assessment output --------
        invalid = out.filter(
            pl.col("class_label").is_null()
            | (pl.col("class_label") < 0)
            | (pl.col("class_label") >= m0.N_CLASSES))
        if invalid.height:
            examples = invalid.select(*REQ_KEYS, "at_bat_number", "batter",
                                      "class_label").head(5).rows()
            fail(out_dir, initial_sha=None, gate="invalid_class_labels",
                 detail={
                     "n_invalid": int(invalid.height),
                     "examples": examples,
                     "detail": ("unrecognized/null events must not be "
                                "classified as non-K or scored; correct "
                                "the outcome source or obtain an "
                                "explicit owner decision")})
        # ---- duplicate actual-PA identity: counted correctly, refused ---
        identity = ["game_pk", "side", "pitcher", "at_bat_number", "batter"]
        duplicate_rows = int(out.height - out.select(identity).n_unique())
        if duplicate_rows:
            fail(out_dir, initial_sha=None, gate="duplicate_pa_identity",
                 detail={"duplicate_rows": duplicate_rows,
                         "detail": "observations are never silently "
                                   "deduplicated"})

        # ---- start reconciliation via actual key-set differences -------
        assessment_keys = out.select(*REQ_KEYS).unique()
        missing = req_keys.join(assessment_keys, on=REQ_KEYS, how="anti")
        unrequested = assessment_keys.join(req_keys, on=REQ_KEYS,
                                           how="anti")
        if unrequested.height:
            fail(out_dir, initial_sha=None, gate="unrequested_outcomes",
                 detail={
                     "n_unrequested_starts": int(unrequested.height),
                     "examples": unrequested.head(5).rows(),
                     "detail": "semi-join construction makes this "
                               "impossible; a violation is an internal "
                               "accounting error"})

        # ---- write once + durable receipt -------------------------------
        out_path = out_dir / "assessment_2025H1_v1.parquet"
        out.write_parquet(out_path)
        accounting = {
            "request_starts": int(req_keys.height),
            "assessment_starts": int(assessment_keys.height),
            "missing_outcome_starts": int(missing.height),
            "missing_outcome_examples": missing.head(5).rows(),
            "unrequested_outcome_starts": int(unrequested.height),
            "assessment_pas": int(out.height),
            "label_counts": {
                str(label): int(
                    out.filter(pl.col("class_label") == label).height)
                for label in [-1, 0, 1, 2, 3]},
            "lineup_uncovered_slots": int(n_uncovered),
        }
        receipt = {
            "preparation_id": PREPARATION_ID,
            "ack_route": ack_route,
            "code_identity": code_identity,
            "assessment_window": [assessment_start, assessment_end],
            "input_frame_identities": {
                "pa_frame_sha256": _frame_sha(pa),
                "lineups_frame_sha256": _frame_sha(lineups),
            },
            "accounting": accounting,
            "outputs": {"assessment_2025H1_v1.parquet":
                        _sha_file(out_path)},
        }
        receipt_path = out_dir / "preparation_receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=1,
                                           sort_keys=True, default=str),
                                encoding="utf-8")
    except Exception as exc:
        # fail() has already written the authoritative gate record; the
        # outer handler must not clobber it with a generic record
        if not failure_path.exists():
            failure = {"stage": PREPARATION_ID, "failure": True,
                       "error": repr(exc)}
            failure_path.write_text(json.dumps(failure, indent=1,
                                               sort_keys=True),
                                    encoding="utf-8")
        raise
    return {"out_dir": str(out_dir),
            "assessment_path": str(out_path),
            "assessment_sha256": receipt["outputs"][
                "assessment_2025H1_v1.parquet"],
            "accounting": accounting}


def fail(out_dir: Path, *, initial_sha, gate: str, detail: dict) -> None:
    rec = {"stage": PREPARATION_ID, "failure": True, "gate": gate,
           "detail": detail, "initial_receipt_sha256": initial_sha}
    (Path(out_dir) / "failure_record.json").write_text(
        json.dumps(rec, indent=1, sort_keys=True), encoding="utf-8")
    msg = json.dumps(detail, sort_keys=True, default=str)[:400]
    raise ValueError(f"{gate}: {msg}")


def _require_columns(frame: pl.DataFrame, required: list, name: str) -> None:
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(f"{name}: missing column(s) {missing}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Stage-1 assessment preparation (no fitting, no "
                    "scoring). Technical ack gate only.")
    p.add_argument("--pa-source", required=True)
    p.add_argument("--lineups", required=True)
    p.add_argument("--expected-pa-sha256", required=True)
    p.add_argument("--expected-lineups-sha256", required=True)
    p.add_argument("--assessment-start", required=True)
    p.add_argument("--assessment-end", required=True)
    p.add_argument("--out-dir", required=True,
                   help="fresh write-once preparation directory")
    p.add_argument("--execution-ack", required=True)
    args = p.parse_args(argv)
    if args.execution_ack != EXECUTION_ACK_TOKEN:
        print("PREPARATION REFUSED: invalid acknowledgement; no input "
              "read, nothing created.", file=sys.stderr)
        return 2
    for name, path, exp in (("PA source", args.pa_source,
                             args.expected_pa_sha256),
                            ("projected lineups", args.lineups,
                             args.expected_lineups_sha256)):
        actual = _sha_file(Path(path))
        if actual != exp:
            print(f"INPUT IDENTITY MISMATCH for {name}: "
                  f"actual={actual} expected={exp}; refusing before "
                  "decoding.", file=sys.stderr)
            return 1
    pa = pl.read_parquet(args.pa_source)
    lineups = pl.read_parquet(args.lineups)
    res = prepare_assessment(pa, lineups, args.out_dir,
                             assessment_start=args.assessment_start,
                             assessment_end=args.assessment_end,
                             execution_ack=args.execution_ack,
                             ack_route="cli")
    print(json.dumps(res, indent=1, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
