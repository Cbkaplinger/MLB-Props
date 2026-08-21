#!/bin/bash
#SBATCH -J tune_s72_mono
#SBATCH -p general
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err

set -euo pipefail
mkdir -p logs

REPO_DIR="${REPO_DIR:-$HOME/MLB-Props}"
ENV_NAME="${ENV_NAME:-mlb_props_env}"
TRIALS="${TRIALS:-120}"

source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"
cd "$REPO_DIR"

python "models/Strikeout-Model/research/tune_lightgbm_feature_set_optuna.py" \
  --feature-set production_sparse72_monotone \
  --trials "$TRIALS" \
  --k-rate-mae-max 0.0745 \
  --tbf-sens-max 0.012 \
  --output-tag sparse72_monotone_optuna
