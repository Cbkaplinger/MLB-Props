"""Synthetic tests for the REGISTERED checkpoint sha256 pin gate
(``checkpoint_sha256_expected`` in
``research/offseason_2026/pregame_pa_ext/freeze_pregame_pa_ext_v2.json``).

The committed registration pins the RECONSTRUCTED real checkpoint's
canonical payload hash (REGISTERED_CHECKPOINT_SHA256 below, registered
2026-10-20 after the single authorized deterministic reconstruction; see
the freeze's ``checkpoint_registration`` record for the full registration
receipt). The registered pin is a FIXED literal -- it is never computed
dynamically from whatever artifact scoring happens to load. With a
non-null pin, ``load_serialized_checkpoint`` verifies the artifact sha256
against it and fails loud on mismatch
(CHECKPOINT_REGISTERED_PIN_MISMATCH). Every fixture value in these tests
is derived from synthetic artifacts, never the real hash.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import pregame_pa_ext.adapter as ad  # noqa: E402

# The COMMITTED registration: canonical payload sha256 of the reconstructed
# real checkpoint (fixed literal; see freeze checkpoint_registration for the
# full record incl. the distinct raw-file sha256 used only for MLflow
# artifact byte-verification).
REGISTERED_CHECKPOINT_SHA256 = (
    "176fb18bc3b06328f4425175907506ea0dbcea45727e8879ff06249a751decfe")


def fake_models() -> dict:
    return {"block_2025H1": {f: 0.1 for f in ad.FEAT_H3}}


def write_freeze_config(tmp_path: Path, pin) -> Path:
    cfg = {
        "freeze_id": "pregame-pa-ext-v2-synth",
        "checkpoint_artifact": "checkpoints/h3_raw_checkpoint.json",
        "checkpoint_sha256_expected": pin,
    }
    p = tmp_path / "freeze_pregame_pa_ext_v2_synth.json"
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return p


def write_checkpoint(tmp_path: Path) -> Path:
    ck = tmp_path / "checkpoints" / "h3_raw_checkpoint.json"
    ad.serialize_checkpoint(fake_models(),
                            {"block_2025H1": {"n_rows": 10,
                                              "max_abs_diff": 0.0}},
                            ck)
    return ck


def wire(monkeypatch, tmp_path: Path, pin) -> Path:
    ck = write_checkpoint(tmp_path)
    freeze = write_freeze_config(tmp_path, pin)
    monkeypatch.setattr(ad, "CHECKPOINT_PATH", ck)
    monkeypatch.setattr(ad, "FREEZE_CONFIG_RELPATH", str(freeze))
    return ck


def test_registered_config_pins_reconstructed_checkpoint():
    """The committed registration config carries checkpoint_sha256_expected
    = the reconstructed checkpoint's canonical payload hash (fixed literal;
    the gate is ENFORCED on every load; scoring itself remains gated by
    owner authorization, not by this pin)."""
    assert ad.registered_checkpoint_pin() == REGISTERED_CHECKPOINT_SHA256


def test_null_pin_gate_disabled_checkpoint_loads_normally(
        tmp_path, monkeypatch):
    """(a) null registered pin = gate disabled: the checkpoint loads
    normally, meta records the disabled gate."""
    ck = wire(monkeypatch, tmp_path, None)
    models, meta = ad.load_serialized_checkpoint()
    assert set(models) == {"block_2025H1"}
    assert meta["sha256"] == ad.checkpoint_sha256({
        "features": list(ad.FEAT_H3),
        "recipe": {"w_prior": ad.W_PRIOR,
                   "half_life_days": ad.HALF_LIFE_DAYS},
        "blocks": fake_models(),
        "verification": {"block_2025H1": {"n_rows": 10,
                                          "max_abs_diff": 0.0}},
    })
    assert meta["registered_pin"] is None
    assert meta["registered_pin_enforced"] is False


def test_nonnull_matching_pin_loads(tmp_path, monkeypatch):
    """(b) non-null registered pin + matching artifact = loads; meta
    records the enforced pin."""
    ck = write_checkpoint(tmp_path)
    doc = json.loads(ck.read_text(encoding="utf-8"))
    assert doc["sha256"] == ad.checkpoint_sha256(doc["payload"])
    freeze = write_freeze_config(tmp_path, doc["sha256"])
    monkeypatch.setattr(ad, "CHECKPOINT_PATH", ck)
    monkeypatch.setattr(ad, "FREEZE_CONFIG_RELPATH", str(freeze))
    models, meta = ad.load_serialized_checkpoint()
    assert set(models) == {"block_2025H1"}
    assert meta["registered_pin"] == doc["sha256"]
    assert meta["registered_pin_enforced"] is True


def test_nonnull_mismatched_pin_fails_loud(tmp_path, monkeypatch):
    """(c) non-null registered pin + mismatched artifact = fail loud with
    CHECKPOINT_REGISTERED_PIN_MISMATCH (never a silent load)."""
    ck = wire(monkeypatch, tmp_path, "f" * 64)
    with pytest.raises(ad.AdapterError, match="CHECKPOINT_REGISTERED_PIN_"
                                              "MISMATCH"):
        ad.load_serialized_checkpoint()
    assert ck.exists()  # nothing mutated on a refused load


def test_malformed_pin_fails_loud(tmp_path, monkeypatch):
    """A non-null registered pin that is not a 64-char hex sha256 fails
    loud (CHECKPOINT_PIN_MALFORMED) instead of silently comparing."""
    ck = wire(monkeypatch, tmp_path, "not-a-sha")
    with pytest.raises(ad.AdapterError, match="CHECKPOINT_PIN_MALFORMED"):
        ad.load_serialized_checkpoint()
    assert ck.exists()


# ------------------------------------------- scoring-path registered-pin gate
def test_require_registered_pin_returns_committed_registration():
    """The SCORING gate (require_registered_checkpoint_pin) passes under
    the COMMITTED registration (the reconstructed checkpoint's pin) and
    returns the registered value."""
    assert ad.require_registered_checkpoint_pin() == \
        REGISTERED_CHECKPOINT_SHA256


def test_require_registered_pin_rejects_null_registration(tmp_path,
                                                          monkeypatch):
    """The CHECKPOINT_PIN_NOT_REGISTERED path (kept covered on a synthetic
    null registration: a null pin refuses scoring before anything runs)."""
    freeze = write_freeze_config(tmp_path, None)
    monkeypatch.setattr(ad, "FREEZE_CONFIG_RELPATH", str(freeze))
    with pytest.raises(ad.AdapterError,
                       match="CHECKPOINT_PIN_NOT_REGISTERED"):
        ad.require_registered_checkpoint_pin()


def test_require_registered_pin_returns_registered_value(tmp_path,
                                                         monkeypatch):
    """With an explicit registration (the synthetic artifact's own
    sha256), the scoring gate returns the pin."""
    ck = write_checkpoint(tmp_path)
    doc = json.loads(ck.read_text(encoding="utf-8"))
    freeze = write_freeze_config(tmp_path, doc["sha256"])
    monkeypatch.setattr(ad, "FREEZE_CONFIG_RELPATH", str(freeze))
    assert ad.require_registered_checkpoint_pin() == doc["sha256"]


# ------------------------------------- synthetic lake for run_real pin tests
def synth_pa_table(n_days: int = 40, seed: int = 7) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    pitchers = [870001, 870002, 870003]
    batters = list(range(660001, 660010))
    p_k = {870001: 0.25, 870002: 0.20, 870003: 0.30}
    b_k = {b: 0.20 + 0.01 * i for i, b in enumerate(batters)}
    rows = []
    for d in range(n_days):
        gd = date(2025, 1, 1) + timedelta(days=d)
        pk = pitchers[d % 3]
        for slot in range(9):
            bt = batters[slot % len(batters)]
            for _ in range(2):
                p = 0.5 * p_k[pk] + 0.5 * b_k[bt]
                rows.append({
                    "game_pk": 900000 + d, "at_bat_number": len(rows) + 1,
                    "batter": bt, "pitcher": pk, "game_date": gd,
                    "y": int(rng.random() < p),
                })
    return pl.DataFrame(rows)


def synth_projected(pa: pl.DataFrame, game_date) -> pl.DataFrame:
    batters = sorted(pa["batter"].unique().to_list())
    slots = {f"u_slot_{i + 1}": batters[i % len(batters)] for i in range(9)}
    return pl.DataFrame([{
        "game_pk": 999001, "side": "Bot", "pitcher": 870001,
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


def wire_scoring_lake(tmp_path: Path, monkeypatch) -> dict:
    """Full synthetic private-lake stand-in with EVERY scoring input
    present and valid (serialized sha256-pinned checkpoint artifact,
    matching BF PMF pin, projected lineups, PA table) -- and the COMMITTED
    registration left in force (FREEZE_CONFIG_RELPATH is NOT
    monkeypatched). The synthetic artifact deliberately does NOT match the
    committed registered pin."""
    from datetime import date as _date
    pa = synth_pa_table()
    proj = synth_projected(pa, _date(2025, 3, 15))
    bf = pl.DataFrame([{
        "game_pk": 999001, "side": "Bot", "pitcher": 870001,
        "game_date": _date(2025, 3, 15),
        **{f"pmf37_{j}": float(v) for j, v in enumerate(synth_bf37())},
    }])
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
    ad.serialize_checkpoint(
        synth_models(pa),
        {"block_2025H1": {"n_rows": 10, "max_abs_diff": 0.0}}, ck)
    monkeypatch.setattr(ad, "PREGAME_STATE_DIR", ps)
    monkeypatch.setattr(ad, "OVERNIGHT_P2_DIR", op2)
    monkeypatch.setattr(ad, "PAEXT_OUT_DIR", out)
    monkeypatch.setattr(ad, "BF_WORKLOAD_DIR", bfw)
    monkeypatch.setattr(ad, "CHECKPOINT_PATH", ck)
    monkeypatch.setattr(ad, "REGISTERED_BF_FORECASTS_SHA256",
                        ad.sha256_file(bf_path))
    return {"out_dir": out, "checkpoint_path": ck}


def test_run_real_rejects_committed_registration_mismatch_before_inference(
        tmp_path, monkeypatch):
    """NEGATIVE TEST: with the COMMITTED registration in force (the
    reconstructed real checkpoint's pin), run_real refuses a synthetic
    artifact whose payload hash does NOT match the registered pin --
    CHECKPOINT_REGISTERED_PIN_MISMATCH raised BEFORE any inference or
    output write, even when every other scoring input (BF PMF artifact,
    projected lineups, PA table) is present and valid on the synthetic
    lake. Inference is proven not to run (sentinel guard on
    build_projected_pa_probs) and no output file is written."""
    dirs = wire_scoring_lake(tmp_path, monkeypatch)
    calls = []

    def _no_inference(*args, **kwargs):
        calls.append(1)
        raise AssertionError(
            "inference must not run past the registered-pin gate")

    monkeypatch.setattr(ad, "build_projected_pa_probs", _no_inference)
    out = dirs["out_dir"] / "outputs" / "projected_pa_probs_v1.parquet"
    with pytest.raises(ad.AdapterError,
                       match="CHECKPOINT_REGISTERED_PIN_MISMATCH"):
        ad.run_real()
    assert calls == []          # inference never entered
    assert not out.exists()     # no output write
    assert not (dirs["out_dir"] / "outputs").exists()


def test_run_real_proceeds_with_explicit_test_registration(
        tmp_path, monkeypatch):
    """POSITIVE CONTROL on the same synthetic lake: registering the
    synthetic checkpoint artifact's own sha256 as an explicit TEST
    registration un-blocks run_real, which then completes and writes the
    output; the summary records the enforced pin. (No real hash is
    invented -- the pin is derived from the synthetic artifact.)"""
    dirs = wire_scoring_lake(tmp_path, monkeypatch)
    doc = json.loads(dirs["checkpoint_path"].read_text(encoding="utf-8"))
    p = dirs["out_dir"] / "freeze_pregame_pa_ext_v2_synth.json"
    p.write_text(json.dumps({
        "freeze_id": "pregame-pa-ext-v2-synth",
        "checkpoint_sha256_expected": doc["sha256"],
    }, indent=2), encoding="utf-8")
    monkeypatch.setattr(ad, "FREEZE_CONFIG_RELPATH", str(p))
    summary = ad.run_real()
    assert Path(summary["output"]).exists()
    assert summary["checkpoint"]["registered_pin"] == doc["sha256"]
    assert summary["checkpoint"]["registered_pin_enforced"] is True
