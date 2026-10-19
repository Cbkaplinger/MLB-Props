# BUNDLE_EXTRACTION — market-eval-v1 input extraction record

**Date:** 2026-10-14. **Scope:** exact input columns, transformations,
missingness rules, model/checkpoint dates, preds lineage, and BF construction
for every bundle consumed by market-eval-v1 prep (C2). All facts extracted
from the actual bundles (files read, schemas dumped, hashes recomputed).

## 1. Quote archive — `book_lines_pitcher.parquet`

Path: `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Odds-Historical\theoddsapi\book_lines_pitcher.parquet`
sha256_16 `325abdf01f5f0b84` (matches the accepted odds-coverage-v1 manifest).

4,025,730 rows. Columns used (others ignored):

| Column | Dtype | Role |
| --- | --- | --- |
| `event_id` | str | vendor event key (join to envelope + identity) |
| `snapshot` | str | clock label: `open18`, `board`, `morning`, `close`, `board_2023_24` |
| `snapshot_ts` | str ISO-Z | quote time (UTC); **verified constant within (event, snapshot)** |
| `game_date` | str date | vendor UTC date (differs from local ET date across midnight) |
| `season_type` | str | only `regular` used |
| `book` | str | 13 books: barstool, betmgm, betonlineag, betrivers, bovada, draftkings, fanatics, fanduel, mybookieag, pointsbetus, superbook, unibet_us, williamhill_us |
| `market` | str | `pitcher_strikeouts` / `pitcher_strikeouts_alternate` pooled |
| `player` | str | display name (not used in joins) |
| `player_norm` | str | vendor-normalized name (join key) |
| `line` | f64 | total strikeouts line (0.5..10.5 in-cohort) |
| `side` | str | `over` / `under` |
| `price` | i64 | American odds |

### Transformations (registered, in order)

1. Filter to the two K markets + `season_type == "regular"`: 2,440,774 rows.
2. Price validity: drop `|price|` outside [1, 100000] (vendor junk):
   **10 rows dropped**, none with null `snapshot_ts`.
3. Duplicate dedup at key (event, snapshot, book, market, player_norm, line,
   side): keep max price (bettor-best); price ties keep the FIRST file row
   (enforced by a file-row index — C2 determinism fix).
4. Market pooling at key (event, snapshot, book, **player_norm**, line, side):
   one row at max price across the two markets. **C2 fix:** the v1 key omitted
   `player_norm`, which arbitrarily deleted one pitcher's quotes whenever two
   pitchers shared an (event, snapshot, book, line, side) key — 750,797 such
   keys exist in the archive (different pitchers at the same line/book/snapshot).
   Result: 1,516,039 pooled quote rows (v1 kept fewer, unpredictably).

### Missingness rules

- `quote_ts` nulls: 0.
- Junk prices outside [1, 100000]: 10 (dropped, counted).
- No rescues attempted; every drop is counted in `prep_summary.json`.

## 2. Snapshot envelope — `snapshot_envelope.parquet`

sha256_16 `2b73bc4096b34641`. Columns used: `event_id`, `commence_time`.
Earliest commence_time per event = `first_pitch_ts` (UTC) for Tier A.
Verified unique per event. Tier A starts = 4,624 (2025-03-18..2025-09-28,
184 slate dates); starts without an envelope row are Tier B (clock proxy,
2024-07-01..2024-09-30, 88 slate dates).

## 3. Frozen predictor payload — `predictor_payload.parquet`

Path: `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v1\data\predictor_payload.parquet`
sha256 `19511a492767ca061f216bf0a1679e94a77706b2737aea4cf1ab93c312b58a96`
(frozen before any label join; 7,194 rows × 155 columns).

Key + per-start columns used:

| Column(s) | Content |
| --- | --- |
| `game_pk`, `side` (Top/Bot), `pitcher` (MLBAM), `game_date` | start identity |
| `forecast_cutoff` | scheduled game_date (ET) — the forecast cutoff; C2 converts it to `predictor_available_ts` = 00:00 ET of that date (UTC) |
| `p_h3_raw_1..9`, `p_l5_raw_1..9` | projected per-PA probabilities of the projected nine-batter sequence (raw arms) |
| `p_h3_cal_1..9`, `p_l5_cal_1..9` | calibrated variants (lineage only; NOT used by market-eval) |
| `pmf_h3_raw_0..23`, `pmf_l5_raw_0..23` | frozen projected-state K PMFs (support 0..23; P(K>=24)=0 by payload contract) — the two registered arms |
| `pmf37_0..36` | per-start BASE BF PMF (37 categories, index 36 = P(N>=37)) |
| `n_fallback_slots`, `n_cold_slots`, `slot_src_type_1..9` | lineup-slot provenance |
| `prior_n`, `cold_start`, `nine_distinct` | pitcher prior state |
| `mean_k_h3_raw`, `mean_k_l5_raw` | E[K] per arm |
| `block` | development block label |

### Missingness rules

