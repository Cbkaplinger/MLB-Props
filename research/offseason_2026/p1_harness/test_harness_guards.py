"""Guard tests for the P1 harness v2 feature builder.

(a) a feature row whose source date equals its game_date is REJECTED
(b) a feature row whose source date is strictly in the future of its
    game_date is REJECTED
(c) a fully strict frame passes with no error
(d) v2 CHANGE (owner ruling 2): rows with NULL source dates now FAIL the
    validator. Every fallback must record its source_type; null source dates
    are no longer skipped. The valid fallback shape (cold-start entity with
    the league source date + source_type recorded) passes.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import polars as pl
import pytest

HARNESS = Path(__file__).resolve().parent
REPO_ROOT = HARNESS.parents[2]
sys.path.insert(0, str(HARNESS / "scripts"))

from build_features import (  # noqa: E402
    SOURCE_TYPE_COLD,
    SOURCE_TYPE_ENTITY,
    validate_no_future_leakage,
)


def test_import_resolves_inside_checkout() -> None:
    """The builder under test is THIS checkout's file, never a path fallback."""
    import build_features

    mod_path = Path(build_features.__file__).resolve()
    assert mod_path.is_relative_to(REPO_ROOT), (
        f"imported build_features from outside the checkout: {mod_path}"
    )
    assert mod_path == HARNESS / "scripts" / "build_features.py"


def make_features(
    src_pitcher,
    src_batter,
    src_lg,
    game_date=date(2025, 8, 1),
    type_pitcher=SOURCE_TYPE_ENTITY,
    type_batter=SOURCE_TYPE_ENTITY,
    type_lg="league_history",
) -> pl.DataFrame:
    """Minimal features frame."""
    return pl.DataFrame(
        {
            "game_pk": [1],
            "at_bat_number": [1],
            "batter": [123456],
            "game_date": [game_date],
            "src_date_pitcher": [src_pitcher],
            "n_prior_pitcher": [100],
            "src_type_pitcher": [type_pitcher],
            "src_date_batter": [src_batter],
            "n_prior_batter": [100],
            "src_type_batter": [type_batter],
            "lg_src_date": [src_lg],
            "lg_n_prior": [700000],
            "src_type_lg": [type_lg],
        }
    )


STRICT = date(2025, 7, 31)  # strictly before game_date 2025-08-01


def test_same_date_source_is_rejected() -> None:
    """(a) source date == game_date must raise (same-day info is leakage)."""
    df = make_features(src_pitcher=date(2025, 8, 1), src_batter=STRICT, src_lg=STRICT)
    with pytest.raises(AssertionError, match="pitcher"):
        validate_no_future_leakage(df)


def test_future_dated_source_is_rejected() -> None:
    """(b) source date strictly after game_date must raise."""
    df = make_features(
        src_pitcher=STRICT,
        src_batter=STRICT,
        src_lg=date(2025, 8, 15),  # league prior dated after the PA
    )
    with pytest.raises(AssertionError, match="league"):
        validate_no_future_leakage(df)


def test_strict_frame_passes() -> None:
    """(c) all source dates strictly before game_date -> no error."""
    df = make_features(src_pitcher=STRICT, src_batter=STRICT, src_lg=STRICT)
    validate_no_future_leakage(df)


def test_null_source_dates_now_fail() -> None:
    """(d) v2: null source dates must FAIL (v1 skipped them)."""
    df = make_features(src_pitcher=None, src_batter=None, src_lg=None)
    with pytest.raises(AssertionError, match="null_source_date"):
        validate_no_future_leakage(df)


def test_null_source_type_fails() -> None:
    """(d) every fallback must record its source_type; a null type fails."""
    df = make_features(
        src_pitcher=STRICT, src_batter=STRICT, src_lg=STRICT, type_batter=None
    )
    with pytest.raises(AssertionError, match="null_source_type"):
        validate_no_future_leakage(df)


def test_valid_cold_start_fallback_passes() -> None:
    """(d) the documented cold-start fallback passes: source date falls back to
    the league source date with source_type league_prior_no_entity_history."""
    df = make_features(
        src_pitcher=STRICT,
        src_batter=STRICT,
        src_lg=STRICT,
        type_pitcher=SOURCE_TYPE_COLD,
        type_batter=SOURCE_TYPE_COLD,
    )
    validate_no_future_leakage(df)


def test_valid_fixed_prior_fallback_passes() -> None:
    """(d) the opening-day fixed prior fallback passes: source_type
    external_fixed_prior with the fixed prior source date 2022-04-06."""
    df = make_features(
        src_pitcher=date(2022, 4, 6),
        src_batter=date(2022, 4, 6),
        src_lg=date(2022, 4, 6),
        game_date=date(2022, 4, 7),
        type_pitcher=SOURCE_TYPE_COLD,
        type_batter=SOURCE_TYPE_COLD,
        type_lg="external_fixed_prior",
    )
    validate_no_future_leakage(df)
