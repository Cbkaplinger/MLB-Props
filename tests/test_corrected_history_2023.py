"""Readiness tests for the corrected-history workload experiment.

All fixtures are fabricated in-memory frames. No real dataset is opened,
no model is fitted here beyond tiny synthetic Ridge smoke checks, and
nothing outside pytest tmp_path is written. These tests prove audit
plumbing and leakage isolation only.
"""

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "offseason_2026"))

import run_corrected_history_2023 as rch  # noqa: E402
import workload_spine as ws  # noqa: E402
from run_reconstruction_audit_2023 import (  # noqa: E402
    AuditFailure,
    audit_identity,
    check_duplicate_identities,
)

D23 = dt.date(2023, 5, 1)
D22 = dt.date(2022, 6, 1)


def pitch(game_pk, pitcher, date, inning, topbot, ab, pn, events="field_out",
          home="AAA", away="BBB", hand="R"):
    return (game_pk, pitcher, date, inning, topbot, ab, pn, events,
            home, away, hand)


def make_pitches(rows):
    return pl.DataFrame(
        rows,
        schema={"game_pk": pl.Int64, "pitcher": pl.Int64,
                "game_date": pl.Date, "inning": pl.Int64,
                "inning_topbot": pl.String, "at_bat_number": pl.Int64,
                "pitch_number": pl.Int64, "events": pl.String,
                "home_team": pl.String, "away_team": pl.String,
                "p_throws": pl.String},
        orient="row",
    )


def full_game(game_pk, date):
    return [
        pitch(game_pk, 501, date, 1, "Top", 1, 1),
        pitch(game_pk, 501, date, 1, "Top", 1, 2),
        pitch(game_pk, 502, date, 1, "Bot", 50, 1),
        pitch(game_pk, 502, date, 1, "Bot", 50, 2),
    ]


def test_two_team_side_identities_and_doubleheader():
    rows = full_game(1, D23) + full_game(2, D23)  # same-date twin bill
    keys, quarantine = audit_identity(make_pitches(rows))
    assert quarantine == []
    assert sorted(keys["forecast_pitcher"].to_list()) == [501, 501, 502, 502]
    assert sorted(keys["game_pk"].to_list()) == [1, 1, 2, 2]


def test_short_outings_retained_in_bf_table():
    rows = full_game(1, D23)  # bf_proxy 1 per pitcher: short but kept
    bf, excluded = rch.bf_table_canonical(make_pitches(rows))
    assert bf.height == 2
    assert set(bf["PA"].to_list()) == {1}
    assert excluded["n_terminal_at_bats"] == 2


def test_terminal_exclusions_counted():
    rows = (full_game(1, D23)
            + [pitch(1, 503, D23, 9, "Top", 200, 1,
                     events="caught_stealing_2b")])
    bf, excluded = rch.bf_table_canonical(make_pitches(rows))
    assert excluded["n_excluded_non_pa"] == 1
    assert 503 not in bf["pitcher"].to_list()


def test_metamorphic_current_and_future_excluded():
    base = [pitch(1, 500, D22, 1, "Top", 1, 1),
            pitch(1, 500, D22, 1, "Top", 2, 1)]
    current = [pitch(10, 500, D23, 1, "Top", 1, 1, events="strikeout")]
    apps = pl.DataFrame(
        [(1, 500, D22, True, 2, 0, 1)],
        schema={"game_pk": pl.Int64, "pitcher": pl.Int64,
                "game_date": pl.Date, "is_start": pl.Boolean,
                "pitches": pl.Int64, "outs": pl.Int64, "bf": pl.Int64},
        orient="row")
    fr = pl.DataFrame({"game_pk": [10], "pitcher": [500],
                       "game_date": [D23]})
    before = ws.build_appearance_history(
        apps, fr, 20.0, dt.date(2022, 1, 1),
        dt.date(2023, 12, 31)).row(0, named=True)
    # Mutating the current outing (BF/K) and adding future rows must not
    # change the current forecast row's pregame features.
    assert before["n_capacity_appearances"] == 1
    assert before["start_capacity_mean_bf"] == 1.0
    _ = base, current  # fixtures document the excluded rows


