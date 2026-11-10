"""Candidate-parity entry point (parity-platoon-candidate-v1).

ONE THIN, COMMITTED INVOCATION (no generic framework): does the
integrated prediction path (`label_free_prediction.run_prediction`,
main lineage) reproduce the saved candidate forecasts from the same
fitted model and pinned inputs, for ONE explicitly selected registered
arm? Supported arms (registered 2026-11-09 ablation-baseline decision):
- "platoon_challenger": the 12-feature platoon recipe (development
  challenger);
- "multinomial_control": the 8-feature multinomial + pooled W0 recipe
  (reference control).
Both arms' saved forecasts live in ONE platoon_comparison reference
dir (model_artifacts.json carries both model keys; the keyed/pmf
parquets carry both arms' columns), so arm selection only chooses the
registered model key, keyed-probability column suffix, and saved PMF
column name below. Anything else refuses BEFORE any decode or write.

SYNTHETIC-TESTED ONLY until separately authorized; write-once outputs.
Reuses: statcast_event_bridge (terminal-event labels),
label_free_prediction / label_free_inference (the integrated path),
adapter (projected_long, validate_bf37_by_start, sha256_file),
binary_k_comparison (registered cohort-hash recipe),
platoon_comparison / platoon_features / forecast_states_v2 /
m0_multiclass (imported seams, identities recorded). No workload
recomputation (the saved pooled-by-date BF37 artifact IS the runner's
own record), no refit, no reference regeneration, no outcome scoring.

Identity discipline:
- the expected SHA-256 of the accepted reference receipt is a REQUIRED
  execution parameter; the receipt is verified by file hash BEFORE its
  output manifest is interpreted; model/reference artifact hashes are
  then verified from that receipt BEFORE those files are decoded;
- input byte pins (PA, lineups, raw events) and the cohort sorted-key
  content hash are required parameters, ENFORCED pre-decode;
- no expected value is derived from the files being checked.

Population: requests are restricted to the declared cohort BEFORE
feature construction; key-set equality is required at both forecast
grains (PA grain, start/bucket grain); expected row counts derive from
the validated keys and the 9-slot/24-bucket contract (no hard-coded
intermediate request count). Duplicate or null comparison identities
refuse before any comparison or deduplication.

Acceptance: key equality plus maximum absolute difference <= 1e-12 on
every declared class-probability column and every K-PMF bucket. Exact
observed differences are reported; zero is not required. Any mismatch
stops the action (failure_record.json, NO receipt_final, no
parity_comparison.json).

Access disclosure (declared): full-file decode of the PA table, the
projected-lineups parquet, and the declared raw Statcast event files
(bridge label consumption). Filtering happens after decode. Post-R3
rows are documented in the PA source (which spans through 2025-09-28)
and in the full-season 2025 raw-event file; their presence in any other
decoded file is not asserted. They are excluded from the comparison
population by the cohort key restriction and the wrapper's structural
filters. Execution requires fresh owner authorization; prior
experiment approvals do not carry over.

Receipt ordering (explicit): execution-ack gate -> destination
nonexistence (before any private decode) -> reference-receipt hash
verification -> manifest interpretation + artifact hash verification ->
receipt_initial.json (identities + expectations) -> pre-decode input
byte pins -> decode/bridge -> cohort identity + restriction -> keyed
BF37 -> prediction -> comparison -> receipt_initial immutability
verification -> parity_comparison.json -> receipt_final.json (both
published atomically AFTER the immutability check passes). Any refusal
or failure writes failure_record.json describing the ACTUAL stage and
the files actually written, and re-raises.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import binary_k_comparison as bk  # noqa: E402
from pregame_pa_ext import forecast_states_v2 as fv  # noqa: E402
from pregame_pa_ext import label_free_inference as lfi  # noqa: E402
from pregame_pa_ext import label_free_prediction as lp  # noqa: E402
from pregame_pa_ext import m0_multiclass as m0  # noqa: E402
from pregame_pa_ext import platoon_comparison as pc  # noqa: E402
from pregame_pa_ext import platoon_features as pf  # noqa: E402
from pregame_pa_ext import statcast_event_bridge as seb  # noqa: E402

EXPERIMENT_ID = "parity_platoon_candidate_v1"
ACK_ROUTE = "EXECUTE-PARITY-PLATOON-CANDIDATE-V1"
EXECUTION_ACK_TOKEN = ACK_ROUTE
TOLERANCE = 1e-12
REF_RECEIPT_NAME = "receipt_final.json"
REF_MANIFEST_FIELD = "outputs"
REF_MODEL_FILE = "model_artifacts.json"
REF_KEYED_FILE = "keyed_pa_probabilities.parquet"
REF_PMF_FILE = "k_pmf_per_start_v1.parquet"
REF_BF_FILE = "bf37_pooled_by_date_v1.parquet"
ARM_CHALLENGER = "platoon_challenger"
ARM_CONTROL = "multinomial_control"
# explicit supported arm/model/column mapping (registered ablation
# baseline 2026-11-09); both arms live in one platoon_comparison
# reference dir; any other selection refuses before decode or write
SUPPORTED_ARMS = {
    ARM_CHALLENGER: {"model_key": "platoon_challenger",
                     "keyed_suffix": "_platoon",
                     "pmf_column": "pmf_platoon"},
    ARM_CONTROL: {"model_key": "multinomial_control",
                  "keyed_suffix": "_control",
                  "pmf_column": "pmf_multinomial_control"},
}
WRAP_PMF_COLUMN = "pmf_h3_raw"
KEYED_COLS = ["game_pk", "side", "pitcher", "slot", "batter"]
START_KEYS = ["game_pk", "side", "pitcher"]
PMF_KEYS = START_KEYS + ["bucket"]
N_SLOTS = 9
N_BUCKETS = 24


def _write_json(path: Path, payload: dict) -> None:
    """Atomic local JSON publication (temp + os.replace): a failed or
    interrupted write can never leave a partial or valid-looking
    success artifact."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True,
                              default=str), encoding="utf-8")
    os.replace(tmp, path)