- `forecast_cutoff` nulls: 0. Every start has 9 projected batters
  (nine_distinct enforced by the accepted pregame-state-v1 gates).
- Uncovered slots would carry source type `league_rate_fill_uncovered_slot`;
  expected inert (accepted v2 coverage was 100%); implemented and tested
  upstream, never needed here.
- The payload carries NO team labels and the envelope carries NO game_pk:
  doubleheader (vendor_date, pitcher) keys cannot be resolved event-by-event
  and are excluded (54 keys, 25 starts).

### Model / checkpoint dates (overnight-p2 frozen H3/LOG5 checkpoint)

The payload's raw arms reconstruct the frozen overnight-p2 v3 ladder
checkpoint deterministically (G2 coefficient verification <= 1e-8 against
stored preds before any projected-row inference):

| Block | base_train window | calibration sub-block | assessment |
| --- | --- | --- | --- |
| block_2024H1 | 2023-01-01.. | 2023-08-03..2023-10-01 (61,023 PAs) | 2024H1 |
| block_2024H2 | .. | 2024-05-02..2024-06-30 (59,484) | 2024H2 |
| block_2025H1 | .. | 2024-08-02..2024-09-30 (59,579) | 2025H1 |
| confirm_2025H2 | .. | 2025-05-02..2025-06-30 (60,137) | 2025H2 |

Run identity: `6a62d8edf60ec0951d30a3114ac3603da7d5296d52a1c1ea800dc1dff7c6def2`.
Library pins (overnight-p2 run_identity.json): python 3.11.9, polars 1.43.0,
numpy 2.4.6, scikit-learn 1.9.0.

### Preds lineage (execution-time checkpoints, sha256)

| Preds parquet | sha256 |
| --- | --- |
| `preds_block_2024H1.parquet` | `5b8219ae54d599ad444d099430e36ae5cf7be63c84dbf2370a16b161313d71f6` |
| `preds_block_2024H2.parquet` | `a311f4429457ced383b8ef834846978b4682b912e53bb46319107efc0cd980d3` |
| `preds_block_2025H1.parquet` | `6187d232e8917ce40b481feda5521cecefa0ce8418741ef65aff7dfc8702cbd7` |
| `preds_confirm_2025H2.parquet` | `e60b5aa306dcd5e2157d0de61392681c287a190607330461b98cf91701c88d2a` |

Executed fit-key receipts (deterministic replays, add-only):
`overnight-p2\data\keys_executed_*.parquet` +
`reports\executed_keys_summary.json` (sha256 `6c831a5e5c47239721a61d636c5d4f458b10b3e478f563c86c69a0993996009d`).

## 4. BF construction (BASE empirical, bf_pmf_from_37, cap 60)

Identical BF PMF for BOTH arms (registered in pregame-pa-ext-v1
`scripts/preregistration.json`):

1. **BASE empirical**: per-start 37-category add-one empirical BF PMF
   (`pmf37_0..36`) from bf-workload-v1 machinery; index 36 = P(N >= 37).
2. **Tail extension** `bf_pmf_from_37(pmf37, cap=60)` (helpers/
   kcount_combiner.py): body n=1..36 kept as-is; the overflow mass P(N>=37)
   is redistributed over n=37..60 with a geometric tail whose per-step ratio
   is `1 - mean_hazard` where `mean_hazard` = mean of the last six implied
   hazards h(31..36) (h(n) = pmf37[n-1] / cumulative survival). Zero overflow
   or zero tail hazard places nothing. Assert: sums to 1 within 1e-9.
3. **Combiner**: `pbar_n` = mean of the projected nine per-PA probabilities
   CYCLED to n (n = 1..60); `P(K=k) = sum_n P(N=n) * Binom(k; n, pbar_n)`,
   k = 0..23 (last bucket absorbs >= 23), k_max = 24, KCOUNT_CAP = 60.
4. `mean_k = sum_n n * P(N=n) * pbar_n` over the full 1..60 support.

## 5. Identity bridge — `player_id_map.parquet`

sha256_16 `8a463f5c34281afd`. Columns used: `mlb_id` -> `pitcher`;
`player_name` -> sorted-token normalized key (`sorted_name`: NFKD-fold to
ASCII, lowercase, keep [a-z ] only, tokens sorted). Joined to archive
`player_norm` on (pitcher_key) with vendor-UTC vs local-ET date tolerance
+/-1 day, closest first, ties by (date_dist, event_id, vendor_game_date)
(C2 deterministic ordering).

## 6. Realized K (SCORING ONLY — never joined at prep)

`C:\Users\ckaplinger\MLB-Props-Research\bf-workload-v1\data\start_metrics_v2.parquet`
(7,194 rows; key (game_pk, side, pitcher) unique; (game_pk, pitcher) also
unique). `realized_k` non-null for all rows, range 0..15. Persisted count
errors `base_h3_*` / `base_l5_*` (rps, logscore, rmse_mean_k,
brier_ge6/8/10/12) are REUSED by the scoring run, never recomputed.
