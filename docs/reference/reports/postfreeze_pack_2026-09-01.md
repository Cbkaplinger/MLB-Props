# Merged evidence pack (consolidated 2026-09-17)

> Content-intact merge of `postfreeze_pack_2026-09-01.md`, `postfreeze_pack_2026-09-01.md`, `postfreeze_pack_2026-09-01.md`, `postfreeze_pack_2026-09-01.md`, `postfreeze_pack_2026-09-01.md`, `postfreeze_pack_2026-09-01.md`. Newest first. Originals survive in git history; update citations to this file.

---

<!-- section 1/6 from postfreeze_deep_diagnosis_2026-09-01.md (merged 2026-09-17, content intact) -->

# Post-freeze deep diagnosis (2026-09-01)

Analysis-only. **No live KING / floor change.**

Producer: `production/ops/run_postfreeze_deep_diagnosis.py`

## Executive memo

- KING post-freeze: n=74, ROI=-0.0155, PnL=-80.18.
- Edge↔ROI Spearman overs: {'n': 45, 'pearson_r': -0.0906, 'pearson_p': 0.5539, 'spearman_r': -0.081, 'spearman_p': 0.5969}.
- Edge↔ROI Spearman unders: {'n': 29, 'pearson_r': 0.2609, 'pearson_p': 0.1717, 'spearman_r': 0.1693, 'spearman_p': 0.3801}.
- Brier skill vs market: over={'n': 45, 'brier_model': 0.32246, 'brier_market': 0.25221, 'skill_vs_market': -0.27854}, under={'n': 29, 'brier_model': 0.21223, 'brier_market': 0.2491, 'skill_vs_market': 0.14804}.
- If over edge↔ROI is flat/negative, raising a universal floor will not heal overs.
- Prefer side/line gates; keep CLV as a skill check alongside ROI/PnL.
- Do not promote on this single ~10-day window alone.

## Edge% vs per-bet ROI

| Slice | n | Pearson | Spearman |
| --- | ---: | --- | --- |
| king_all | 74 | 0.0881 (p=0.4553) | 0.1093 (p=0.354) |
| king_over | 45 | -0.0906 (p=0.5539) | -0.081 (p=0.5969) |
| king_under | 29 | 0.2609 (p=0.1717) | 0.1693 (p=0.3801) |

## Abs-edge buckets (KING)

| Side | Edge bucket | n | ROI | WR | CLV>0 |
| --- | --- | ---: | ---: | ---: | ---: |
| all | 0.12–0.14 | 11 | 0.03 | 0.5455 | 0.3333 |
| all | 0.14–0.16 | 12 | -0.2353 | 0.4167 | 0.25 |
| all | 0.16–0.18 | 6 | -0.4386 | 0.3333 | 1.0 |
| all | 0.18–0.22 | 11 | 0.2981 | 0.6364 | 1.0 |
| all | 0.22–1.0 | 16 | 0.0971 | 0.5625 | 0.5 |
| over | 0.12–0.14 | 8 | -0.2684 | 0.375 | 0.5 |
| over | 0.14–0.16 | 9 | -0.5234 | 0.2222 | 0.25 |
| over | 0.16–0.18 | 2 | -0.0313 | 0.5 | None |
| over | 0.18–0.22 | 6 | 0.0592 | 0.5 | 1.0 |
| over | 0.22–1.0 | 7 | -0.3408 | 0.2857 | 1.0 |
| under | 0.12–0.14 | 3 | 0.8568 | 1.0 | 0.0 |
| under | 0.14–0.16 | 3 | 1.1742 | 1.0 | None |
| under | 0.16–0.18 | 4 | -0.5987 | 0.25 | 1.0 |
| under | 0.18–0.22 | 5 | 0.6107 | 0.8 | None |
| under | 0.22–1.0 | 9 | 0.3801 | 0.7778 | 0.3333 |

## Universal floor sweep (stake>0 post-freeze)

| Floor | n | ROI | PnL | n_over/under | CLV>0 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.08 | 74 | -0.0155 | -80.18 | 45/29 | 0.5862 |
| 0.1 | 66 | -0.0097 | -47.5 | 39/27 | 0.5417 |
| 0.12 | 56 | 0.0344 | 151.25 | 32/24 | 0.5 |
| 0.14 | 45 | 0.0353 | 129.53 | 24/21 | 0.5833 |
| 0.16 | 33 | 0.0969 | 289.46 | 15/18 | 0.75 |
| 0.18 | 27 | 0.1652 | 437.82 | 13/14 | 0.7143 |
| 0.2 | 22 | 0.137 | 300.51 | 10/12 | 0.6 |

