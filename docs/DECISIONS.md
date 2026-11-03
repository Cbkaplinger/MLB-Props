# DECISIONS - one decision log

> One dated section per decision. **Current decision register first; historical
> source material (verbatim archived quotes) is separated below the divider** -
> where the register and a historical quote conflict, the register wins and the
> historical quote stands as evidence. Frozen registrations, protocols, pins
> and hashes outrank everything in this file (ADR-0001, decision 5).

## Current decision register

| # | Decision | Rationale | Status | Evidence | Consequence | What could reverse it |
|---|---|---|---|---|---|---|
| D1 | **Evidence gates before any promotion** - pre-registered cards; receipts (consumed inputs, code SHA, output hashes) written before acceptance; promotion needs calibration + policy replay + owner gate; a negative result closes the recipe, not the idea | Provenance defects recurred (in-place receipt repair with original bytes lost; a merge before the corrected head was reviewed) | **ACTIVE - governing rule** (owner adoption of the ADR wording pending) | full original text retained in the source-material table below `docs/archive/consolidated/adr/PROPOSED-evidence-gates.md` | Slower per experiment; no reruns or disputes; READY and authorized stay separate | A dated supersession entry in this register, by owner decision |
| D2 | **Exact aggregation first, workload dependence second** - Question A (exact Poisson-binomial) sequenced before any Question B work. **Market matching: pre-repair market scores are invalid (historical, preserved). Full-key identity repair implemented at 23db50d and independently verified; repaired 2025H1 close comparison stands as a development benchmark.** | Attribution: one component per experiment | **REPORTED, EXECUTION STATUS UNRESOLVED** - a decision-flip result (one flip in 19,292) was reported by the builder handoff, but Chat 1 disputes the components at the full SHA `c07976d...`; no published immutable execution artifact verifies it; NOT accepted evidence; no promotion authorized | full original text retained in the source-material table below + its dated outcome; decision-flip record (PR #29 lineage, merged `71a1c5c`) | The exact-aggregation recipe is closed as a documented curiosity; the count layer keeps the slot-average aggregator; effort moved to the decision-flip lane | A new pre-registered card on a different population or decision definition (owner) |
| D3 | **Multiclass PA outcome model direction** - extend the PA lane to multi-outcome slot modeling (ball/strike/in-play) rather than binary K-only | The PA lane already carries slot-level primitives; multiclass is the next information-gain candidate | **ACCEPTED as development-only diagnostic** (M0 v2 executed at `2e2482b`, Chat 2 independently verified). Design card for broader implementation: pending | full original text retained in the source-material table below `docs/archive/consolidated/adr/PROPOSED-multiclass-pa-outcome-model.md` | None until adopted and gated | Owner decision before any implementation; ADR-0001 gates apply if adopted |
| D4 | **Research/shipping cycle PRD** (R1-R6 sequencing) | Sequencing the research questions against the 2027 season | **SUPERSEDED** - replaced by `docs/ROADMAP.md` (the architect owns it) | full original text retained at `docs/archive/consolidated/adr/PROPOSED-prd-research-shipping-cycle.md` (pinned blob in the source-material table below) | Forward planning lives in the roadmap | n/a (the roadmap owns forward planning) |

## Production/research boundary and component migration

- **Production path (frozen, live):** Statcast inputs -> L1-L3 pipeline ->
  `features.py` + registries -> k-rate ensemble (frozen artifacts,
  manual-winner blend) + TBF ridge -> `count_layer.py` Poisson + WS1c Platt ->
  policy filter (floors, cap, under-lean, DK+FD, clip) -> flat sizing -> board
  -> odds ledger -> grading. Depth: `docs/diagrams/10-system-paths.md`.
- **Research path (gated):** registered questions evaluated over the SAME
  frozen artifacts with paired populations; it never feeds production
  automatically.
- **The boundary is D1 (ADR-0001):** a research component migrates only
  through calibration -> policy replay -> paper trade -> owner gate.
  **Component migration to date: NONE** - Question A (D2) closed at the
  boundary; the count layer keeps the slot-average aggregator.
- **Override limit:** this register, the ADRs, the PRD, and role rules cannot
  override frozen registrations, protocols, pins, or hashes; on disagreement
  the frozen artifact is authoritative and the prose gets a dated supersession
  label.

---

# Historical source material (retained full text; the register above is the active record)

> The full original documents below were consolidated here once verbatim. That
> second copy is retired from this active file: each source is preserved at its
> archived path and pinned by git blob SHA, and the register above (decision,
> rationale, consequence, status, evidence) is the authoritative reading.
> To read the full original text of any entry, use the archived source path or
> the pinned blob (git cat-file -p <blob>). Nothing unique was deleted.

| ID | Full original text (retained home) | Pinned blob |
| --- | --- | --- |
| ADR-0001 evidence gates | docs/archive/consolidated/adr/PROPOSED-evidence-gates.md | 13a5e1d5db7b71b3c09622a66bf06d855c3f52a8 |
| ADR-0002 exact aggregation first | docs/archive/consolidated/adr/PROPOSED-exact-aggregation-first.md | 90042ed982abf46168a557db1ecfc909ef191920 |
| Multiclass PA outcome model | docs/archive/consolidated/adr/PROPOSED-multiclass-pa-outcome-model.md | 9d49d6151c1fceae8411ea43e875282d2d929c00 |
| PRD: research and shipping cycle (SUPERSEDED by docs/ROADMAP.md) | `docs/archive/consolidated/adr/PROPOSED-prd-research-shipping-cycle.md` | `5a6eb940dccd0ddee2cb9bbba94b918b4ac11d5b` |
