# MLB Props

Research project for pregame MLB pitcher strikeout projections using Statcast
data. The current approach predicts strikeout rate with LightGBM, then combines
that rate with a separate projected batters-faced estimate.

## Project status

The repository is being converted from exploratory notebooks into a
reproducible pipeline. Existing notebook metrics are historical research
results and should not be interpreted as validated betting performance.
Same-game `PA`, which contaminated earlier evaluation, has been removed from
the model feature lists.

See [the model card](docs/model-card.md) for the target, leakage rules, known
limitations, and requirements for a trustworthy backtest, and
[docs/dev-notes.md](docs/dev-notes.md) for the historical development record
(with banners marking metrics invalidated by the leakage fix).

## Repository layout

```text
Models/Strikeout-Model/     Model research notebooks
Training-Data-Cleaned/      Statcast cleaning notebooks
RosterScraper/              MLB roster utility
src/mlb_props/              Shared configuration and safety checks
tests/                      Fast tests that do not require training data
data/                       Local-only data layout documentation
docs/                       Model documentation
```

## Setup

Python 3.11 or newer is recommended.

```powershell
# Windows
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

```bash
# macOS
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Run notebooks from the repository root:

```bash
jupyter lab
```

## Data paths

Data is never committed. By default, the model reads:

```text
data/processed/Pitcher2023-2025.parquet
```

Set environment variables when data lives elsewhere:

```powershell
# Windows PowerShell
$env:MLB_PROPS_DATA_DIR = "D:\MLB-Data"
$env:MLB_PROPS_PITCHER_STARTS = "D:\MLB-Data\processed\Pitcher2023-2025.parquet"
```

```bash
# macOS
export MLB_PROPS_DATA_DIR="$HOME/MLB-Data"
export MLB_PROPS_PITCHER_STARTS="$HOME/MLB-Data/processed/Pitcher2023-2025.parquet"
```

See [data/README.md](data/README.md) and [.env.example](.env.example) for the
expected layout and all overrides.

## Development

```bash
pytest
```

Use one cross-platform main branch. Create short-lived branches for features or
fixes (for example, `fix/portable-paths`), not separate Mac and Windows
branches. Machine-specific paths belong in environment variables and must not
be committed.

