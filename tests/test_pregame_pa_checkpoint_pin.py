"""Synthetic tests for the REGISTERED checkpoint sha256 pin gate
(``checkpoint_sha256_expected`` in
``research/offseason_2026/pregame_pa_ext/freeze_pregame_pa_ext_v2.json``).

The registered pin is a PLACEHOLDER (null) until the real-data
reconstruction (build_checkpoint.py) produces the artifact and its printed
hash is registered; while null the gate is DISABLED and the checkpoint
loads normally. When the pin is non-null, the adapter's
``load_serialized_checkpoint`` verifies the artifact sha256 against it and
fails loud on mismatch. No real hash is invented here -- every value in
these tests is derived from synthetic fixtures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))

import pregame_pa_ext.adapter as ad  # noqa: E402


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


def test_registered_config_default_pin_is_null_gate_disabled():
    """The committed registration config carries checkpoint_sha256_expected
    = null (placeholder): the gate is DISABLED until a real-data
    reconstruction registers the artifact hash."""
    assert ad.registered_checkpoint_pin() is None


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