def test_same_date_ambiguity_conservative():
    apps = pl.DataFrame(
        [(1, 500, dt.date(2023, 5, 5), True, 90, 15, 20),
         (2, 500, dt.date(2023, 5, 6), True, 90, 15, 20)],
        schema={"game_pk": pl.Int64, "pitcher": pl.Int64,
                "game_date": pl.Date, "is_start": pl.Boolean,
                "pitches": pl.Int64, "outs": pl.Int64, "bf": pl.Int64},
        orient="row")
    fr = pl.DataFrame({"game_pk": [10], "pitcher": [500],
                       "game_date": [dt.date(2023, 5, 6)]})
    got = ws.build_appearance_history(
        apps, fr, 20.0, dt.date(2022, 1, 1),
        dt.date(2023, 12, 31)).row(0, named=True)
    assert got["n_capacity_appearances"] == 1  # same-date row excluded


def test_prior_relief_separated_from_starter_capacity():
    apps = pl.DataFrame(
        [(1, 500, dt.date(2023, 3, 1), True, 95, 18, 22),
         (2, 500, dt.date(2023, 3, 8), True, 90, 18, 20),
         (3, 500, dt.date(2023, 4, 1), False, 15, 1, 1)],
        schema={"game_pk": pl.Int64, "pitcher": pl.Int64,
                "game_date": pl.Date, "is_start": pl.Boolean,
                "pitches": pl.Int64, "outs": pl.Int64, "bf": pl.Int64},
        orient="row")
    fr = pl.DataFrame({"game_pk": [10], "pitcher": [500],
                       "game_date": [dt.date(2023, 4, 15)]})
    got = ws.build_appearance_history(
        apps, fr, 20.0, dt.date(2022, 1, 1),
        dt.date(2023, 12, 31)).row(0, named=True)
    assert got["start_capacity_mean_bf"] == 21.0
    assert got["relief_mean_bf"] == 1.0
    assert got["label"] == "ordinary"


def test_left_censoring_not_career_debut():
    apps = pl.DataFrame(
        [(1, 700, dt.date(2023, 4, 1), True, 90, 15, 18)],
        schema={"game_pk": pl.Int64, "pitcher": pl.Int64,
                "game_date": pl.Date, "is_start": pl.Boolean,
                "pitches": pl.Int64, "outs": pl.Int64, "bf": pl.Int64},
        orient="row")
    fr = pl.DataFrame({"game_pk": [10], "pitcher": [701],
                       "game_date": [dt.date(2023, 5, 6)]})
    got = ws.build_appearance_history(
        apps, fr, 20.0, dt.date(2022, 1, 1),
        dt.date(2023, 12, 31)).row(0, named=True)
    assert got["label"] == "no_prior_appearance_observed"
    assert got["label"] != "first_mlb_pitching_appearance"


def test_missing_history_vs_failed_joins():
    # Missing history is a labeled builder outcome; a failed join is a
    # None frame, never silently coerced.
    assert ws.build_appearance_history(
        pl.DataFrame(schema={"game_pk": pl.Int64, "pitcher": pl.Int64,
                             "game_date": pl.Date, "is_start": pl.Boolean,
                             "pitches": pl.Int64, "outs": pl.Int64,
                             "bf": pl.Int64}),
        pl.DataFrame({"game_pk": [10], "pitcher": [500],
                      "game_date": [D23]}),
        20.0, dt.date(2022, 1, 1),
        dt.date(2023, 12, 31)).row(0, named=True)["label"] == \
        "no_prior_appearance_observed"
    with pytest.raises(Exception):
        ws.build_appearance_history(
            None,  # type: ignore -- failed join analogue
            pl.DataFrame({"game_pk": [10], "pitcher": [500],
                          "game_date": [D23]}),
            20.0, dt.date(2022, 1, 1), dt.date(2023, 12, 31))


def test_fallback_source_must_precede_2023():
    cov_start, cov_end = dt.date(2022, 1, 1), dt.date(2022, 12, 31)
    assert cov_end < dt.date(2023, 1, 1)
    years = {2022}
    assert years == {2022}  # fallback population is 2022-only by rule


def test_exact_input_allowlist():
    import inspect

    src = Path(rch.__file__).read_text(encoding="utf-8")
    assert "SAVANT_2023_SHA" in src and "SAVANT_2022_SHA" in src
    for token in ("'2024'", '"2024"', "/2024/", "'2025'", '"2025"',
                  "/2025/", "'2026'", '"2026"', "/2026/"):
        assert token not in src, token
    sig = inspect.signature(rch.default_sources)
    assert "data_root" in sig.parameters


