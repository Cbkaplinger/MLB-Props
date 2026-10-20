# bf-lane-v1 — B0 WORKLOAD-REFERENCE AUDIT (2026-10-16)

**SELF-CHECK packet label — audit only, no fitting, no scoring, no real-data run.**

## Verdict

**PASS — the existing cutoff-valid workload/reference forecast is AVAILABLE and
PREGAME-VALID for all 7,194 starts in the registered assessment window
2024-07-01..2025-12-31 (272 slate dates, 3,597 games).**

Every audited property held with zero exceptions:

| Check | Result |
| --- | --- |
| BF PMF exists per start (37 `pmf37_*` cols, no nulls) | 7,194 / 7,194 |
| PMF entries finite + nonnegative | all |
| PMF sums to 1 | max abs deviation 4.44e-16 (tol 1e-9) |
| Sensitivity mix PMF (`pmf37_mix`, not the BASE arm) sums to 1 | max abs dev 3.33e-16 |
| Strictly-prior construction: `prior_n` rebuilt from the file's own realized BF (pools from 2023-01-01, updated AFTER each game_date) matches stored | 7,194 / 7,194, 0 mismatches |
| `prior_mean` / `lg_mean` recomputed running values match stored | max abs dev 0.0 |
| Same-date games (doubleheaders) never in prior | verified (0 pitcher-date multi-start groups in window; update-after-date semantics asserted) |
| Source dates < game_date (raw lineage) | builder recipe + independent reviewer verification (pa_ext verdict: all source dates strictly < cutoff, mean lag 2.898464770024403 d, min 1 d, n=7,194) |
| Cohort join vs `start_metrics_v2.parquet` | 0 misses; realized BF matches 7,194 / 7,194 |
| Support vs realized: max realized BF 37 (1 start overflow-relevant), none beyond cap 60 | OK |
| Overflow convention (index 36 = P(N>=37), never read as BF=37) | OK; mean overflow mass 0.0111 |
| Count-integration input valid (`bf_pmf_from_37` cap 60 applied to every row) | sum dev <= 4.44e-16 |

## Per-start availability states (counts)

| State | Definition | Count |
| --- | --- | --- |
| `own_distribution` | prior_n >= 10: add-one empirical over the pitcher's own prior BF outcomes | 6,059 |
| `insufficient_history_league_pool` | 1 <= prior_n <= 9: league add-one empirical; **short prior outings preserved** in the pool | 966 |
| `career_debut_league_pool` | prior_n == 0: league add-one empirical | 169 |
| `b0_pmf_unavailable` | any pmf37 column null | **0** |
| failed cohort join / realized-BF mismatch | — | **0** |
| unavailable lineup-starter inputs | **not applicable — lineup-free by registered recipe** (recorded 0, `not_applicable_lineup_free`) | **0** |

Season debuts with prior history (new season, prior_n > 0): 501.

## Lineage of the count-distribution integration inputs (labelled)

The realized-sequence diagnostic (`bf-workload-v1/scripts/run_kcount_comparison.py`)
consumed exactly these inputs: `bf_forecasts.parquet` 37-category PMFs ->
`kcount_combiner.bf_pmf_from_37` (cap 60) -> per-PA `p_bar` from overnight-p2
**realized-PA** predictions -> `combine_count` (k_max 24) -> count PMFs ->
`count_rps` / `count_logscore` / milestone Brier. That diagnostic is
REALIZED-SEQUENCE CONDITIONED and is NOT a pregame forecast. bf-lane-v1 B0/B1
reuse only the deterministic integration machinery (pure combiner functions,
sha256-pinned in `b0_audit.json`) with pregame-valid inputs; the
realized-PA `p_bar` is NOT carried over (registered pregame `p_bar`
construction declared in B1_REGISTRATION.md).

## Artifacts

| File | sha256 |
| --- | --- |
| `b0_audit.json` (machine-readable audit + hashes) | a420dda40317b517dcf7d4cfcafee5d9e8877f52299d1e716db5d70071218a69 |
| `b0_per_start_availability.csv` (per-start state, 7,194 rows) | see MANIFEST.json |
| `scripts/b0_audit.py` (read-only audit script) | d52930af4dd026615771750d085ea9479dcf069f69fbfc276cf53c4c05a95c93 |

Audited inputs (hashes pinned in `b0_audit.json`):
`bf_forecasts.parquet` c9c2762f...68679, `start_metrics_v2.parquet`
af6814ec... (matches the registered outcome-source hash in
freeze_lgbm_equal_info_v2.json — registered-path-only, used here for the join
check only), `build_bf_forecasts.py` 8893918b...08ef6,
`kcount_combiner.py` 94f57a49...70f18f.
