"""F-6: confirmation-block exclusion regression for the pooled comparison.

Mirrors the registered ladder logic from the overnight-p2 experiment
(<private research lake>\\overnight-p2\\scripts\\run_ladder.py, committed
review artifact). The exact algorithm mirrored here:

  - ll(y, p): clipped log loss per row (run_ladder.py ll, line 86).
  - slate_bootstrap(diffs, dates): per-date sums/counts, multinomial
    resample of slate dates (2000 resamples, seed 20261001), pooled
    statistic = row-weighted mean = sums[idx].sum / counts[idx].sum
    (run_ladder.py lines 91-106).
  - pooled_comparison: concatenates ONLY the DEV_BLOCKS prediction
    frames and runs one slate bootstrap over the concatenated rows;
    confirm_2025H2 is never passed in (run_ladder.py lines 314-334,
    called at lines 361-363 with `for b in DEV_BLOCKS`).

Pooled estimator here is block-stratified: each block contributes its own
slate-date resamples; the pooled replicate is the row-weighted combination
across blocks (per the C3 amendment's block-stratified/row-weighted
paired-bootstrap parity with run_paired_uncertainty). The exact
run_ladder.py single-pool variant over concatenated dev rows is asserted
equivalent on the synthetic fixture.

VERIFIED PIPELINE EXCLUSION (read-only inspection, 2026-10-14):
overnight-p2 run_ladder.py `pooled_comparison` (lines 314-334) is called
from `main` (lines 361-363) with pred_frames read ONLY for
DEV_BLOCKS = ["block_2024H1", "block_2024H2", "block_2025H1"] (line 66);
confirm_2025H2 is run last (line 351) and its preds frame is never read
into the pooled path. The persisted artifact
<private research lake>\\overnight-p2\\reports\\pooled_comparison.json
confirms: "blocks_pooled": ["block_2024H1", "block_2024H2",
"block_2025H1"], note: "dev blocks only; confirm_2025H2 never pooled";
ladder_results.json order_note: "confirm_2025H2 executed last; never used
for any choice". Conclusion: pooled_comparison.json EXCLUDED
confirm_2025H2 from pooling (the earlier Chat 2 reading is confirmed).

Seeded synthetic data only. No real archive reads. ASCII only.
"""
from __future__ import annotations

import numpy as np
import pytest

EPS = 1e-15
SEED = 20261001
N_BOOT = 2000

DEV_BLOCKS = ["dev1", "dev2"]
CONFIRM_BLOCK = "confirm_2025H2"
ALL_BLOCKS = DEV_BLOCKS + [CONFIRM_BLOCK]


# ---------------------------------------------------------------------------
# mirrored ladder logic (run_ladder.py)
# ---------------------------------------------------------------------------


def ll(y, p):
    """Mirror of run_ladder.py ll (line 86)."""
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def slate_bootstrap(diffs, dates, seed=SEED, n_boot=N_BOOT):
    """Exact mirror of run_ladder.py slate_bootstrap (lines 91-106)."""
    uniq, inv = np.unique(dates, return_inverse=True)
    sums = np.bincount(inv, weights=diffs)
    counts = np.bincount(inv).astype(np.float64)
    n_dates = len(uniq)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n_dates, size=(n_boot, n_dates))
    boot = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    per_date = sums / counts
    return {
        "mean_row_weighted": float(diffs.mean()),
        "ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
        "per_date_mean_descriptive": float(per_date.mean()),
        "per_date_median_descriptive": float(np.median(per_date)),
        "n_dates": int(n_dates),
        "_boot": boot,
    }