## Asymmetric floor grid (best ROI, n≥25)

| Over floor | Under floor | n | ROI | PnL | CLV>0 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.18 | 0.12 | 37 | 0.1851 | 592.2 | 0.6 |
| 0.16 | 0.12 | 39 | 0.1788 | 589.21 | 0.6 |
| 0.18 | 0.14 | 34 | 0.1422 | 427.86 | 0.75 |
| 0.16 | 0.14 | 36 | 0.1369 | 424.87 | 0.75 |
| 0.18 | 0.1 | 40 | 0.1347 | 450.18 | 0.5833 |
| 0.16 | 0.1 | 42 | 0.1301 | 447.19 | 0.5833 |
| 0.14 | 0.12 | 48 | 0.0761 | 293.87 | 0.5 |
| 0.14 | 0.1 | 51 | 0.038 | 151.85 | 0.5 |

## Line × side (KING)

| Line | Side | n | ROI | WR | CLV>0 | PnL |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 2.5 | over | 4 | -1.0 | 0.0 | None | -245.43 |
| 3.5 | over | 17 | -0.0594 | 0.4706 | 0.5714 | -77.67 |
| 3.5 | under | 3 | 0.656 | 0.6667 | 1.0 | 117.18 |
| 4.5 | over | 18 | -0.4086 | 0.3333 | 0.7778 | -422.25 |
| 4.5 | under | 10 | 0.4001 | 0.7 | 0.0 | 258.63 |
| 5.5 | over | 4 | -0.07 | 0.5 | 0.5 | -17.3 |
| 5.5 | under | 7 | 0.476 | 0.7143 | 0.5 | 267.62 |
| 6.5 | over | 2 | 0.2466 | 0.5 | 0.0 | 32.17 |
| 6.5 | under | 4 | -0.1222 | 0.5 | 0.3333 | -49.16 |
| 7.5 | under | 2 | 0.0177 | 0.5 | 1.0 | 4.1 |
| 8.5 | under | 3 | 0.2639 | 0.6667 | None | 51.92 |

## Over-line veto sensitivity

| Veto over lines | n | ROI | PnL | CLV>0 |
| --- | ---: | ---: | ---: | ---: |
| [4.5] | 56 | 0.0825 | 342.07 | 0.5 |
| [3.5, 4.5] | 39 | 0.1478 | 419.73 | 0.4615 |
| [2.5, 3.5, 4.5] | 35 | 0.2563 | 665.16 | 0.4615 |
| [4.5, 5.5] | 52 | 0.0921 | 359.37 | 0.5 |

## High-|edge| overs

```json
[
  {
    "abs_edge_min": 0.12,
    "n": 32,
    "roi": -0.2702,
    "win_rate": 0.3438
  },
  {
    "abs_edge_min": 0.14,
    "n": 24,
    "roi": -0.2707,
    "win_rate": 0.3333
  },
  {
    "abs_edge_min": 0.16,
    "n": 15,
    "roi": -0.1603,
    "win_rate": 0.4
  },
  {
    "abs_edge_min": 0.18,
    "n": 13,
    "roi": -0.1706,
    "win_rate": 0.3846
  },
  {
    "abs_edge_min": 0.2,
    "n": 10,
    "roi": -0.1579,
    "win_rate": 0.4
  }
]
```

## CLV ↔ outcome

```json
{
  "clv_vs_win_spearman": {
    "r": -0.0587,
    "p": 0.7622,
    "n": 29
  },
  "clv_vs_bet_roi_spearman": {
    "r": -0.0287,
    "p": 0.8824,
    "n": 29
  },
  "over_when_clv_gt0": {
    "n": 12,
    "roi": 0.1951
  },
  "over_when_clv_le0": {
    "n": 7,
    "roi": -0.6796
  },
  "under_when_clv_gt0": {
    "n": 5,
    "roi": -0.7841
  },
  "under_when_clv_le0": {
    "n": 5,
    "roi": 0.1061
  }
}
```

## Reliability bins

