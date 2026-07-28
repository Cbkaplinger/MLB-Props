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

Regenerate figures and PDFs after editing:

```powershell
python docs/paper/make_figures.py
python docs/paper/render_pdf.py
python docs/paper/render_resume_summary.py
```

Requires Playwright Chromium (`python -m playwright install chromium`) and
matplotlib (research extras).
