"""Synthetic integration tests for the reconstruction-audit runner.

All fixtures are fabricated in-memory frames; no real dataset is opened,
no model is fitted or scored, and nothing outside pytest tmp_path is
written. These tests exercise audit plumbing only -- they are software
tests, not baseball evidence or model results.
"""

import datetime as dt
import hashlib
import sys
from pathlib import Path

import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"))

import run_reconstruction_audit_2023 as ra  # noqa: E402
import workload_spine as ws  # noqa: E402

D2023 = dt.date(2023, 5, 1)
D2022 = dt.date(2022, 6, 1)

# Declared provenance for synthetic runs (fabricated label only).
SRC = "synthetic test provenance"
CUTOFF = dt.date(2022, 12, 31)


def pitch(game_pk, pitcher, date, inning, topbot, ab, pn):
    return (game_pk, pitcher, date, inning, topbot, ab, pn)


def make_pitches(rows):
    return pl.DataFrame(
        rows,
        schema={
            "game_pk": pl.Int64, "pitcher": pl.Int64,
            "game_date": pl.Date, "inning": pl.Int64,
            "inning_topbot": pl.String,
            "at_bat_number": pl.Int64, "pitch_number": pl.Int64,
        },
        orient="row",
    )


def full_game(game_pk, date):
    return [
        pitch(game_pk, 501, date, 1, "Top", 1, 1),
        pitch(game_pk, 501, date, 1, "Top", 1, 2),
        pitch(game_pk, 502, date, 1, "Bot", 50, 1),
        pitch(game_pk, 502, date, 1, "Bot", 50, 2),
    ]


def two_games_2023():
    return make_pitches(full_game(1, D2023) + full_game(2, D2023))


def one_game_2022():
    return make_pitches(full_game(9, D2022))


def match_counts(monkeypatch, pitches_2023):
    """Pin expected counts to the synthetic frame (testing only)."""
    bf = ra.bf_proxy_table(pitches_2023)
    n_expanded = pitches_2023["game_pk"].n_unique() * 2
    n_pa9 = bf.filter(pl.col("bf_proxy") >= 9).height
    monkeypatch.setattr(ra, "EXPECTED_N_EXPANDED", n_expanded)
    monkeypatch.setattr(ra, "EXPECTED_N_PA9", n_pa9)
    monkeypatch.setattr(ra, "EXPECTED_N_OUTSIDE", n_expanded - n_pa9)
    return n_expanded, n_pa9


def run_ok(monkeypatch, tmp_path, name, reference="match"):
    p23 = two_games_2023()
    n_expanded, _ = match_counts(monkeypatch, p23)
    ref = None
    if reference == "match":
        ref = ra.bf_proxy_table(p23).rename({"bf_proxy": "bf"})
    out = tmp_path / name
    manifest, code = ra.run_audit(
        p23, one_game_2022(), 20.0, out,
        dt.date(2022, 1, 1), dt.date(2023, 12, 31), reference=ref,
        population_mean_source=SRC, source_cutoff=CUTOFF)
    assert n_expanded == 4
    return manifest, code, out


# ---------------------------------------------------------------------------
# Identity contract
# ---------------------------------------------------------------------------


def test_valid_canonical_identities():
    keys, quarantine = ra.audit_identity(two_games_2023())
    assert quarantine == []
    assert keys.height == 4


def test_team_side_distinction():
    keys, _ = ra.audit_identity(make_pitches(full_game(1, D2023)))
    by_pitcher = {r["forecast_pitcher"]: r
                  for r in keys.iter_rows(named=True)}
    assert by_pitcher[501]["inning_topbot"] == "Top"
    assert by_pitcher[501]["is_home"] is True
    assert by_pitcher[502]["inning_topbot"] == "Bot"
    assert by_pitcher[502]["is_home"] is False


def test_first_pitcher_membership_is_start():
    keys, _ = ra.audit_identity(make_pitches(full_game(1, D2023)))
    key_set = set(keys.select("game_pk", "forecast_pitcher").iter_rows())
    assert ra.is_start(1, 501, key_set) is True
    assert ra.is_start(1, 999, key_set) is False  # never BF-based


def test_role_agnostic_identity():
    # Position-player status lives outside the pitch frame; the schema
    # cannot carry it, so membership cannot depend on it.
    frame = make_pitches(full_game(1, D2023))
    assert "role" not in frame.columns
    position_player_ids = {501}
    keys, _ = ra.audit_identity(frame)
    assert 501 in keys["forecast_pitcher"].to_list()
    assert position_player_ids == {501}  # recorded separately, unused


