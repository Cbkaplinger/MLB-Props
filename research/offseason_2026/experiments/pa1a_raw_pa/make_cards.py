"""PA-1A/1B card generator (Phase 5, owner-authorized). Writes two immutable
experiment cards + hashes.json under research/offseason_2026/experiments/.
Read-only otherwise. No training/scoring here.
"""
import hashlib, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from boundary import assert_workspace_path  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
DS = REPO / "research/offseason_2026/datasets/pa_table_2023_2024.parquet"
EXPA = REPO / "research/offseason_2026/experiments/pa1a_raw_pa"
EXPB = REPO / "research/offseason_2026/experiments/pa1b_oracle_xk"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def tree_status() -> dict:
    n = subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                       text=True, cwd=REPO).stdout.count("\n")
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True, cwd=REPO).stdout.strip()
    return {"dirty_paths": n, "head": head,
            "note": "108 dirty paths pre-existing (concurrent session, attributed "
                    "2026-09-29); this process writes nothing outside its two "
                    "experiment directories"}


COMMON = {
    "input_dataset": {"path": "research/offseason_2026/datasets/pa_table_2023_2024.parquet",
                      "sha256": sha(DS)},
    "populations": {
        "primary": {"total": 211292, "y2023_history": 105225, "e1": 55815, "e2": 50252,
                    "rule": "drop 360 truncated_pa (unknown outcome); retain 1275 field_error (known non-K)"},
        "sensitivity": {"total": 211652, "y2023_history": 105385, "e1": 55918, "e2": 50349,
                        "rule": "retain the 360 truncated_pa rows under assumed is_k=0; reported separately; no effect-size promise"},
        "truncated_exclusions": {"2023": 160, "e1": 103, "e2": 97, "total": 360},
    },
    "date_boundaries": {"e1": "2024-03-28..2024-06-30", "e2": "2024-07-01..2024-09-30",
                        "prior_history": "2023-03-30..2023-10-01 (never scored)"},
    "clip_rule": "inputs clipped to [1e-6, 1-1e-6] before odds transform; outputs clipped to [1e-6, 1-1e-6]; no tuning",
    "prohibited_operations": ["PA-1B run", "M3+", "shrinkage sweep", "league-prior refresh",
                              "handedness/park/TTO/discipline/pitch-mix features", "calibration fitting",
                              "frozen xTBF", "projected lineups", "count distributions",
                              "odds/sportsbook data", "2025/2026 scoring", "policy/ROI/CLV/Kelly analysis",
                              "dataset modification", "production modification", "writes outside experiment dirs",
                              "git stage/commit/reset/clean", "auto-repair of failed preflight",
                              "auto-launch of follow-ups"],
    "owner_authorization": "Phase 5 owner message (2026-09-29): authorized writing immutable PA-1A/1B cards, "
                           "bounded preflight, and PA-1A execution only. Cards immutable post-write; deviations "
                           "filed separately; substantive deviation = blocking FAIL.",
}

