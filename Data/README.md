# Local data layout

Data files are intentionally excluded from Git. The notebooks expect this
layout by default:

```text
data/
├── raw/
│   └── savant/
│       └── regular/
│           ├── 2022/
│           ├── 2023/
│           ├── 2024/
│           └── 2025/
└── processed/
    ├── Pitcher2023-2025.parquet
    └── OppBatting2023-2025.parquet
```

Each raw season directory may contain one Parquet export. The processed
pitcher-start file is the input to both strikeout-model notebooks.

The local data directory can live anywhere. Set `MLB_PROPS_DATA_DIR` to its
root or `MLB_PROPS_PITCHER_STARTS` to override the pitcher-start file directly.
See `.env.example` for all supported path variables.

Do not commit raw or processed data. Keep the source data on the Mac and
transfer only the model-ready files needed on another machine.