def test_outcome_invariance_identity_and_membership():
    thin = make_pitches(full_game(1, D2023))
    fat = make_pitches(full_game(1, D2023) + [
        pitch(1, 503, D2023, 7, "Top", 900, 1),  # later relief outings
        pitch(1, 504, D2023, 8, "Bot", 950, 1),
    ])
    a, _ = ra.audit_identity(thin)
    b, _ = ra.audit_identity(fat)
    assert a.sort("forecast_pitcher").equals(b.sort("forecast_pitcher"))


def test_multiple_pitch_rows_one_identity():
    rows = ([pitch(1, 501, D2023, 1, "Top", 1 + i, j)
             for i in range(30) for j in (1, 2)]
            + [pitch(1, 502, D2023, 1, "Bot", 500, 1)])
    keys, quarantine = ra.audit_identity(make_pitches(rows))
    assert quarantine == []
    assert sorted(keys["forecast_pitcher"].to_list()) == [501, 502]


def test_duplicate_canonical_identities_fail():
    keys, _ = ra.audit_identity(make_pitches(full_game(1, D2023)))
    with pytest.raises(ra.AuditFailure, match="duplicate"):
        ra.check_duplicate_identities(pl.concat([keys, keys]))


def test_quarantine_missing_half():
    rows = [pitch(1, 501, D2023, 1, "Top", 1, 1)]
    keys, quarantine = ra.audit_identity(make_pitches(rows))
    assert keys.height == 0
    assert len(quarantine) == 1
    assert quarantine[0]["game_pk"] == 1
    assert "reason" in quarantine[0]


# ---------------------------------------------------------------------------
# Population / history / periods
# ---------------------------------------------------------------------------


def test_population_mismatch_fail_manifest(tmp_path):
    # Real counts (4 keys) never equal the registered 4860-class
    # expectations: FAIL manifest, counts preserved, never PASS.
    out = tmp_path / "mismatch"
    manifest, code = ra.run_audit(
        two_games_2023(), one_game_2022(), 20.0, out,
        dt.date(2022, 1, 1), dt.date(2023, 12, 31),
        population_mean_source=SRC, source_cutoff=CUTOFF)
    assert code == 1
    assert manifest["overall"] == "FAIL"
    assert manifest["population"]["n_expanded"] == 4
    assert "mismatch" in manifest["error"]
    assert (out / "reconstruction_audit_manifest.json").is_file()


def test_run_level_quarantine_recorded(tmp_path):
    bad = make_pitches([pitch(1, 501, D2023, 1, "Top", 1, 1)])
    out = tmp_path / "quar"
    manifest, code = ra.run_audit(
        bad, one_game_2022(), 20.0, out,
        dt.date(2022, 1, 1), dt.date(2023, 12, 31),
        population_mean_source=SRC, source_cutoff=CUTOFF)
    assert code == 1
    assert manifest["identity"]["n_quarantined_games"] == 1
    assert manifest["identity"]["quarantine"][0]["game_pk"] == 1


def test_same_date_and_same_game_excluded():
    apps = pl.DataFrame(
        [(1, 500, dt.date(2023, 5, 5), True, 90, 15, 20),
         (2, 500, dt.date(2023, 5, 6), True, 90, 15, 20),  # same date
         (10, 500, dt.date(2023, 5, 6), True, 5, 1, 2)],  # same game
        schema={"game_pk": pl.Int64, "pitcher": pl.Int64,
                "game_date": pl.Date, "is_start": pl.Boolean,
                "pitches": pl.Int64, "outs": pl.Int64, "bf": pl.Int64},
        orient="row",
    )
    fr = pl.DataFrame({"game_pk": [10], "pitcher": [500],
                       "game_date": [dt.date(2023, 5, 6)]})
    got = ws.build_appearance_history(
        apps, fr, 20.0, dt.date(2022, 1, 1),
        dt.date(2023, 12, 31)).row(0, named=True)
    assert got["n_capacity_appearances"] == 1  # only the 05-05 start


def test_prohibited_periods_fail(tmp_path):
    bad = make_pitches(full_game(1, dt.date(2024, 5, 1)))
    out = tmp_path / "o"
    manifest, code = ra.run_audit(
        bad, one_game_2022(), 20.0, out,
        dt.date(2022, 1, 1), dt.date(2024, 12, 31),
        population_mean_source=SRC, source_cutoff=CUTOFF)
    assert code == 1
    assert manifest["overall"] == "FAIL"
    assert "period violation" in manifest["error"]


def test_digest_mismatch_before_parsing(tmp_path):
    decoy = tmp_path / "decoy.parquet"
    decoy.write_bytes(b"not parquet at all")
    with pytest.raises(ra.AuditFailure, match="hash mismatch"):
        ra.verify_input(decoy, "0" * 64, "decoy")
    with pytest.raises(ra.AuditFailure, match="missing input"):
        ra.verify_input(tmp_path / "absent.parquet", "0" * 64, "absent")


