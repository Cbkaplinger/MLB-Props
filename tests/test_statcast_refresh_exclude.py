"""Coverage-gate exclusion for schedule-verified non-played games."""

from Python.statcast import missing_official_pks


def test_no_missing_no_exclusion():
    assert missing_official_pks(frozenset({1, 2}), frozenset({1, 2})) == []


def test_missing_reported_without_exclusion():
    assert missing_official_pks(frozenset({1, 2, 3}), frozenset({1, 2})) == [3]


def test_excluded_cancelled_game_passes():
    assert missing_official_pks(frozenset({1, 2, 3}), frozenset({1, 2}), frozenset({3})) == []


def test_exclusion_cannot_hide_real_gap():
    # Excluding a played-but-missing game still reports the other missing one.
    assert missing_official_pks(
        frozenset({1, 2, 3}), frozenset({1}), frozenset({2})
    ) == [3]


def test_exclusion_of_unrelated_pk_is_noop():
    assert missing_official_pks(frozenset({1}), frozenset({1}), frozenset({999})) == []
