# Paper manuscript

Markdown source, figures, and PDF export for the modeling write-up.

| File | Role |
|---|---|
| `manuscript.md` | Canonical draft (edit this) |
| `manuscript.pdf` | Readable export for review / resume |
| `resume-summary.md` | One-page portfolio summary |
| `resume-summary.pdf` | One-page PDF for resume attachments |
| `manuscript.html` | Intermediate render (regenerated) |
| `figures/` | Figure PNGs used by the manuscript |
| `make_figures.py` | Rebuild figures from reported metrics |
| `render_pdf.py` | MD → HTML → PDF via Playwright |
| `render_resume_summary.py` | Resume summary → PDF |

Deferred modeling follow-ons (Marcel age curve, Steamer/ZiPS, closing lines)
live in `docs/diagrams/04-roadmap.md` under **Later → Deferred external baselines**.

Live monitoring and policy governance now run through the focused notebook split
and simulator tooling in `production/notebooks/results_*.ipynb` and
`production/ops/policy_simulator.py`; cite these as the canonical product-layer
status references instead of embedding volatile daily numbers directly in the manuscript.

Regenerate figures and PDFs after editing:

```powershell
python docs/paper/make_figures.py
python docs/paper/render_pdf.py
python docs/paper/render_resume_summary.py
```

Requires Playwright Chromium (`python -m playwright install chromium`) and
matplotlib (research extras).

## Editorial targets (resume-ready)

- Keep main manuscript at or below ~15 pages in PDF export.
- Prioritize clear narrative over exhaustive logs:
  1. problem + leakage-safe setup,
  2. frozen model results vs baselines,
  3. current live-monitoring status + limitations,
  4. decision-grade next steps.
- Move low-value detail to appendices or `docs/research/`.
