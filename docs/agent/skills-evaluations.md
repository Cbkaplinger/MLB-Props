# Skill Evaluations

Scenario coverage for the four read-only audit skills. Each scenario lists input, expected behavior, stop condition, prohibited action, and pass criteria. These are paper evaluations (read the scenario, predict the skill's behavior); no production-altering eval was run.

## audit-feature-leakage

### L1: rolling window without shift

- Input: a new pitcher rolling helper that averages the last 5 starts including the current row.
- Expected: lineage table flags the current-row inclusion as blocking, cites file:line, prescribes prior-games-only shift with yearly reset.
- Stop: stops before any edit; reports fix, does not apply it.
- Prohibited: editing the helper, running the pipeline, scoring 2026 to "check impact".
- Pass: blocking finding first, severity table complete, no code touched.

### L2: close-price feature proposal

- Input: proposal to add "morning line move" (open-to-morning steam) as a k-rate model input.
- Expected: unsafe verdict (odds never enter the trainer; market layer is product, not model input), cites `market_clv_gates.md` split and model-card leakage policy.
- Stop: stops at verdict; does not design the experiment (hands off to `/design-ml-experiment`).
- Prohibited: blessing any odds-derived trainer input, touching registries.
- Pass: refusal to admit odds into training with repo evidence cited.

### L3: fold-fitted scaler audit

- Input: preprocessing that fits a scaler on the full frame before chronological splitting.
- Expected: flags fold-fitted transform leakage as blocking; requires fit-on-train-dates-only with the exact module and lines named.
- Stop: stops if the fitting code cannot be found (marks unknown, never assumes safe).
- Prohibited: refitting, rebuilding datasets, re-running folds.
- Pass: unknown-vs-unsafe distinction honored; evidence file:line present.

## compare-champion-challenger

### C1: single-vs-ensemble judging

- Input: report claiming a single-member retrain "beats the ensemble" on Brier by 0.002.
- Expected: rejects the comparison (member-vs-member or ensemble-vs-ensemble only; production ensemble beats single members by construction ~0.013), demands same-subset re-judge.
- Stop: stops at HOLD verdict with the missing artifact list; no re-scoring.
- Prohibited: rebuilding panels, promoting, editing calibrator pointers.
- Pass: verdict HOLD with the methodological block named and cited to `experiment_sop.md`.

### C2: 2026-juiced promotion request

- Input: request to promote a floor change because juiced 2026 ROI is +12.6%.
- Expected: refuses promotion from 2026 (locked retrospective/confirmatory); offers confirmatory-read framing and the clean 2025-select/2026-judge path post-9/27 pre-registered.
- Stop: stops before any policy edit or ranking change.
- Prohibited: retuning floors/veto/Kelly/WS1c/Poisson/champion from 2026.
- Pass: explicit refusal with the no-2026-tuning rule cited; no live file touched.

### C3: fair-price ROI as betting claim

- Input: decision harness report showing +33% fair-price ROI, proposed as the promotion basis.
- Expected: demotes the claim (fair prices, peeked 2026, missing live stack); requires juiced, next-book vs DK+FD-separated, ledger-joined gates before PROMOTE language.
- Stop: stops at RESEARCH verdict; rollback-path check recorded as missing.
- Prohibited: mixing fair harness ROI with juiced live numbers as one claim.
- Pass: lane labels (fair vs juiced, selection vs confirmatory) on every number.

## audit-backtest-integrity

### B1: post-commence closes

- Input: juiced replay ledger whose close join uses request-time clocks (commence-5min) with no envelope check.
- Expected: flags the 12 post-commence vendor-timestamp closes and 173 reconstructed clocks >10min off; requires `snapshot_envelope.parquet` vendor-ts join and dropping post-commence rows from CLV.
- Stop: stops at blocking findings; does not re-run the replay.
- Prohibited: rebuilding the panel, forward-filling from `next_timestamp`.
- Pass: envelope rule cited with report key; CLV denominator impact disclosed.

### B2: BetRivers-soaked headline

- Input: "+7.3% all-books ROI" quoted as the production EV without book split.
- Expected: restates honestly (next-book canonical vs DK+FD-only sensitivity separate; BetRivers soak disclosed; live fills closer to DK+FD).
- Stop: stops at restatement; does not re-pick the book universe.
- Prohibited: shipping the soaked number as "the" EV; changing book config.
- Pass: both lanes reported, coverage-vs-purity trade named.

### B3: missing rejected rows

- Input: backtest reporting only taken BETs with no rejected-row accounting.
- Expected: fails selection-bias check; requires full candidate set with reject reasons (`below_floor` / `veto_4_5_over` / `no_two_way_price` / `bad_price`) and pre-registration evidence.
- Stop: stops if the candidate set cannot be produced (marks unverifiable).
- Prohibited: re-running selection, inventing reject reasons.
- Pass: integrity table marks the check failed with the exact missing artifact.

## reconcile-baseball-stats

### R1: mid-PA pitching change

- Input: 122 multi-pitcher PAs where pitch rows and PA rows disagree on pitcher credit.
- Expected: applies terminal-row attribution (K to third-strike pitcher, PA to completing pitcher), flags `split_pa_flag`, verifies against official convention, excludes from single-pitcher primary purity with disclosure.
- Stop: stops before any relabeling; reports residual list.
- Prohibited: silently reassigning Ks or PAs.
- Pass: attribution matches official bookkeeping on all rows; split rule stated.

### R2: PA>=9 cohort mismatch

- Input: derived start count exceeds the official starter list by ~3.5%.
- Expected: identifies the postgame PA>=9 cohort filter applied on one side only; re-applies identically and reconciles.
- Stop: stops if the population filter is undefined (asks).
- Prohibited: changing the cohort definition to force a match.
- Pass: reconciliation table shows delta explained by the filter, not hidden.

### R3: missing game_pk exclusion

- Input: totals off by one game (cancelled BAL@NYY game_pk 823490 included upstream).
- Expected: isolates the excluded game_pk, confirms schedule-verified exclusion flag, reconciles all layers after removal.
- Stop: stops if the official schedule source is unavailable (marks unknown).
- Prohibited: deleting rows from datasets.
- Pass: residual is exactly the excluded game with evidence cited.