CARD_A = {
    "experiment_id": "PA-1A",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "git": tree_status(),
    **COMMON,
    "label": "PA-probability research using realized batter identities; not board-time lineup replay, "
             "not production comparison, and not betting evidence.",
    "arms": {
        "M0": "p0 = league_k_prior (0.223813, ratified 2022-derived scalar used in both 2024 blocks; "
              "not final/optimal; no as-of arm; refresh sensitivity may be proposed later only if M2 shows "
              "level/calibration failure)",
        "M1": "p1 = coalesce(k_rate_std, league_k_prior); fallback_reason='pitcher_no_prior_history' when null; "
              "k_rate_std is UNSHRUNK expanding prior-season-to-date (pitcher_rolling.py:1040); disclosure recorded",
        "M2": "p_p = coalesce(k_rate_std, league_k_prior); p_b = b_k_rate_std_shrunk; l = league_k_prior; "
              "odds(x)=x/(1-x); odds_m2 = odds(p_p)*odds(p_b)/odds(l); p2 = odds_m2/(1+odds_m2)",
    },
    "bootstrap": {"primary": {"cluster": "game_date", "B": 2000, "seed": 0, "ci": "percentile 95"},
                  "sensitivity": {"cluster": "game_pk", "B": 2000, "seed": 0, "ci": "percentile 95"},
                  "seven_day_moving_block": "DEFERRED (not existing infrastructure; specified, not implemented)",
                  "paired_deltas": ["M1-M0 logloss", "M2-M1 logloss", "M1-M0 brier", "M2-M1 brier",
                                    "M2-M0 logloss", "M2-M0 brier"],
                  "sign_convention": "negative delta favors the second arm"},
    "metrics": ["n", "ks", "observed_rate", "mean_pred", "logloss", "brier", "bias",
                "calibration_in_the_large", "calib_intercept", "calib_slope", "ece_20bin",
                "reliability_table_20_fixed_bins", "paired_deltas_with_CIs",
                "pct_bootstrap_replicates_favoring_challenger"],
    "calibration_spec": {"M0": "slope N/A - constant prediction; report constant, observed rate, "
                               "observed-minus-predicted, bias, logloss, brier",
                         "M1_M2": "diagnostic logit(P)=alpha+beta*logit(p) per block; alpha, beta, SE, n, "
                                  "converged, variation flag; NEVER used to transform predictions",
                         "sparse_bins": "report n explicitly; no merging after seeing results"},
    "slices": ["block", "month", "p_throws", "stand", "hand_matchup(same/opposite)",
               "fallback_reason", "pitcher_history_bucket(debut/<5/5-9/10-19/>=20 starts via P-window nulls)",
               "batter_history_bucket(0/1-49/50-149/>=150 prior PA from batter_games join, diagnostic only)",
               "matchup_number(1/2/3+)", "trip_proxy(1/2/3/4+)"],
    "slice_rules": "n and K stated per slice; sparse slices flagged; no favorable-slice search; "
                   "no post-hoc slice definitions; no promotion from one subgroup; "
                   "sequence fields are diagnostics, never inputs",
    "outputs_schema": {"metrics.json": "arm x block metrics + paired deltas + slices",
                       "reliability.parquet": "arm, block, bin_lo, bin_hi, n, ks, mean_p, obs_rate, gap",
                       "per_pa.parquet": "keys + p0/p1/p2 + fallback_reason + sequence diagnostics",
                       "preflight.json": "gate-by-gate PASS/WARN/FAIL with evidence",
                       "deviations.md": "runtime deviations (empty if none)"},
}

CARD_B = {
    "experiment_id": "PA-1B",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "git": tree_status(),
    **COMMON,
    "label": "Oracle opportunity decomposition; not pregame xK and not actionable replay.",
    "status": "SPECIFIED ONLY - NOT AUTHORIZED TO RUN (runs only after PA-1A owner review)",
    "definition": "group PA-1A per-PA predictions by (game_pk, starter); oracle_xK = sum(p_t) over "
                  "actual eligible starter PAs; actual K = sum(is_k) over the same rows",
    "metrics": ["MAE", "RMSE", "mean_bias", "error by actual-TBF bucket (<=17, 18-23, 24-27, >=28)",
                "error by month", "error by starter-history availability"],
    "prohibited_here": ["frozen xTBF", "projected lineups", "O1", "Poisson", "Poisson-binomial",
                        "calibrators", "odds", "policies", "betting results", "production comparison"],
    "completeness_preflight_outputs": "completeness.json (group counts, PA-count distribution, "
                                      "truncated-containing starts, multi-pitcher-ambiguous starts, "
                                      "canonical-TBF reconciliation, proposed PA-1B primary population)",
    "outputs_schema": {"completeness.json": "measurements only; no scoring"},
}


def main() -> None:
    for d in (EXPA, EXPB):
        d.mkdir(parents=True, exist_ok=True)
    import polars as pl
    schema = {k: str(v) for k, v in pl.read_parquet_schema(DS).items()}
    schema_hash = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()
    CARD_A["input_schema_hash"] = schema_hash
    CARD_B["input_schema_hash"] = schema_hash
    pa, pb = EXPA / "card.json", EXPB / "card.json"
    pa.write_text(json.dumps(CARD_A, indent=2), encoding="utf-8")
    pb.write_text(json.dumps(CARD_B, indent=2), encoding="utf-8")
    hashes = {"pa1a_card_sha256": sha(pa), "pa1b_card_sha256": sha(pb),
              "dataset_sha256": CARD_A["input_dataset"]["sha256"],
              "schema_sha256": schema_hash}
    (EXPA / "hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    (EXPB / "hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    print(json.dumps(hashes, indent=1))


if __name__ == "__main__":
    main()
