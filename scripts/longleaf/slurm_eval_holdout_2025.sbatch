#!/bin/bash
#SBATCH -J eval_holdout_2025
#SBATCH -p general
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err

set -euo pipefail
mkdir -p logs

REPO_DIR="${REPO_DIR:-$HOME/MLB-Props}"
ENV_NAME="${ENV_NAME:-mlb_props_env}"

source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"
cd "$REPO_DIR"

python "production/ops/compare_feature_set_market_skill.py" \
  --feature-set production_sparse72 \
  --feature-set production_sparse72_monotone \
  --feature-set production_final58_consensus \
  --eval-start-date 2025-01-01 \
  --eval-end-date 2025-12-31 \
  --output-tag holdout_2025

python - <<'PY'
import pandas as pd
df = pd.read_csv("artifacts/odds_log/feature_set_market_skill_compare_holdout_2025.csv")
iso = df[df["calibration_mode"]=="isotonic"].copy()
iso = iso.sort_values(["brier_skill_vs_market","logloss_skill_vs_market"], ascending=False)
out = iso[["feature_set","calibration_mode","n_eval_rows","brier_skill_vs_market","logloss_skill_vs_market","brier","logloss","ece","mce"]].copy()
out["decision_rank"] = range(1, len(out)+1)
out.to_csv("artifacts/odds_log/model_acceptance_table_2025_holdout.csv", index=False)
print(out.to_string(index=False))
PY
