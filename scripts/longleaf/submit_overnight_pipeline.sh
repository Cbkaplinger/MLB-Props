#!/usr/bin/env bash
set -euo pipefail

# Submits 3 tuning passes for sparse72_monotone + sparse72 in parallel per pass,
# then submits holdout evaluation only after all tuning jobs succeed.
#
# Usage:
#   bash scripts/longleaf/submit_overnight_pipeline.sh

pass1_trials="${PASS1_TRIALS:-200}"
pass2_trials="${PASS2_TRIALS:-160}"
pass3_trials="${PASS3_TRIALS:-120}"

echo "Submitting pass 1..."
j1m=$(TRIALS="$pass1_trials" sbatch --parsable scripts/longleaf/slurm_tune_sparse72_monotone.sbatch)
j1s=$(TRIALS="$pass1_trials" sbatch --parsable scripts/longleaf/slurm_tune_sparse72.sbatch)
echo "pass1 mono=${j1m} sparse=${j1s}"

echo "Submitting pass 2..."
j2m=$(TRIALS="$pass2_trials" sbatch --parsable scripts/longleaf/slurm_tune_sparse72_monotone.sbatch)
j2s=$(TRIALS="$pass2_trials" sbatch --parsable scripts/longleaf/slurm_tune_sparse72.sbatch)
echo "pass2 mono=${j2m} sparse=${j2s}"

echo "Submitting pass 3..."
j3m=$(TRIALS="$pass3_trials" sbatch --parsable scripts/longleaf/slurm_tune_sparse72_monotone.sbatch)
j3s=$(TRIALS="$pass3_trials" sbatch --parsable scripts/longleaf/slurm_tune_sparse72.sbatch)
echo "pass3 mono=${j3m} sparse=${j3s}"

deps="${j1m}:${j1s}:${j2m}:${j2s}:${j3m}:${j3s}"
echo "Submitting evaluation with dependency afterok:${deps}"
je=$(sbatch --parsable --dependency=afterok:${deps} scripts/longleaf/slurm_eval_holdout_2025.sbatch)
echo "eval job=${je}"
echo "Done. Monitor with: squeue -u \$USER"