def _sha_file(path: Path) -> str:
    return bk._sha_file(Path(path))


def _code_identity() -> dict:
    ident = {}
    for mod in (lp, lfi, pc, pf, fv, ad, seb, m0, bk):
        name = mod.__name__.rsplit(".", 1)[-1]
        ident[f"{name}_sha256"] = _sha_file(Path(mod.__file__))
    return ident


def _runtime_versions() -> dict:
    return {"python": sys.version.split()[0],
            "polars": pl.__version__,
            "numpy": np.__version__}


def _require_finite(frame: pl.DataFrame, cols: list, ctx: str) -> None:
    for c in cols:
        v = frame[c]
        if v.null_count() > 0:
            raise ValueError(f"{ctx}: null values in {c!r}")
        if not np.all(np.isfinite(v.to_numpy())):
            raise ValueError(f"{ctx}: nonfinite values in {c!r}")


def _reject_dup_null(frame: pl.DataFrame, keys: list, ctx: str) -> None:
    null_mask = pl.any_horizontal([pl.col(c).is_null() for c in keys])
    if frame.filter(null_mask).height > 0:
        raise ValueError(f"{ctx}: null identity key(s) present")
    dups = frame.group_by(keys).agg(n=pl.len()).filter(pl.col("n") > 1)
    if dups.height > 0:
        raise ValueError(
            f"{ctx}: {dups.height} duplicate identity key(s) "
            f"(sample: {dups.select(keys).head(3).rows()})")


def _verify_reference_receipt(ref_dir: Path,
                              expected_receipt_sha: str) -> dict:
    """Verify the accepted reference receipt by file hash BEFORE its
    manifest is interpreted; resolve artifact hashes from it."""
    receipt_path = Path(ref_dir) / REF_RECEIPT_NAME
    if not receipt_path.exists():
        raise ValueError(f"reference receipt missing: {receipt_path}")
    actual = _sha_file(receipt_path)
    if actual != expected_receipt_sha:
        raise ValueError(
            f"reference receipt identity mismatch: actual={actual} "
            f"expected={expected_receipt_sha}; refusing to interpret "
            "an unverified manifest")
    manifest = json.loads(receipt_path.read_text(encoding="utf-8"))
    if REF_MANIFEST_FIELD not in manifest:
        raise ValueError(
            f"reference receipt lacks the {REF_MANIFEST_FIELD!r} "
            "manifest field; artifact identity cannot be resolved")
    return manifest


