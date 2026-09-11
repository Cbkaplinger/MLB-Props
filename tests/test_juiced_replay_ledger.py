"""Unit tests for juiced replay policy helpers. No live data required."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "production" / "ops" / "market_research"))

from juiced_replay_ledger import (  # noqa: E402
    BANDS,
    band_units,
    live_floor,
    policy_reason,
)


def test_live_floor_probation_and_map() -> None:
    floors = {2.5: 0.20, 3.5: 0.18, 4.5: 0.14, 6.5: 0.12}
    assert live_floor(2.5, "over", floors) == 0.20
    assert live_floor(3.5, "over", floors) == 0.18
    assert live_floor(3.5, "under", floors) == 0.18
    assert live_floor(6.5, "over", floors) == 0.12
    assert live_floor(9.5, "over", floors) == 0.12  # default base


def test_veto_and_floor_reasons() -> None:
    floors = {2.5: 0.20, 4.5: 0.14, 6.5: 0.12}
    assert policy_reason("over", 4.5, 0.50, floors) == "veto_4_5_over"
    assert policy_reason("under", 4.5, 0.50, floors) == ""
    assert policy_reason("over", 6.5, 0.10, floors) == "below_floor"
    assert policy_reason("over", 6.5, 0.12, floors) == ""


def test_edge_bands_preregistered() -> None:
    assert BANDS == ((0.18, 2.0), (0.12, 1.5), (0.0, 1.0))
    assert band_units(0.19) == 2.0
    assert band_units(0.12) == 1.5
    assert band_units(0.11) == 1.0


def test_featured_totals_clocks() -> None:
    from pull_featured_totals import request_ts

    assert request_ts("2025-07-04", "morning") == "2025-07-04T16:00:00Z"
    assert request_ts("2025-07-04", "evening") == "2025-07-04T23:55:00Z"
