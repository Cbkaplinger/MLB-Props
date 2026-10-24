# DECISIONS - one decision log

> One dated section per decision. **Current decision register first; historical
> source material (verbatim archived quotes) is separated below the divider** -
> where the register and a historical quote conflict, the register wins and the
> historical quote stands as evidence. Frozen registrations, protocols, pins
> and hashes outrank everything in this file (ADR-0001, decision 5).

## Current decision register

| # | Decision | Rationale | Status | Evidence | Consequence | What could reverse it |
|---|---|---|---|---|---|---|
| D1 | **Evidence gates before any promotion** - pre-registered cards; receipts (consumed inputs, code SHA, output hashes) written before acceptance; promotion needs calibration + policy replay + owner gate; a negative result closes the recipe, not the idea | Provenance defects recurred (in-place receipt repair with original bytes lost; a merge before the corrected head was reviewed) | **ACTIVE - governing rule** (owner adoption of the ADR wording pending) | ADR-0001 quote below; archived source `docs/archive/consolidated/adr/PROPOSED-evidence-gates.md` | Slower per experiment; no reruns or disputes; READY and authorized stay separate | A dated supersession entry in this register, by owner decision |
| D2 | **Exact aggregation first, workload dependence second** - Question A (exact Poisson-binomial) sequenced before any Question B work. **Market matching component: UNDER AUDIT** — the ±1-day tolerance is a suspected failure mode, not a demonstrated root cause. Existing market scores are quarantined pending identity verification. | Attribution: one component per experiment | **REPORTED, EXECUTION STATUS UNRESOLVED** - a decision-flip result (one flip in 19,292) was reported by the builder handoff, but Chat 1 disputes the components at the full SHA `c07976d...`; no published immutable execution artifact verifies it; NOT accepted evidence; no promotion authorized | ADR-0002 quote below + its dated outcome; decision-flip record (PR #29 lineage, merged `71a1c5c`) | The exact-aggregation recipe is closed as a documented curiosity; the count layer keeps the slot-average aggregator; effort moved to the decision-flip lane | A new pre-registered card on a different population or decision definition (owner) |
| D3 | **Multiclass PA outcome model direction** - extend the PA lane to multi-outcome slot modeling (ball/strike/in-play) rather than binary K-only | The PA lane already carries slot-level primitives; multiclass is the next information-gain candidate | **PROPOSED** - design card pending owner adoption; no implementation authorized | Multiclass ADR quote below; archived source `docs/archive/consolidated/adr/PROPOSED-multiclass-pa-outcome-model.md` | None until adopted and gated | Owner decision before any implementation; ADR-0001 gates apply if adopted |
| D4 | **Research/shipping cycle PRD** (R1-R6 sequencing) | Sequencing the research questions against the 2027 season | **SUPERSEDED** - replaced by `docs/ROADMAP.md` (the architect owns it) | PRD quote below; archived source `docs/archive/consolidated/adr/PROPOSED-prd-research-shipping-cycle.md` | Forward planning lives in the roadmap | n/a (the roadmap owns forward planning) |

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

# Historical source material (verbatim archived quotes; evidence, not the register)

> Each quote below is the full original ADR at consolidation time, with source
> path and blob SHA. The register above supersedes these where they conflict.

## ADR-0001: Evidence gates before any promotion

- **Source:** `docs/adr/PROPOSED-evidence-gates.md` @ blob `13a5e1d5db7b71b3c09622a66bf06d855c3f52a8`
- **Status:** PROPOSED - owner adoption pending (quoted verbatim below; the original file is archived at `docs/archive/consolidated/adr/PROPOSED-evidence-gates.md`)

---

# ADR-0001: Evidence gates before any promotion

> Numbering note: the research-cycle labels ADR-0001/ADR-0002 are local to this proposal; the repository accepted sequence already includes ADR-0007 (MLflow research mirror). Renumber on adoption if the owner prefers.

**Status:** PROPOSED (2026-10-21; pending owner approval)

## Context

Several lanes have produced PA-level or aggregation improvements that did not
survive evaluation. Provenance defects have recurred (in-place receipt repair
with original bytes lost; a merge before the corrected head was reviewed).

## Decision

1. Each research question gets a pre-registered card: one contrast, one primary
   metric, a paired population, and a stated stop condition.
2. A result is valid only if the receipt records the consumed inputs, the
   executed code SHA and the output hashes, and those are written before
   acceptance.
3. Research code never feeds production automatically. Promotion needs a
   separate gate: calibration, policy replay, and an owner decision.
4. A negative result closes the specific recipe, not the idea.
5. Frozen registrations, pins and hashes outrank living documents - and this
   includes THIS ADR, the PRD, and any role rules: they cannot override
   frozen registrations, protocols, pins, or hashes.

## Consequences

Slower per experiment; avoids reruns and disputes. "READY" and "authorized"
remain separate states.

## ADR-0002: Exact aggregation first, workload dependence second

- **Source:** `docs/adr/PROPOSED-exact-aggregation-first.md` @ blob `90042ed982abf46168a557db1ecfc909ef191920`
- **Status:** PROPOSED - owner adoption pending (quoted verbatim below; the original file is archived at `docs/archive/consolidated/adr/PROPOSED-exact-aggregation-first.md`)

---

# ADR-0002: Exact aggregation first, workload dependence second

> Numbering note: the research-cycle labels ADR-0001/ADR-0002 are local to this proposal; the repository accepted sequence already includes ADR-0007 (MLflow research mirror). Renumber on adoption if the owner prefers.

**Status:** PROPOSED (2026-10-21; pending owner approval)

## Decision

Run Question A (exact Poisson-binomial over the registered cycling order)
before Question B (workload dependence). Question A changes one component and
leaves the BF PMF alone. Question B changes the generative structure and needs
its own design.

## Alternatives rejected

- Starting with Question B: changes the generative model first, so any result
  would be confounded with the aggregator change.
- Replacing the aggregator and the workload model together: makes any result
  impossible to attribute to one component.

## Scope statement

Exact aggregation improves mathematical fidelity under its stated assumptions
(each start's count distribution from the registered slot probabilities over
the registered cycling order). Predictive benefit remains UNMEASURED until the
paired count-RPS evaluation runs; fidelity is not a predictive claim.

## Kill criteria

If Question A's count-RPS improvement is not distinguishable from zero, drop
it and move to Question B or to the next lane. **Non-significance supports the
registered stop / no-promotion decision only - it is NOT a conclusion of
equivalence** (the study is not powered to prove the arms identical).

## Question B subjects (design card only; not implemented until R2 reports)

- **C-B1: exposure-index heterogeneity with the supplied BF distribution** -
  the workload exposure index varies across starts; the model must consume the
  supplied BF distribution's heterogeneity rather than a collapsed scalar.
- **C-B2: endogenous exit/workload coupling** - pitcher exit (pull/hook) and
  workload are modeled as coupled, not as an exogenous TBF input.

Each is a design-card subject per the PRD (R3): model structure, delta vs the
frozen baseline, primary metric, paired population, stop condition, and
required synthetic tests - no code and no real outcomes before R2 reports.

### Status note (2026-10-21, corrected per owner review)

**REPORTED, EXECUTION STATUS UNRESOLVED - NOT CLOSED.** A decision-flip result
(one flip in 19,292; also stated in `docs/ROADMAP.md`) was reported by the
builder handoff, but Chat 1 disputes that the count-RPS/CLI components exist
at the full SHA beginning `c07976d`. No published immutable execution artifact
has been located by this lane. The prior "CLOSED" wording in this log was an
unverified acceptance of a reported handoff figure and is SUPERSEDED by this
status note (the proposed-ADR text above is preserved unchanged as the
historical quote). Resolution: the research pair's same-SHA reconciliation
(Chat 2 locates the implementation; Chat 1 inspects and executes the synthetic
command) - until then **no promotion, no execution authorization, and no
equivalence claim**. Mathematical fidelity under its assumptions is unchanged
by this dispute; predictive benefit remains unmeasured.

## PROPOSED ADR — Multiclass plate-appearance outcome model

- **Source:** `docs/adr/PROPOSED-multiclass-pa-outcome-model.md` @ blob `9d49d6151c1fceae8411ea43e875282d2d929c00`
- **Status:** PROPOSED - owner adoption pending (quoted verbatim below; the original file is archived at `docs/archive/consolidated/adr/PROPOSED-multiclass-pa-outcome-model.md`)

---

# PROPOSED ADR — Multiclass plate-appearance outcome model

**Status:** PROPOSED (architect direction, 2026-10-21). Owner direction: the
project is moving toward a model that predicts every outcome of a plate
appearance. This ADR sequences that work. It does not override frozen
registrations, pins, hashes, or pre-registered protocols.

## Context

The research PA lane is binary today: L3 (ridge logistic, K versus not-K) is the
DEVELOPMENT baseline. The count layer aggregates PA strikeout probabilities
over a BF distribution; Question A showed exact Poisson-binomial aggregation
improves count-RPS by a small, statistically resolved amount on the 4,823
development starts. Two open limits remain: workload is exogenous to
performance, and every non-strikeout market (walks, hits, outs, runs) is out
of reach.

## Decision

Target a single multinomial model over PA outcomes: K, BB, HBP, 1B, 2B, 3B,
HR, ball-in-play out (final taxonomy fixed in the M0 card). Strikeout
probability becomes one marginal of a coherent distribution. The model is a
research lane; production is unchanged until a separate promotion gate.

## Stages (one card each; no stage starts before the previous gate result)

| Stage | Question | Gate |
| --- | --- | --- |
| M0 | Does a softmax version of L3 (same features, same fit/eval blocks) match L3 on the K marginal and beat league-constant and log5 baselines on multiclass log loss? | K-vs-not-K log loss non-inferior to L3 at a pre-declared margin (date-clustered, paired); multiclass log loss better than the baselines; per-class reliability reported, rare classes pooled |
| M1 | Does the K head, aggregated with the exact Poisson-binomial machinery, preserve count-RPS against the Question A result? | Count-RPS non-inferior to the Question A challenger on the 4,823 dev starts |
| M2 | Do the non-K heads support a second market (outs, walks, hits) with market data? | Separate card per market, own price-layer evaluation |
| M3 | Can PA outcomes feed a game-state process (baserunners, runs, pitch count) so exit becomes endogenous? | This is the structural answer to C-B2 in the Question B card; its own pre-registration |
| M4 | Does the 2015-2022 history extension help rare classes (3B, HBP, HR)? | Separate registered evaluation; it changes cumulative inputs for all players |

## Why this order

- M0 reuses the existing PA table, folds, and bootstrap; it needs no new data.
- The K marginal must not regress: the binary model is the incumbent for the
  market the project actually bets.
- Rare classes have thin 2023 training counts, so calibration and variance
  are the main M0 risk; M4 exists because of it.
- Multiclass is an enabler, not a proven accuracy gain. Its benefit for K
  specifically is unmeasured until M0 reports.

## Non-goals

No production change, no confirmation access, no betting-layer claim, no
market work before M2, no new feature families inside M0.

## Statistics

The statistics rules in `docs/AGENTS_ROLES.md` (2026-10-21) apply. Primary
endpoints for M0 are two (K-marginal non-inferiority, multiclass log loss),
with Holm adjustment at m=2.

## PRD: next research and shipping cycle

- **Source:** `docs/adr/PROPOSED-prd-research-shipping-cycle.md` @ blob `5a6eb940dccd0ddee2cb9bbba94b918b4ac11d5b`
- **Status:** PROPOSED - owner adoption pending (quoted verbatim below; the original file is archived at `docs/archive/consolidated/adr/PROPOSED-prd-research-shipping-cycle.md`)

---

# PRD: next research and shipping cycle

**Status:** PROPOSED (2026-10-21; pending owner approval)
**Goal:** Decide with evidence whether the count layer, workload model or
aggregation should change before the 2027 season.
**Assumed deadline:** season opening late March 2027 (owner to confirm).

## Requirements

- **R1. DONE 2026-10-21: PR #25 merged at `71a1c5c` (one dated status note for this PRD below; mutable research state is not copied into the other architecture files - their PROPOSED status labels are the only live markers).**
- **R2.** Review the Question A implementation and spec. Then the owner decides
  whether to authorize one real-data evaluation: count-RPS primary, paired
  bootstrap, confirmation untouched.
- **R3.** Pre-register Question B (workload dependence) as a design card with the two named subjects C-B1 (exposure-index heterogeneity with the supplied BF distribution) and C-B2 (endogenous exit/workload coupling) - see ADR-0002. Do not implement it until R2 reports.
- **R4.** Define the abstain-versus-handle policy for newcomers (owner
  decision; 57 debut-date newcomers plus Enns 608650 / Hart 606996).
- **R5.** Finish the cleanup sweep and reconcile the docs and diagrams.
- **R6.** Promotion path: calibration, policy replay and a paper-trading
  window. Nothing is promoted without an owner gate.

## Non-goals

Retuning the rejected R60/m30 recipe, touching the confirmation block, or any
production change this cycle.

## Success criteria

Each question has a closed verdict with valid provenance. Any promoted change
beats the frozen baseline on the pre-registered metric and survives replay.

## Risks

Provenance defects; scope creep (the Question A work is already inside
PR #25); a small expected gain from Question A.


## Status note (one dated note for this PRD; 2026-10-21)

- PR #25 (batter-history diagnostic closed REJECTED; Question A exact
  Poisson-binomial aggregator built with synthetic tests; publication fix
  included) MERGED at `71a1c5c`. Question A evaluation on real outcomes
  remains UNAUTHORIZED and unrun (owner gate, R2). Abstain-vs-handle (R4)
  remains the open owner decision.
