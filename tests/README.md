# Test Surface

`tests/` contains regression and safety checks for the core pipeline and live ops utilities.

## Guidance

- Keep tests aligned with any path, import, or CLI changes performed during cleanup/reorg.
- For cleanup passes, prioritize smoke-path coverage:
  - pipeline build flow
  - projections logging/grading
  - odds board and ledger grading

Run from repo root:

```powershell
python -m pytest
```
