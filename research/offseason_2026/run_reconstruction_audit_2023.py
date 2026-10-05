"""Bounded reconstruction-audit runner (2023 forecasts + 2022 history).

PREPARATION ONLY. Real-data execution requires a separate, explicit owner
authorization naming the exact command. Nothing in this module reads real
data at import time; the ``main()`` CLI always hash-verifies real inputs
BEFORE parsing and enforces permitted periods fail-closed.

Contract (from committed spec ``pregame-workload-dev-spec.md`` v2.2 and
``workload_spine.py`` RULE_VERSION workload_spine_v2.2):
- canonical first-pitcher identity via ``_starter_keys`` delegation;
- one identity per observed team side; missing halves quarantined, never
  silently dropped;
- ``is_start`` from canonical key membership only (never realized BF);
- position-player status is a separate attribute and never overrides
  membership (role is not an input anywhere in this pipeline);
- strictly prior-date history with same-game exclusion;
- expected reconciliation counts are checked, never forced.

No fitting, scoring, prediction, candidate ranking, or market analysis
exists in this module.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import polars as pl

import workload_spine as ws  # noqa: E402
# Binds the canonical first-pitcher dependency at import time; the file
# below is hashed into every manifest. Delegation itself runs through
# ws.first_pitcher_keys (the reviewed path), never around it.
import Python.pitcher_features as pitcher_features_base  # noqa: E402

AUDIT_VERSION = "reconstruction_audit_v1"
REQUIRED_RULE_VERSION = "workload_spine_v2.2"

SAVANT_2023_REL = Path("data/Savant-Data/regular/2023/statcast_2023_regular.parquet")
SAVANT_2022_REL = Path("data/Savant-Data/regular/2022/statcast_2022_regular.parquet")
SAVANT_2023_SHA = "b9f9db9923badca17e551cf23be8429bfba984361732a8911bf0d68a40d5285f"
SAVANT_2022_SHA = "63d40a4955da73ab8f9b01d87d90dd676acdf8b7447c574a5edf807897724ce4"

PERMITTED_FORECAST_YEARS = frozenset({2023})
PERMITTED_HISTORY_YEARS = frozenset({2022})

EXPECTED_N_EXPANDED = 4860
EXPECTED_N_PA9 = 4663
EXPECTED_N_OUTSIDE = 197

PITCH_KEY_COLUMNS = (
    "game_pk", "pitcher", "game_date", "inning",
    "inning_topbot", "at_bat_number", "pitch_number",
)


class AuditFailure(Exception):
    """Fail-closed audit error carrying a nonzero exit code."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_input(path: Path, expected_sha: str, label: str) -> dict:
    """Hash-verify a real input BEFORE any parsing. Raises on failure."""
    if not path.is_file():
        raise AuditFailure("missing input %s: %s" % (label, path))
    actual = sha256_file(path)
    if actual != expected_sha.lower():
        raise AuditFailure(
            "BLOCKED: hash mismatch for %s: %s" % (label, actual))
    st = path.stat()
    return {"path": str(path), "sha256": actual, "bytes": st.st_size}


def frame_years(frame: pl.DataFrame, date_col: str = "game_date") -> set[int]:
    col = frame[date_col]
    if col.dtype == pl.Date:
        return set(d.year for d in col.to_list())
    if col.dtype == pl.Datetime:
        return set(d.year for d in col.to_list())
    return set(int(str(d)[:4]) for d in col.to_list())


def check_period(frame: pl.DataFrame, allowed: frozenset[int], label: str) -> None:
    years = frame_years(frame)
    if not years <= set(allowed):
        raise AuditFailure(
            "period violation in %s: years %s outside %s"
            % (label, sorted(years), sorted(allowed)))


