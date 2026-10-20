# Language/runtime decision memo — 2026-10-16 (Chat 3)

**Decision: stay Python. No language migration now.** Required by the owner's
default-assumption rule; justified by the audit corpus.

## Basis

- The repository's center of gravity is numerical computing, ETL, experiment
  workflows, modeling libraries, and notebooks: Polars (333 importing files),
  NumPy (190), pandas (126), scikit-learn (102), LightGBM (20) — the ecosystem
  IS the product. SciPy/pandas/scikit-learn are the standard scientific-ML stack.
- The audit corpus found **zero language-level problems**: the defects are
  governance (5 proven-dead canonical modules, 8 undeclared dependencies, a CI
  test-collection blind spot, 23 static orphans, 62 undocumented entry points,
  documentation entropy) — all solvable inside Python, most already specified as
  slices.
- A migration would create a second large, unvalidated system mid-experiment,
  risking metric drift against frozen-model results (the exact failure mode the
  exact-SHA discipline exists to prevent).

## Exception bar (high, by design)

A non-Python component is justified only when ONE of these is proven, in writing:

| Trigger | Threshold | Candidate boundary |
|---|---|---|
| Profiled hot numeric bottleneck | profiled hot loop, >2x speedup available, isolable interface | Numba/Cython/Rust extension or vectorized NumPy/Polars |
| Warehouse-scale transformation need | data volume/relational operations outgrow Parquet+Polars patterns | SQL/DuckDB/dbt (still Python-orchestrated) |
| UI layer beyond notebooks | an operator-facing dashboard becomes a maintained product | TypeScript/React (current Streamlit surface is one file — not warranted) |
| Proven runtime/service bottleneck | measured latency/throughput failure in a deployed service | Go/Rust service boundary |
| Shell/bootstrap fit | deployment automation (already PowerShell — correct) | shell/infra tooling (status quo) |

Current status against the bar: no profiler evidence exists; the Streamlit
dashboard is a single module (not a product); deployment is PowerShell +
Modal (Python) — **all exceptions fail the bar today**. Revisit only with
evidence attached.

## Review trigger

Re-open this memo if: (a) a profiling pass shows a Python bottleneck in the live
serving path, (b) the dashboard becomes a maintained UI, or (c) data volumes
force warehouse-pattern transformations. Otherwise the next review is the
offseason retrospective.
