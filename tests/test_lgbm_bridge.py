"""Mechanical tests for the frozen LightGBM-to-count bridge."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "research" / "offseason_2026"))
sys.path.insert(0, str(HERE / "src"))

import run_lgbm_bridge as rb  # noqa: E402
from Python.features import FORBIDDEN_PREGAME_FEATURES  # noqa: E402


class FakeBooster:
    def __init__(self, value: float, n_features: int):
        self.value = value
        self.n_features = n_features

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        return np.full(len(matrix), self.value)

    def num_feature(self) -> int:
        return self.n_features


def _feats(n: int) -> list[str]:
    return ["f%02d" % i for i in range(n)]


def test_blend_weights_and_clip():
    members = [
        {"booster": FakeBooster(0.9, 3), "features": _feats(3),
         "weight": 0.6, "stem": "a"},
        {"booster": FakeBooster(0.1, 3), "features": _feats(3),
         "weight": 0.4, "stem": "b"},
    ]
    frame = pl.DataFrame({f: [0.0, 1.0] for f in _feats(3)})
    out = rb.blend_predict(members, frame)
    assert out.shape == (2,)
    assert out[0] == pytest.approx(0.6 * 0.9 + 0.4 * 0.1)
    members_hi = [
        {"booster": FakeBooster(2.0, 3), "features": _feats(3),
         "weight": 0.5, "stem": "a"},
        {"booster": FakeBooster(2.0, 3), "features": _feats(3),
         "weight": 0.5, "stem": "b"},
    ]
    out_hi = rb.blend_predict(members_hi, frame)
    assert (out_hi == 1.0).all()


def test_blend_rejects_missing_columns():
    members = [{"booster": FakeBooster(0.5, 3),
                "features": _feats(3), "weight": 1.0, "stem": "a"}]
    frame = pl.DataFrame({"f00": [0.0], "f01": [0.0]})
    with pytest.raises(rb.RunFailure, match="missing"):
        rb.blend_predict(members, frame)


def test_load_rejects_duplicate_sidecar_features(tmp_path,
                                                 monkeypatch):
    d = tmp_path
    feats = ["a", "a", "b"]
    (d / "m.json").write_text(json.dumps(
        {"features": feats, "evaluation": {"features": len(feats)}}))
    (d / "m.txt").write_text("booster")
    fake = hashlib.sha256(b"x").hexdigest()
    monkeypatch.setattr(
        rb, "ENSEMBLE", [{"stem": "m", "weight": 1.0}])
    monkeypatch.setattr(
        rb, "FROZEN_ARTIFACT_SHA", {"m.txt": fake, "m.json": fake})
    monkeypatch.setattr(rb.rt, "sha256_file", lambda p: fake)
    with pytest.raises(rb.RunFailure, match="duplicate feature"):
        rb.load_frozen_ensemble(d)


def test_load_rejects_booster_sidecar_count_mismatch(tmp_path,
                                                     monkeypatch):
    d = tmp_path
    feats = ["a", "b"]
    (d / "m.json").write_text(json.dumps(
        {"features": feats, "evaluation": {"features": 3}}))
    (d / "m.txt").write_text("booster")
    fake = hashlib.sha256(b"x").hexdigest()
    monkeypatch.setattr(
        rb, "ENSEMBLE", [{"stem": "m", "weight": 1.0}])
    monkeypatch.setattr(
        rb, "FROZEN_ARTIFACT_SHA", {"m.txt": fake, "m.json": fake})
    monkeypatch.setattr(rb.rt, "sha256_file", lambda p: fake)
    with pytest.raises(rb.RunFailure, match="count mismatch"):
        rb.load_frozen_ensemble(d)


def test_feature_contract_gate_blocks_labels():
    members = [{"stem": "x", "features": ["k_rate_P5", "K"],
                "weight": 1.0}]
    g = rb.feature_contract_gate(members)
    assert g["pass"] is False
    assert g["violations"]["x"] == ["K"]
    members_ok = [{"stem": "x", "features": ["k_rate_P5",
                                             "park_k_factor"],
                   "weight": 1.0}]
    assert rb.feature_contract_gate(members_ok)["pass"] is True


def test_feature_contract_gate_forbidden_set_complete():
    for label in ("K", "PA", "Outs", "k_rate"):
        assert label in FORBIDDEN_PREGAME_FEATURES


def test_rolling_feature_invariance_to_current_game():
    """A rolling-window feature for game N must be identical
    regardless of game N's own K/PA (mechanical outcome-invariance
    proof on the real builder expression)."""
    from Python import pitcher_rolling as pr

    def build(k3: float, pa3: float) -> float | None:
        rows = [
            {"pitcher": 1, "game_pk": 100, "K": 10.0, "PA": 20.0,
             "game_date": date(2024, 5, 1)},
            {"pitcher": 1, "game_pk": 101, "K": 8.0, "PA": 24.0,
             "game_date": date(2024, 5, 6)},
            {"pitcher": 1, "game_pk": 102, "K": k3, "PA": pa3,
             "game_date": date(2024, 5, 11)},
        ]
        df = pl.DataFrame(rows).with_columns(
            pr._rolling_rate("K", "PA", 5, 1).alias("kr_P5"))
        return df["kr_P5"][-1]

    assert build(6.0, 30.0) == pytest.approx(build(12.0, 18.0))