def audit_identity(pitch_frame: pl.DataFrame) -> tuple[pl.DataFrame, list[dict]]:
    """Canonical per-game identity with explicit quarantine.

    Returns (keys, quarantine). Every input game either yields
    team-side keys or a quarantine record with a reason; no game is
    silently dropped.
    """
    missing = sorted(set(PITCH_KEY_COLUMNS) - set(pitch_frame.columns))
    if missing:
        raise AuditFailure("pitch frame missing columns: %s" % (missing,))
    keys_parts: list[pl.DataFrame] = []
    quarantine: list[dict] = []
    for key, game in pitch_frame.partition_by("game_pk", as_dict=True).items():
        game_pk = key[0] if isinstance(key, tuple) else key
        try:
            keys_parts.append(ws.first_pitcher_keys(game))
        except ValueError as exc:
            quarantine.append({"game_pk": game_pk, "reason": str(exc)})
    keys = (
        pl.concat(keys_parts, how="vertical")
        if keys_parts
        else pl.DataFrame(schema={
            "game_pk": pl.Int64, "forecast_pitcher": pl.Int64,
            "inning_topbot": pl.String, "is_home": pl.Boolean,
            "game_date": pl.Date,
        })
    )
    return keys, quarantine


def check_duplicate_identities(keys: pl.DataFrame) -> pl.DataFrame:
    dups = (
        keys.group_by(["game_pk", "forecast_pitcher"])
        .agg(pl.len().alias("n"))
        .filter(pl.col("n") > 1)
    )
    if dups.height:
        raise AuditFailure(
            "duplicate canonical identities: %d (game_pk, pitcher) pairs"
            % dups.height)
    return dups


def is_start(game_pk: int, pitcher: int, key_set: set[tuple[int, int]]) -> bool:
    """Start membership from canonical keys only. No BF, no role input."""
    return (game_pk, pitcher) in key_set


def bf_proxy_table(pitch_frame: pl.DataFrame) -> pl.DataFrame:
    """Realized batters-faced proxy: distinct at-bats per (game, pitcher).

    Descriptive stratum input only (PA>=9 is outcome-defined, never a
    pregame eligibility rule).
    """
    return pitch_frame.group_by(["game_pk", "pitcher"]).agg(
        pl.col("at_bat_number").n_unique().alias("bf_proxy"))


def reconcile_population(keys: pl.DataFrame,
                         bf_table: pl.DataFrame) -> dict:
    keyed = keys.select(
        pl.col("game_pk"),
        pl.col("forecast_pitcher").alias("pitcher"),
    ).join(bf_table, on=["game_pk", "pitcher"], how="left")
    n_expanded = keyed.height
    n_pa9 = keyed.filter(pl.col("bf_proxy") >= 9).height
    n_outside = n_expanded - n_pa9
    result = {
        "n_expanded": n_expanded,
        "n_pa9": n_pa9,
        "n_outside": n_outside,
        "expected": {
            "n_expanded": EXPECTED_N_EXPANDED,
            "n_pa9": EXPECTED_N_PA9,
            "n_outside": EXPECTED_N_OUTSIDE,
        },
        "match": (
            n_expanded == EXPECTED_N_EXPANDED
            and n_pa9 == EXPECTED_N_PA9
            and n_outside == EXPECTED_N_OUTSIDE
        ),
    }
    if not result["match"]:
        result["mismatch_detail"] = (
            "got (%d, %d, %d), expected (%d, %d, %d)"
            % (n_expanded, n_pa9, n_outside,
               EXPECTED_N_EXPANDED, EXPECTED_N_PA9, EXPECTED_N_OUTSIDE))
    return result


def build_history_appearances(
        pitch_2022: pl.DataFrame,
        pitch_2023: pl.DataFrame) -> tuple[pl.DataFrame, list[dict]]:
    """Prior-appearance rows with canonical is_start for both seasons.

    Returns (appearances, history_quarantine). Games that cannot yield
    canonical keys are quarantined with reasons and contribute no
    appearances; the audit continues and the manifest records them.

    pitches = pitch-row count; outs is recorded as 0 because builder
    v2.2 never reads the outs column (documented, not hidden).
    """
    parts = []
    history_quarantine: list[dict] = []
    for pitch_frame in (pitch_2022, pitch_2023):
        keys, quarantine = audit_identity(pitch_frame)
        history_quarantine.extend(quarantine)
        good_games = set(keys["game_pk"].to_list())
        key_flag = keys.select(
            "game_pk",
            pl.col("forecast_pitcher").alias("pitcher"),
            pl.lit(True).alias("is_start"),
        )
        game_dates = (
            pitch_frame.filter(pl.col("game_pk").is_in(good_games))
            .select("game_pk", "game_date")
            .unique(subset=["game_pk"])
        )
        parts.append(
            bf_proxy_table(
                pitch_frame.filter(pl.col("game_pk").is_in(good_games))
            ).join(key_flag, on=["game_pk", "pitcher"], how="left")
            .with_columns(pl.col("is_start").fill_null(False))
            .join(game_dates, on="game_pk", how="left")
            .rename({"bf_proxy": "bf"})
            .with_columns(
                pl.col("bf").alias("pitches"),
                pl.lit(0, dtype=pl.Int64).alias("outs"),
            )
            .select("game_pk", "pitcher", "game_date", "is_start",
                    "pitches", "outs", "bf")
        )
    appearances = (
        pl.concat(parts, how="vertical")
        if parts else pl.DataFrame(schema={
            "game_pk": pl.Int64, "pitcher": pl.Int64,
            "game_date": pl.Date, "is_start": pl.Boolean,
            "pitches": pl.Int64, "outs": pl.Int64, "bf": pl.Int64,
        })
    )
    return appearances, history_quarantine


