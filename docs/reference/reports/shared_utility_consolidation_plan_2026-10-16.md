# Shared-utility consolidation plan — 2026-10-16 (Chat 3, PLAN ONLY — no code consolidated)

Scope/method: function-definition dedup scan across all 406 tracked `.py` files;
def-name frequency (≥4 files), family attribution, and per-family caller class
(research-runner vs production vs scripts vs models). Base `origin/main` @
`1927c8c…`. Confidence: HIGH on counts; MEDIUM on semantic equivalence (signatures
compared at definition level, not full-body AST). **Strictly a plan.**

## The governing semantic finding

**Research runners are intentionally self-contained.** The 25 `sha256_file`
definitions and most `_fit_*`/`_metrics` families live in
`research/offseason_2026/**` and `models/**/research/**` — frozen-evidence
surfaces where byte-reproducible, dependency-light runners are a *convention*
(a shared lib would change runner identity over time and violate the
execution-identity discipline the program just enforced). **Consolidation of
frozen runners is prohibited.** The actionable surface is smaller and specific:

## Family inventory

| Family | Files | Surface | Verdict |
|---|---|---|---|
| `sha256_file` (+`sha`, `_sha256` variants) | 25 + 8 + 7 | ~40 file-local hashing helpers; mostly research runners; some in production/scripts | **consolidate non-frozen copies only** (below); research copies stay |
| `_fit_calibrator`, `_prob_metrics`, `_returns_per_dollar`, `_result_to_y` | 7/6/6/6 — **all in `production/ops/compare_*` + `build_policy_governance_report.py`** | the governance-script cluster | **highest-value consolidation target** — same-purpose governance scripts drifting apart |
| `_fit_tbf` (11), `_fit_lgbm` (9), `_lgbm` (8), `_load_wf` (8), `_load` (9) | models/research + `fit_prob_calibration.py` | frozen-era research + one production file | mostly frozen; verify per-file before any move |
| `brier` (8) | market_research + research | metric helper | candidate for one canonical metrics module |
| `run_diagnostic` (7) | research runners | frozen convention | keep |
| specialized hashes (`code_hash`, `eval_identity_hash`, `content_hash`, `hash_raw`, `ticket_set_hash`) | 1 each | distinct semantics, not variants | keep (document as distinct, not duplicates) |

## Consolidation plan (production/ops governance cluster first)

1. **Canonical candidate:** new `src/Python/governance_common.py` (or
   `production/ops/_common.py` — owner picks the home) holding
   `_fit_calibrator`, `_prob_metrics`, `_returns_per_dollar`, `_result_to_y`,
   `brier`, `sha256_file`.
2. **Migration order:** (a) diff the 4–7 copies per function to classify
   semantic equivalence vs true drift (drifted copies need a behavior decision
   BEFORE merging — the drift may be the point of each script); (b) extract
   identical bodies; (c) thin adapters where a script needs a variant; (d)
   retire file-local defs last.
3. **Compatibility shim:** not needed between sibling scripts (no external
   callers) — shim only if a test imports a script-local helper (check per
   function).
4. **Tests:** golden-value regression tests for each extracted function
   (frozen input → frozen output), run before and after extraction.
5. **Risk:** Medium — governance scripts feed promotion decisions; a silent
   behavior change during consolidation would be worse than the drift. Hence
   step (a) is a semantic gate, not a formality.
6. **Rollback:** one revert; scripts are sibling files with no data migration.
7. **Hashing helpers (non-frozen):** one `sha256_file` into the same common
   module; `hash_raw`/`ticket_set_hash` etc. stay in their domains.
8. **Import-cycle risk:** low — common module is leaf-level (stdlib only).
9. **Smallest PR:** extract exactly ONE function family (recommend
   `sha256_file` across production/ops + scripts first — lowest drift risk),
   then the governance cluster as its own PR.

## Explicit non-actions

No frozen research runner is edited; no `models/**/research` file moves; no
consolidation without the per-family semantic-diff gate; nothing executes until
the owner approves the first PR.