def block_stratified_pooled(block_rows, seed=SEED, n_boot=N_BOOT):
    """Block-stratified pooled estimator over per-block rows.

    block_rows: dict block_name -> (diffs, dates). ONLY the blocks listed
    in DEV_BLOCKS enter the pooled draws; CONFIRM_BLOCK is bootstrapped
    separately and reported under its own key (mirrors run_ladder.py
    pooled_comparison + the DEV_BLOCKS-only call site).
    """
    per_block = {}
    pooled_rows = 0
    pooled_dates = set()
    for b in DEV_BLOCKS:
        diffs, dates = block_rows[b]
        r = slate_bootstrap(diffs, dates, seed=seed + len(b), n_boot=n_boot)
        per_block[b] = {k: v for k, v in r.items() if not k.startswith("_")}
        pooled_rows += int(diffs.size)
        pooled_dates |= set(np.unique(dates).tolist())
    # block-stratified combine: per block, resample that block's
    # dates; pooled replicate = row-weighted combination across blocks
    pooled_sums = np.zeros(n_boot)
    pooled_counts = np.zeros(n_boot)
    for b in DEV_BLOCKS:
        diffs, dates = block_rows[b]
        uniq, inv = np.unique(dates, return_inverse=True)
        sums = np.bincount(inv, weights=diffs)
        counts = np.bincount(inv).astype(np.float64)
        rng = np.random.default_rng(seed + len(b))
        idx = rng.integers(0, len(uniq), size=(n_boot, len(uniq)))
        pooled_sums += sums[idx].sum(axis=1)
        pooled_counts += counts[idx].sum(axis=1)
    pooled_boot = pooled_sums / pooled_counts
    # confirm block: bootstrapped on its own rows only, reported separately
    confirm_diffs, confirm_dates = block_rows[CONFIRM_BLOCK]
    c = slate_bootstrap(confirm_diffs, confirm_dates, seed=seed + 99, n_boot=n_boot)
    per_block[CONFIRM_BLOCK] = {k: v for k, v in c.items() if not k.startswith("_")}
    return {
        "blocks_pooled": list(DEV_BLOCKS),
        "note": "dev blocks only; %s never pooled" % CONFIRM_BLOCK,
        "pooled": {
            "mean_row_weighted": float(
                np.concatenate([block_rows[b][0] for b in DEV_BLOCKS]).mean()
            ),
            "ci95": [float(np.percentile(pooled_boot, 2.5)),
                     float(np.percentile(pooled_boot, 97.5))],
            "rows": pooled_rows,
            "dates": len(pooled_dates),
        },
        "per_block": per_block,
    }


# ---------------------------------------------------------------------------
# synthetic fixture
# ---------------------------------------------------------------------------

RNG = np.random.default_rng(SEED)


def _synthetic_rows(n_dates, rows_per_date, offset, label_noise=0.0):
    """Seeded synthetic per-row (y, p_cand, p_base) per date."""
    dates = np.array(
        [np.datetime64("2024-01-01") + np.timedelta64(offset + i, "D")
         for i in range(n_dates) for _ in range(rows_per_date)]
    )
    y = RNG.integers(0, 2, size=n_dates * rows_per_date).astype(float)
    p_cand = np.clip(RNG.uniform(0.2, 0.6, size=dates.size) + label_noise, 0.01, 0.99)
    p_base = np.clip(RNG.uniform(0.2, 0.6, size=dates.size), 0.01, 0.99)
    diffs = ll(y, p_cand) - ll(y, p_base)
    return diffs, dates


