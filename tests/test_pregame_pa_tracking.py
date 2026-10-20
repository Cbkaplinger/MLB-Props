"""Synthetic tracking tests for the pregame-pa-ext-v2 adapter's D-1
tracking connection.

Wires a fully synthetic private-lake stand-in (same pattern as
test_bf37_wiring.py) and drives the ACTUAL execution entry point
``run_real(tracking_uri=...)`` against a temp sqlite MLflow store: no
hand-replicated logging calls -- the run must appear in the store through
the SHARED count-eval-v1 wrapper (``track_and_verify.log_run`` +
``verify_run``), with exact metric round-trip and output artifact
byte-hash verification. The canonical mlflow.db is never touched.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))
sys.path.insert(0,
                str(HERE / "research" / "offseason_2026" / "pregame_pa_ext"))

import pregame_pa_ext.adapter as ad  # noqa: E402
import build_checkpoint as bc  # noqa: E402

mlflow = pytest.importorskip("mlflow")

PMF37_COLS = [f"pmf37_{j}" for j in range(37)]
CUTOFF = date(2025, 3, 15)


# --------------------------------------------------------------- fixtures
def synth_pa_table(n_days: int = 40, seed: int = 7,
                   start: date = date(2025, 1, 1)) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    pitchers = [870001, 870002, 870003]
    batters = [660001, 660002, 660003, 660004, 660005, 660006,
               660007, 660008, 660009]
    p_k = {870001: 0.25, 870002: 0.20, 870003: 0.30}
    b_k = {b: 0.20 + 0.01 * i for i, b in enumerate(batters)}
    rows = []
    for d in range(n_days):
        gd = start + timedelta(days=d)
        pk = pitchers[d % 3]
        game_pk = 900000 + d
        for slot in range(9):
            bt = batters[slot % len(batters)]
            for _ in range(2):
                p = 0.5 * p_k[pk] + 0.5 * b_k[bt]
                rows.append({
                    "game_pk": game_pk, "at_bat_number": len(rows) + 1,
                    "batter": bt, "pitcher": pk, "game_date": gd,
                    "y": int(rng.random() < p),
                })
    return pl.DataFrame(rows)


def synth_projected(pa: pl.DataFrame, game_date, game_pk: int = 999001,
                    pitcher: int = 870001) -> pl.DataFrame:
    batters = sorted(pa["batter"].unique().to_list())
    slots = {f"u_slot_{i + 1}": batters[i % len(batters)] for i in range(9)}
    return pl.DataFrame([{
        "game_pk": game_pk, "side": "Bot", "pitcher": pitcher,
        "game_date": game_date, "opp_team": "OPP",
        "n_prior_team_games": 10, "n_pool_distinct": 9,
        "nine_distinct": len(set(slots.values())),
        **slots,
        **{f"sup_slot_{i + 1}": 9 - (i % 3) for i in range(9)},
        **{f"how_slot_{i + 1}": "greedy" for i in range(9)},
        "n_fallback_slots": 0, "n_distinct_ids": len(set(slots.values())),
    }])


def synth_models(pa: pl.DataFrame) -> dict:
    p_daily = ad.entity_daily_state(pa, "pitcher")
    b_daily = ad.entity_daily_state(pa, "batter")
    lg = ad.league_daily_state(pa)
    rows = pa.select(
        "game_pk", "at_bat_number", "batter", "pitcher", "game_date",
    ).sort("game_date")
    feat = ad.attach_prior_features(rows, p_daily, b_daily, lg)
    feat = feat.join(pa.select("game_pk", "at_bat_number", "batter", "y"),
                     on=["game_pk", "at_bat_number", "batter"], how="inner")
    feat = feat.filter(pl.col("lg_rate").is_finite())
    model = ad.fit_models_from_frames(feat, feat)
    return {"block_2024H2": model, "block_2025H1": model,
            "confirm_2025H2": model}


def synth_bf37(h: float = 0.06) -> np.ndarray:
    pmf37 = np.empty(37)
    surv = 1.0
    for n in range(36):
        pmf37[n] = surv * h
        surv *= 1 - h
    pmf37[36] = surv
    return pmf37


def bf_row(game_pk: int, side: str, pitcher: int, pmf37: np.ndarray,
           game_date=CUTOFF) -> dict:
    return {
        "game_pk": game_pk, "side": side, "pitcher": pitcher,
        "game_date": game_date,
        **{f"pmf37_{j}": float(v) for j, v in enumerate(pmf37)},
    }


def synth_lake(tmp_path: Path, pa: pl.DataFrame, proj: pl.DataFrame,
               bf: pl.DataFrame) -> dict:
    ps = tmp_path / "pregame-state-v1"
    op2 = tmp_path / "overnight-p2"
    bfw = tmp_path / "bf-workload-v1"
    out = tmp_path / "pregame-pa-ext-v2"
    for d in (ps / "data", op2 / "data", bfw / "data", out / "checkpoints"):
        d.mkdir(parents=True, exist_ok=True)
    proj.write_parquet(ps / "data" / "projected_lineups_variant_v2.parquet")
    pa.write_parquet(op2 / "data" / "pa_table.parquet")
    bf_path = bfw / "data" / "bf_forecasts.parquet"
    bf.write_parquet(bf_path)
    ck = out / "checkpoints" / "h3_raw_checkpoint.json"
    return {
        "pregame_state_dir": ps,
        "overnight_p2_dir": op2,
        "bf_path": bf_path,
        "checkpoint_path": ck,
        "out_dir": out,
    }


def register_test_pin(dirs: dict, monkeypatch, sha: str) -> None:
    """Synthetic tests supply an explicit TEST registration: the pin is
    the serialized SYNTHETIC checkpoint artifact's own sha256 (no real
    hash is invented). run_real refuses a null registered pin
    (CHECKPOINT_PIN_NOT_REGISTERED), so every scoring-path test must
    register a pin."""
    p = dirs["out_dir"] / "freeze_pregame_pa_ext_v2_synth.json"
    p.write_text(json.dumps({
        "freeze_id": "pregame-pa-ext-v2-synth",
        "checkpoint_sha256_expected": sha,
    }, indent=2), encoding="utf-8")
    monkeypatch.setattr(ad, "FREEZE_CONFIG_RELPATH", str(p))


def wire_lake(monkeypatch, dirs: dict, models: dict,
              registered_sha: str) -> None:
    verification = {"block_2025H1": {"n_rows": 10, "max_abs_diff": 0.0}}
    ad.serialize_checkpoint(models, verification, dirs["checkpoint_path"])
    monkeypatch.setattr(ad, "PREGAME_STATE_DIR", dirs["pregame_state_dir"])
    monkeypatch.setattr(ad, "OVERNIGHT_P2_DIR", dirs["overnight_p2_dir"])
    monkeypatch.setattr(ad, "PAEXT_OUT_DIR", dirs["out_dir"])
    monkeypatch.setattr(ad, "CHECKPOINT_PATH", dirs["checkpoint_path"])
    monkeypatch.setattr(ad, "BF_WORKLOAD_DIR",
                        dirs["bf_path"].parent.parent)
    monkeypatch.setattr(ad, "REGISTERED_BF_FORECASTS_SHA256",
                        registered_sha)
    ck_sha = json.loads(
        dirs["checkpoint_path"].read_text(encoding="utf-8"))["sha256"]
    register_test_pin(dirs, monkeypatch, ck_sha)


def sha_of(path: Path) -> str:
    return ad.sha256_file(path)


@pytest.fixture(scope="module")
def pa_mod() -> pl.DataFrame:
    return synth_pa_table()


@pytest.fixture(scope="module")
def models_mod(pa_mod) -> dict:
    return synth_models(pa_mod)


@pytest.fixture(scope="module")
def wrapper_mod():
    tv = ad.load_track_wrapper()
    assert Path(tv.__file__).name == "track_and_verify.py"
    return tv


def test_wrapper_is_the_shared_count_eval_module(wrapper_mod):
    """The adapter loads the SAME shared D-1 wrapper module used by the
    count-eval-v1/bf-lane harness (the frozen LightGBM runner's owner of
    compare -> save -> log -> verify)."""
    harness = HERE / "research" / "offseason_2026" / "specs" / \
        "count-eval-v2-spec" / "harness" / "track_and_verify.py"
    assert Path(wrapper_mod.__file__).resolve() == harness.resolve()
    assert hasattr(wrapper_mod, "log_run")
    assert hasattr(wrapper_mod, "verify_run")
    assert hasattr(wrapper_mod, "TrackingFailure")


def test_run_real_tracks_through_shared_wrapper(
        tmp_path, monkeypatch, pa_mod, models_mod, wrapper_mod):
    """Through the ACTUAL adapter path: run_real(tracking_uri=...) on the
    synthetic lake logs one run to a temp sqlite store via the shared
    wrapper, VERIFIES it (exact metrics + output artifact byte hash), and
    the run is independently retrievable from the store."""
    proj = pl.concat([
        synth_projected(pa_mod, CUTOFF, game_pk=999001, pitcher=870001),
        synth_projected(pa_mod, CUTOFF, game_pk=999002, pitcher=870002),
    ])
    bf = pl.DataFrame([
        bf_row(999001, "Bot", 870001, synth_bf37(0.06)),
        bf_row(999002, "Bot", 870002, synth_bf37(0.08)),
    ])
    dirs = synth_lake(tmp_path, pa_mod, proj, bf)
    wire_lake(monkeypatch, dirs, models_mod, sha_of(dirs["bf_path"]))
    db = tmp_path / "mlflow.db"
    tracking_uri = "sqlite:///" + db.as_posix()
    artifact_location = (tmp_path / "mlartifacts").as_posix()

    summary = ad.run_real(tracking_uri=tracking_uri,
                          experiment="pregame-pa-ext-v2-synth",
                          run_name="synthetic-tracking-test",
                          artifact_location=artifact_location)

    tracked = summary["tracking"]
    assert tracked["status"] == "VERIFIED"
    run_id = tracked["run_id"]
    assert run_id

    # fresh-client independent retrieval from the temp store
    from mlflow.tracking import MlflowClient
    client = MlflowClient(tracking_uri=tracking_uri)
    run = client.get_run(run_id)
    assert run.info.run_name == "synthetic-tracking-test"
    assert run.data.params["adapter"] == "pregame-pa-ext-v2"
    assert run.data.params["checkpoint_sha256"] == \
        summary["checkpoint"]["sha256"]
    assert run.data.params["bf_pmf_sha256"] == \
        summary["bf37_artifact"]["sha256"]
    assert run.data.metrics["n_projected_starts"] == 2.0
    assert run.data.metrics["n_pa_rows_scored"] == 18.0
    assert run.data.metrics["n_starts_pmf_computed"] == 2.0
    # the logged output artifact is the actual write-once parquet
    got = client.download_artifacts(run_id, "outputs/projected_pa_probs_v1.parquet")
    assert sha_of(Path(got)) == sha_of(Path(summary["output"]))
    out = pl.read_parquet(Path(summary["output"]))
    assert out.height == 18

    # exactly one run in the experiment
    exp = client.get_experiment_by_name("pregame-pa-ext-v2-synth")
    assert exp is not None
    runs = client.search_runs([exp.experiment_id])
    assert [r.info.run_id for r in runs] == [run_id]


def test_run_real_without_tracking_uri_is_unchanged(
        tmp_path, monkeypatch, pa_mod, models_mod):
    """Default (no tracking_uri) behavior is unchanged: no tracking key in
    the summary, no run created anywhere."""
    proj = synth_projected(pa_mod, CUTOFF)
    bf = pl.DataFrame([bf_row(999001, "Bot", 870001, synth_bf37())])
    dirs = synth_lake(tmp_path, pa_mod, proj, bf)
    wire_lake(monkeypatch, dirs, models_mod, sha_of(dirs["bf_path"]))
    summary = ad.run_real()
    assert "tracking" not in summary
    assert Path(summary["output"]).exists()


def test_run_real_surfaces_tracking_failure(
        tmp_path, monkeypatch, pa_mod, models_mod, wrapper_mod):
    """An unreachable tracking store surfaces the shared wrapper's
    TrackingFailure AFTER the canonical output is finalized untouched
    (logging failure never triggers a refit or loses the output)."""
    proj = synth_projected(pa_mod, CUTOFF)
    bf = pl.DataFrame([bf_row(999001, "Bot", 870001, synth_bf37())])
    dirs = synth_lake(tmp_path, pa_mod, proj, bf)
    wire_lake(monkeypatch, dirs, models_mod, sha_of(dirs["bf_path"]))
    # nothing listens on port 1: connection refused, fast and definitive
    bad_uri = "http://127.0.0.1:1/api"
    with pytest.raises(wrapper_mod.TrackingFailure):
        ad.run_real(tracking_uri=bad_uri)
    out = dirs["out_dir"] / "outputs" / "projected_pa_probs_v1.parquet"
    assert out.exists()
    assert pl.read_parquet(out).height == 9


# ------------------------------------------- dual-phase pipeline linkage
def wire_lake_existing_checkpoint(monkeypatch, dirs: dict,
                                  registered_sha: str) -> None:
    """Wire the synthetic lake WITHOUT serializing a checkpoint: the
    caller places the reconstructed artifact at dirs['checkpoint_path']
    itself (the scoring phase must consume the reconstruction's
    serialized artifact, not build a new one). Registers the reconstructed
    artifact's own sha256 as the TEST pin (run_real refuses a null pin)."""
    monkeypatch.setattr(ad, "PREGAME_STATE_DIR", dirs["pregame_state_dir"])
    monkeypatch.setattr(ad, "OVERNIGHT_P2_DIR", dirs["overnight_p2_dir"])
    monkeypatch.setattr(ad, "PAEXT_OUT_DIR", dirs["out_dir"])
    monkeypatch.setattr(ad, "CHECKPOINT_PATH", dirs["checkpoint_path"])
    monkeypatch.setattr(ad, "BF_WORKLOAD_DIR",
                        dirs["bf_path"].parent.parent)
    monkeypatch.setattr(ad, "REGISTERED_BF_FORECASTS_SHA256",
                        registered_sha)
    ck_sha = json.loads(
        dirs["checkpoint_path"].read_text(encoding="utf-8"))["sha256"]
    register_test_pin(dirs, monkeypatch, ck_sha)