```json
{
  "all": [
    {
      "bin": 1,
      "n": 18,
      "mean_p_model": 0.5591,
      "hit_rate": 0.4444,
      "gap_hit_minus_p": -0.1146,
      "roi": -0.0368
    },
    {
      "bin": 2,
      "n": 21,
      "mean_p_model": 0.6324,
      "hit_rate": 0.4762,
      "gap_hit_minus_p": -0.1562,
      "roi": -0.0722
    },
    {
      "bin": 3,
      "n": 16,
      "mean_p_model": 0.6733,
      "hit_rate": 0.5,
      "gap_hit_minus_p": -0.1733,
      "roi": 0.0014
    },
    {
      "bin": 4,
      "n": 19,
      "mean_p_model": 0.7725,
      "hit_rate": 0.5263,
      "gap_hit_minus_p": -0.2461,
      "roi": 0.0249
    }
  ],
  "over": [
    {
      "bin": 1,
      "n": 11,
      "mean_p_model": 0.5548,
      "hit_rate": 0.3636,
      "gap_hit_minus_p": -0.1912,
      "roi": -0.246
    },
    {
      "bin": 2,
      "n": 14,
      "mean_p_model": 0.6357,
      "hit_rate": 0.4286,
      "gap_hit_minus_p": -0.2071,
      "roi": -0.1073
    },
    {
      "bin": 3,
      "n": 8,
      "mean_p_model": 0.6556,
      "hit_rate": 0.5,
      "gap_hit_minus_p": -0.1556,
      "roi": 0.0578
    },
    {
      "bin": 4,
      "n": 12,
      "mean_p_model": 0.7521,
      "hit_rate": 0.25,
      "gap_hit_minus_p": -0.5021,
      "roi": -0.5161
    }
  ],
  "under": [
    {
      "bin": 1,
      "n": 6,
      "mean_p_model": 0.5646,
      "hit_rate": 0.5,
      "gap_hit_minus_p": -0.0646,
      "roi": 0.0486
    },
    {
      "bin": 2,
      "n": 8,
      "mean_p_model": 0.6192,
      "hit_rate": 0.625,
      "gap_hit_minus_p": 0.0058,
      "roi": 0.1571
    },
    {
      "bin": 3,
      "n": 7,
      "mean_p_model": 0.7024,
      "hit_rate": 0.7143,
      "gap_hit_minus_p": 0.0119,
      "roi": 0.5182
    },
    {
      "bin": 4,
      "n": 8,
      "mean_p_model": 0.7828,
      "hit_rate": 0.75,
      "gap_hit_minus_p": -0.0328,
      "roi": 0.3057
    }
  ]
}
```

## Brier skill vs market

```json
{
  "all": {
    "n": 74,
    "brier_model": 0.27926,
    "brier_market": 0.25099,
    "skill_vs_market": -0.11262
  },
  "over": {
    "n": 45,
    "brier_model": 0.32246,
    "brier_market": 0.25221,
    "skill_vs_market": -0.27854
  },
  "under": {
    "n": 29,
    "brier_model": 0.21223,
    "brier_market": 0.2491,
    "skill_vs_market": 0.14804
  }
}
```

## Adjustment principles (still not live edits)

1. No universal floor raise to fix overs if edge↔ROI on overs is flat/negative.
2. Side-aware + line-aware gates beat one knobs-for-all floor.
3. Optimize ROI/PnL and CLV jointly; do not buy a one-week ROI spike with CLV collapse.
4. Recalibrate only under a pre-registered split that excludes this eval window.
5. Re-run weekly; promote only under interim stance gates.

JSON: `artifacts/odds_log/postfreeze_deep_diagnosis_20260901.json`

---

<!-- section 2/6 from postfreeze_king_profile_metrics_2026-09-01.md (merged 2026-09-17, content intact) -->

# Post-freeze KING-profile metrics (2026-09-01)

**Companion to:** `ssac27_audit_pack_2026-09-01.md`  
**Ensemble:** `0.60 production_sparse72_monotone + 0.40 production_final58_consensus` (`production/ops/live_krate_ensemble.json`)  
**Freeze:** `KING_PROFILE_AUG2026` @ `2026-08-21T16:10:00Z`  
**Lane definition:** deduped settled ledger rows with `game_date > 2026-08-21` **and** `passes_floor == True` (operational tickets with stake &gt; 0 under the live floor gate).

## Headline (honest)

| Lane | n | ROI | Win rate | CLV mean (pp) | CLV &gt;0 share | Date span |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| **Post-freeze KING floor** | **74** | **−1.55%** | 48.6% | +1.59 | 58.6% (n_clv=29) | 2026-08-22 → 2026-08-31 |
| Post-freeze KING · over | 45 | −24.6% | 37.8% | +0.58 | 63.2% (n=19) | same |
| Post-freeze KING · under | 29 | +29.3% | 65.5% | +3.51 | 50.0% (n=10) | same |
| Pre-freeze policy-search window · floor (context) | 172 | +2.56% | 50.0% | +0.75 | 58.5% (n=123) | 2026-07-30 → 2026-08-17 |

