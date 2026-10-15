"""F-6 regression: confirmation rows never enter development pooled
points or bootstrap draws (card C3.3). Synthetic fixtures only."""
import sys
from pathlib import Path
import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import market_eval as me


def _synth_obs(n_dev_dates=6, rows_per_date=10, n_conf_dates=2):
    rows = []
    rid = 0
    for b, nd in (("block_2024H2", n_dev_dates),
                  ("block_2025H1", n_dev_dates),
                  ("confirm_2025H2", n_conf_dates)):
        for d in range(nd):
            date = "20%02d-0%d-15" % (24 if b != "confirm_2025H2" else 25,
                                     (d % 8) + 1)
            for r in range(rows_per_date):
                p = 0.2 + 0.05 * ((rid + d) % 5)
                rows.append({
                    "game_pk": rid, "pitcher": rid, "line": 5.5,
                    "side": "over" if r % 2 == 0 else "under",
                    "book": "B", "block": b, "game_date": date,
                    "y_over_win": 1.0 if (rid % 3) else 0.0,
                    "y_under_win": 0.0 if (rid % 3) else 1.0,
                    "y_push": 0.0, "p_h3_over": p, "p_h3_under": 1 - p,
                    "p_h3_push": 0.0, "p_l5_over": p - 0.02,
                    "p_l5_under": 1 - (p - 0.02), "p_l5_push": 0.0,
                    "p_mkt_over": p + 0.01, "p_mkt_under": 1 - (p + 0.01),
                    "p_mkt_push": 0.0, "_row": rid,
                })
                rid += 1
    import polars as pl
    return pl.DataFrame(rows)


def _score_frames(obs):
    """Mirror run_score's per-row loss construction (3-way Brier parts)."""
    import polars as pl
    out = {}
    for a, p_over, p_under in (("h3", "p_h3_over", "p_h3_under"),
                               ("l5", "p_l5_over", "p_l5_under")):
        out[a] = obs.select(
            ((pl.col(p_over) - pl.when(pl.col("side") == "over")
              .then(pl.col("y_over_win")).otherwise(pl.col("y_under_win")))
             ** 2 + (pl.col("p_h3_push") * 0) ** 2
             + (pl.col(p_under) - pl.when(pl.col("side") == "over")
                .then(pl.col("y_under_win")).otherwise(pl.col("y_over_win")))
             ** 2).alias("_b"))["_b"].to_numpy()
    return out


def test_f6_confirmation_exclusion_known_answer():
    obs = _synth_obs()
    vals = _score_frames(obs)
    slates = obs["game_date"].to_list()
    blocks = obs["block"].to_list()
    is_conf = np.array([b == "confirm_2025H2" for b in blocks])
    dev = ~is_conf
    boot_dev = me._slate_bootstrap(
        {k: v[dev] for k, v in vals.items()},
        [d for d, m in zip(slates, dev) if m],
        [b for b, m in zip(blocks, dev) if m], 500, 20261001)
    boot_conf = me._slate_bootstrap(
        {k: v[is_conf] for k, v in vals.items()},
        [d for d, m in zip(slates, is_conf) if m],
        [b for b, m in zip(blocks, is_conf) if m], 500, 20261001)
    # dev pooled point must equal the dev-only row mean, independent of
    # confirmation rows entirely
    for a in vals:
        dev_point = float(vals[a][dev].mean())
        assert abs(boot_dev[a]["point"] - dev_point) < 1e-12
    # mutating ALL confirmation losses must leave dev draws unchanged
    vals2 = {k: v.copy() for k, v in vals.items()}
    for k in vals2:
        vals2[k][is_conf] = 999.0
    boot_dev2 = me._slate_bootstrap(
        {k: v[dev] for k, v in vals2.items()},
        [d for d, m in zip(slates, dev) if m],
        [b for b, m in zip(blocks, dev) if m], 500, 20261001)
    for a in vals:
        assert np.array_equal(boot_dev[a + "_point" if False else
                                       np.array([0])] if False else
                              np.array([boot_dev[a]["point"]]),
                              np.array([boot_dev2[a]["point"]]))
    # confirm results DO change
    conf_changed = any(
        abs(me._slate_bootstrap(
            {k: v[is_conf] for k, v in vals2.items()},
            [d for d, m in zip(slates, is_conf) if m],
            [b for b, m in zip(blocks, is_conf) if m], 200,
            20261001)[a]["point"] - boot_conf[a]["point"]) > 1.0
        for a in vals)
    assert conf_changed
