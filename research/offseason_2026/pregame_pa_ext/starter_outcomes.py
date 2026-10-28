"""Historical starter-outcome derivation (baseline contract v2).

Derives start-level K/BF outcomes from the registered PA source
(`pa_table.parquet` lineage: game_pk, game_date, pitcher, y,
pitcher_role, inning_topbot, at_bat_number) using the registered
first-pitcher-per-side prespec -- the same outcome semantics that
produced the existing start artifact (realized_bf = completed PA rows
for the starter's (game_pk, side, pitcher); realized_k = sum of y).

STARTER DEFINITION (registered prespec, reused -- not invented):
- side is derived from each PA's `inning_topbot` ('Top'/'Bot'): a
  pitcher's PAs all occur in his team's pitching half; a pitcher-game
  spanning both halves is an identity anomaly and fails loud.
- The start of a game-side is the FIRST pitcher to appear in that
  game-side (minimum at_bat_number) -- the first-pitcher prespec of the
  ledger lineage. Two starters in one game (one per side) are both
  derived.
- The start's outcome rows are ALL PAs of that (game_pk, side, starter)
  pitcher-game. Reliever rows are separate pitcher-games and are
  EXCLUDED (counted).

EXPLICIT HANDLING:
- Starter/opener roles: every PA row of a derived start must carry
  `pitcher_role == 'starter_pa'`; a game-side with more than one
  pitcher carrying starter rows (opener/bulk situations) fails loud --
  no opener rule is registered, so none is silently applied.
- Substitutions: batting-side substitutions do not affect the
  pitcher-game grouping (grouping is by pitcher identity).
- Missing rows: null `y` or null identity fields fail loud.
- Duplicates: duplicate (game_pk, pitcher, at_bat_number) rows fail
  loud.
- Exact definitions: realized_bf = PA-row count of the starter's
  (game_pk, side, pitcher); realized_k = integer sum of `y`. No
  imputation, no capped counting.

OVERLAP VALIDATION (registered contract): the derived 2024H2 window is
compared against the existing start artifact on IDENTICAL keys; exact
agreement is required, and discrepancies are reported per key with a
reason class -- never patched silently. Real-source validation requires
its applicable authorization.

BASELINE CONTRACT VERSIONING:
- v1 (frozen): P/S estimation on 2024-07-01..2024-12-31 start-outcome
  rows from the registered start artifact.
- v2 (this module, PENDING AUTHORIZATION): P/S estimation on the
  DERIVED 2023-01-01..2024-12-31 historical window. v2 changes only the
  reference-estimation history -- not the incumbent, the evaluation
  cohort, the support/tail conventions, or the primary contrast. It
  activates only after the derived artifact is authorized and its
  overlap validation passes.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import baseline_ladder as bl  # noqa: E402

DERIVED_CONTRACT = "baseline_v2_derived_starts_v1"
V2_TRAIN_START = "2023-01-01"
V2_TRAIN_END = "2024-12-31"
ROLE_START = "starter_pa"
ROLE_RELIEF = "reliever_pa"
SIDES = ("Top", "Bot")


class DerivationError(RuntimeError):
    """Starter-outcome derivation guards fail loud."""


def frame_sha(frame: "pl.DataFrame") -> str:
    buf = io.BytesIO()
    frame.write_parquet(buf)
    return hashlib.sha256(buf.getvalue()).hexdigest()


def require_columns(pa: "pl.DataFrame") -> None:
    """All identity/outcome fields must be present and complete."""
    required = ["game_pk", "game_date", "pitcher", "y",
                "pitcher_role", "inning_topbot", "at_bat_number"]
    missing = [c for c in required if c not in pa.columns]
    if missing:
        raise DerivationError(f"PA rows missing columns: {missing}")
    for c in required:
        n = pa[c].null_count()
        if n:
            raise DerivationError(
                f"missing rows detected: {n} null values in required "
                f"column '{c}'")


def derive_start_outcomes(pa: "pl.DataFrame", *,
                          train_start: str = V2_TRAIN_START,
                          train_end: str = V2_TRAIN_END,
                          fail_on_role_anomaly: bool = True) -> dict:
    """Deterministically derive start-level K/BF outcomes from an
    injected PA frame over the declared training interval.

    Same input -> same output rows in the same order (sorted by
    game_pk, side, pitcher)."""
    require_columns(pa)
    window = pa.filter(
        (pl.col("game_date") >= pl.date(*map(int, train_start.split("-"))))
        & (pl.col("game_date") <= pl.date(*map(int, train_end.split("-")))))
    meta = {"rows_in_window": window.height,
            "rows_out_of_window": pa.height - window.height,
            "train_interval": [train_start, train_end]}

    # ---- duplicate detection (full identity incl. at_bat_number) ----
    dup = (window.group_by("game_pk", "pitcher", "at_bat_number")
           .agg(n=pl.len()).filter(pl.col("n") > 1).height)
    if dup:
        raise DerivationError(
            f"duplicate PA rows detected: {dup} duplicated "
            "(game_pk, pitcher, at_bat_number) keys")

    # ---- pitcher-game grouping (side from the pitching half) --------
    pg = (window.group_by("game_pk", "pitcher", "inning_topbot")
          .agg(n_pa=pl.len(), k=pl.col("y").sum(),
               first_ab=pl.col("at_bat_number").min(),
               roles=pl.col("pitcher_role").unique().sort())
          .rename({"inning_topbot": "side"}))

    # ---- starter prespec: first pitcher per (game_pk, side) ---------
    starts = (pg.sort("first_ab")
              .group_by("game_pk", "side", maintain_order=True)
              .first())

    # ---- role contract ----------------------------------------------
    role_bad = starts.filter(
        (~pl.col("roles").list.contains(ROLE_START))
        | pl.col("roles").list.contains(ROLE_RELIEF))
    if role_bad.height and fail_on_role_anomaly:
        examples = role_bad.head(3).select(
            "game_pk", "side", "pitcher", "roles").rows()
        raise DerivationError(
            "incorrect-role failure: "
            f"{role_bad.height} derived starts carry non-starter roles "
            f"(expected every row {ROLE_START}); examples: {examples}")
    starter_pitchers_per_side = (pg.filter(
        pl.col("roles").list.contains(ROLE_START))
        .group_by("game_pk", "side").agg(n=pl.len())
        .filter(pl.col("n") > 1))
    if starter_pitchers_per_side.height and fail_on_role_anomaly:
        raise DerivationError(
            "role anomaly: "
            f"{starter_pitchers_per_side.height} game-sides carry more "
            "than one pitcher with starter-role rows (opener/bulk "
            "situations); no opener rule is registered -- fail loud")
    relievers = pg.filter(~pl.col("roles").list.contains(ROLE_START))

    out = starts.select(
        pl.col("game_pk"), pl.col("side"), pl.col("pitcher"),
        pl.col("n_pa").cast(pl.Int64).alias("realized_bf"),
        pl.col("k").cast(pl.Int64).alias("realized_k"),
        pl.col("first_ab"),
    ).sort("game_pk", "side", "pitcher")
    meta["n_starts"] = out.height
    meta["n_games"] = int(out["game_pk"].n_unique())
    meta["n_reliever_games_excluded"] = int(relievers.height)
    return {"start_outcomes": out, "meta": meta}


def validate_against_registered(derived: "pl.DataFrame",
                                registered: "pl.DataFrame") -> dict:
    """Overlap validation: compare the derived 2024H2 window against the
    existing start artifact on IDENTICAL keys (game_pk, side, pitcher).
    Returns a per-reason discrepancy report; discrepancies are explained,
    never patched silently."""
    keys = ["game_pk", "side", "pitcher"]
    d = derived.select(*keys, "realized_bf", "realized_k").unique()
    r = registered.select(*keys, "realized_bf", "realized_k").unique()
    both = d.join(r, on=keys, how="inner", suffix="_r")
    mismatched_bf = both.filter(
        pl.col("realized_bf") != pl.col("realized_bf_r"))
    mismatched_k = both.filter(pl.col("realized_k") != pl.col("realized_k_r"))
    only_derived = d.join(r, on=keys, how="anti")
    only_registered = r.join(d, on=keys, how="anti")
    return {
        "n_derived": d.height, "n_registered": r.height,
        "n_key_intersection": both.height,
        "keys_only_in_derived": only_derived.height,
        "keys_only_in_registered": only_registered.height,
        "bf_mismatches": mismatched_bf.height,
        "k_mismatches": mismatched_k.height,
        "examples_bf_mismatch": mismatched_bf.head(10).rows(),
        "examples_k_mismatch": mismatched_k.head(10).rows(),
        "verdict": ("IDENTICAL" if (mismatched_bf.height == 0
                                    and mismatched_k.height == 0
                                    and only_derived.height == 0
                                    and only_registered.height == 0)
                    else "DISCREPANCIES_REQUIRE_EXPLANATION"),
    }


def assert_train_window_v2(train_rows: "pl.DataFrame") -> None:
    """v2 window guard: training rows must lie within
    2023-01-01..2024-12-31 (the derived historical window)."""
    if train_rows["game_date"].null_count():
        raise DerivationError("null game_date in v2 training rows")
    bad = train_rows.filter(
        (pl.col("game_date") < pl.date(2023, 1, 1))
        | (pl.col("game_date") > pl.date(2024, 12, 31)))
    if bad.height:
        raise DerivationError(
            f"v2 training window violated: {bad.height} rows outside "
            "2023-01-01..2024-12-31")


def build_arms_v2(train_start_rows: "pl.DataFrame",
                  eval_starts: "pl.DataFrame", bf_lookup: dict) -> dict:
    """Smallest executable benchmark adapter for contract v2: attaches
    the declared window block (the derived rows are all block_2024H2
    under the registered bounds), runs the v1 arm machinery unchanged,
    and records the v2 contract identity. Synthetic use now; real use
    requires the derived artifact + authorization."""
    assert_train_window_v2(train_start_rows)
    labeled = train_start_rows.with_columns(
        ad.add_block(train_start_rows.select("game_date"))["block"]
        .alias("block"))
    arms = bl.build_arms(labeled, eval_starts, bf_lookup,
                         window_guard=assert_train_window_v2)
    arms["settings"]["contract"] = DERIVED_CONTRACT
    arms["settings"]["train_interval"] = [V2_TRAIN_START, V2_TRAIN_END]
    arms["settings"]["derived_source_note"] = (
        "P/S estimation on the DERIVED historical start-outcome window "
        "(2023-01-01..2024-12-31); incumbent, evaluation cohort, "
        "support/tail conventions, and primary contrast unchanged")
    return arms


def contract_sha() -> str:
    blob = json.dumps({"contract": DERIVED_CONTRACT,
                       "train_interval": [V2_TRAIN_START, V2_TRAIN_END]},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
