# Verification Checklist (independent verifier)

- [ ] Initial vs final manifest compared (counts by type).
- [ ] Every deletion/move inspected; migrated info exists exactly once.
- [ ] Broken internal refs + deleted paths searched (local links, imports,
      configs, scheduler strings, notebook refs).
- [ ] Full test suite run; result ≥ baseline with no new failures.
- [ ] Configured lint/format/type checks run.
- [ ] Production/Modal/scheduled entry points validated without deploying
      (parse + import + dry-run where safe; never deploy, never alert).
- [ ] Canonical notebooks executed top-to-bottom to temp copies where
      data permits; external-data blockers documented.
- [ ] Selector + metric populations reconciled (460/485/844 table + funnel).
- [ ] No secrets introduced or exposed (keys, tokens, webhooks, ntfy, paths,
      creds in code/notebooks/outputs/docs).
- [ ] No remote git operation (`status`/`diff`/`ls-files`/`log`/`grep` only).
- [ ] Pre-existing user changes preserved; own changes distinguished.
- [ ] Residual ambiguity + risk reported honestly (retain-but-flag list).
- [ ] `git diff --stat` + `git status --short` captured; uncommitted confirmed.
