# Source Package Layout

`src/Python/` is the canonical implementation surface.

## Structure

- `src/Python/`: production and research-shared library code.
- `src/Notebooks/`: legacy/development notebook surface for diagnostics.

## Ground-truth rule

- Operational truth lives in `production/` CLIs and policies.
- `src/Notebooks/` should not be treated as the primary production workflow.
- Prefer Polars for all new data transformation logic.