def _verify_artifact_hash(manifest: dict, ref_dir: Path,
                          name: str) -> Path:
    expected = manifest[REF_MANIFEST_FIELD].get(name)
    if expected is None:
        raise ValueError(
            f"reference manifest lacks an entry for {name!r}")
    p = Path(ref_dir) / name
    if not p.exists():
        raise ValueError(f"reference artifact missing: {p}")
    actual = _sha_file(p)
    if actual != expected:
        raise ValueError(
            f"reference artifact identity mismatch for {name}: "
            f"actual={actual} expected={expected}")
    return p


def _load_cohort(cohort_keys_path, expected_cohort_hash) -> pl.DataFrame:
    ck = pl.read_parquet(cohort_keys_path)
    missing = [c for c in START_KEYS if c not in ck.columns]
    if missing:
        raise ValueError(f"cohort keys input lacks column(s) {missing}")
    _reject_dup_null(ck, START_KEYS, "cohort keys")
    cohort_unique = ck.select(START_KEYS).unique()
    computed = bk._cohort_hash(
        [tuple(r) for r in cohort_unique.iter_rows()])
    if computed != expected_cohort_hash:
        raise ValueError(
            f"cohort identity mismatch: actual={computed} "
            f"expected={expected_cohort_hash}")
    return cohort_unique


def _keyed_bf37(bf_by_date_path: Path,
                starts: pl.DataFrame) -> pl.DataFrame:
    """Keyed per-start BF37 from the SAVED pooled-by-date vectors
    (reuse; no workload recomputation)."""
    b = pl.read_parquet(bf_by_date_path)
    for c in ("cutoff_date", "bf_category", "bf37_w0_pooled"):
        if c not in b.columns:
            raise ValueError(f"BF reference lacks column {c!r}")
    _reject_dup_null(b, ["cutoff_date", "bf_category"], "BF reference")
    cats = sorted(set(b["bf_category"].to_list()))
    if cats != list(range(37)):
        raise ValueError(
            f"BF reference categories malformed: {cats[:5]}...; "
            "expected exactly 0..36")
    _require_finite(b, ["bf37_w0_pooled"], "BF reference")
    if b.filter(pl.col("bf37_w0_pooled") < 0).height > 0:
        raise ValueError("BF reference carries negative densities")
    dates_needed = set(starts["game_date"].unique().to_list())
    b = b.with_columns(
        pl.col("cutoff_date").str.to_date("%Y-%m-%d").alias("_d"))
    available = set(b["_d"].unique().to_list())
    missing = sorted(dates_needed - available)
    if missing:
        raise ValueError(
            f"{len(missing)} start game_date(s) absent from the saved "
            f"BF by-date reference (first: {missing[:3]}); refusing "
            "rather than inventing a distribution")
    wide = b.pivot(values="bf37_w0_pooled", index="_d",
                   on="bf_category").sort("_d")
    vec_by_date = {}
    for r in wide.iter_rows(named=True):
        v = np.asarray([r[str(j)] if str(j) in wide.columns
                        else r[j] for j in range(37)], dtype=np.float64)
        if abs(float(v.sum()) - 1.0) > 1e-9:
            raise ValueError(
                f"BF reference distribution invalid at {r['_d']}: "
                f"sum={float(v.sum())!r}")
        vec_by_date[r["_d"]] = v
    rows = []
    for r in starts.select(START_KEYS + ["game_date"]).iter_rows(
            named=True):
        v = vec_by_date[r["game_date"]]
        rows.append({"game_pk": int(r["game_pk"]),
                     "side": str(r["side"]),
                     "pitcher": int(r["pitcher"]),
                     **{f"pmf37_{j}": float(v[j])
                        for j in range(37)}})
    return pl.DataFrame(rows)


