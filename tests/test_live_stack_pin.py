"""Live-stack regression pins (#113.4 backend pack).

Fails on ANY unapproved live-policy drift. If a pin fails after an
APPROVED policy change, update the pin in the same commit (src+test ship
together). Pins: Poisson default, WS1c pointer == production file,
4.5-over veto, 2.5/3.5 probation @0.18, edge cap @0.20 + robust refusal,
postseason HOLD cutoff,
watch vanish tracking, atomic ledger write.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python.count_layer import COUNT_LAYER_FAMILY_DEFAULT  # noqa: E402
from Python.kpi_policy import load_kpi_policy  # noqa: E402
from Python.odds_board import (  # noqa: E402
    _clip_offset,
    _edge_cap_reason,
    _postseason_hold_reason,
    _probation_edge_floor,
    _robust_refusal_reason,
    _side_line_veto_reason,
)
from Python.odds_ledger import atomic_write_parquet  # noqa: E402


def test_pin_poisson_default() -> None:
    assert COUNT_LAYER_FAMILY_DEFAULT == "poisson"


def test_pin_ws1c_pointer_matches_file() -> None:
    ptr = json.loads((ROOT / "artifacts" / "models"
                      / "prob_calibration_production.json").read_text(encoding="utf-8"))
    assert "ws1c" in str(ptr.get("joblib", "")).lower()
    bundle = joblib.load(ROOT / "artifacts" / "models" / ptr["joblib"])
    assert set(bundle.line_maps) >= {"2_5", "4_5", "6_5", "9_5"}


def test_pin_veto_and_probation() -> None:
    rules = load_kpi_policy().get("quality_gate", {}).get("rules", {})
    assert rules.get("block_side_line_veto") is True
    assert _side_line_veto_reason("over", 4.5, rules) == "veto_4_5_over"
    assert _side_line_veto_reason("over", 5.5, rules) is None
    assert _side_line_veto_reason("under", 4.5, rules) is None
    assert _probation_edge_floor("over", 2.5, rules, 0.12) >= 0.18
    assert _probation_edge_floor("over", 3.5, rules, 0.12) >= 0.18
    assert _probation_edge_floor("over", 6.5, rules, 0.12) == 0.12
    assert _probation_edge_floor("under", 2.5, rules, 0.12) == 0.12


def test_pin_postseason_cutoff() -> None:
    rules = load_kpi_policy().get("quality_gate", {}).get("rules", {})
    end = (rules.get("season") or {}).get("regular_end")
    assert end == "2026-09-27"
    assert _postseason_hold_reason({"game_date": "2026-09-27"}, rules) is None
    assert _postseason_hold_reason({"game_date": "2026-10-03"}, rules) == "postseason_hold"


def test_pin_edge_cap_and_robust_refusal() -> None:
    # Owner-directed 2026-09-11 (named change + disclosed 2026 peek).
    # Refusal REVERTED same day: cap-only validates on 2025 (+8.0% vs base
    # +4.2%), refusal destroys it (-0.2%). Code path stays tested for the
    # October family dimension; live key must be absent/disabled.
    rules = load_kpi_policy().get("quality_gate", {}).get("rules", {})
    assert rules.get("block_edge_above_cap") is True
    assert float(rules.get("edge_cap")) == 0.20
    assert not rules.get("robust_shrink_refusal", False)
    assert _edge_cap_reason(0.25, rules) == "edge_cap"
    assert _edge_cap_reason(0.15, rules) is None
    on = dict(rules, robust_shrink_refusal=True)
    assert _robust_refusal_reason(0.70, 0.15, 0.12, on) == "robust_refusal"
    assert _robust_refusal_reason(0.60, 0.19, 0.12, on) is None


def test_pin_offset_cap() -> None:
    # Owner-directed 2026-09-11 (correction audit cap_0.02).
    rules = load_kpi_policy().get("quality_gate", {}).get("rules", {})
    assert float(rules.get("offset_cap")) == 0.02
    assert _clip_offset(0.06, rules) == 0.02
    assert _clip_offset(-0.06, rules) == -0.02
    assert _clip_offset(0.015, rules) == 0.015


def test_pin_watch_vanish_tracking() -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "frozen_edge_watch",
        ROOT / "production" / "ops" / "frozen_edge_watch.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["frozen_edge_watch"] = mod
    spec.loader.exec_module(mod)
    old = [{"player_name": "A", "line": 6.5, "best_side": "over",
            "recommendation": "BET", "policy_reason": "", "edge": 0.15,
            "best_price": -110, "stake": 60.0}]
    flips, lost = mod.diff_frames(old, [])
    assert flips == [] and len(lost) == 1 and lost[0].get("_vanished") is True


def test_pin_atomic_ledger_write(tmp_path: Path) -> None:
    p = tmp_path / "ledger.parquet"
    df = pl.DataFrame([{"ticket_id": "t1", "pnl": 1.5}])
    atomic_write_parquet(df, p)
    assert pl.read_parquet(p).height == 1
    assert list(p.parent.glob("*.tmp")) == []
