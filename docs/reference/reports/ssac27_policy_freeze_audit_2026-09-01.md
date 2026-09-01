# SSAC27 Item 4 — Policy-Freeze vs Evaluation-Window Audit

**Date:** 2026-09-01  
**Verdict:** **FAIL — cannot draw an honest post-freeze evaluation line.**  
**Required action:** Reclassify the audited `n=26` ROI/Sharpe lane as **policy-search evidence**. Do not treat it as post-freeze out-of-sample deployment performance in headlines, abstracts, or resume claims.

---

## Question

Is the 26-bet lane's ROI/Sharpe valid as post-freeze evaluation? That requires:

1. deployment blend `0.60 sparse72_monotone / 0.40 final58`,
2. edge floor `0.12`,
3. isotonic transfer-calibration,

to be **frozen on a strict date**, with **all 26 bets posterior** to that freeze.

---

## Timeline (artifact + git backed)

| Event | Timestamp / span | Evidence |
| --- | --- | --- |
| 26-bet slate dates | **2026-07-30 → 2026-08-17** | `open_top3_transfer_bestfloor_picks_aug21_deduped_top3_from_dedupedsweep.csv` filtered `config=top3`, `best_floor=0.12` (`n=26`) |
| Manual replay generated | **2026-08-21T05:37:07Z** | `open_top3_transfer_manual_replay_aug21_deduped_top3_from_dedupedsweep.json` `generated_utc` |
| Model stems used by live blend | **2026-08-21 ~05:41** | `live_krate_ensemble.json` stems `..._20260821_0541*` |
| Live blend file committed | **2026-08-21 01:49:35 -0400** | git `8ad4681` — creates `production/ops/live_krate_ensemble.json` |
| Selection rule (explicit) | same commit | `"best_manual_roi_after_open_calibration_transfer_deduped"` |
| Isotonic calibrator | **2026-08-21_160723** | `artifacts/models/prob_calibration_isotonic_20260821_160723.*` |
| Declared freeze stamp | **2026-08-21T16:10:00Z** | `production/ops/kpi_policy.json` → `king_profile_freeze.frozen_utc` |
| Freeze block landed in git | **2026-08-27** | git `de942c3` adds `king_profile_freeze` to `kpi_policy.json` (stamp claims Aug 21; commit is Aug 27) |
| Edge floor `0.12` reaffirmed | **2026-08-06** (pre-lane end) | `docs/research/floor_freeze_log.md` — floor alone is earlier; blend+isotonic are not |

---

## Finding

**Every one of the 26 graded bets is dated before the declared freeze.**

- Last bet date: `2026-08-17`
- Freeze stamp: `2026-08-21T16:10:00Z`
- Gap: freeze is **4+ days after** the evaluation window ends

Worse than a simple timing miss: the live blend was **selected on** this lane's ROI. `live_krate_ensemble.json` records:

```text
selection_rule: best_manual_roi_after_open_calibration_transfer_deduped
```

So the 26-bet ROI/Sharpe is the **objective that chose the policy**, not an evaluation after the policy was locked.

Floor `0.12` was reaffirmed earlier (2026-08-06), but that does not rescue the lane: blend weights and isotonic transfer were chosen/fit on 2026-08-21 against this same search window.

---

## What this does *not* imply

- It does **not** invalidate leakage-safe modeling, chronological MAE lanes, or governance engineering.
- It does **not** say the 26-bet numbers are fabricated — they are real replay metrics on a real window.
- It **does** say they are the wrong *epistemic* class for “deployed post-freeze performance.”

---

## Required manuscript / messaging changes

1. Label the 26-bet ROI/Sharpe/PnL lane as **policy-search / pre-freeze selection evidence** everywhere it appears.
2. Strip ROI/Sharpe from abstract/resume *headline claims* of deployment success (numbers may remain only as search-window diagnostics with the FAIL label).
3. Keep DSR/PSR power discussion — it still correctly warns the sample is underpowered.
4. True post-freeze performance = bets with `game_date > 2026-08-21` (or strictly after `frozen_utc`) under the locked blend/floor/isotonic pointer. That lane is not yet the paper's audited 26.

---

## Resume-ready one-liner

Frozen production profile `KING_PROFILE_AUG2026` (2026-08-21): blend `0.60/0.40`, floor `0.12`, isotonic pointer locked. The previously cited 26-bet ROI/Sharpe window (2026-07-30–08-17) is **pre-freeze policy-search evidence**, not post-freeze OOS validation.