Source machine JSON (local/gitignored artifacts): `artifacts/odds_log/postfreeze_king_profile_metrics_20260901.json`.

## What this means

1. There **is** a real post-freeze sample now (n=74 KING-floor tickets over ~10 days) — larger than the demoted n=26 search lane, still short of DSR power targets (~98 / ~147).
2. Aggregate post-freeze ROI is **slightly negative**. Do **not** replace the demoted 26-bet ROI story with a claim of validated edge.
3. Side asymmetry dominates: **unders carry, overs bleed**. Any portfolio claim that ignores side is misleading.
4. CLV on the thin post-freeze CLV-available subset is mildly positive (~59% beat-close) — interesting, not conclusive (`building_sample`).
5. Broader floor-calibration tables that start at `2026-07-31` **mix pre- and post-freeze days** and must not be labeled “post-freeze OOS.”

## Watch-outs

- `passes_floor==False` rows often have `stake==0` (logged candidates, not bet). Always filter stake&gt;0 / passes_floor for money metrics.
- Deduped vs raw still matters for PnL.
- Freeze-day `2026-08-21` itself is excluded from the strict post lane (policy locked mid-day).
- Re-run this extract after each settle week; do not freeze these point estimates into the abstract as “edge.”

---

<!-- section 3/6 from interim_postfreeze_ops_stance_2026-09-01.md (merged 2026-09-17, content intact) -->

# Interim Post-Freeze Ops Stance

**Dated:** 2026-09-01  
**Status:** **SUPERSEDED for live ops** — 4.5-over hard veto + soft probation were **promoted** 2026-09-01 (`postfreeze_pack_2026-09-01.md`). Keep this file as the pre-promote shadow rationale only.  
**What to do next:** [`docs/EXECUTION_BACKLOG.md`](../../EXECUTION_BACKLOG.md) (Session Snapshot). Do not treat shadow-only rows below as current live instructions.  
**Evidence:** `docs/reference/reports/postfreeze_pack_2026-09-01.md` + shadow extract `docs/reference/reports/postfreeze_pack_2026-09-01.md`.

## What we believe right now

1. Post-freeze KING floor tickets (n=74, 2026-08-22→08-31) are slightly red in aggregate (**ROI ≈ −1.55%**).
2. Side asymmetry dominates: **overs ≈ −24.6% (n=45)** vs **unders ≈ +29.3% (n=29)**.
3. Line hot spot: **4.5 overs** are the clearest bleed (~n=18, ROI ≈ −41%, WR ≈ 33%).
4. Mild positive CLV on a thin subset does **not** authorize stake-up or a claimed edge.
5. Mixed pre/post floor-calibration tables are **contaminated** for OOS floor picking.

## Interim rules (shadow until promoted)

| Rule | Action | Live KING? |
| --- | --- | --- |
| Stake | Flat — no size-up on unders’ short heater | Already flat; keep |
| 4.5 overs | **Hard veto** in shadow lane `veto_4_5_over` | Not applied live yet |
| 2.5 / 3.5 overs | **Probation** (track; candidate veto in `veto_low_line_overs`) | Not applied live yet |
| Over floor | Shadow raise to **0.16** (`asym_over16_under12`) while under stays **0.12** | Not applied live yet |
| Under floor | Keep **0.12** — do not ease on 10-day luck | Unchanged |
| Calibration | No recalibration on the post-freeze window | Unchanged |
| Blend / champion | No swap without Item 9 sign-off | Unchanged |

## Promotion gates (shadow → live)

Promote an asymmetric / veto rule into live config only if **all** hold on a pre-registered expanding post-freeze window:

1. Trailing sample: **≥ 3 weeks post-freeze** *or* **≥ 40** tickets under the candidate gate.
2. Candidate ROI **≥** status-quo KING ROI on the same dates (preferably ≥ 0).
3. Full-cohort CLV beat-close on the gated set **≥ 0.52** (or no material regression vs status quo if CLV n is thin).
4. Explicit user sign-off to edit `KING_PROFILE` / live floors (Standing Rules).

Until then: score candidates with `production/ops/run_shadow_asymmetric_policy.py`; do not silent-edit production.

## Paper / communication

