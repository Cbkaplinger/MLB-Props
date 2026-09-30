# Skill Provenance

Where each project skill came from, under what license, and what changed locally. No qira-os paths are listed as upstream: Helios/Qira skill bodies were never read or copied (see IP table below).

## Upstream record

- Matt Pocock skills repo: `https://github.com/mattpocock/skills`
- License: MIT, Copyright (c) 2026 Matt Pocock
- Fetched commit SHA: `d81f3a183412e71a5b1e84ca21bc1a35eea03a60` (main, 2026-09-30)
- Only two skills fetched: `skills/engineering/improve-codebase-architecture/` (SKILL.md + HTML-REPORT.md as design reference) and `skills/engineering/grill-with-docs/` (SKILL.md). Nothing else from that repo was taken.

MIT license text (required notice, applies to the two adapted skills):

```
MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## IP classification (before any skill write)

| Skill | Classification | Rationale |
|---|---|---|
| audit-feature-leakage | PERSONALLY_AUTHORED_GENERIC | Written from mlb-props leakage policy (`model-card.md`, `research_assistant_instructions.md`). |
| design-ml-experiment | PERSONALLY_AUTHORED_GENERIC | Written from `experiment_sop.md` + `research_assistant_instructions.md`. |
| compare-champion-challenger | PERSONALLY_AUTHORED_GENERIC | Written from `champion_challenger_protocol.md` + juiced replay doctrine. |
| audit-backtest-integrity | PERSONALLY_AUTHORED_GENERIC | Written from `oddsapi_replay_architecture.md` + `experiment_sop.md` section 8. |
| reconcile-baseball-stats | PERSONALLY_AUTHORED_GENERIC | Written from PA-1A attribution record + pipeline grain definitions. |
| archive-research-memory | PERSONALLY_AUTHORED_GENERIC | Written from repo doc conventions (dated reports, SUPERSEDED rule). |
| document-architecture | PERSONALLY_AUTHORED_GENERIC | Written from `repo_canonical_map.md` + diagrams layout. |
| write-adr | PERSONALLY_AUTHORED_GENERIC | Written from repo ADR needs; template is original. |
| consolidate-code | PERSONALLY_AUTHORED_GENERIC | Written from repo review order + promotion discipline. |
| audit-dead-code | PERSONALLY_AUTHORED_GENERIC | Written from `repo_canonical_map.md` keep/hold/delete protocol. |
| improve-codebase-architecture | PUBLIC_OPEN_SOURCE | Adapted from Matt Pocock (MIT, SHA above). |
| grill-with-docs | PUBLIC_OPEN_SOURCE | Adapted from Matt Pocock (MIT, SHA above). |
| Helios/Qira skill names (28 stubs) | EMPLOYER_INTERNAL | Read-only name list from `Helios/.cursor/skills/README.md`; bodies never opened, nothing copied. Generic ideas only (grill a plan, red-green-refactor, deep modules), independently authored into MLB text. |

## Skill table

| Skill | Mode | Upstream | License | Upstream version | Local changes | Owner | Review date |
|---|---|---|---|---|---|---|---|
| audit-feature-leakage | NATIVE_NEW | none (repo specs) | n/a | n/a | original | repo owner | 2026-09-30 |
| design-ml-experiment | NATIVE_NEW | none (repo specs) | n/a | n/a | original | repo owner | 2026-09-30 |
| compare-champion-challenger | NATIVE_NEW | none (repo specs) | n/a | n/a | original | repo owner | 2026-09-30 |
| audit-backtest-integrity | NATIVE_NEW | none (repo specs) | n/a | n/a | original | repo owner | 2026-09-30 |
| reconcile-baseball-stats | NATIVE_NEW | none (repo specs) | n/a | n/a | original | repo owner | 2026-09-30 |
| archive-research-memory | NATIVE_NEW | none (repo specs) | n/a | n/a | original | repo owner | 2026-09-30 |
| document-architecture | NATIVE_NEW | none (repo specs) | n/a | n/a | original | repo owner | 2026-09-30 |
| write-adr | NATIVE_NEW | none (repo specs) | n/a | n/a | original | repo owner | 2026-09-30 |
| consolidate-code | NATIVE_NEW | none (repo specs) | n/a | n/a | original | repo owner | 2026-09-30 |
| audit-dead-code | NATIVE_NEW | none (repo specs) | n/a | n/a | original | repo owner | 2026-09-30 |
| improve-codebase-architecture | PUBLIC_ADAPTATION | mattpocock/skills `skills/engineering/improve-codebase-architecture/` | MIT (2026 Matt Pocock) | d81f3a18 | CONTEXT.md + docs/adr/ repoint; MLB safety; temp-report rule; no Helios paths | repo owner | 2026-09-30 |
| grill-with-docs | PUBLIC_ADAPTATION | mattpocock/skills `skills/engineering/grill-with-docs/` | MIT (2026 Matt Pocock) | d81f3a18 | CONTEXT.md + docs/adr/ repoint; MLB safety; no Helios paths | repo owner | 2026-09-30 |

## What was NOT taken

- No Helios pointer `SKILL.md` bodies (they hardcode absolute Helios paths and Qira names).
- No `Helios/qira-os/.cursor/skills/**` content of any kind.
- No Helios START-HERE.md, scripts, or `.scratch`.
- No other Matt Pocock skills (no `setup-matt-pocock-skills`, `triage`, `to-tickets`, `implement`, `wayfinder`, Linear wiring, `grill-me`, `tdd`, `diagnosing-bugs`, `domain-modeling`, `code-review`, `zoom-out`).
- User-global skills (`helios-qira-build`, `helios-ticket-attack`, `cloud-architecture-visual-docs`) left in place; none duplicated into this repo.
