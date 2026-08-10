# Model Results Analysis

This folder is the streamlined analysis surface for daily model-result review.
It is intentionally smaller and more narrative than
`production/notebooks/results_dashboard.ipynb`.

## Files

- `model_results_story.ipynb`
  - concise, ordered notebook for daily decision-making
  - focuses on model-quality diagnostics and actionable next steps

## Purpose split

- `production/notebooks/results_dashboard.ipynb`
  - full operational dashboard and deep-dive research cells
- `analysis/model_results/model_results_story.ipynb`
  - executive storyline and highest-ROI diagnostics only

## Recommended daily flow

1. Run `production/notebooks/results_dashboard.ipynb` sections that refresh artifacts.
2. Run `analysis/model_results/model_results_story.ipynb` top-to-bottom.
3. Read the scorecard section first, then review flagged slices.
