"""Unit tests for research join keys (order-invariant + verified aliases)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "production" / "ops" / "market_research"))

from join_keys import PLAYER_ALIASES, sorted_key  # noqa: E402


def test_sorted_key_order_invariant() -> None:
    assert sorted_key("Logan Allen") == sorted_key("Allen Logan")


def test_verified_aliases() -> None:
    assert sorted_key("Mike Soroka") == "michael soroka"
    assert sorted_key("Daniel Lynch") == "daniel iv lynch"


def test_aliases_are_exact_match_only() -> None:
    # Unrelated same-last-name players must NOT collapse.
    assert sorted_key("Spencer Schwellenbach") != sorted_key("Spencer Arrighetti")
    assert "michael soroka" in PLAYER_ALIASES.values()


def test_suggest_nickname_hit() -> None:
    from join_keys import suggest_aliases  # noqa: E402

    out = suggest_aliases(["mike soroka"], {"michael soroka", "mike soroka"})
    assert out == [{"needle": "mike soroka", "verdict": "nickname",
                    "alias": "michael soroka"}]


def test_suggest_suffix_hit() -> None:
    from join_keys import suggest_aliases  # noqa: E402

    out = suggest_aliases(["daniel lynch"], {"daniel iv lynch"})
    assert out == [{"needle": "daniel lynch", "verdict": "suffix",
                    "alias": "daniel iv lynch"}]


def test_suggest_rejects_ambiguous_and_missing() -> None:
    from join_keys import suggest_aliases  # noqa: E402

    out = suggest_aliases(
        ["arrighetti spencer", "cantillo joseph"],
        {"miles spencer", "schwellenbach spencer"})
    by_n = {p["needle"]: p for p in out}
    assert by_n["arrighetti spencer"]["verdict"] == "ambiguous (2)"
    assert by_n["cantillo joseph"]["verdict"] == "no candidate"
