# CORRECTION 1 — pa-aggregation contract (2026-10-09, linked correction)

> **Status: LINKED CORRECTION to `pa-aggregation-contract-2026-10-09.md` +
> Amendment 1.** Issued after the independent-review order. The original
> scored run (`pa-aggregation-abc-20261009_173155`) and its manifest are
> PRESERVED unchanged; this correction relabels and extends, it does not
> rewrite.

## 1. Baseline identity correction

The arm labeled "A — canonical I3b" is relabeled **"I1 scalar-rate/binomial
reference"**. Its construction is verified as the frozen kcount-integration
**I1** arm: expanding hazard BF PMFs (training-policy run, `pmfB_*`) x the
scalar `p_bar_l1` = the w=150 shrunk pitcher K rate (log5 against a
league-average batter collapses to the pitcher rate; pa-k label convention,
2022+2023 pre-origin pool) x `combine_count` binomial mixture. The retained
**I3b** research recipe (hazard BF PMF + binomial + log5 scalar, as scored
in the 2024 transfer) is a SEPARATE construction; this run does not claim
superiority over I3b and does not re-evaluate I3b. The reproduction gate
max-diff 0.00e+00 was against stored **I1** PMFs (`pkI1_*`), consistent
with this relabeling.

## 2. Denominator-attribution sensitivity (frozen before running)

On the SAME 4,46-row authorized historical cohort, identical BF PMFs:

- **A_v1** = `combine_count(bf_ext, p_v1)` where `p_v1` = the w=150 shrunk
  pitcher rate built from the EXACT `pa_completed_v1` priors used by B/C
  (v1 label convention, per-origin league rate).
- **Sensitivity family (separate from the original Holm family; its own
  Holm over exactly these 2 comparisons; original p-values never reused):
  {B−A_v1 (matched-denominator matchup sensitivity), A_v1−I1_ref
  (denominator effect)}**; seed 20261001, slate-date bootstrap 2000.
- Post-review development sensitivity label; not promotion evidence.
- Rate/league comparisons by origin/key reported alongside (pa-k vs v1).
- **Executed results (corr1 run 20261009_181757): B−A_v1 = −0.029221
  [−0.036118, −0.022232], p_adj 0.0010\*; A_v1−I1_ref = −0.003816
  [−0.008051, +0.000524], p_adj 0.078 n.s.**
- **League-rate comparison status: UNAVAILABLE.** `p_bar_l1` is the
  shrunk pitcher rate (the collapsed log5 point), NOT the historical
  league-rate series; the pa-k league rate is not recoverable from the
  eval artifacts as stored. The row-level pitcher-rate comparison
  (mean |gap| 0.00727, p90 0.01817, max 0.08258, 1,023/4,446 rows >0.01)
  is the only denominator comparison reported; the league-rate series
  stays marked unavailable unless recovered from the original source
  and contract.

## 3. Gates added (runner-enforced)

- B/C pre-collapse conditional-mean equality asserted per row for every BF
  support n with mass (tolerance 1e-9; fail loud).
- Conflicting duplicate lineup slots (same slot, different batter, same
  fetch) rejected BEFORE deduplication.
- Opposing-starter swap invariance test runnable at unit level.
- Debut (n_prior=0) and sparse-history (n_prior<150) slices reported.
- External input roots parameterized (--kc-dir/--bf-dir/--bf-training-dir).
- Exported prediction rows carry oracle/input-status flags
  (oracle_lineup=true, i1_ref source flag, lineup_status).

## 3b. Post-collapse residual accounting (clarification, nothing erased)

The original receipt reported per-row post-collapse |E_C − E_B| with
abs-max ≤ 1.8e-4 across all 4,446 real rows; the CORRECTION-1 test
observes a ~4e-8 mixture-mean residual on one synthetic row. These are
**different quantities over different populations, same unchanged code**:
the 1.8e-4 is the max over 4,446 real rows (large-n rows accumulate float
error across up to 60 mixture terms); 4e-8 is the single synthetic row.
Neither is gated by MEAN_TOL=1e-9, which applies to the per-support-n
pre-collapse identity `E[K|n] = Σ p_i(first n)` (exact). The post-collapse
residual remains a reported quantity (`xK_diff_CB`), not a gate; no
tolerance was changed to accommodate an observed discrepancy.

## 4. Output discipline

The corrected run writes to a NEW directory; the original run directory,
manifest, and predictions are untouched and remain linked here as the
pre-correction record.