def sample_cutoff_check(forecast_rows: pl.DataFrame,
                        appearances: pl.DataFrame,
                        population_mean_bf: float,
                        coverage_start, coverage_end,
                        step: int = 200, minimum: int = 20) -> dict:
    """Rebuild single-row histories on a deterministic sample and compare.

    Equality shows the full run treated every sampled row identically
    to an isolated rebuild (determinism and row-independence). It does
    not by itself prove the cutoff rule correct; rule-correctness rests
    on the builder's unit tests and inspection. Sampled, never exhaustive.
    """
    idxs = list(range(0, forecast_rows.height, step))
    if len(idxs) < minimum:
        idxs = list(range(min(minimum, forecast_rows.height)))
    full = ws.build_appearance_history(
        appearances, forecast_rows, population_mean_bf,
        coverage_start, coverage_end)
    full_rows = full.to_dicts()
    mismatches = []
    for i in idxs:
        one = forecast_rows.slice(i, 1)
        solo = ws.build_appearance_history(
            appearances, one, population_mean_bf,
            coverage_start, coverage_end).row(0, named=True)
        if solo != full_rows[i]:
            mismatches.append(i)
    return {"sampled": len(idxs), "mismatches": mismatches,
            "ok": not mismatches}


def code_identity() -> dict:
    return {
        "audit_version": AUDIT_VERSION,
        "workload_spine_rule": ws.RULE_VERSION,
        "workload_spine_file": sha256_file(Path(ws.__file__)),
        "starter_keys_file": sha256_file(
            Path(pitcher_features_base.__file__)),
    }


def resolve_out(out_arg: str) -> Path:
    """Accept only a NEW directory under the system temp root."""
    out = Path(out_arg)
    if out.exists():
        raise AuditFailure("output directory already exists: %s" % out)
    resolved = out.resolve()
    tmp_root = Path(tempfile.gettempdir()).resolve()
    if resolved == tmp_root or tmp_root not in resolved.parents:
        raise AuditFailure(
            "output must be a new directory under system temp: %s" % out)
    if REPO.resolve() in (resolved, *resolved.parents):
        raise AuditFailure("output must not resolve into the repository")
    return resolved


