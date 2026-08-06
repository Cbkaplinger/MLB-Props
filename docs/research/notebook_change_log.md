# Notebook change log

This file tracks every substantial change to
`production/results_dashboard.ipynb` and the support modules its new sections
lean on (`src/Python/skill_stats.py`, `tests/test_skill_stats.py`,
`tests/test_market.py`). The intent is the same as `floor_freeze_log.md`: no
silent dashboard additions. If a chart moves or a CI method changes, the
reason and the section number land here in chronological order.

## Conventions

- One entry per change-batch, oldest at the bottom.
- Each entry lists: date (UTC), section number touched, one-line intent, the
  artifact(s) the section writes (paths under `artifacts/odds_log/`), and any
  code modules added or modified.
- Renames / removals get a `REMOVED:` or `RENAMED:` line; restating the section
  in a new form is `SUPERSEDED:` with a back-link to the prior entry.
- Section numbers are stable: a new logical section gets the next free number
  (currently 19+), it does not re-use a removed one's slot.

## Artifacts written by the dashboard (current inventory)

| Path | Section | What's in it |
| --- | --- | --- |
| `artifacts/odds_log/ledger.parquet` | (pre-existing) | the live ledger; SHA-256 is the floor-freeze cell-hash |
| `artifacts/odds_log/clv_reliability.parquet` | 11 | decile-level observed vs CLV-predicted win rate + n (the weekly calibration artifact) |
| `artifacts/odds_log/edge_band_discrete.parquet` | 12 | per-`[f, f+1)` edge band: n, flat-1u ROI, mean CLV, BCa CI, win rate |
| `artifacts/odds_log/clv_floor_bca.parquet` | 18 | edge-floor CLV sweep recomputed with BCa (the authoritative sweep) |
| `artifacts/odds_log/next_50_checkpoint.json` | 18 | pre-registered next-50-bet decision rule + ledger snapshot + SHA-256 |

---

## 2026-08-06 — Added Sections 11–18 (CLV skill suite)

A batch of eight new dashboard sections plus a sibling
`src/Python/skill_stats.py` module and its test suite, all driven by the
2026-08-06 floor-review conversation. Each section was prioritized against
"which chart resolves the current ambiguity fastest," in that order:

- **Section 11 — CLV-vs-realized-win-rate reliability plot + z-test.** Bins
  by `clv_pp` decile, plots observed vs CLV-predicted win rate (Brier-style),
  and runs a two-proportion z-test on `CLV ≥ +1.0pp` vs `CLV < +1.0pp`.
  Writes `clv_reliability.parquet`. Backed by
  `skill_stats.two_proportion_z_test`.
- **Section 12 — Band-discrete flat-1u panel.** 1pp-wide `[f, f+1)` edge
  bands with `n`, flat-1u ROI, mean CLV and **BCa** CI (percentile bootstrap
  is biased at the per-band n≈10-40). Flags sub-floor bands with positive ROI
  explicitly as "do NOT use this to argue for lowering the floor" — the
  recursive-floor-rediscovery trap. Writes `edge_band_discrete.parquet`.
  Backed by `skill_stats.bootstrap_bca_ci`.
- **Section 13 — Rolling 30-bet CLV ±2 SE ribbon.** Normal-approximation
  ribbon over the rolling mean to see whether the CLV signal is 2-3 hot days
  or genuinely steady. Reports the share of windows that clear the SE ribbon.
  Backed by `skill_stats.rolling_stat_with_se`.
- **Section 14 — Stake-weighted CLV + BCa CI.** `sum(clv × stake) / sum(stake)`
  with a BCa CI, compared side-by-side with equal-weighted CLV and a cumulative
  running chart. The metric that actually governs bankroll outcomes; needed
  before any Kelly-scaling decision. Backed by
  `skill_stats.stake_weighted_bootstrap_ci`.
- **Section 15 — Per-band CLV distribution histograms.** 2pp-wide bands with
  stacked win/loss colored histograms for `clv_pp`, marked with the band mean
  *and* median. The chart that catches a `[6,9)`-style band whose mean is
  ≈ 0 only because it's bimodal. Prints a `|mean − median| > 1pp` skew flag
  per band.
