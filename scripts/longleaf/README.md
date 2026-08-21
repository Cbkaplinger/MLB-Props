# Longleaf Run Pack (CPU)

This folder contains ready-to-submit SLURM jobs for sparse72 tuning and
holdout evaluation.

## Files

- `bootstrap_longleaf_env.sh`: one-time env/bootstrap helper
- `slurm_tune_sparse72_monotone.sbatch`: primary tuning job
- `slurm_tune_sparse72.sbatch`: challenger tuning job
- `slurm_eval_holdout_2025.sbatch`: 2025 holdout compare + acceptance table

## Quick start (on Longleaf login node)

```bash
cd ~/MLB-Props
bash scripts/longleaf/bootstrap_longleaf_env.sh ~/MLB-Props mlb_props_env
```

Submit jobs:

```bash
mkdir -p logs
sbatch scripts/longleaf/slurm_tune_sparse72_monotone.sbatch
sbatch scripts/longleaf/slurm_tune_sparse72.sbatch
sbatch scripts/longleaf/slurm_eval_holdout_2025.sbatch
```

Recommended overnight submit (3 passes + dependency-ordered eval):

```bash
bash scripts/longleaf/submit_overnight_pipeline.sh
```

Monitor:

```bash
squeue -u $USER
tail -f logs/tune_s72_mono_<jobid>.out
tail -f logs/eval_holdout_2025_<jobid>.out
```

## Recommended defaults

- CPU only (`general` partition).
- No GPU needed for LightGBM/Optuna workflow.
- Start with 16 CPU / 64G RAM for tuning, 8 CPU / 32G for evaluation.
- Run all heavy work via `sbatch`/`srun` compute allocations (not login node).

## Preflight checks (required)

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate mlb_props_env
python -c "import optuna, polars, lightgbm, sklearn, pandas, numpy, pyarrow, scipy, requests, xgboost; print('deps ok')"
test -f data/Odds-Open-Close-2025-2026/pitcher_strikeouts_early_open_2025_2026.csv && echo "open data present"
```

