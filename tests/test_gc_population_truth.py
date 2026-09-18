"""GC regression guards: champion population truth, CLV scale, void exclusion.

Codifies the 2026-09-17 460/485/844 reconciliation so stale counts cannot
silently return, plus the live-vs-replay CLV scale convention.
"""

import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python.market import bet_pnl, clv_pp  # noqa: E402
from Python.odds_ledger import apply_void, settled_bets  # noqa: E402

from conftest import artifact_path  # noqa: E402


def test_champion_judge_disk_truth() -> None:
    """Rebuilt-panel truth: 2026 judge n=460, ROI ~+8.75% (not 485, not 844)."""
    p = artifact_path("artifacts", "odds_log", "champion_2026_grade.json")
    g = json.loads(p.read_text(encoding="utf-8"))
    assert g["n"] == 460, f"judge set changed: n={g['n']}"
    assert g["stake"] == 460 * 50.0
    assert abs(g["roi"] - g["pnl"] / g["stake"]) < 1e-9
    assert abs(g["roi"] - 0.0875) < 0.005
    assert abs(g["wr"] - 0.574) < 0.01


def test_champion_selection_disk_truth() -> None:
    """Rebuilt-panel truth: 2025 selection n=505, ROI ~+11.0% (not 558)."""
    p = artifact_path("artifacts", "odds_log", "select_2025_report.json")
    rep = json.loads(p.read_text(encoding="utf-8"))
    champs = rep.get("configs", rep if isinstance(rep, list) else [])
    if isinstance(rep, dict) and "champion" in rep:
        champ = rep["champion"]
    else:
        champ = max(champs, key=lambda c: c.get("lcb", -9)) if champs else {}
    assert champ, "no champion config found in select_2025_report.json"
    n = champ.get("n_2025", champ.get("n"))
    assert n == 505, f"selection set changed: n={n}"


def test_clv_pp_returns_fraction_scale() -> None:
    """`clv_pp` returns a fraction difference; pp display is x100.

    Guards the live (fraction) vs paid/juiced (percent) scale trap:
    callers must multiply by 100 before labeling "pp".
    """
    assert abs(clv_pp(0.60, 0.55) - 0.05) < 1e-12
    assert abs(clv_pp(0.55, 0.60) + 0.05) < 1e-12
    pp_display = 100.0 * clv_pp(0.60, 0.55)
    assert abs(pp_display - 5.0) < 1e-9


def test_roi_is_pnl_over_stake() -> None:
    """ROI = sum(PnL)/sum(stake) on settled, staked, deduplicated tickets."""
    pnl = bet_pnl(50.0, -110, won=True)
    assert pnl > 0
    assert abs(pnl - 50.0 * 100.0 / 110.0) < 1e-9
    assert bet_pnl(50.0, -110, won=False) == -50.0


def test_void_excluded_from_settled() -> None:
    """Void/DNP tickets never enter `settled_bets` or money math."""
    frame = pl.DataFrame([
        {"ticket_id": "a", "status": "settled", "result": "win",
         "pnl": 45.0, "note": ""},
        {"ticket_id": "b", "status": "settled", "result": "loss",
         "pnl": -50.0, "note": ""},
        {"ticket_id": "c", "status": "open", "result": "pending",
         "pnl": 0.0, "note": ""},
    ])
    frame = apply_void(frame, ticket_id="b", reason="scratch")
    settled = settled_bets(frame)
    assert settled["ticket_id"].to_list() == ["a"]
    assert settled["pnl"].sum() == 45.0