def run_audit(pitches_2023: pl.DataFrame,
              pitches_2022: pl.DataFrame,
              population_mean_bf: float,
              out_dir: Path,
              coverage_start, coverage_end,
              reference: pl.DataFrame | None = None,
              *,
              population_mean_source: str,
              source_cutoff: dt.date) -> tuple[dict, int]:
    """Injected-frame audit orchestration. Returns (manifest, exit_code).

    Exit codes: 0 PASS, 1 FAIL (manifest written, overall FAIL), 2
    INCOMPLETE (reference comparison unavailable). Check failures are
    recorded in a FAIL manifest with diagnostics; the manifest never
    claims PASS on failure.
    """
    if ws.RULE_VERSION != REQUIRED_RULE_VERSION:
        raise AuditFailure(
            "builder rule %s != required %s"
            % (ws.RULE_VERSION, REQUIRED_RULE_VERSION))
    if not (population_mean_bf == population_mean_bf
            and population_mean_bf not in (float("inf"), float("-inf"))):
        raise AuditFailure("population_mean_bf must be finite")
    if (not isinstance(population_mean_source, str)
            or not population_mean_source.strip()):
        raise AuditFailure(
            "population-mean source must be a nonblank declared string")
    if not isinstance(source_cutoff, dt.date):
        raise AuditFailure("source cutoff must be a date")
    try:
        out_dir.mkdir(parents=True, exist_ok=False)
    except OSError:
        raise AuditFailure("cannot create output directory: %s" % out_dir)

    quarantine: list[dict] = []
    history_quarantine: list[dict] = []
    population: dict | None = None
    cutoff: dict = {"sampled": 0, "mismatches": [], "ok": True}
    n_keys = 0
    bf_comparison: dict = {"status": "NOT AVAILABLE",
                           "mismatches": None,
                           "n_actual": None,
                           "n_reference": None,
                           "n_missing_in_reference": None,
                           "n_unexpected_in_reference": None,
                           "missing_sample": [],
                           "unexpected_sample": []}
    try:
        check_period(pitches_2023, PERMITTED_FORECAST_YEARS,
                     "forecast frame")
        check_period(pitches_2022, PERMITTED_HISTORY_YEARS,
                     "history frame")

        keys, quarantine = audit_identity(pitches_2023)
        n_keys = keys.height
        if n_keys == 0:
            raise AuditFailure("no forecast keys derived")
        check_duplicate_identities(keys)
        population = reconcile_population(keys,
                                          bf_proxy_table(pitches_2023))
        if not population["match"]:
            raise AuditFailure(
                "population mismatch: %s; counts preserved, "
                "eligibility unchanged" % population["mismatch_detail"])
        earliest_forecast = min(keys["game_date"].to_list())
        if not source_cutoff < earliest_forecast:
            raise AuditFailure(
                "source cutoff %s does not precede earliest forecast "
                "date %s" % (source_cutoff, earliest_forecast))

        appearances, history_quarantine = build_history_appearances(
            pitches_2022, pitches_2023)
        forecast_rows = keys.select(
            pl.col("game_pk"),
            pl.col("forecast_pitcher").alias("pitcher"),
            pl.col("game_date"),
        )
        cutoff = sample_cutoff_check(
            forecast_rows, appearances, population_mean_bf,
            coverage_start, coverage_end)
        if not cutoff["ok"]:
            raise AuditFailure(
                "cutoff sample mismatches at rows %s"
                % cutoff["mismatches"])

        bf_comparison = {"status": "NOT AVAILABLE",
                           "mismatches": None,
                           "n_actual": None,
                           "n_reference": None,
                           "n_missing_in_reference": None,
                           "n_unexpected_in_reference": None,
                           "missing_sample": [],
                           "unexpected_sample": []}
        if reference is not None:
            missing_cols = sorted(
                {"game_pk", "pitcher", "bf"} - set(reference.columns))
            if missing_cols:
                raise AuditFailure(
                    "reference missing columns: %s" % (missing_cols,))
            actual = bf_proxy_table(pitches_2023).rename(
                {"bf_proxy": "bf"})
            ref = reference.select("game_pk", "pitcher", "bf")
            actual_ids = set(actual.select("game_pk", "pitcher").iter_rows())
            ref_ids = set(ref.select("game_pk", "pitcher").iter_rows())
            missing_ids = sorted(actual_ids - ref_ids)
            unexpected_ids = sorted(ref_ids - actual_ids)
            joined = actual.join(ref, on=["game_pk", "pitcher"],
                                 how="inner", suffix="_ref")
            bad = joined.filter(pl.col("bf") != pl.col("bf_ref")).height
            bf_comparison = {
                "status": ("MATCH" if bad == 0 and not missing_ids
                           and not unexpected_ids else "MISMATCH"),
                "mismatches": bad,
                "compared": joined.height,
                "n_actual": len(actual_ids),
                "n_reference": len(ref_ids),
                "n_missing_in_reference": len(missing_ids),
                "n_unexpected_in_reference": len(unexpected_ids),
                "missing_sample": missing_ids[:50],
                "unexpected_sample": unexpected_ids[:50],
            }
            if bf_comparison["status"] != "MATCH":
                raise AuditFailure(
                    "BF/reference identity discrepancies: "
                    "mismatches=%d missing=%d unexpected=%d"
                    % (bad, len(missing_ids), len(unexpected_ids)))

        overall = ("PASS" if bf_comparison["status"] != "NOT AVAILABLE"
                   else "INCOMPLETE")
        code = 0 if overall == "PASS" else 2
        error: str | None = None
    except AuditFailure as exc:
        overall, code, error = "FAIL", 1, str(exc)

    manifest: dict = {
        "audit_version": AUDIT_VERSION,
        "code": code_identity(),
        "permitted_periods": {
            "forecast": sorted(PERMITTED_FORECAST_YEARS),
            "history": sorted(PERMITTED_HISTORY_YEARS),
        },
        "coverage_bounds": {"start": str(coverage_start),
                            "end": str(coverage_end)},
        "identity": {
            "n_keys": n_keys,
            "n_quarantined_games": len(quarantine),
            "quarantine": quarantine,
            "n_history_quarantined_games": len(history_quarantine),
            "history_quarantine": history_quarantine,
        },
        "population": population,
        "cutoff_sample": cutoff,
        "fallback": {
            "population_mean_bf": population_mean_bf,
            "population_mean_source": population_mean_source,
            "source_cutoff": str(source_cutoff),
            "provenance": "DECLARED by caller; not independently verified",
        },
        "bf_comparison": bf_comparison,
        "overall": overall,
        "error": error,
    }
    out_payloads = {
        "reconciliation": {
            "population": population,
            "n_keys": n_keys,
            "n_quarantined_games": len(quarantine),
        },
        "quarantine": quarantine,
        "history_quarantine": history_quarantine,
        "cutoff_sample": cutoff,
        "bf_comparison": bf_comparison,
    }
    written = []
    for name, payload in out_payloads.items():
        path = out_dir / ("%s.json" % name)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True,
                                   default=str), encoding="ascii")
        written.append(str(path))
    manifest["outputs"] = written
    manifest["output_digests"] = {
        p: sha256_file(Path(p)) for p in written
    }
    manifest_path = out_dir / "reconstruction_audit_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str),
        encoding="ascii")
    return manifest, code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bounded 2023 reconstruction audit (needs execution "
                    "authorization).")
    parser.add_argument("--out", required=True)
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--population-mean-bf", required=True, type=float)
    parser.add_argument("--population-mean-source", required=True)
    parser.add_argument("--source-cutoff", required=True,
                        help="ISO date the fallback source precedes; must "
                             "precede the earliest forecast date")
    parser.add_argument("--reference", default=None)
    parser.add_argument("--reference-sha256", default=None)
    args = parser.parse_args(argv)

    try:
        if args.reference and not args.reference_sha256:
            raise AuditFailure(
                "--reference-sha256 is required with --reference")
        try:
            source_cutoff = dt.date.fromisoformat(args.source_cutoff)
        except ValueError:
            raise AuditFailure(
                "--source-cutoff must be an ISO date, got %r"
                % (args.source_cutoff,))
        root = Path(args.data_root) if args.data_root else REPO / "data"
        meta_2023 = verify_input(root / SAVANT_2023_REL.relative_to("data"),
                                 SAVANT_2023_SHA, "savant_2023")
        meta_2022 = verify_input(root / SAVANT_2022_REL.relative_to("data"),
                                 SAVANT_2022_SHA, "savant_2022")
        pitches_2023 = pl.read_parquet(meta_2023["path"])
        pitches_2022 = pl.read_parquet(meta_2022["path"])
        meta_reference = None
        reference = None
        if args.reference:
            meta_reference = verify_input(Path(args.reference),
                                          args.reference_sha256,
                                          "reference")
            reference = pl.read_parquet(meta_reference["path"])
        out_dir = resolve_out(args.out)
        years_2023 = frame_years(pitches_2023)
        years_2022 = frame_years(pitches_2022)
        manifest, code = run_audit(
            pitches_2023, pitches_2022, args.population_mean_bf, out_dir,
            coverage_start=min(years_2022), coverage_end=max(years_2023),
            reference=reference,
            population_mean_source=args.population_mean_source,
            source_cutoff=source_cutoff)
        manifest["input_identity"] = {"savant_2023": meta_2023,
                                      "savant_2022": meta_2022,
                                      "reference": meta_reference}
        (out_dir / "reconstruction_audit_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True, default=str),
            encoding="ascii")
        print(json.dumps({"overall": manifest["overall"],
                          "manifest": str(out_dir
                                          / "reconstruction_audit_manifest.json")}))
        return code
    except AuditFailure as exc:
        print("AUDIT %s" % exc, file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