- **Section 16 — Pseudo-ROC.** Sweeps `t` and plots TPR vs FPR of
  `clv_pp ≥ t` as a classifier of `result == win`. Reports AUC and marks the
  `+1.0pp` Section 11 threshold on the curve. A skill oracle should beat the
  0.5 diagonal; AUC ≥ 0.6 = real skill, 0.5–0.6 = real but weak.
- **Section 17 — CLV outcome-pairing scatter.** `(p_market, p_close)` colored
  by result, with the diagonal `p_close == p_market` (no-CLV line). Tests
  whether wins cluster upper-left-of-diagonal — selection-tracking outcomes
  rather than just bet-direction. Includes a 2×2 contingency bar chart and a
  risk ratio.
- **Section 18a — BCa-CLV sweep + authoritative artifact.** Replaces
  Section 10's percentile CIs with BCa, writes
  `clv_floor_bca.parquet`, and plots the BCa sweep alongside Section 10's
  percentile sweep so the user can see the deviation directly. The
  floor ≥ 14–20% bands had over-confident CIs from percentile bootstrap at
  low n; this is the corrected authoritative sweep the n_clv ≥ 150 gate
  uses.
- **Section 18b — Pre-registered next-50-bet checkpoint.** Doesn't run any
  analysis; freezes the universe-as-of-now at `next_50_checkpoint.json` with
  timestamp, ledger SHA-256, result-status counts, and the full decision
  rule (mean CLV ≥ +0.30pp AND win-rate ≥ 0.54 → escalate stake; either
  missed → revert to quarter-Kelly; all other → no change, re-evaluate at
  n_clv = 200). This is the actual fix for "recursive floor-rediscovery":
  the future audit can assert the "next 50 settled" were chosen from bets
  unsettled at this snapshot.

### Code modules

- **NEW:** `src/Python/skill_stats.py` — pure-Python skill checks (`two_proportion_z_test`,
  `bootstrap_bca_ci`, `stake_weighted_bootstrap_ci`, `rolling_stat_with_se`).
  `_inverse_std_normal_cdf` uses a robust bisection (prior Wichura/Acklam
  approximation constant-transcription bugs cost a lot of debugging time and
  were retired).
- **NEW:** `tests/test_skill_stats.py` — covers z-test detection / validation,
  BCa centering / zero-exclusion / constant-data / custom-statistic / small-n
  rejection, stake-weighted pull-toward-heavy / equal-weights-match-plain /
  validations, and rolling SE bracketing / monotone-then-stable behavior.

### `market.py` and `test_market.py` touch-ups (no behavior change)

- **MODIFIED:** `src/Python/market.py` — `unit_anchor_kelly_frac` docstring
  re-pinned to the *current* `DEFAULT_EDGE_FLOOR` (0.12) / `DEFAULT_KELLY_FRACTION`
  (0.125). The earlier "8% @ -110 ≈ 4.2%" wording in the docstring was the
  pre-freeze value and is kept only as a historical note; the actual constants
  never moved.
- **MODIFIED:** `tests/test_market.py` —
  `test_unit_anchor_is_about_4_2_percent` →
  `test_unit_anchor_reflects_current_floor` (now re-computes the expected
  anchor from `DEFAULT_EDGE_FLOOR` / `DEFAULT_KELLY_FRACTION` so it can't go
  stale the way the old 0.042 hardcode did). `test_size_in_units_one_at_anchor`
  re-pinned to `DEFAULT_EDGE_FLOOR` for the same reason.

### Floor freeze

The companion `docs/research/floor_freeze_log.md` records the 2026-08-06
reaffirmation of `DEFAULT_EDGE_FLOOR = 0.12` with the actual cell-hash
(`cfddcf674c20da314fab1243c52fa2a637e875cec3c09ce825b8ebe60ac49e37`) and
the resolved ledger snapshot (330 rows, 199 settled, 72 bets at
`floor ≥ 12%`).