def run_parity(*, pa_path, lineups_path, cohort_keys_path,
               raw_event_paths, reference_dir,
               expected_reference_receipt_sha256,
               expected_pa_sha256, expected_lineups_sha256,
               expected_raw_event_sha256s, expected_cohort_hash,
               out_dir, execution_ack, arm=ARM_CHALLENGER) -> dict:
    """One exact parity execution; see the module docstring."""
    if execution_ack != EXECUTION_ACK_TOKEN:
        raise ValueError(
            f"execution acknowledgement required: {ACK_ROUTE}")
    if arm not in SUPPORTED_ARMS:
        raise ValueError(
            f"unsupported arm selection {arm!r}; supported arms: "
            f"{sorted(SUPPORTED_ARMS)} (registered saved "
            "model/reference arms only)")
    arm_map = SUPPORTED_ARMS[arm]
    ref_keyed_suffix = arm_map["keyed_suffix"]
    ref_pmf_column = arm_map["pmf_column"]
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(
            f"destination exists (write-once policy): {out_dir}")

    # reference receipt verified BEFORE any manifest interpretation,
    # and artifact hashes verified BEFORE those files are decoded
    manifest = _verify_reference_receipt(
        Path(reference_dir), expected_reference_receipt_sha256)
    model_path = _verify_artifact_hash(manifest, reference_dir,
                                       REF_MODEL_FILE)
    keyed_path = _verify_artifact_hash(manifest, reference_dir,
                                       REF_KEYED_FILE)
    pmf_path = _verify_artifact_hash(manifest, reference_dir,
                                     REF_PMF_FILE)
    bf_path = _verify_artifact_hash(manifest, reference_dir,
                                    REF_BF_FILE)

    out_dir.mkdir(parents=True)
    initial = {
        "execution_acknowledgement": {"route": ACK_ROUTE,
                                      "token": execution_ack},
        "arm_selection": {"arm": arm, **arm_map},
        "code_identity": _code_identity(),
        "runtime_versions": _runtime_versions(),
        "expected_input_identities": {
            "pa_sha256": expected_pa_sha256,
            "lineups_sha256": expected_lineups_sha256,
            "raw_event_sha256s": list(expected_raw_event_sha256s),
            "cohort_content_hash": expected_cohort_hash,
            "reference_receipt_sha256":
                expected_reference_receipt_sha256,
        },
        "reference_artifacts_verified": {
            REF_MODEL_FILE: _sha_file(model_path),
            REF_KEYED_FILE: _sha_file(keyed_path),
            REF_PMF_FILE: _sha_file(pmf_path),
            REF_BF_FILE: _sha_file(bf_path)},
        "tolerance": TOLERANCE,
        "access_disclosure": (
            "full-file decode of the PA table, the projected-lineups "
            "parquet, and the declared raw Statcast event files; "
            "filtering happens after decode; post-R3 rows are "
            "documented in the PA source (which spans through "
            "2025-09-28) and in the full-season 2025 raw-event file; "
            "their presence in any other decoded file is not "
            "asserted; they are excluded from the comparison "
            "population by the cohort key restriction and the "
            "wrapper's structural filters"),
    }
    state = {"stage": "receipt_initial", "files_written": []}
    initial_path = out_dir / "receipt_initial.json"
    _write_json(initial_path, initial)
    state["files_written"].append("receipt_initial.json")
    initial_sha = _sha_file(initial_path)

    def _fail(err) -> None:
        (out_dir / "failure_record.json").write_text(
            json.dumps({"stage": EXPERIMENT_ID,
                        "failure_stage": state["stage"],
                        "failure": True,
                        "error": repr(err),
                        "files_written": list(state["files_written"]),
                        "note": ("failure_record describes the actual "
                                 "stage and the files actually "
                                 "written; original references "
                                 "untouched")},
                       indent=1, sort_keys=True, default=str),
            encoding="utf-8")

    try:
        # ---- pre-decode input byte pins (ENFORCED) -------------------
        state["stage"] = "input_pins"
        if len(expected_raw_event_sha256s) != len(raw_event_paths):
            raise ValueError(
                "raw-event pin count does not match the declared "
                "raw-event file list")
        pins = [(Path(pa_path), expected_pa_sha256, "pa"),
                (Path(lineups_path), expected_lineups_sha256,
                 "lineups")]
        pins += [(Path(p), s, f"raw_event[{i}]")
                 for i, (p, s) in enumerate(zip(raw_event_paths,
                                                expected_raw_event_sha256s))]
        for p, expected, name in pins:
            if not p.exists():
                raise ValueError(f"{name} input missing: {p}")
            actual = _sha_file(p)
            if actual != expected:
                raise ValueError(
                    f"INPUT IDENTITY MISMATCH for {name}: "
                    f"actual={actual} expected={expected}")

        # ---- decode + labels (bridge consumes the raw files) ---------
        state["stage"] = "decode_bridge"
        pa = pl.read_parquet(pa_path)
        lineups = pl.read_parquet(lineups_path)
        pa_labeled, label_acc = seb.attach_terminal_event_labels(
            pa, [Path(p) for p in raw_event_paths])

        # ---- cohort identity + restriction BEFORE construction -------
        state["stage"] = "cohort_restriction"
        cohort_unique = _load_cohort(cohort_keys_path,
                                     expected_cohort_hash)
        lineups_restricted = lineups.join(cohort_unique,
                                          on=START_KEYS, how="semi")
        if lineups_restricted.height == 0:
            raise ValueError(
                "empty request population after cohort restriction")
        long, n_uncovered = ad.projected_long(lineups_restricted)
        if n_uncovered > 0:
            raise ValueError(
                f"{n_uncovered} uncovered slot(s) in the restricted "
                "lineups; the parity population must be complete")
        starts = long.select(START_KEYS + ["game_date"]).unique()
        cohort_set = {(int(a), str(b), int(c))
                      for a, b, c in cohort_unique.iter_rows()}
        starts_set = {(int(r["game_pk"]), str(r["side"]),
                       int(r["pitcher"]))
                      for r in starts.iter_rows(named=True)}
        if starts_set != cohort_set:
            raise ValueError(
                "cohort/lineup start keys differ: missing="
                f"{sorted(cohort_set - starts_set)[:3]} extra="
                f"{sorted(starts_set - cohort_set)[:3]}")
        n_starts = len(cohort_set)
        expected_pa_rows = N_SLOTS * n_starts
        expected_pmf_rows = N_BUCKETS * n_starts

        # ---- keyed BF37 from the SAVED by-date vectors (reuse) -------
        state["stage"] = "workload_mapping"
        bf_keyed = _keyed_bf37(bf_path, starts)
        bf_keyed, bf_meta = ad.validate_bf37_by_start(
            bf_keyed.select(START_KEYS + ad.PMF37_COLS), starts)

        # ---- saved fitted candidate model (hash-verified file) -------
        state["stage"] = "model_load"
        model_all = json.loads(model_path.read_text(encoding="utf-8"))
        ref_model_key = arm_map["model_key"]
        if ref_model_key not in model_all:
            raise ValueError(
                f"model artifact lacks the {ref_model_key!r} entry")
        model = model_all[ref_model_key]
        classes = [int(c) for c in model["classes"]]

        # ---- integrated prediction path ------------------------------
        state["stage"] = "prediction"
        result = lp.run_prediction(model, pa_labeled,
                                   lineups_restricted, bf_keyed)

        # ---- PA-grain comparison --------------------------------------
        state["stage"] = "comparison"
        ref_keyed = pl.read_parquet(keyed_path)
        wrap_keyed = result["keyed_pa_probabilities"]
        ref_cols = [f"p_class_{c}{ref_keyed_suffix}" for c in classes]
        wrap_cols = [f"p_class_{c}" for c in classes]
        for frame, ctx, cols in ((ref_keyed, "reference keyed",
                                  KEYED_COLS + ref_cols),
                                 (wrap_keyed, "wrapper keyed",
                                  KEYED_COLS + wrap_cols)):
            absent = [c for c in cols if c not in frame.columns]
            if absent:
                raise ValueError(f"{ctx}: missing column(s) {absent}")
            _reject_dup_null(frame, KEYED_COLS, ctx)
        if ref_keyed.height != expected_pa_rows:
            raise ValueError(
                f"reference keyed row count {ref_keyed.height} != "
                f"derived {expected_pa_rows} ({N_SLOTS} x {n_starts})")
        if wrap_keyed.height != expected_pa_rows:
            raise ValueError(
                f"wrapper keyed row count {wrap_keyed.height} != "
                f"derived {expected_pa_rows} ({N_SLOTS} x {n_starts})")
        rk = ref_keyed.sort(KEYED_COLS)
        wk = wrap_keyed.sort(KEYED_COLS)
        if rk.select(KEYED_COLS).rows() != \
                wk.select(KEYED_COLS).rows():
            raise ValueError(
                "PA-grain key sets differ (missing or extra "
                "comparison identities); no inner-join comparison")
        _require_finite(rk, ref_cols, "reference keyed")
        _require_finite(wk, wrap_cols, "wrapper keyed")
        pa_diffs = {}
        for c in classes:
            d = np.abs(
                rk[f"p_class_{c}{ref_keyed_suffix}"].to_numpy()
                - wk[f"p_class_{c}"].to_numpy())
            pa_diffs[f"p_class_{c}"] = float(d.max())
        pa_max = max(pa_diffs.values())

        # ---- PMF-grain comparison -------------------------------------
        ref_pmf = pl.read_parquet(pmf_path)
        wrap_pmf = result["k_pmf_per_start"]
        for frame, ctx, val_col in ((ref_pmf, "reference pmf",
                                      ref_pmf_column),
                                    (wrap_pmf, "wrapper pmf",
                                     WRAP_PMF_COLUMN)):
            absent = [c for c in PMF_KEYS + [val_col]
                      if c not in frame.columns]
            if absent:
                raise ValueError(f"{ctx}: missing column(s) {absent}")
            _reject_dup_null(frame, PMF_KEYS, ctx)
        bad_bucket = ref_pmf.filter(
            ~pl.col("bucket").is_in(list(range(N_BUCKETS))))
        if bad_bucket.height > 0:
            raise ValueError(
                f"reference pmf bucket outside 0..{N_BUCKETS - 1} "
                f"({bad_bucket.height} row(s))")
        if ref_pmf.height != expected_pmf_rows:
            raise ValueError(
                f"reference pmf row count {ref_pmf.height} != derived "
                f"{expected_pmf_rows} ({N_BUCKETS} x {n_starts})")
        if wrap_pmf.height != expected_pmf_rows:
            raise ValueError(
                f"wrapper pmf row count {wrap_pmf.height} != derived "
                f"{expected_pmf_rows} ({N_BUCKETS} x {n_starts})")
        rp = ref_pmf.sort(PMF_KEYS)
        wp = wrap_pmf.sort(PMF_KEYS)
        if rp.select(PMF_KEYS).rows() != \
                wp.select(PMF_KEYS).rows():
            raise ValueError(
                "PMF-grain key sets differ (missing or extra "
                "comparison identities)")
        _require_finite(rp, [ref_pmf_column], "reference pmf")
        _require_finite(wp, [WRAP_PMF_COLUMN], "wrapper pmf")
        pmf_max = float(np.abs(
            rp[ref_pmf_column].to_numpy()
            - wp[WRAP_PMF_COLUMN].to_numpy()).max())

        # ---- acceptance ------------------------------------------------
        state["stage"] = "acceptance_check"
        comparison = {
            "tolerance": TOLERANCE,
            "n_starts": n_starts,
            "n_pa_rows": expected_pa_rows,
            "n_pmf_rows": expected_pmf_rows,
            "pa_grain_max_abs_diff_per_class": pa_diffs,
            "pa_grain_max_abs_diff": pa_max,
            "pmf_grain_max_abs_diff": pmf_max,
            "column_mappings": {
                "keyed": {f"p_class_{c}{ref_keyed_suffix}":
                          f"p_class_{c}" for c in classes},
                "pmf": {ref_pmf_column: WRAP_PMF_COLUMN}},
            "within_tolerance": (pa_max <= TOLERANCE
                                 and pmf_max <= TOLERANCE),
        }
        if not comparison["within_tolerance"]:
            raise ValueError(
                f"PARITY MISMATCH: pa_grain_max_abs_diff={pa_max!r}, "
                f"pmf_grain_max_abs_diff={pmf_max!r}, "
                f"tolerance={TOLERANCE!r}; exact per-class "
                f"differences={pa_diffs}")

        # ---- finalization: immutability verified BEFORE publication ---
        state["stage"] = "finalization"
        if _sha_file(initial_path) != initial_sha:
            raise ValueError(
                "receipt_initial immutability check FAILED: the "
                "initial receipt mutated during execution; no success "
                "artifacts published")

        _write_json(out_dir / "parity_comparison.json", comparison)
        state["files_written"].append("parity_comparison.json")

        final = dict(initial)
        final["counts"] = {
            "n_starts": n_starts,
            "n_uncovered_slots": int(n_uncovered),
            "n_pa_rows": int(wrap_keyed.height),
            "n_pmf_rows": int(wrap_pmf.height),
            "n_pa_rows_excluded_r3":
                int(result["n_pa_rows_excluded_r3"]),
        }
        final["label_accounting"] = label_acc
        final["cohort_identity"] = {
            "n_keys": n_starts,
            "content_hash": expected_cohort_hash,
            "match": True}
        final["comparison"] = comparison
        final["outputs"] = {
            "parity_comparison.json": _sha_file(
                out_dir / "parity_comparison.json")}
        final["acceptance"] = {"receipt_chain": initial_sha,
                               "status": "COMPLETED"}
        _write_json(out_dir / "receipt_final.json", final)
        state["files_written"].append("receipt_final.json")
        if _sha_file(initial_path) != initial_sha:
            raise ValueError(
                "receipt_initial mutated after the immutability check; "
                "success artifacts published under a compromised "
                "chain - treat receipt_final as INVALID")
        return comparison
    except Exception as e:  # noqa: BLE001
        _fail(e)
        raise


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Candidate-parity check: integrated prediction "
                    "path vs saved candidate forecasts for one "
                    "registered arm (platoon_challenger or "
                    "multinomial_control)")
    ap.add_argument("--arm", default=ARM_CHALLENGER,
                    help="registered saved arm to verify "
                         "(default: platoon_challenger)")
    ap.add_argument("--pa-source", required=True)
    ap.add_argument("--lineups", required=True)
    ap.add_argument("--cohort-keys", required=True)
    ap.add_argument("--raw-events", required=True,
                    help="comma-separated raw Statcast parquet paths")
    ap.add_argument("--reference-dir", required=True)
    ap.add_argument("--expected-reference-receipt-sha256",
                    required=True)
    ap.add_argument("--expected-pa-sha256", required=True)
    ap.add_argument("--expected-lineups-sha256", required=True)
    ap.add_argument("--expected-raw-event-sha256s", required=True,
                    help="comma-separated, same order as --raw-events")
    ap.add_argument("--expected-cohort-hash", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--execution-ack", required=True)
    args = ap.parse_args(argv)
    run_parity(
        arm=args.arm,
        pa_path=args.pa_source,
        lineups_path=args.lineups,
        cohort_keys_path=args.cohort_keys,
        raw_event_paths=args.raw_events.split(","),
        reference_dir=args.reference_dir,
        expected_reference_receipt_sha256=
        args.expected_reference_receipt_sha256,
        expected_pa_sha256=args.expected_pa_sha256,
        expected_lineups_sha256=args.expected_lineups_sha256,
        expected_raw_event_sha256s=
        args.expected_raw_event_sha256s.split(","),
        expected_cohort_hash=args.expected_cohort_hash,
        out_dir=args.out_dir,
        execution_ack=args.execution_ack)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