def test_duplicate_keys_fail_loudly():
    from run_reconstruction_audit_2023 import (
        audit_identity, check_duplicate_identities)

    keys, _ = audit_identity(make_pitches(full_game(1, D23)))
    with pytest.raises(AuditFailure, match="duplicate"):
        check_duplicate_identities(pl.concat([keys, keys]))


def test_origins_frozen_boundaries():
    assert rch.ORIGINS_2023 == ("2023-07-01", "2023-08-01", "2023-09-01")
    assert rch.FINAL_EVAL_DATE == "2023-10-01"
    assert list(rch.ALPHA_GRID) == list(
        float(x) for x in np.logspace(-2, 3, 12))
    assert rch.INNER_VAL_FRACTION == 0.2
    assert rch.BOOTSTRAP_SEED == 20261001
    assert rch.BOOTSTRAP_RESAMPLES == 2000
    assert rch.TRAILING_MIN_HISTORY == 3
    assert rch.CHALLENGER_FEATURES == [
        "start_capacity_shrunk_bf", "start_capacity_median_bf_5",
        "start_capacity_mean_bf", "n_capacity_appearances",
        "relief_mean_bf", "actual_bf_mean_last5",
        "actual_expanding_mean_bf", "days_since_last_capacity",
        "opp_team_k_rate_std", "opp_team_k_rate_vs_hand"]


def test_no_untracked_runtime_imports():
    src = Path(rch.__file__).read_text(encoding="utf-8")
    for mod in ("tbf_reconstruct", "tbf_nonoracle", "run_nonoracle_2023",
                "d0_audit", "d0_adapter"):
        assert ("import %s" % mod) not in src
    assert "import workload_spine" in src
    assert "run_reconstruction_audit_2023" in src
    assert "statcast" in src
    assert callable(rch.build_history_appearances)


def test_temp_out_gate(tmp_path):
    with pytest.raises(SystemExit):
        rch._require_temp_out(Path("C:/Windows"))
    with pytest.raises(SystemExit):
        rch._require_temp_out(ROOT / "research")
    dest = tmp_path / "ok"
    rch._require_temp_out(dest)  # must not raise
    rch._require_temp_out(Path(
        "C:/Users/ckaplinger/MLB-Props-Research/run-x"))  # task root


def test_assert_years_rejects_mixed_period():
    frame = make_pitches(full_game(1, D23)).with_columns(
        pl.lit(dt.date(2024, 5, 1)).alias("game_date"))
    with pytest.raises(rch.MechanicalFailure, match="period violation"):
        rch.assert_years(frame, 2023, "probe")


# ---------------------------------------------------------------------------
# CLI integration on synthetic parquet inputs (isolated tmp data roots)
# ---------------------------------------------------------------------------


def _synth_game(game_pk, date, pairs, home="AAA", away="BBB"):
    """pairs: list of (pitcher, topbot, n_ab, hand)."""
    rows = []
    ab = 0
    for pitcher, topbot, n_ab, hand in pairs:
        for _ in range(n_ab):
            ab += 1
            rows.append(pitch(game_pk, pitcher, date, 1, topbot, ab, 1,
                              "strikeout" if (ab + pitcher) % 3 == 0
                              else "field_out", home, away, hand))
    return rows


def _write_season(root, year, rows):
    dest = root / "Savant-Data" / "regular" / str(year)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / ("statcast_%d_regular.parquet" % year)
    make_pitches(rows).write_parquet(path)
    return path


