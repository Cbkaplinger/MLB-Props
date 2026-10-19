# Repository-scale duplication audit — 2026-10-16 (Chat 3, report-first)

Scope: all 809 tracked files at `origin/main` @ `1927c8c…`. Method: exact
duplicates by Git blob SHA across every file type; near-duplicates by
6-word-shingle Jaccard similarity within type families (markdown, Python
splitting tests from sources, JSON, notebook **code cells with outputs
stripped**, csv/yaml/toml/ps1), threshold 0.75, clusters ≤12 members; huge
data-JSON skipped for shingles. Confidence: HIGH on exact groups, MEDIUM-HIGH on
near-dup semantics (similarity ≠ intent — each cluster's intent assessed
individually). Full data: `duplication_audit.json` in session records.
**Nothing deleted, moved, or edited.**

## Headline findings

1. **Exact duplicates: 7 groups** — identical to the 2026-10-15 census; no new
   exact groups appeared.
2. **Near-duplicates: 27 pairs ≥0.75, clustering into 13 groups** — and the
   dominant pattern is systematic: **`*-draft.md` vs final prereg pairs**.
   The deletion ledger previously recorded 2 such pairs; the audit found **6**.
3. **Negative finding (valuable): zero near-duplicate Python code clusters** —
   `prune_artifacts.py` (122 vs 220 lines) and the two `odds_board.py` tools
   stay below threshold; the codebase has no copy-paste implementation debt at
   the 0.75 level. Code-consolidation work is NOT needed; the duplication risk
   is concentrated in documentation packets.

## Cluster ledger

| Cluster | Members | Max J | Semantics | Frozen status | Canonical | Recommended action | Risk | Validation |
|---|---|---|---|---|---|---|---|---|
| **Prereg draft/final pairs (6)** — `pa-k-baseline` (1.00), `expanding-training` (1.00), `pregame-opportunity-contract` (0.975), `i4-card-source-experiment` (0.934), `kcount-integration` (0.905), `i5-tail-challenger` (0.81) | 12 files | 1.00 | drafts vary from finals (2 identical, 4 drifted) — finals are the registered/frozen versions; drafts are pre-freeze working copies | finals = **frozen evidence**; drafts = superseded working copies | the non-draft file in each pair | extend ledger T6: archive all 6 drafts with pointers (one slice), OR owner picks retain-as-lineage per pair | Low-Med (evidence packets; never delete finals) | link check; blob identity for the 2 identical; diff summary for the 4 drifted |
| Enforcement negative-probes (6 files) | `bf-pilot-diagnostic-reclass-2026-10-14/enforcement_checks/membership_*.json` | 0.995 | each file tests a DIFFERENT failure mode (badstatus/dup/extra/flip/missing/swapped) | frozen evidence | none needed — all intentional | **keep as-is**; annotate as intentional fixture family in the register | none | n/a |
| Within-experiment pairs | `pa1b_oracle_xk/bootstrap.json` vs `paired_comparisons.json` (0.979); `hashes.json` across two experiments (0.80) | 0.979 | related-by-design outputs of the same pipeline | frozen evidence | each | **keep**; owner confirms bootstrap/paired split intent | none | n/a |
| Known intentional mirrors | `.cursorignore`/`.clineignore` | 1.00 | documented convention | — | both | keep (already dispositioned) | none | n/a |

## Cross-cutting conclusions

1. **Documentation entropy is concentrated, not diffuse:** outside the 6 prereg
   pairs and known historical surfaces, the doc tree has no near-duplicate mass.
   The consolidation design (S1–S7) is sufficient; no new doc-restructuring
   axis is needed.
2. **The draft→final prereg convention leaks working copies into the frozen
   tree** — 6 of them. Smallest reversible slice: extend T6 to a single
   "prereg-draft disposition" PR covering all six (archive with pointer, or
   retain-as-lineage by owner pick), touching only `research/offseason_2026/*-draft.md`
   files.
3. **Code duplication debt: none found at threshold** — the two name-collision
   pairs remain distinct-tools findings, not consolidation targets.

## Disposition

Report-only. Ledger impact: T6 widens 2 → 6 pairs (recorded here; the ledger
file update rides the next committed slice per the dated-report convention).
Feed into: deletion/quarantine ledger §B, adoption matrix (repo-docs-canonicalizer
owns the prereg slice).
