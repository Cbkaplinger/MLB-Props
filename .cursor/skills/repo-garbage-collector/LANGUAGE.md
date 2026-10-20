# Cleanup language (shared glossary)

Use these terms exactly. Consistent language is the point — do not drift into
"junk", "legacy stuff", "dead weight", or "cleanup candidates" as informal
synonyms.

- **Canonical living** — hand-maintained; updated when its source of truth changes (README, CONTEXT, standards, current-state page).
- **Frozen evidence** — generated once, then immutable: experiment cards, manifests, prereg docs, run packets. Annotate; never rewrite, never relabel.
- **Historical evidence** — dated reports, archives, lineage notebooks; retain; errata/pointers only.
- **Operational** — runbooks/notebooks tied to daily ops; updated only when ops behavior changes.
- **Superseded** — a document whose authority moved elsewhere; carries a SUPERSEDED banner + forward pointer; content preserved.
- **Archive** — a MOVE with history preserved (`git mv`) + manifest + pointer updates; never a silent relocation.
- **Lake** — external artifact storage (MLB-Props-Research / external-lake); holds bulk outputs, forecasts, bootstrap arrays. Git holds identity: manifests, hashes, receipts.
- **Generated (tracked)** — reproducible output deliberately committed for provenance (figures, paper PDFs, results index); has a declared generator + validation guard.
- **Draft vs final (prereg)** — `*-draft.md` is a pre-freeze working copy; the non-draft file is the registered/frozen version. Drafts are superseded working copies: archive + pointer + repoint references; never delete while cited.
- **Static orphan** — no static importer, no entry point, not a test. **Uncertain until** dynamic-import targets, string references, CLI callers, scheduled refs, and out-of-tree invocation are checked.
- **Proven dead** — orphan AND zero dynamic targets AND zero string references AND zero CLI/scheduled/doc-as-instruction references AND owner ruling recorded.
- **Fixture family** — a set of near-identical evidence files that intentionally differ in one field (e.g. negative-probe JSONs). Keep; never flag as duplication.
- **Delete-candidate** — a file that has passed every Article-1 condition of the cleanup constitution AND has an owner ruling. Nothing less.
- **Fail-stop** — on precondition failure: halt, report the exact missing condition, propose nothing.
- **No-re-litigate** — settled evidence stays settled unless a new commit, manifest, import/caller reference, or reproducible artifact contradicts the prior conclusion.