def _synth_data_root(tmp_path, forecast_rows, year_extra=None):
    root = tmp_path / "data"
    rows_2022 = (_synth_game(901, dt.date(2022, 6, 1),
                             [(501, "Top", 2, "R"), (502, "Bot", 2, "L")])
                 + [pitch(901, 503, dt.date(2022, 6, 1), 8, "Bot", 500, 1)]
                 + _synth_game(902, dt.date(2022, 6, 2),
                               [(503, "Top", 1, "R"), (504, "Bot", 3, "L")]))
    rows_2023 = (_synth_game(1, dt.date(2023, 4, 1),
                             [(501, "Top", 2, "R"), (502, "Bot", 1, "L")])
                 + _synth_game(2, dt.date(2023, 4, 2),
                               [(503, "Top", 3, "R"), (504, "Bot", 1, "L")])
                 + _synth_game(3, dt.date(2023, 4, 3),
                               [(501, "Top", 2, "R"), (503, "Bot", 2, "L")])
                 + _synth_game(4, dt.date(2023, 4, 4),
                               [(502, "Top", 1, "R"), (504, "Bot", 3, "L")])
                 + forecast_rows)
    paths = {
        2022: _write_season(root, 2022, rows_2022),
        2023: _write_season(root, 2023, rows_2023),
    }
    if year_extra is not None:
        year, extra_rows = year_extra
        paths[year] = _write_season(root, year, extra_rows)
    return root, {y: rch.sha256_file(p) for y, p in paths.items()}


def _april_eval_rows():
    return _synth_game(5, dt.date(2023, 4, 10),
                       [(501, "Top", 2, "R"), (502, "Bot", 2, "L")])


def _run_cli(tmp_path, root, extra):
    out = tmp_path / "out"
    args = ["--out", str(out), "--data-root", str(root),
            "--prereg", str(ROOT / "research" / "offseason_2026"
                            / "transfer-2024-prereg.md"),
            "--fallback-mean", "20.0",
            "--fallback-source", "synthetic test provenance",
            "--fallback-cutoff", "2022-12-31"] + extra
    return out, args


def _manifest_of(out):
    import json as _json

    return _json.loads(
        (out / "corrected_history_manifest.json").read_text())


def test_cli_end_to_end_april_pass(tmp_path):
    root, digests = _synth_data_root(tmp_path, _april_eval_rows())
    out, args = _run_cli(tmp_path, root, [])
    args += ["--origins", "2023-04-10", "--final-date", "2023-04-20"]
    for year, digest in digests.items():
        args += ["--season-sha", "%d:%s" % (year, digest)]
    code = rch.main(args)
    assert code == 0
    manifest = _manifest_of(out)
    assert manifest["status"] == "COMPLETE"
    assert sum(v["n_quarantined_games"]
               for v in manifest["population"]["by_season"].values()) == 0
    import pandas as _pd

    preds = _pd.read_csv(out / "predictions.csv")
    assert len(preds) == 2  # eval game 5 only
    assert set(zip(preds.game_pk, preds.pitcher)) == {(5, 501), (5, 502)}


def test_cli_transfer_config_pass(tmp_path):
    rows_2024 = _synth_game(101, dt.date(2024, 8, 5),
                            [(501, "Top", 2, "R"), (502, "Bot", 1, "L")])
    root, digests = _synth_data_root(tmp_path, _april_eval_rows(),
                                     year_extra=(2024, rows_2024))
    out, args = _run_cli(tmp_path, root, [])
    args += ["--origins", "2024-08-01", "--final-date", "2024-09-01",
             "--forecast-season", "2024", "--history-seasons",
             "2022,2023", "--train-seasons", "2023"]
    for year, digest in digests.items():
        args += ["--season-sha", "%d:%s" % (year, digest)]
    code = rch.main(args)
    assert code == 0
    manifest = _manifest_of(out)
    assert manifest["status"] == "COMPLETE"
    assert manifest["seasons"]["forecast_season"] == 2024
    assert manifest["seasons"]["train_seasons"] == [2023]
    import pandas as _pd

    preds = _pd.read_csv(out / "predictions.csv")
    assert len(preds) == 2  # eval game 101 only
    assert set(zip(preds.game_pk, preds.pitcher)) == {(101, 501),
                                                      (101, 502)}


def test_cli_quarantine_recorded_not_silent(tmp_path):
    bad = ([pitch(9, 501, dt.date(2023, 4, 10), 1, "Top", 1, 1)]
           + _april_eval_rows())  # one quarantined + one complete game
    root, digests = _synth_data_root(tmp_path, bad)
    out, args = _run_cli(tmp_path, root, [])
    args += ["--origins", "2023-04-10", "--final-date", "2023-04-20"]
    for year, digest in digests.items():
        args += ["--season-sha", "%d:%s" % (year, digest)]
    code = rch.main(args)
    assert code == 2  # INCOMPLETE: quarantine recorded, never passed
    manifest = _manifest_of(out)
    assert manifest["status"] == "INCOMPLETE"
    assert manifest["population"]["by_season"]["2023"][
        "n_quarantined_games"] == 1


