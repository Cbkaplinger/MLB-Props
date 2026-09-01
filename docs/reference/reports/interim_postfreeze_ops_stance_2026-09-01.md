# Interim Post-Freeze Ops Stance

**Dated:** 2026-09-01  
**Status:** ACTIVE interim guidance — **shadow / paper first**; live `KING_PROFILE` / floors / staking **unchanged** until explicit promotion sign-off.  
**Evidence:** `docs/reference/reports/postfreeze_king_profile_metrics_2026-09-01.md` + shadow extract `docs/reference/reports/shadow_asymmetric_policy_2026-09-01.md`.

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

Brier skill vs market (status quo): overs **−0.28**, unders **+0.15**, overall **−0.11**. Detail: `docs/reference/reports/shadow_asymmetric_policy_2026-09-01.md`.

## Next review

Re-run shadow script after each settle week. Revisit this stance when promotion gates trip or when real-ticket ledger (Item 6/12) reaches usable n.