- Null / placebo lanes: **illustrative / non-claim** (`§8.2.2`).
- DSR on N=5161: **policy-search selection diagnosis**, not post-freeze edge proof.
- Post-freeze table: honest ops sample, **not** a validated edge.

## Shadow results (executed 2026-09-01; real KING stakes unless noted)

| Lane | n | ROI | Notes |
| --- | ---: | ---: | --- |
| Status quo KING floor | 74 | −1.55% | Live gate, unchanged |
| Veto 4.5 overs | 56 | **+8.25%** | Preferred first candidate |
| Veto low-line overs (2.5/3.5/4.5) | 35 | +25.6% | Higher ROI, thinner / learning cost |
| Asym over≥0.16 / under≥0.12 | 58 | +10.6% | May include stake-imputed candidates |
| Asym + veto 4.5 | 53 | +14.0% | Combined shadow |

Brier skill vs market (status quo): overs **−0.28**, unders **+0.15**, overall **−0.11**. Detail: `docs/reference/reports/postfreeze_pack_2026-09-01.md`.

## Next review

Re-run shadow script after each settle week. Revisit this stance when promotion gates trip or when real-ticket ledger (Item 6/12) reaches usable n.

---

<!-- section 4/6 from interim_live_skip_rules_2026-09-01.md (merged 2026-09-17, content intact) -->

# Interim Live Skip Rules

**Dated:** 2026-09-01  
**Status:** **PROMOTED to live policy** (see `postfreeze_pack_2026-09-01.md`). Paper/`KING` freeze notes updated; quality gate enforces hard veto.  
**Further instructions / what next:** [`docs/EXECUTION_BACKLOG.md`](../../EXECUTION_BACKLOG.md) — this report is the rule card, not the work queue.  
**Evidence:** post-freeze KING ledger + weekly settle pack.

## Hard rule (do this)

| Bet | Action |
| --- | --- |
| **4.5 over** | **Do not bet.** |

Post-freeze: 4.5 overs n=18 ROI ≈ **−41%** WR 33%. Removing them flips status-quo −1.55% → **+8.25%** on the same window. All-time KING floor: 4.5 overs n=48 ROI ≈ **−27%**.

## Soft probation (judgment OK)

| Bet | Action |
| --- | --- |
| 2.5 over | Prefer skip when unsure (tiny n, red). Not a hard system veto yet. |
| 3.5 over | Caution / half-size OK; do **not** auto-veto (bleed milder than 4.5). |
| 5.5 over | Watch list (all-time ugly, post-freeze thin). Discretionary skip fine. |

## Keep betting

- **Unders** at current floor / flat stake (including **4.5 unders** — those are not the drag).
- Mid/high overs without a hard veto, subject to normal edge floor.

## Explicit non-rules

- No book-quality filter (books used for lines; usually synced).
- No live calibration swap.
- No stake-up on unders.
- No hard veto of *all* ≤4.5 overs unless weekly pack + bootstrap still favor it after more settles.

## Logging

Log every **real** ticket (and every hard skip of a 4.5 over that would have been KING) into `real_bets` / notes so paper ≠ cash stays honest. Checklist: `docs/reference/reports/real_bets_logging_checklist.md`.

## Review

Re-run weekly:

```bash
python production/ops/run_weekly_policy_settle_pack.py
```

Promote anything beyond the 4.5-over hard skip only with expanding n + bootstrap CI not dominated by status quo + explicit sign-off.

---

<!-- section 5/6 from live_policy_promotion_2026-09-01.md (merged 2026-09-17, content intact) -->

# Live Policy Promotion — 2026-09-01

**Status:** PROMOTED (user sign-off 2026-09-01)  
**Scope:** decision policy only — **no** calibration map swap, **no** champion→monotone, **no** book-quality filter.  
**Master work-state after this promote:** [`docs/EXECUTION_BACKLOG.md`](../../EXECUTION_BACKLOG.md) (FORWARD / DEFERRED / Waiting on user).

## What went live

| Rule | Mechanism | Location |
| --- | --- | --- |
| **Hard veto `over @ 4.5`** | Quality-gate HOLD + scorer `policy_reason=veto_4_5_over` | `production/ops/kpi_policy.json` → `quality_gate.rules.side_line_vetoes`; `src/Python/odds_board.py` |
| Soft probation `over @ 2.5 / 3.5` | `probation_edge_floor=0.18` + line floor 3.5→0.18 | kpi_policy + `line_floor_policy.json` |
| Unders (incl. 4.5 under) | Unchanged | Keep betting under existing floors |
| Book-quality filter | **WONT_DO** | Explicit non-goal |
| Calibration / monotone | Unchanged | Deferred |