@pytest.fixture(scope="module")
def recon_mod(tmp_path_factory):
    """ONE synthetic reconstruction over a PA table spanning the three
    registered blocks (2023-01-01..2025-06-30): builds the verification
    preds from a deterministic refit of the same frozen recipe, then runs
    the REAL ``bc.reconstruct`` (refit + <=1e-8 gate + sha256-pinned
    write-once serialization). Shared by the dual-phase tests.

    EXPLICIT SYNTHETIC REGISTRATION inside the fixture: bc.reconstruct
    verifies its own serialize->reload round-trip via
    ``ad.load_serialized_checkpoint``, which consults the COMMITTED
    registration -- now pinned to the REAL reconstructed checkpoint's
    canonical payload hash. A synthetic reconstruction must never be
    verified against the real pin, so the fixture points
    ``ad.FREEZE_CONFIG_RELPATH`` at an explicit synthetic gate-disabled
    registration (null pin: RECONSTRUCTION does not require the pin) while
    it runs, then restores the committed binding. The real committed pin,
    the dual-phase pipeline retrieval, and the failure/no-refit guarantees
    are unchanged; the reconstructed REAL artifact is untouched."""
    pa = synth_pa_table(n_days=912, seed=11,
                        start=date(2023, 1, 1))
    feat = bc.build_feature_frame(pa)
    preds_dir = tmp_path_factory.mktemp("preds")
    fnames = {"block_2024H2": "preds_block_2024H2.parquet",
              "block_2025H1": "preds_block_2025H1.parquet",
              "confirm_2025H2": "preds_confirm_2025H2.parquet"}
    for block, (te_y, te_m, te_d) in bc.BLOCK_TRAIN_END.items():
        cal_last = feat.filter(
            (pl.col("game_date") >= pl.date(2023, 1, 1))
            & (pl.col("game_date") <= pl.date(te_y, te_m, te_d))
        )["game_date"].max()
        cal_first = cal_last - timedelta(days=59)
        train = feat.filter(
            (pl.col("game_date") >= pl.date(2023, 1, 1))
            & (pl.col("game_date") < cal_first))
        cal = feat.filter(
            (pl.col("game_date") >= cal_first)
            & (pl.col("game_date") <= pl.date(te_y, te_m, te_d)))
        model = ad.fit_models_from_frames(train, cal)
        sub = feat.filter(pl.col("game_date") <= pl.date(te_y, te_m, te_d))
        preds = sub.select("game_pk", "at_bat_number", "batter").with_columns(
            pl.Series("pred_H3_raw", ad.apply_h3_raw(sub, model)))
        preds.write_parquet(preds_dir / fnames[block])
    out_root = tmp_path_factory.mktemp("recon")
    ck = out_root / "checkpoints" / "h3_raw_checkpoint.json"
    synth_reg = out_root / "freeze_pregame_pa_ext_v2_synth.json"
    synth_reg.write_text(json.dumps({
        "freeze_id": "pregame-pa-ext-v2-synth",
        "checkpoint_artifact": "checkpoints/h3_raw_checkpoint.json",
        "checkpoint_sha256_expected": None,
    }, indent=2), encoding="utf-8")
    _orig = ad.FREEZE_CONFIG_RELPATH
    ad.FREEZE_CONFIG_RELPATH = str(synth_reg)
    try:
        report = bc.reconstruct(pa, ck, preds_dir=preds_dir)
    finally:
        ad.FREEZE_CONFIG_RELPATH = _orig
    return {"pa": pa, "report": report, "ck": ck}