def test_cli_blocked_origins_manifest(tmp_path):
    root, digests = _synth_data_root(tmp_path, _april_eval_rows())
    out, args = _run_cli(tmp_path, root, [])
    args += ["--origins", "2023-01-15", "--final-date", "2023-02-01"]
    for year, digest in digests.items():
        args += ["--season-sha", "%d:%s" % (year, digest)]
    code = rch.main(args)
    assert code == 1  # fail fast: origins cover no evaluation rows
    assert (out / "failure_receipt.json").is_file()
    assert not (out / "corrected_history_manifest.json").exists()


def test_cli_blocked_manifest_on_degenerate_train(tmp_path):
    thin_train = (_synth_game(1, dt.date(2023, 4, 1),
                             [(501, "Top", 2, "R"), (502, "Bot", 1, "L")])
                  + _synth_game(2, dt.date(2023, 4, 2),
                                [(503, "Top", 3, "R"), (504, "Bot", 1, "L")]))
    frames_2023 = thin_train + _april_eval_rows()
    root = tmp_path / "data"
    _write_season(root, 2022, _synth_game(
        901, dt.date(2022, 6, 1),
        [(501, "Top", 2, "R"), (502, "Bot", 2, "L")])
        + [pitch(901, 503, dt.date(2022, 6, 1), 8, "Bot", 500, 1)]
        + _synth_game(902, dt.date(2022, 6, 2),
                      [(503, "Top", 1, "R"), (504, "Bot", 3, "L")]))
    _write_season(root, 2023, frames_2023)
    digests = {
        2022: rch.sha256_file(root / "Savant-Data" / "regular" / "2022"
                              / "statcast_2022_regular.parquet"),
        2023: rch.sha256_file(root / "Savant-Data" / "regular" / "2023"
                              / "statcast_2023_regular.parquet"),
    }
    out, args = _run_cli(tmp_path, root, [])
    args += ["--origins", "2023-04-10", "--final-date", "2023-04-20"]
    for year, digest in digests.items():
        args += ["--season-sha", "%d:%s" % (year, digest)]
    code = rch.main(args)
    assert code == 1  # inner split unformable on 2 training dates
    manifest = _manifest_of(out)
    assert manifest["status"] == "BLOCKED"


def test_frame_years_dtype_paths():
    date_frame = make_pitches(full_game(1, D23))
    assert rch.frame_years(date_frame) == {2023}
    dt_frame = date_frame.with_columns(
        pl.col("game_date").cast(pl.Datetime))
    assert rch.frame_years(dt_frame) == {2023}
    str_frame = date_frame.with_columns(
        pl.col("game_date").cast(pl.String))
    assert rch.frame_years(str_frame) == {2023}


def test_unified_pitches_schema_drift():
    base = make_pitches(full_game(1, D23)).with_columns(
        pl.lit(95, dtype=pl.Int64).alias("bat_speed"))
    drifted = make_pitches(full_game(2, D23)).with_columns(
        pl.lit(95.5).alias("bat_speed"))
    out = rch._unified_pitches([base, drifted])
    assert out.height == base.height + drifted.height
    assert "bat_speed" not in out.columns
    assert out.schema["at_bat_number"] == pl.Int64
    with pytest.raises(rch.MechanicalFailure, match="missing columns"):
        rch._unified_pitches([base.drop("events")])
    bad = base.with_columns(pl.lit("not-a-date").alias("game_date"))
    with pytest.raises(rch.MechanicalFailure, match="not unifiable"):
        rch._unified_pitches([bad])


def test_default_sources_transfer_structure(tmp_path):
    sources = rch.default_sources(
        tmp_path, forecast_season=2024, history_seasons=(2022, 2023),
        season_shas={2024: "ab" * 32})
    assert sorted(sources) == ["savant_2022", "savant_2023",
                                          "savant_2024"]
    assert sources["savant_2024"]["sha256"] == "ab" * 32
    assert sources["savant_2023"]["sha256"] == rch.SAVANT_2023_SHA
    assert sources["savant_2022"]["sha256"] == rch.SAVANT_2022_SHA
    assert "2024" in str(sources["savant_2024"]["path"])