# ---------------------------------------------------------------------------
# Reference comparison
# ---------------------------------------------------------------------------


def test_bf_match_and_missing_unexpected(monkeypatch, tmp_path):
    p23 = two_games_2023()
    match_counts(monkeypatch, p23)
    actual = ra.bf_proxy_table(p23).rename({"bf_proxy": "bf"})
    ref = actual.slice(0, 3).vstack(
        pl.DataFrame({"game_pk": [999], "pitcher": [999],
                       "bf": pl.Series([5], dtype=pl.UInt32)}))
    out = tmp_path / "refcheck"
    manifest, code = ra.run_audit(
        p23, one_game_2022(), 20.0, out,
        dt.date(2022, 1, 1), dt.date(2023, 12, 31), reference=ref,
        population_mean_source=SRC, source_cutoff=CUTOFF)
    assert code == 1  # MISMATCH via missing + unexpected
    assert manifest["overall"] == "FAIL"
    assert manifest["bf_comparison"]["n_missing_in_reference"] == 1
    assert manifest["bf_comparison"]["n_unexpected_in_reference"] == 1


def test_bf_value_mismatch_fails(monkeypatch, tmp_path):
    p23 = two_games_2023()
    match_counts(monkeypatch, p23)
    ref = ra.bf_proxy_table(p23).rename({"bf_proxy": "bf"}).with_columns(
        pl.when(pl.col("game_pk") == 1).then(999).otherwise(pl.col("bf"))
        .alias("bf"))
    out = tmp_path / "bfbad"
    manifest, code = ra.run_audit(
        p23, one_game_2022(), 20.0, out,
        dt.date(2022, 1, 1), dt.date(2023, 12, 31), reference=ref,
        population_mean_source=SRC, source_cutoff=CUTOFF)
    assert code == 1
    assert manifest["bf_comparison"]["status"] == "MISMATCH"


def test_reference_missing_columns_fail(monkeypatch, tmp_path):
    p23 = two_games_2023()
    match_counts(monkeypatch, p23)
    ref = pl.DataFrame({"game_pk": [1], "pitcher": [501]})
    out = tmp_path / "refcols"
    manifest, code = ra.run_audit(
        p23, one_game_2022(), 20.0, out,
        dt.date(2022, 1, 1), dt.date(2023, 12, 31), reference=ref,
        population_mean_source=SRC, source_cutoff=CUTOFF)
    assert code == 1
    assert "reference missing columns" in manifest["error"]


def test_missing_reference_incomplete(monkeypatch, tmp_path):
    manifest, code, _ = run_ok(monkeypatch, tmp_path, "noref",
                               reference=None)
    assert code == 2
    assert manifest["overall"] == "INCOMPLETE"
    assert manifest["bf_comparison"]["status"] == "NOT AVAILABLE"


# ---------------------------------------------------------------------------
# Outputs, paths, manifest integrity
# ---------------------------------------------------------------------------


def test_output_path_rejection(tmp_path):
    with pytest.raises(ra.AuditFailure, match="already exists"):
        ra.resolve_out(str(ROOT))  # repository path exists: refused first
    with pytest.raises(ra.AuditFailure, match="system temp"):
        ra.resolve_out(str(Path(ra.REPO) / "missing_dir_xyz"))
    with pytest.raises(ra.AuditFailure, match="already exists"):
        ra.resolve_out(str(tmp_path))  # existing directory refused
    fresh = tmp_path / "fresh"
    assert ra.resolve_out(str(fresh)) == fresh.resolve()


def test_successful_synthetic_manifest(monkeypatch, tmp_path):
    manifest, code, out = run_ok(monkeypatch, tmp_path, "good")
    assert code == 0
    assert manifest["overall"] == "PASS"
    assert manifest["audit_version"] == "reconstruction_audit_v1"
    assert manifest["population"]["match"] is True
    assert manifest["cutoff_sample"]["ok"] is True
    assert manifest["bf_comparison"]["status"] == "MATCH"
    manifest_path = out / "reconstruction_audit_manifest.json"
    assert manifest_path.is_file()
    for path_str, digest in manifest["output_digests"].items():
        raw = Path(path_str).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest


def test_no_canonical_modification(monkeypatch, tmp_path):
    spine = Path(ws.__file__)
    before = hashlib.sha256(spine.read_bytes()).hexdigest()
    manifest, code, out = run_ok(monkeypatch, tmp_path, "clean")
    assert code == 0
    assert hashlib.sha256(spine.read_bytes()).hexdigest() == before
    leftovers = [p for p in out.rglob("*") if p.is_file()]
    assert leftovers, "expected audit outputs under the temp dir"
    assert all(Path(ra.tempfile.gettempdir()).resolve() in
               (p.resolve(), *p.resolve().parents) for p in leftovers)


