# Source Package Layout

`src/` contains project source code and notebook development surfaces.

## Structure

- `src/Python/` — canonical pipeline, feature, modeling, market, and utility modules.
- `src/Notebooks/` — development notebooks for feature and pipeline inspection.

## Usage Rules

- Treat `src/Python/` as pipeline-core (`keep` by default during cleanup).
- Do not move modules without updating imports and tests in the same pass.
- Prefer Polars for new data transformation logic in this package.
