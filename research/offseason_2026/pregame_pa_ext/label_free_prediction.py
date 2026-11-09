"""Label-free prediction orchestration for BOTH registered feature
contracts (adopted scope 2026-11-09): the 8-feature reference control
(`platoon_comparison.FEATURES`) and the 12-feature platoon challenger
(`platoon_comparison.CHALLENGE_FEATURES`), sharing identical keyed
workload inputs and K-count aggregation.

SYNTHETIC-TESTED ONLY. Pure dict-in, dict-out; no I/O, no fitting, no
outcome assessment, no comparison scoring, no bootstrap, no real-data
run. Reuses the existing feature-construction seams
(`forecast_states_v2.build_v2_states`, `adapter.attach_prior_features`,
and, for the challenger contract only,
`platoon_features.build_split_class_rates` /
`platoon_features.forecast_matchup_hands` /
`platoon_features.attach_platoon_features`) and the existing label-free
inference (`label_free_inference.run_label_free_inference`). The wiring
mirrors the registered temporal-robustness runner's request-path
construction. No parallel math, no model registry.

Inputs (injected frames or permitted registered outputs):
1. model: an already-fitted model dict whose declared features match
   ONE of the two registered contracts (set-matched; the model's
   declared ORDER is authoritative for feature selection). Anything
   else refuses, naming both contracts.
2. pa: PA source carrying `game_date`, `game_pk`, `pitcher`, `batter`,
   `y` (registered binary-K indicator for states-v2); the challenger
   contract additionally requires the registered terminal-event labels
   `stand`, `p_throws`, `class_label` (statcast_event_bridge output
   semantics).
3. lineups: projected lineups (game_pk, side, pitcher, game_date,
   nine_distinct, u_slot_1..9).
4. bf37_by_start: keyed BF37 distributions for the same starts.

Outputs: keyed full class-probability vectors and keyed 24-bucket
K-count PMFs (via the existing label-free inference entry point), plus
the matched contract name.

This orchestration does NOT:
- fit, tune, or score;
- read real artifacts, private data, or protected partitions;
- infer VERIFIED, authorization, or promotion from process completion.

Historical labels in the PA source are used only as permitted
strictly-prior history for feature construction; they are not assessment
outcomes for the forecast requests. Strictly-prior dates do not certify
real historical source availability - that limitation remains upstream.

Structural access limits: request dates at/after R3 (2025-07-01) are
refused as structurally inaccessible; PA rows at/after the boundary are
excluded with a disclosed count.
"""
from __future__ import annotations

from datetime import date

import polars as pl

from pregame_pa_ext import adapter as ad
from pregame_pa_ext import forecast_states_v2 as fv
from pregame_pa_ext import label_free_inference as lfi
from pregame_pa_ext import platoon_comparison as pc
from pregame_pa_ext import platoon_features as pf

R3_START = date(2025, 7, 1)

# the two registered feature contracts (registered lists, order-authoritative
# from the model dict; set-matched here)
REFERENCE_CONTRACT = list(pc.FEATURES)
CHALLENGER_CONTRACT = list(pc.CHALLENGE_FEATURES)
_REGISTERED_CONTRACTS = {
    "reference_control_v1": REFERENCE_CONTRACT,
    "platoon_challenger_v1": CHALLENGER_CONTRACT,
}
_PLATOON_REQ = {"stand", "p_throws", "class_label"}
_REQ_PA_BASE = {"game_date", "game_pk", "pitcher", "batter", "y"}
_REQ_LU = {"game_pk", "side", "pitcher", "game_date", "nine_distinct"}
_REQ_LU.update(f"u_slot_{s}" for s in range(1, 10))


def _match_contract(declared: list) -> str:
    """Set-match the declared features against the two registered
    contracts; refuse anything else, naming both. The model dict's
    declared ORDER is authoritative for feature selection."""
    for name, contract in _REGISTERED_CONTRACTS.items():
        if sorted(declared) == sorted(contract):
            return name
    raise ValueError(
        f"model features match neither registered contract: "
        f"reference_control_v1 ({len(REFERENCE_CONTRACT)} features: "
        f"platoon_comparison.FEATURES) nor platoon_challenger_v1 "
        f"({len(CHALLENGER_CONTRACT)} features: "
        f"platoon_comparison.CHALLENGE_FEATURES); declared "
        f"{len(declared)} feature(s)")


