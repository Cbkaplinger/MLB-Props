# PROJECT_STATE — one-screen current state

**Date:** 2026-10-19. Point-in-time summary; `docs/EXECUTION_BACKLOG.md`
remains the live work queue and wins on conflicts.

## Champion (production)

Legacy production game-level model — **frozen**. Retrain path closed;
no live-path changes; dashboard parked.

## Active work

- **PA/H3 architecture development** — ongoing (per-PA / H3 projected-state
  line of work; see `docs/EXECUTION_BACKLOG.md`).
- **Market-eval v2 implementation** — implementation pinned at
  `02ce162f119208b762edf1fd690edd5e7ee9b8ea`
  (`research/offseason_2026/market_eval/`): prep v2 (outcome-free,
  write-once) + gated scorer + 28 synthetic tests + spec docs. The pin is
  preserved unchanged; review docs are a docs-only commit on top.
- **Market-eval lane (F-6):** F-6 (C3.3 confirmation-exclusion) COMPLETED:
  one validated population assignment in `run_score` (fail-loud on
  unknown/null block labels), dev-only headline, serialized confirmation
  metrics (`confirm_metrics.json` + `bootstrap.json` `confirm`),
  per-population ROI/count summaries, registered in the card as C3.7, and
  pinned by a run_score-invoking regression
  (`tests/test_f6_confirmation_separation.py`; the earlier
  `tests/test_f6_confirmation_exclusion.py` and `_slate_bootstrap`
  known-answer tests remain as helper-level coverage). overnight-p2
  `pooled_comparison.json` previously verified to exclude confirm_2025H2
  from pooling. Holding for Chat 2 review.
- **Scoring status (2026-10-15):** canonical scoring run EXECUTED once at
  `108d5ba9` (2026-10-14 23:44 local), after the stale lake scorer
  (`457991d8...`) was replaced pre-run with the reviewed committed bytes
  (blob `99db556c...f4e31`, sha256 `c2745980...4c6c5`, byte-identity
  verified). Outputs preserved write-once in
  `market-eval-v1\outputs\score_v2\`; all file hashes re-verified
  (CHAT2_HANDOFF.md, copied byte-identical to
  `research/offseason_2026/market_eval/CHAT2_HANDOFF.md`; EXECUTED-RUN
  record in EXPERIMENT_CARD.md, both copies). Results are PRELIMINARY
  pending Chat 2 integrity review (reviewer verdict PENDING). Binding
  result labels: dev headline (25,978 rows) = pooled Tier A + Tier B;
  Tier A = STRICT-CLOCK lane; Tier B sensitivity-only (2024 Tier B uses
  proxy clocks; no strict execution-timing claims beyond that
  provenance). No authorized reruns, model promotion, or production
  changes. The 17:15 accidental run (C3.6) remains UNRESOLVED.

## PRs and reviewed SHAs

| Item | State |
| --- | --- |
| PR #1 (PA remediation review) | MERGED at `72d7923` |
| PR #2 (paired slate-date uncertainty repair) | OPEN (non-draft) |
| Reviewed SHA `6567c51` | backlog/docs review snapshot reviewed by Chat 2 |
| Pinned snapshot `02ce162f` | market-eval v2 implementation, byte-identical to lake sources, 28 tests pass on committed bytes |
| Branch `research/market-eval-v2` (PR #3) | published review branch: pin + docs-only follow-up commits; DRAFT research-only PR |
| PR #12 (hygiene checker) | MERGED at `d57ba17f57c8c932411a9e5be885a3de69d25411` (2026-10-19) |
| PR #13 (governance/cleanup-skills) | review PASS at head `5571b338b4a4e1b037ca78a38873d857fae7fcc9` (CI green, MERGEABLE); MERGED 2026-10-19; post-merge `origin/main` = `dd3318f0492ebbd41ae4e813c43d8416fd5b134f` |

## Completed-item canonical pointers (2026-10-19)

- **PR #12 merged** — canonical merge SHA
  `d57ba17f57c8c932411a9e5be885a3de69d25411` on `origin/main`.
- **Directory mapping resolved** — upstream BF fit, the failed count
  attempt, and the count recovery run are three distinct directories with
  distinct provenance; the earlier conflated account is superseded by the
  closeout corrections below.
- **Recovery inventory** — 21 files (not 11); the audit addition is
  recorded lake-only in the CLOSEOUT_CORRECTIONS.md sibling (see the
  historical evidence section below for hashes and withdrawal detail).
- **Count recovery analysis independently reproduced** — accepted
  WITH LIMITATION (package finalization failed; computation complete).
- **Metric-context scorecard published** — RECOUNT scorecard committed at
  `8f8c0f5de53b427e73190aad5af7f7ce300b745f` (compact count-lane record:
  target K/start, support 0..22 exact + >=23 absorbing, natural log,
  thresholds K>=6/8/10/12, B0/B1 count-RPS + log score + threshold
  Briers + realized event rates; no count-lane prior-data predictor
  exists and PA-lane 0.520552 is not cross-layer comparable; market
  de-vig Brier 0.4469 vs H3 0.4684 / LOG5 0.4663 on matched contracts).
- **Market review CLOSED** — the de-vig market dominates both PA arms at
  matched contracts (de-vig Brier 0.4469 < H3 0.4684 < LOG5 0.4663);
  market-eval lane conclusions are final for this round.

## Next action

Select ONE next scientific question from the existing backlog/roadmap,
conditioned on the closed market result (de-vig market dominates both PA
arms at matched contracts). Candidates: BF distributional challengers
(beta-binomial v2 gate), pitch/arsenal feature blocks for the PA lane,
projected-batter PA-probability extension scoring, or the
count-aggregation comparison (pbar vs Poisson-binomial). Selection only;
no execution until owner authorizes.

## Closeout corrections (2026-10-19, lake-only)

Scientific closeout corrections for the count_b1_recovery_v1 recovery run are
recorded lake-only at
`C:\Users\ckaplinger\MLB-Props-Research\bf-2026-eval-v1-outputs\CLOSEOUT_CORRECTIONS.md`
(SIBLING of the frozen run dir; nothing inside `count_b1_recovery_v1\` was
modified, moved, or deleted). SHA-256 of the file at write time:
`b88dae06...` for RECONCILIATION_CHAT2.md is recorded inside it; the closeout
file itself records: (a) RECONCILIATION_CHAT2.md authorship/timing/hash and the
write-once boundary note; (b) WITHDRAWAL of the earlier 11-file / missing-PMF
account (actual inventory = 21 files; finalization defect = two misnamed pooled
filenames + missing run_manifest.json; no analytical evidence missing);
(c) accepted conclusion: B1 improves the registered development-fold
BF/workload count-distribution endpoint vs B0 by -0.02818 count-RPS
[-0.03656, -0.01980]; computation complete; package finalization failed;
acceptance WITH LIMITATION; no production promotion or betting-performance
claim.

## Historical: Chat 2 review scope (closed 2026-10-19)

The Chat 2 independent integrity review of the executed canonical scoring
run (CHAT2_HANDOFF.md + the EXECUTED-RUN record in EXPERIMENT_CARD.md),
including the 17:15 incident blinding question (C3.6), has been resolved:
the market review is CLOSED per the completed-item pointers above
(de-vig market dominates both PA arms at matched contracts). The evidence
records below are preserved as-is; the PRELIMINARY label on the scoring
run is superseded by the closed review outcome for this round.