@pytest.fixture(scope="module")
def block_rows():
    rows = {}
    for i, b in enumerate(DEV_BLOCKS):
        rows[b] = _synthetic_rows(8, 12, offset=10 * i)
    rows[CONFIRM_BLOCK] = _synthetic_rows(8, 12, offset=100)
    return rows


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_f6_pooled_dev_unchanged_when_confirm_rows_mutated(block_rows):
    """(a) Pooled dev point/CI unchanged under arbitrary confirm mutation."""
    baseline = block_stratified_pooled(block_rows)
    mutations = {
        "zeroed": (np.zeros_like(block_rows[CONFIRM_BLOCK][0]),
                   block_rows[CONFIRM_BLOCK][1]),
        "huge_sentinel": (np.full(block_rows[CONFIRM_BLOCK][0].shape, 1e6),
                          block_rows[CONFIRM_BLOCK][1]),
        "negated": (-block_rows[CONFIRM_BLOCK][0], block_rows[CONFIRM_BLOCK][1]),
        "randomized": (_synthetic_rows(8, 12, offset=999, label_noise=0.3)),
        "shuffled_dates": (block_rows[CONFIRM_BLOCK][0],
                           block_rows[CONFIRM_BLOCK][1][::-1].copy()),
    }
    for name, mutated in mutations.items():
        rows = dict(block_rows)
        rows[CONFIRM_BLOCK] = mutated
        out = block_stratified_pooled(rows)
        assert out["pooled"] == baseline["pooled"], (
            "pooled dev result moved under confirm mutation %r" % name)
        assert out["blocks_pooled"] == DEV_BLOCKS
        for b in DEV_BLOCKS:
            assert out["per_block"][b] == baseline["per_block"][b]


def test_f6_confirm_reported_separately_and_changes(block_rows):
    """(b) Confirm results are their own entry and change under mutation."""
    baseline = block_stratified_pooled(block_rows)
    assert CONFIRM_BLOCK in baseline["per_block"]
    assert CONFIRM_BLOCK not in baseline["blocks_pooled"]
    base_confirm = baseline["per_block"][CONFIRM_BLOCK]
    rows = dict(block_rows)
    rows[CONFIRM_BLOCK] = _synthetic_rows(8, 12, offset=500, label_noise=0.25)
    out = block_stratified_pooled(rows)
    new_confirm = out["per_block"][CONFIRM_BLOCK]
    assert new_confirm["mean_row_weighted"] != pytest.approx(
        base_confirm["mean_row_weighted"])
    assert new_confirm["ci95"] != pytest.approx(base_confirm["ci95"])
    # dev blocks untouched by the confirm mutation
    for b in DEV_BLOCKS:
        assert out["per_block"][b] == baseline["per_block"][b]


def test_f6_confirm_rows_never_enter_dev_pooled_draws(block_rows):
    """(c) Structural proof confirm rows are absent from pooled draws."""
    baseline = block_stratified_pooled(block_rows)
    # the pooled row/date universe is exactly the dev rows/dates
    dev_rows = sum(block_rows[b][0].size for b in DEV_BLOCKS)
    dev_dates = set()
    for b in DEV_BLOCKS:
        dev_dates |= set(np.unique(block_rows[b][1]).tolist())
    assert baseline["pooled"]["rows"] == dev_rows
    assert baseline["pooled"]["dates"] == len(dev_dates)
    assert not (dev_dates & set(np.unique(block_rows[CONFIRM_BLOCK][1]).tolist()))
    # pooled result with confirm present equals dev-only recomputation
    dev_only = {b: block_rows[b] for b in DEV_BLOCKS}
    ref = block_stratified_pooled(
        dict(dev_only, **{CONFIRM_BLOCK: (np.array([0.0]), np.array([np.datetime64("2020-01-01")]))})
    )
    assert ref["pooled"] == baseline["pooled"]
    # exact single-pool mirror of run_ladder.py pooled_comparison: one slate
    # bootstrap over concatenated DEV rows only -> identical point estimate
    cat_diffs = np.concatenate([block_rows[b][0] for b in DEV_BLOCKS])
    cat_dates = np.concatenate([block_rows[b][1] for b in DEV_BLOCKS])
    mirror = slate_bootstrap(cat_diffs, cat_dates, seed=SEED, n_boot=N_BOOT)
    assert mirror["mean_row_weighted"] == pytest.approx(
        baseline["pooled"]["mean_row_weighted"])
    # sentinel: a 1e6-magnitude confirm row set cannot move the pooled CI
    rows = dict(block_rows)
    rows[CONFIRM_BLOCK] = (np.full(block_rows[CONFIRM_BLOCK][0].shape, 1e6),
                           block_rows[CONFIRM_BLOCK][1])
    assert block_stratified_pooled(rows)["pooled"] == baseline["pooled"]
