# REVIEW_SNAPSHOT — market-eval-v1 pinned review commit

**Date:** 2026-10-14. **Purpose:** byte-identical, git-pinned snapshot of the
market-eval-v1 implementation (prep v2 + gated scorer + tests + spec docs)
for independent review (Chat 2). Lake paths stay authoritative; this is a
read-only pin, not a fork.

## Pinned commit

- Repo: this repository (local worktree; branch `main` at pin time)
- Commit SHA: `02ce162f119208b762edf1fd690edd5e7ee9b8ea`
- Snapshot dir: `research/offseason_2026/market_eval/`
- Blob-identity proof: every blob below was exported with
  `git cat-file blob HEAD:<path>` and sha256-compared against the lake
  source file — all 9 IDENTICAL (a scoped `.gitattributes` with `* -text`
  prevents EOL normalization so committed bytes equal lake bytes exactly).

## File manifest (sha256, byte-identical lake source == committed blob)

| sha256 | bytes | file |
| --- | ---: | --- |
| `457991d81d44f9541dcb6a2889f35979aa0d9d844cd1ab91d57e1aea5e20e929` | 61,806 | market_eval.py |
| `66db5cec257d3c5cd5b495d3f62768afbe545cae887836a72e16e9627f00f292` | 23,932 | verify_ledger.py |
| `524cd6f297db71da1d303507c22e9bf7deec27f605373963ace507bcb0780e3f` | 18,892 | EXPERIMENT_CARD.md |
| `611fa46e617e03e31fc9dbc7b76435d2853ba594b0a7108fb137a2e4fd5731d0` | 8,368 | BUNDLE_EXTRACTION.md |
| `798385a393340b42c3ca2de17cfbc389854c79fefcc3b778db5e76b761889a33` | 6,167 | ARTIFACT_MAP.md |
| `ad3a801baa405f78dec2af997572cb0e1b16aca55a03894449d2a578e8579765` | 4,782 | METRIC_SCHEMA.md |
| `f1ca5797ba53051eb114f9086ed3e535fcd34519d080bb064a6aedf47ac4fe3e` | 3,086 | EXCLUSION_LEDGER.md |
| `8d082a686a45fd1c24e6afb4708eb3b6c0cc992cfd926847e976d13e951f5d53` | 23,390 | tests/test_market_eval.py |
| `d83b8ee7b1a37baa495a3584a28e3b34222a428e678f02c54dde776582c3b681` | 15,137 | tests/test_score_end_to_end.py |

Plus `research/offseason_2026/market_eval/.gitattributes` (3 lines, `* -text`;
snapshot infrastructure, not lake content).

## Excluded from the snapshot (by design)

- `outputs/prep/`, `outputs/prep_v2/`, `outputs/verification/` — parquet/JSON
  outputs stay lake-authoritative; prep_v2 hashes are pinned in
  `outputs/prep_v2/manifest.json` (matched_contracts `185abda9a238dd97`,
  actionable_pairs `32d65386b92718e4`, closing_refs `fbcad4d833cb7dc9`,
  paper_bets `6e310c49bc238795`; input hashes incl. book_lines
  `325abdf01f5f0b84`, payload `19511a49...58a96`).
- `reports/test_results.txt`, `.pytest_cache/`, `__pycache__/` — generated.
- No data parquets, no model artifacts, no BF rebuild.

## Import/test isolation

No conftest shim was needed: the test files resolve `market_eval.py` via
`sys.path.insert(0, parents[1])`, so the committed copy imports itself in the
repo layout. Repo pyproject sets `testpaths = ["tests"]`, so the snapshot is
not collected by the repo's default suite.

## Test evidence (on the committed bytes)

```
# from the repository worktree root (this repo, snapshot dir committed)
python -m pytest research/offseason_2026/market_eval/tests -q
```

Result 2026-10-14: **28 passed, 0 failed** (18 test_market_eval.py +
10 test_score_end_to_end.py). Synthetic fixtures only; no archive reads;
no writes outside tmp_path.

## Review docs (written after the pin; committed as a docs-only follow-up
## commit; canonical copies also in the private research lake)

`REVIEW_SNAPSHOT.md`, `SPLIT_MAP.md`, `MOMENTS.md`, `INCIDENT.md`,
`REVIEW_HANDOFF.md` — canonical copies in the private research lake
(`<private research lake>\market-eval-v1\`, local only, not in this repo).
The pin commit `02ce162f119208b762edf1fd690edd5e7ee9b8ea` is preserved
unchanged; the docs commit is a docs-only delta on top of it.
