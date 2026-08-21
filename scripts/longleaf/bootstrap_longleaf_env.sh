#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/longleaf/bootstrap_longleaf_env.sh ~/MLB-Props mlb_props_env

REPO_DIR="${1:-$HOME/MLB-Props}"
ENV_NAME="${2:-mlb_props_env}"

echo "[1/4] Load conda"
if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
else
  echo "Could not find conda.sh at ~/miniconda3. Adjust path and re-run."
  exit 1
fi

echo "[2/4] Create or activate env: ${ENV_NAME}"
if conda env list | awk '{print $1}' | rg -x "${ENV_NAME}" >/dev/null 2>&1; then
  conda activate "${ENV_NAME}"
else
  conda create -y -n "${ENV_NAME}" python=3.11
  conda activate "${ENV_NAME}"
fi

echo "[3/4] Install dependencies"
cd "${REPO_DIR}"
python -m pip install --upgrade pip
if [[ -f requirements.txt ]]; then
  python -m pip install -r requirements.txt
fi
python -m pip install optuna ipykernel

echo "[4/4] Register Jupyter kernel"
python -m ipykernel install --user --name="${ENV_NAME}" --display-name="${ENV_NAME}"

echo "Done. Repo=${REPO_DIR} env=${ENV_NAME}"