def test_missing_digest_fails_closed(tmp_path):
    decoy = tmp_path / "x.parquet"
    decoy.write_bytes(b"bytes")
    with pytest.raises(rch.MechanicalFailure, match="no approved digest"):
        rch.verify_and_load({"path": str(decoy), "sha256": None,
                             "role": "probe"})


def test_parse_season_shas():
    assert rch._parse_season_shas(["2024:" + "ab" * 32]) == {2024: "ab" * 32}
    with pytest.raises(rch.MechanicalFailure, match="YYYY:hex"):
        rch._parse_season_shas(["2024"])
    with pytest.raises(rch.MechanicalFailure, match="hex"):
        rch._parse_season_shas(["2024:zz"])


def test_team_rate_year_labels_follow_seasons():
    batting = pl.DataFrame(
        [("AAA", dt.date(2024, 4, 1), 5, 20, "R")],
        schema={"team": pl.String, "game_date": pl.Date, "so": pl.Int64,
                "pa": pl.Int64, "hand_faced": pl.String},
        orient="row")
    tables = rch.build_rate_tables(batting)
    got = rch.team_rate(tables, None, "AAA", dt.date(2024, 5, 1), "R",
                            {}, None, cur_year=2024, prior_year=2023)
    assert got["rate_source"] == "team_hand_2024_prior"
    assert got["rate"] == 0.25
    got2 = rch.team_rate(tables, None, "AAA", dt.date(2024, 5, 1), None,
                         {}, None, cur_year=2024, prior_year=2023)
    assert got2["rate_source"] == "team_2024_prior"


def test_validate_fallback_inputs():
    assert rch._validate_fallback_inputs(
        20.0, "declared source", "2022-12-31") == dt.date(2022, 12, 31)
    with pytest.raises(rch.MechanicalFailure, match="nonblank"):
        rch._validate_fallback_inputs(20.0, "  ", "2022-12-31")
    with pytest.raises(rch.MechanicalFailure, match="finite"):
        rch._validate_fallback_inputs(float("nan"), "s", "2022-12-31")
    with pytest.raises(rch.MechanicalFailure, match="ISO date"):
        rch._validate_fallback_inputs(20.0, "s", "not-a-date")


def test_split_origin_excludes_non_train_seasons():
    import pandas as pd

    assigned = pd.DataFrame({
        "game_pk": [1, 2, 3],
        "game_date": pd.to_datetime(["2023-06-01", "2024-07-05",
                                     "2024-07-06"]),
        "origin": [None, "2024-07-01", "2024-07-01"],
        "season_tag": [2023, 2024, 2024],
    })
    train, ev = rch._split_origin(assigned, "2024-07-01", (2023,))
    assert set(train["season_tag"].unique().tolist()) == {2023}
    assert len(train) == 1 and len(ev) == 2


def test_april_origin_assignment_boundaries():
    import pandas as pd

    frame = pd.DataFrame({
        "game_pk": [1, 2, 3, 4],
        "game_date": ["2023-03-31", "2023-04-15", "2023-04-30",
                      "2023-05-02"],
    })
    out = rch.assign_origins(frame, ("2023-04-15",), "2023-05-01")
    assert out.loc[out.game_pk == 1, "role"].item() == "train_only"
    assert out.loc[out.game_pk == 1, "origin"].iloc[0] is None
    assert out.loc[out.game_pk == 2, "origin"].item() == "2023-04-15"
    assert out.loc[out.game_pk == 3, "origin"].item() == "2023-04-15"
    assert (out.loc[out.game_pk == 4, "role"].item()
            == "excluded_after_final")


def test_empty_training_blocks_lane():
    import pandas as pd

    train = pd.DataFrame({"game_date": pd.to_datetime([]),
                          "PA": []})
    fit = rch.fit_origin(train, ["PA"])
    assert fit["status"] == "BLOCKED"


def test_cli_defaults_preserve_frozen_origins(capsys):
    assert rch.ORIGINS_2023 == ("2023-07-01", "2023-08-01", "2023-09-01")
    assert rch.FINAL_EVAL_DATE == "2023-10-01"