## Evidence anchors

- Post-freeze KING: status quo ROI −1.55% → veto 4.5 overs **+8.25%** (`weekly_policy_settle_pack_latest`).
- All-time KING floor: 4.5 overs ≈ −27% ROI; rest ≈ +4.5%.
- Bootstrap still wide (few date blocks) — treat as **risk control**, keep weekly settle pack running.

## Operator checklist

1. Follow BET board: 4.5 overs should show **HOLD** / skip with `veto_4_5_over`.
2. Log real tickets + hard skips: `docs/reference/reports/real_bets_logging_checklist.md`.
3. Weekly: `python production/ops/run_weekly_policy_settle_pack.py`.

## Related docs

- Interim skip rules (now promoted): `postfreeze_pack_2026-09-01.md`
- Prior shadow stance: `postfreeze_pack_2026-09-01.md`
- Settle pack report: `weekly_policy_settle_pack_latest.md`

## Explicitly not promoted

- Live recalibration overlay / granular open calib challenger
- Hard veto of all ≤3.5 overs
- Asymmetric live over floor as sole gate (tracked in shadow lanes)
- Book-quality filters

---

<!-- section 6/6 from shadow_asymmetric_policy_2026-09-01.md (merged 2026-09-17, content intact) -->

# Shadow asymmetric / line-veto policy (2026-09-01)

Post-freeze counterfactuals vs locked KING floor. **No live config change.**

Producer: `production/ops/run_shadow_asymmetric_policy.py`
Stance: `docs/reference/reports/postfreeze_pack_2026-09-01.md`

## Policy lanes

| Lane | n | ROI | WR | CLV mean | CLV>0 | n_over/under |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `status_quo_king_floor` | 74 | -0.0155 | 0.4865 | 0.0159 | 0.5862 | 45/29 |
| `veto_4_5_over` | 56 | 0.0825 | 0.5357 | 0.0191 | 0.5 | 27/29 |
| `veto_low_line_overs` | 35 | 0.2563 | 0.6286 | 0.0272 | 0.4615 | 6/29 |
| `asym_over16_under12` | 58 | 0.1056 | 0.569 | 0.0238 | 0.6154 | 20/38 |
| `asym16_plus_veto_4_5` | 53 | 0.1399 | 0.5849 | 0.0246 | 0.5455 | 15/38 |

## Status-quo side × line (KING floor)

| Line | Side | n | ROI | WR | CLV mean | CLV n |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 2.5 | over | 4 | -1.0 | 0.0 | None | 0 |
| 3.5 | over | 17 | -0.0594 | 0.4706 | 0.0043 | 7 |
| 3.5 | under | 3 | 0.656 | 0.6667 | 0.0895 | 1 |
| 4.5 | over | 18 | -0.4086 | 0.3333 | 0.0087 | 9 |
| 4.5 | under | 10 | 0.4001 | 0.7 | -0.0105 | 1 |
| 5.5 | over | 4 | -0.07 | 0.5 | 0.0012 | 2 |
| 5.5 | under | 7 | 0.476 | 0.7143 | 0.0351 | 4 |
| 6.5 | over | 2 | 0.2466 | 0.5 | 0.0 | 1 |
| 6.5 | under | 4 | -0.1222 | 0.5 | -0.0094 | 3 |
| 7.5 | under | 2 | 0.0177 | 0.5 | 0.1594 | 1 |
| 8.5 | under | 3 | 0.2639 | 0.6667 | None | 0 |

## Brier skill vs market (status quo)

```json
{
  "status_quo": {
    "available": true,
    "n": 74,
    "brier_model": 0.27926,
    "brier_market": 0.25099,
    "brier_skill_vs_market": -0.11262
  },
  "status_quo_over": {
    "available": true,
    "n": 45,
    "brier_model": 0.32246,
    "brier_market": 0.25221,
    "brier_skill_vs_market": -0.27854
  },
  "status_quo_under": {
    "available": true,
    "n": 29,
    "brier_model": 0.21223,
    "brier_market": 0.2491,
    "brier_skill_vs_market": 0.14804
  }
}
```

## Read carefully

- `status_quo` / `veto_*` use real KING `passes_floor` stakes.
- `asym_*` may impute stake on non-bet candidates that clear the asymmetric edge gate — treat as directional shadow, not bankroll truth.
- Promote only under gates in the interim stance doc.

JSON: `artifacts/odds_log/shadow_asymmetric_policy_20260901.json`