def _require_cols(frame: pl.DataFrame, cols: set, ctx: str) -> None:
    missing = cols - set(frame.columns)
    if missing:
        raise ValueError(
            f"{ctx}: missing required column(s) {sorted(missing)}")


def run_prediction(model: dict, pa: pl.DataFrame,
                   lineups: pl.DataFrame,
                   bf37_by_start: pl.DataFrame) -> dict:
    """Cutoff-correct prepared features -> existing label-free inference
    -> keyed class probabilities and K-count PMFs, for either registered
    feature contract (reference control or platoon challenger)."""
    declared = list(model.get("features", []))
    contract = _match_contract(declared)
    needs_platoon = contract == "platoon_challenger_v1"

    _require_cols(pa, _REQ_PA_BASE | (_PLATOON_REQ if needs_platoon
                                      else set()), "pa_table")
    _require_cols(lineups, _REQ_LU, "lineups")
    _require_cols(bf37_by_start, {"game_pk", "side", "pitcher"}, "bf37")

    # structural filter: PA rows at/after R3 excluded (disclosed)
    pa_ok = pa.filter(pl.col("game_date") < pl.lit(R3_START))
    n_pa_excluded = int(pa.height - pa_ok.height)
    if pa_ok.height == 0:
        raise ValueError("pa_table empty after the R3 structural filter")

    # requests through the registered projection seam
    long, n_uncovered = ad.projected_long(lineups)
    if n_uncovered > 0:
        raise ValueError(
            f"lineups carry {n_uncovered} uncovered slot(s); the "
            "prediction path refuses incomplete nine-slot coverage")
    if long.height == 0:
        raise ValueError("empty projection request population")
    req_dates = sorted(long["game_date"].unique().to_list())
    if max(req_dates) >= R3_START:
        raise ValueError(
            "request dates reach the R3 confirm partition; "
            "structurally inaccessible")

    # strictly-prior states over the truncated history; cutoffs are the
    # request dates only (asof-backward joins resolve the latest
    # pre-cutoff aggregate for each request row)
    p_v2, b_v2, lg_v2, _ = fv.build_v2_states(pa_ok, list(req_dates))
    feat_req = ad.attach_prior_features(
        long.select("game_date", "pitcher", "batter", "game_pk",
                    "side", "slot"),
        p_v2, b_v2, lg_v2)

    # handedness + platoon features (registered seams, runner order);
    # ONLY the challenger contract consumes the platoon family
    if needs_platoon:
        rates = pf.build_split_class_rates(
            pa_ok, list(req_dates), alpha=pc.ALPHA, n_classes=4)
        hands = pf.forecast_matchup_hands(
            pa_ok,
            feat_req.select(pl.col("batter"), pl.col("pitcher"),
                            pl.col("game_date").alias("cutoff")))
        feat_req = (feat_req
                    .join(hands.select("batter", "pitcher", "cutoff",
                                       "f_stand", "f_hand"),
                          left_on=["batter", "pitcher", "game_date"],
                          right_on=["batter", "pitcher", "cutoff"],
                          how="left")
                    .with_columns(
                        pl.col("game_date").alias("cutoff"),
                        pl.col("f_stand").alias("stand"),
                        pl.col("f_hand").alias("p_throws"))
                    .drop(["f_stand", "f_hand"]))
        feat_req = pf.attach_platoon_features(feat_req, rates,
                                              n_classes=4)

    # null refusal over the full declared contract
    bad = {c: feat_req[c].null_count() for c in declared
           if c in feat_req.columns and feat_req[c].null_count() > 0}
    if bad:
        raise ValueError(
            f"request features contain nulls {bad}: history window does "
            "not precede the earliest cutoff")

    # select to the inference contract (key identity + declared features
    # only, in the model's declared order)
    feat_req = feat_req.select(lfi.KEY_COLS + declared)

    # existing reviewed label-free inference entry point (identical keyed
    # workload inputs and K-count aggregation for both arms)
    inference = lfi.run_label_free_inference(model, feat_req, bf37_by_start)
    return {
        "keyed_pa_probabilities": inference["keyed_pa_probabilities"],
        "k_pmf_per_start": inference["k_pmf_per_start"],
        "scored_starts": inference["scored_starts"],
        "n_starts": inference["n_starts"],
        "n_slots": inference["n_slots"],
        "classes": inference["classes"],
        "n_pa_rows_excluded_r3": n_pa_excluded,
        "contract": contract,
    }