def test_no_cli_bypass_flags():
    src = Path(ra.__file__).read_text(encoding="utf-8")
    for flag in ("--skip", "--no-verify", "--inject", "--frames",
                 "--no-hash", "--skip-verify"):
        assert flag not in src
    assert "--reference-sha256" in src  # reference pin is mandatory


def test_main_missing_inputs_fails_fast(tmp_path):
    code = ra.main(["--out", str(tmp_path / "o"),
                    "--data-root", str(tmp_path / "empty"),
                    "--population-mean-bf", "20.0",
                    "--population-mean-source", "synthetic",
                    "--source-cutoff", "2022-01-01"])
    assert code != 0
    assert not (tmp_path / "o").exists()


def test_code_identity_records_versions():
    identity = ra.code_identity()
    assert identity["audit_version"] == "reconstruction_audit_v1"
    assert identity["workload_spine_rule"] == "workload_spine_v2.2"
    assert len(identity["workload_spine_file"]) == 64
    assert len(identity["starter_keys_file"]) == 64


# ---------------------------------------------------------------------------
# Fallback provenance (R2) and reference pinning (R1)
# ---------------------------------------------------------------------------


def test_blank_source_rejected(tmp_path):
    with pytest.raises(ra.AuditFailure, match="nonblank"):
        ra.run_audit(two_games_2023(), one_game_2022(), 20.0,
                     tmp_path / "o", dt.date(2022, 1, 1),
                     dt.date(2023, 12, 31),
                     population_mean_source="   ", source_cutoff=CUTOFF)


def test_nonfinite_fallback_rejected(tmp_path):
    with pytest.raises(ra.AuditFailure, match="finite"):
        ra.run_audit(two_games_2023(), one_game_2022(), float("nan"),
                     tmp_path / "o", dt.date(2022, 1, 1),
                     dt.date(2023, 12, 31),
                     population_mean_source=SRC, source_cutoff=CUTOFF)


def test_cutoff_must_precede_forecasts(monkeypatch, tmp_path):
    p23 = two_games_2023()
    match_counts(monkeypatch, p23)  # pass the population gate first
    out = tmp_path / "latecut"
    manifest, code = ra.run_audit(
        p23, one_game_2022(), 20.0, out,
        dt.date(2022, 1, 1), dt.date(2023, 12, 31),
        population_mean_source=SRC, source_cutoff=D2023)
    assert code == 1
    assert manifest["overall"] == "FAIL"
    assert "does not precede" in manifest["error"]


def test_fallback_provenance_declared(monkeypatch, tmp_path):
    manifest, code, _ = run_ok(monkeypatch, tmp_path, "prov")
    assert code == 0
    fallback = manifest["fallback"]
    assert fallback["population_mean_bf"] == 20.0
    assert fallback["population_mean_source"] == SRC
    assert fallback["source_cutoff"] == str(CUTOFF)
    assert "not independently verified" in fallback["provenance"]


def test_reference_without_sha_rejected(tmp_path, capsys):
    ref = tmp_path / "ref.parquet"
    pl.DataFrame({"game_pk": [1], "pitcher": [501],
                  "bf": [1]}).write_parquet(ref)
    code = ra.main(["--out", str(tmp_path / "o"),
                    "--data-root", str(tmp_path / "empty"),
                    "--population-mean-bf", "20.0",
                    "--population-mean-source", "synthetic",
                    "--source-cutoff", "2022-01-01",
                    "--reference", str(ref)])
    assert code != 0
    assert "reference-sha256" in capsys.readouterr().err
    assert not (tmp_path / "o").exists()


def test_reference_checked_after_savants(tmp_path, capsys):
    # Savant inputs are verified before the reference is even parsed:
    # with valid reference bytes+digest but missing Savants, the
    # failure names the Savant input, and nothing is created.
    ref = tmp_path / "ref.parquet"
    pl.DataFrame({"game_pk": [1], "pitcher": [501],
                  "bf": [1]}).write_parquet(ref)
    digest = hashlib.sha256(ref.read_bytes()).hexdigest()
    code = ra.main(["--out", str(tmp_path / "o"),
                    "--data-root", str(tmp_path / "empty"),
                    "--population-mean-bf", "20.0",
                    "--population-mean-source", "synthetic",
                    "--source-cutoff", "2022-01-01",
                    "--reference", str(ref),
                    "--reference-sha256", digest])
    assert code != 0
    assert "savant_2023" in capsys.readouterr().err
    assert not (tmp_path / "o").exists()