def test_dual_phase_reconstruction_then_scoring_retrievable_by_pipeline_id(
        tmp_path, monkeypatch, recon_mod, wrapper_mod):
    """DUAL-PHASE DEMONSTRATION: the reconstruction phase
    (``bc.track_reconstruction`` through the SHARED D-1 wrapper) and the
    scoring phase (``ad.run_real`` consuming the SAME serialized artifact)
    both log through one pipeline_id tag, and both runs are retrievable
    from the store by that tag as ONE pipeline."""
    report, ck = recon_mod["report"], recon_mod["ck"]
    pid = "paext-v2-synth-20261019T000000Z"
    db = tmp_path / "mlflow.db"
    tracking_uri = "sqlite:///" + db.as_posix()
    art_loc = (tmp_path / "mlartifacts").as_posix()
    exp = "paext-dual-phase-synth"

    # phase 1: reconstruction (verification gate result + artifact hash)
    r_verdict = bc.track_reconstruction(
        report, tracking_uri=tracking_uri, experiment=exp,
        pipeline_id=pid, artifact_location=art_loc)
    assert r_verdict["status"] == "VERIFIED"
    assert r_verdict["artifact_ok"] is True

    # phase 2: scoring from the SAME serialized checkpoint artifact
    pa = recon_mod["pa"]
    game_date = date(2025, 7, 1)
    proj = synth_projected(pa, game_date)
    bf = pl.DataFrame([bf_row(999001, "Bot", 870001, synth_bf37(),
                              game_date=game_date)])
    dirs = synth_lake(tmp_path, pa, proj, bf)
    shutil.copyfile(ck, dirs["checkpoint_path"])
    wire_lake_existing_checkpoint(monkeypatch, dirs,
                                  sha_of(dirs["bf_path"]))
    summary = ad.run_real(tracking_uri=tracking_uri, experiment=exp,
                          pipeline_id=pid, artifact_location=art_loc)
    assert summary["tracking"]["status"] == "VERIFIED"
    # the TEST registration pin is enforced on the scoring path
    assert summary["checkpoint"]["registered_pin"] == report["sha256"]
    assert summary["checkpoint"]["registered_pin_enforced"] is True

    # both phases retrievable by the shared pipeline_id tag
    from mlflow.tracking import MlflowClient
    client = MlflowClient(tracking_uri=tracking_uri)
    e = client.get_experiment_by_name(exp)
    assert e is not None
    runs = client.search_runs([e.experiment_id],
                              filter_string=f"tags.pipeline_id = '{pid}'")
    assert len(runs) == 2
    by_phase = {r.data.tags["phase"]: r for r in runs}
    assert set(by_phase) == {"reconstruction", "scoring"}
    rec = by_phase["reconstruction"]
    assert rec.data.params["builder"] == "pregame-pa-ext-v2-build_checkpoint"
    assert rec.data.params["checkpoint_sha256"] == report["sha256"]
    assert rec.data.metrics["verification_passed"] == 1.0
    assert rec.data.metrics["n_verification_blocks"] == 3.0
    for block in bc.BLOCK_TRAIN_END:
        assert rec.data.metrics[
            f"verification_max_abs_diff__{block}"] <= 1e-8
    sco = by_phase["scoring"]
    assert sco.data.params["adapter"] == "pregame-pa-ext-v2"
    assert sco.data.params["checkpoint_sha256"] == report["sha256"]
    assert sco.data.metrics["n_projected_starts"] == 1.0


def test_reconstruction_tracking_failure_preserves_checkpoint_no_refit(
        monkeypatch, recon_mod, wrapper_mod):
    """FAILURE RECORDING (reconstruction phase): an MLflow failure during
    ``bc.track_reconstruction`` surfaces TrackingFailure to the caller,
    the already-serialized checkpoint artifact is preserved byte-exactly
    on disk, and NO refit is triggered (reconstruction is never
    re-entered; logging recovery is separate from reconstruction)."""
    report, ck = recon_mod["report"], recon_mod["ck"]
    sha_before = sha_of(ck)
    calls = []

    def _no_refit(*args, **kwargs):
        calls.append(1)
        raise AssertionError("refit attempted during tracking failure")

    monkeypatch.setattr(bc, "reconstruct", _no_refit)
    with pytest.raises(wrapper_mod.TrackingFailure) as ei:
        bc.track_reconstruction(
            report, tracking_uri="http://127.0.0.1:1/api",
            pipeline_id="paext-v2-synth-fail")
    assert "no refit" in str(ei.value)
    assert calls == []
    assert ck.exists()
    assert sha_of(ck) == sha_before
