# Dynamic-import resolution and dead-module proof — 2026-10-16 (Chat 3, report-first)

Resolves the 58 `importlib`/`__import__` sites and the string-reference question
left open by [`python_dead_code_audit_2026-10-16.md`](python_dead_code_audit_2026-10-16.md).
Base `origin/main` @ `1927c8c…`. Method: extraction of every dynamic-import
target literal; whole-tree string-literal scan (`"<module>"` forms including
`Python.*`/`src.Python.*` qualifications) for the five statically-dead modules;
context-line inspection of every ambiguous hit. Confidence: HIGH within the
tracked tree (caveat below unchanged for out-of-tree invocation).

## Verdict: the five modules are PROVEN dead in the tracked tree

| Module | Static imports | String refs as module | Dynamic-import target | CLI callers | Verdict |
|---|---|---|---|---|---|
| `src/Python/ballpark.py` | 0 | **NONE** | no | 0 | **dead** |
| `src/Python/batter_features.py` | 0 | **NONE** | no | 0 | **dead** |
| `src/Python/batter_rolling.py` | 0 | docstring mentions `batter_rolling.parquet` (output artifact, not the module) in `pipeline/rolling.py` | no | 0 | **dead** |
| `src/Python/identity.py` | 0 | `"identity"` hits = calibrator *method name* (`prob_calibration.py`) + test concept, not the module | no | 0 | **dead** |
| `src/Python/reliability.py` | 0 | `"reliability"` hits = reliability *metric* computations (`eval_package.py`) + the Issue #9 stale notebook pointer | no | 0 | **dead** |

(`skill_stats.py` remains test-only: imported solely by `tests/test_skill_stats.py`.)

The dynamic-loading hypothesis that kept these at MEDIUM confidence is now
**refuted for the tracked tree**: none of the 58 dynamic sites references them,
and no dispatch table, getattr-style registry, or qualified string mentions them.
What remains is the standing out-of-tree caveat — lake-archived runners or
external schedulers could invoke them without any repository trace — which is an
owner-knowledge question, not a static-analysis question.

## Contradiction to resolve (owner decision, now sharpened)

`CONTEXT.md` and `README.md` still present `ballpark`, `batter_features`,
`batter_rolling` as canonical pipeline modules. The code says otherwise. Exactly
one of these is true: (a) the modules are retired and the docs are stale, or
(b) they are invoked by lake-archived/external runners the repository cannot see.
The owner can settle this in one sentence; the resulting slice is either a
dead-code quarantine (with full reference list attached) or a docs-truth fix.
Until then: **retain everything; delete nothing.**

## Dynamic-import inventory (complete)

All 58 sites resolve to stdlib (`datetime`, `hashlib`) or known research modules
(`pandas`, `bf_distribution`, `run_corrected_history_2023`, `nested_cv`,
`feature_ablation`, `vif_cluster_reduction`) — every one also statically
importable and already covered by the import graph or test suites. No hidden
module surface exists.
