"""Synthetic integration tests for the Stage A prediction-path
reconciliation runner (lineup_path_stage_a.py).

SYNTHETIC ONLY: no real artifacts are read. The two compared routes are
built from genuinely independent computations:
- Route A fixture ("preserved ledger representation"): features and
  p_h3_raw computed by an INDEPENDENT in-test implementation (explicit
  dict-based state math + explicit sigmoid), never by calling the
  adapter for the expected side.
- Route B: the runner's real reconstruction machinery (entity/league
  daily states -> projected lineups -> attach_prior_features ->
  apply_h3_raw with an injected synthetic checkpoint model).

The gate-level mutation tests prove the actual runner refuses PASS on
deliberate route corruption.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from math import exp
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "research" / "offseason_2026"))

from pregame_pa_ext import adapter as ad  # noqa: E402
from pregame_pa_ext import lineup_path_stage_a as sa  # noqa: E402

GAME_DATE = date(2024, 8, 15)
D1 = date(2024, 7, 1)
D2 = date(2024, 7, 15)
P1, P2 = 700001, 700002
W_PRIOR = 150
LG_RATE = 0.6  # league prior before 07-15: 6 K / 10 PAs (see history)


def _models() -> dict:
    """Hand-crafted frozen-checkpoint model dicts (mean=0, scale=1):
    p = sigmoid(intercept + coef . features), identical for both blocks."""
    coef = [0.30, 0.30, 0.50, 0.02, 0.02, -0.10, 0.40, 0.40]
    model = {"mean": [0.0] * 8, "scale": [1.0] * 8, "coef": coef,
             "intercept": -0.55, "features": list(ad.FEAT_H3)}
    return {"block_2024H2": model, "block_2025H1": model}


def _pa_history() -> pl.DataFrame:
    """Pregame PA history. All rows strictly before GAME_DATE.
    Batter states: one 07-01 row -> cold at asof (last state row 07-01,
    prior 0/0); two rows (07-01 + 07-15) -> prior = the 07-01 row."""
    rows = [
        # start-1 batters vs P1
        (D1, P1, 800001, 1), (D1, P1, 800002, 0), (D1, P1, 800005, 1),
        (D1, P1, 800007, 0),
        (D2, P1, 800003, 1), (D2, P1, 800004, 0), (D2, P1, 800006, 0),
        (D2, P1, 800008, 1), (D2, P1, 800009, 0),
        # start-2 batters vs P2
        (D1, P2, 800101, 0), (D1, P2, 800102, 1), (D1, P2, 800105, 1),
        (D1, P2, 800107, 1),
        (D2, P2, 800103, 1), (D2, P2, 800104, 0), (D2, P2, 800106, 0),
        (D2, P2, 800108, 0), (D2, P2, 800109, 1),
        # cross rows giving two batters non-cold two-row history
        (D1, P2, 800003, 1), (D1, P1, 800103, 0),
    ]
    return pl.DataFrame(rows, schema={
        "game_date": pl.Date, "pitcher": pl.Int64,
        "batter": pl.Int64, "y": pl.Int64}, orient="row")


def _batter_state(batter: int) -> dict:
    """INDEPENDENT expected batter state at GAME_DATE (hand math):
    prior = the entity's 07-01 row when a 07-15 row exists (cold-free),
    else the single 07-01 row (prior 0/0 -> cold)."""
    pa = _pa_history().filter(pl.col("batter") == batter)
    rows = pa.rows()
    last_date = max(r[0] for r in rows)
    prior_rows = [r for r in rows if r[0] < last_date]
    k = sum(r[3] for r in prior_rows)
    n = len(prior_rows)
    ew = (sum(r[3] for r in prior_rows) / n) if n else LG_RATE
    return {"k": k, "n": n, "ew": float(ew), "cold": 1 if n == 0 else 0}


def _pitcher_state(pitcher: int) -> dict:
    pa = _pa_history().filter(pl.col("pitcher") == pitcher)
    rows = pa.rows()
    last_date = max(r[0] for r in rows)
    prior_rows = [r for r in rows if r[0] < last_date]
    k = sum(r[3] for r in prior_rows)
    n = len(prior_rows)
    return {"k": k, "n": n, "ew": k / n}


def _expected_features(pitcher: int, batter: int) -> dict:
    """Independent hand-formula FEAT_H3 values (no adapter calls)."""
    ps = _pitcher_state(pitcher)
    bs = _batter_state(batter)
    return {
        "p_pitcher_prior_w150": (ps["k"] + W_PRIOR * LG_RATE)
        / (ps["n"] + W_PRIOR),
        "p_batter_prior_w150": (bs["k"] + W_PRIOR * LG_RATE)
        / (bs["n"] + W_PRIOR),
        "lg_rate": LG_RATE,
        "n_prior_pitcher": ps["n"],
        "n_prior_batter": bs["n"],
        "cold_start": 1 if (ps["n"] == 0 or bs["n"] == 0) else 0,
        "ew_pitcher": ps["ew"],
        "ew_batter": bs["ew"],
    }


def _independent_p(features: dict, model: dict) -> float:
    """INDEPENDENT probability computation (explicit scalar loop by
    feature name; shares no helper with apply_h3_raw)."""
    eta = model["intercept"]
    for c, fname in zip(model["coef"], ad.FEAT_H3):
        eta += c * features[fname]
    return _sigmoid(eta)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + exp(-x))


S1_BATTERS = [800001, 800002, 800003, 800004, 800005, 800006, 800007,
              800008, 800009]
S2_BATTERS = [800101, 800102, 800103, 800104, 800105, 800106, 800107,
              800108, 800109]
STARTS = [(900001, "Top", P1, S1_BATTERS),
          (900002, "Bot", P2, S2_BATTERS)]


def _lineups() -> pl.DataFrame:
    rows = []
    for game_pk, side, pitcher, batters in STARTS:
        row = {"game_pk": game_pk, "side": side, "pitcher": pitcher,
               "game_date": GAME_DATE, "nine_distinct": True}
        for s in range(1, 10):
            row[f"u_slot_{s}"] = batters[s - 1]
        rows.append(row)
    return pl.DataFrame(rows, schema={
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "game_date": pl.Date, "nine_distinct": pl.Boolean,
        **{f"u_slot_{s}": pl.Int64 for s in range(1, 10)},
    })


def _bf() -> pl.DataFrame:
    rows = []
    for game_pk, side, pitcher, _ in STARTS:
        v = np.full(37, 0.0)
        v[:35] = 0.02
        v[35] = 0.20
        v[36] = 0.10
        rows.append({"game_pk": game_pk, "side": side, "pitcher": pitcher,
                     **{f"pmf37_{k}": float(v[k]) for k in range(37)}})
    return pl.DataFrame(rows)


def _ledger_fixture() -> pl.DataFrame:
    """Route A input: an INDEPENDENT ledger representation. Features via
    hand formulas; p_h3_raw via the independent scalar sigmoid. Shares no
    computation with the runner's route B."""
    models = _models()["block_2024H2"]
    rows = []
    for game_pk, side, pitcher, batters in STARTS:
        for slot, batter in enumerate(batters, start=1):
            f = _expected_features(pitcher, batter)
            p = _independent_p(f, models)
            rows.append({
                "game_pk": game_pk, "side": side, "pitcher": pitcher,
                "game_date": GAME_DATE, "slot": slot, "batter": batter,
                "block": "block_2024H2", **f, "p_h3_raw": p})
    schema = {
        "game_pk": pl.Int64, "side": pl.Utf8, "pitcher": pl.Int64,
        "game_date": pl.Date, "slot": pl.Int64, "batter": pl.Int64,
        "block": pl.Utf8,
        **{c: pl.Float64 for c in ad.FEAT_H3},
        "p_h3_raw": pl.Float64,
    }
    return pl.DataFrame(rows, schema=schema)


# --------------------------------------------------------------- PASS path
def test_stage_a_synthetic_pass_end_to_end(tmp_path):
    res = sa.run_stage_a(_ledger_fixture(), _lineups(), _pa_history(),
                         _bf(), _models(), tmp_path / "pass")
    assert res["status"] == "PASS"
    out = tmp_path / "pass"
    assert (out / "receipt_initial.json").exists()
    assert (out / "receipt_final.json").exists()
    assert not (out / "failure_record.json").exists()
    fin = json.loads(
        (out / "receipt_final.json").read_text(encoding="utf-8"))
    m = fin["metrics"]
    assert m["n_dev_starts"] == 2 and m["n_compared"] == 2
    assert m["population_sum_check"] is True
    assert m["i1_mismatched_slots"] == 0
    assert m["i2_max_abs_diff"] <= 1e-12
    assert m["i4_control_max_abs_pmf_diff"] <= 1e-12
    assert fin["acceptance"]["status"] == "PASS"
    assert fin["acceptance"]["receipt_chain"] == res[
        "receipt_initial_sha256"]
    # keyed outputs exist with the right shapes
    i1 = pl.read_parquet(out / "i1_feature_comparison.parquet")
    assert i1.height == 18  # 2 starts x 9 slots
    i3 = pl.read_parquet(out / "i3_pmf_comparison.parquet")
    assert i3.height == 2 * 24
    assert pl.read_parquet(out / "exclusions.parquet").height == 0


def test_stage_a_independent_route_not_tautological(tmp_path):
    """The two routes come from different computations: the route B
    reconstruction must EXACTLY reproduce the independently computed
    fixture features (I1) and agree within 1e-12 on probabilities (I2)
    -- the fixture never calls the adapter for its stored side."""
    res = sa.run_stage_a(_ledger_fixture(), _lineups(), _pa_history(),
                         _bf(), _models(), tmp_path / "taut")
    assert res["status"] == "PASS"


# ------------------------------------------------- gate mutation tests
def test_stage_a_mutation_prob_route_refuses_pass(tmp_path):
    """Deliberate route corruption (ledger p_h3_raw +1e-6 on one slot)
    must make the actual runner refuse PASS: failure receipt, no PASS
    receipt, gate=I2."""
    led = _ledger_fixture().with_columns(
        pl.when((pl.col("game_pk") == 900001) & (pl.col("slot") == 3))
        .then(pl.col("p_h3_raw") + 1e-6)
        .otherwise(pl.col("p_h3_raw")).alias("p_h3_raw"))
    with pytest.raises(sa.StageAFailure, match="I2_prob_mismatch"):
        sa.run_stage_a(led, _lineups(), _pa_history(), _bf(), _models(),
                       tmp_path / "mut_p")
    out = tmp_path / "mut_p"
    assert (out / "failure_record.json").exists()
    assert not (out / "receipt_final.json").exists()
    rec = json.loads(
        (out / "failure_record.json").read_text(encoding="utf-8"))
    assert rec["gate"] == "I2_prob_mismatch"
    assert rec["initial_receipt_sha256"] != ""


def test_stage_a_mutation_feature_refuses_pass(tmp_path):
    """Corrupting a stored feature value must fail I1 (exact)."""
    led = _ledger_fixture().with_columns(
        pl.when((pl.col("game_pk") == 900001) & (pl.col("slot") == 5))
        .then(pl.col("ew_pitcher") + 1e-9)
        .otherwise(pl.col("ew_pitcher")).alias("ew_pitcher"))
    with pytest.raises(sa.StageAFailure, match="I1_feature_mismatch"):
        sa.run_stage_a(led, _lineups(), _pa_history(), _bf(), _models(),
                       tmp_path / "mut_f")
    assert (tmp_path / "mut_f" / "failure_record.json").exists()
    assert not (tmp_path / "mut_f" / "receipt_final.json").exists()


def test_stage_a_mutation_history_input_refuses_pass(tmp_path):
    """Corrupting the RECONSTRUCTION route's input (flip a strictly-prior
    PA-history outcome feeding the pitcher state) must change route B and
    be detected by the feature gate."""
    pa = _pa_history().with_columns(
        pl.when((pl.col("batter") == 800001) & (pl.col("game_date") == D1))
        .then(0).otherwise(pl.col("y")).alias("y"))
    with pytest.raises(sa.StageAFailure, match="I1_feature_mismatch"):
        sa.run_stage_a(_ledger_fixture(), _lineups(), pa, _bf(),
                       _models(), tmp_path / "mut_pa")
    out = tmp_path / "mut_pa"
    assert (out / "failure_record.json").exists()
    assert not (out / "receipt_final.json").exists()


def test_stage_a_semantic_reorder_refuses_pass(tmp_path):
    """Changing the SEMANTIC slot->batter assignment in the ledger is an
    I1 batter mismatch: the PMF comparison is never reached under a
    changed semantic order."""
    led = _ledger_fixture()
    b1 = led.filter((pl.col("game_pk") == 900001)
                    & (pl.col("slot") == 1))["batter"][0]
    b2 = led.filter((pl.col("game_pk") == 900001)
                    & (pl.col("slot") == 2))["batter"][0]
    swapped = led.with_columns(
        pl.when((pl.col("game_pk") == 900001) & (pl.col("slot") == 1))
        .then(b2)
        .when((pl.col("game_pk") == 900001) & (pl.col("slot") == 2))
        .then(b1)
        .otherwise(pl.col("batter")).alias("batter"))
    with pytest.raises(sa.StageAFailure, match="I1_feature_mismatch"):
        sa.run_stage_a(swapped, _lineups(), _pa_history(), _bf(),
                       _models(), tmp_path / "mut_sem")
    rec = json.loads((tmp_path / "mut_sem" / "failure_record.json")
                     .read_text(encoding="utf-8"))
    fields = set(rec["detail"]["examples"][0][4])
    assert "batter" in fields


# ------------------------------------------------- boundary / refusals
def test_stage_a_prohibited_label_refuses_before_output(tmp_path):
    led = _ledger_fixture().with_columns(pl.lit(7).alias("realized_k"))
    with pytest.raises(RuntimeError, match="PROHIBITED_REALIZED_LABELS"):
        sa.run_stage_a(led, _lineups(), _pa_history(), _bf(), _models(),
                       tmp_path / "proh")
    assert not (tmp_path / "proh").exists()


def test_stage_a_write_once(tmp_path):
    sa.run_stage_a(_ledger_fixture(), _lineups(), _pa_history(), _bf(),
                   _models(), tmp_path / "wo")
    with pytest.raises(ValueError, match="write-once violation"):
        sa.run_stage_a(_ledger_fixture(), _lineups(), _pa_history(),
                       _bf(), _models(), tmp_path / "wo")


def test_stage_a_unexpected_block_rejected(tmp_path):
    led = _ledger_fixture()
    extra = led.head(1).with_columns(
        pl.lit("block_2026_preseason").alias("block"))
    with pytest.raises(sa.StageAFailure, match="unexpected block labels"):
        sa.run_stage_a(pl.concat([led, extra]), _lineups(),
                       _pa_history(), _bf(), _models(),
                       tmp_path / "blk")


def test_stage_a_protected_partition_dropped_and_counted(tmp_path):
    """confirm_2025H2 rows are dropped before any comparison and only
    their COUNT is recorded (protected partition never compared)."""
    led = _ledger_fixture()
    prot = led.head(3).with_columns(
        pl.lit("confirm_2025H2").alias("block"))
    res = sa.run_stage_a(pl.concat([led, prot]), _lineups(),
                         _pa_history(), _bf(), _models(),
                         tmp_path / "prot")
    assert res["metrics"]["route_a_protected_rows_dropped"] == 3
    assert res["metrics"]["n_compared"] == 2
    assert res["status"] == "PASS"


def test_stage_a_exclusion_accounting_exclusive_buckets(tmp_path):
    """Structural exclusions are mutually exclusive and the sum check
    holds: start 2 missing from the lineups artifact -> excluded bucket
    missing_lineup_coverage; start 1 compared."""
    lineups = _lineups().filter(pl.col("game_pk") == 900001)
    res = sa.run_stage_a(_ledger_fixture(), lineups, _pa_history(),
                         _bf(), _models(), tmp_path / "excl")
    m = res["metrics"]
    assert m["n_dev_starts"] == 2
    assert m["n_compared"] == 1
    assert m["n_excluded"] == 1
    assert m["exclusion_buckets"] == {"missing_lineup_coverage": 1}
    assert m["population_sum_check"] is True
    assert res["status"] == "PASS"
    ex = pl.read_parquet(tmp_path / "excl" / "exclusions.parquet")
    assert ex.height == 1 and ex["reason"][0] == "missing_lineup_coverage"


def test_stage_a_missing_bf_excluded(tmp_path):
    bf = _bf().filter(pl.col("game_pk") == 900001)
    res = sa.run_stage_a(_ledger_fixture(), _lineups(), _pa_history(),
                         bf, _models(), tmp_path / "nobf")
    m = res["metrics"]
    assert m["exclusion_buckets"] == {"missing_bf": 1}
    assert m["n_compared"] == 1


def test_stage_a_incomplete_slots_excluded(tmp_path):
    """A start with only 8 usable slots in route A cannot be aggregated
    (cycled_cond_mean requires 9) -> structural exclusion, never a PMF
    call."""
    led = _ledger_fixture().filter(
        ~((pl.col("game_pk") == 900001) & (pl.col("slot") == 9)))
    res = sa.run_stage_a(led, _lineups(), _pa_history(), _bf(),
                         _models(), tmp_path / "slots")
    m = res["metrics"]
    assert m["exclusion_buckets"] == {"slot_coverage_below_9": 1}
    assert m["n_compared"] == 1
    assert res["status"] == "PASS"


# ------------------------------- consolidated-review regression tests
def test_stage_a_denominator_before_null_filter(tmp_path):
    """Population denominator is established BEFORE null-probability
    filtering: a dev start whose only slots are unusable (null p_h3_raw)
    must still appear in the denominator and land in an exclusion
    bucket; the sum check holds over the unfiltered population."""
    led = _ledger_fixture()
    # start 2: all 9 slots unusable
    led_null = led.with_columns(
        pl.when(pl.col("game_pk") == 900002)
        .then(pl.lit(None)).otherwise(pl.col("p_h3_raw"))
        .alias("p_h3_raw"))
    res = sa.run_stage_a(led_null, _lineups(), _pa_history(), _bf(),
                         _models(), tmp_path / "denom")
    m = res["metrics"]
    assert m["n_dev_starts"] == 2          # unfiltered denominator
    assert m["n_compared"] == 1            # only start 1
    assert m["exclusion_buckets"] == {"slot_coverage_below_9": 1}
    assert m["population_sum_check"] is True
    assert m["route_a_unusable_slot_rows_dropped"] == 9
    ex = pl.read_parquet(tmp_path / "denom" / "exclusions.parquet")
    assert ex.height == 1
    assert (ex["game_pk"][0], ex["reason"][0]) == (900002,
                                                   "slot_coverage_below_9")


def test_stage_a_partial_null_slots_excluded(tmp_path):
    """A start with SOME unusable slots drops those rows and falls below
    the 9-slot requirement -> excluded, still in the denominator."""
    led = _ledger_fixture()
    led_partial = led.with_columns(
        pl.when((pl.col("game_pk") == 900001)
                & (pl.col("slot") == 9))
        .then(pl.lit(None)).otherwise(pl.col("p_h3_raw"))
        .alias("p_h3_raw"))
    res = sa.run_stage_a(led_partial, _lineups(), _pa_history(), _bf(),
                         _models(), tmp_path / "partial")
    m = res["metrics"]
    assert m["n_dev_starts"] == 2
    assert m["n_compared"] == 1
    assert m["exclusion_buckets"] == {"slot_coverage_below_9": 1}
    assert m["route_a_unusable_slot_rows_dropped"] == 1


def test_stage_a_block_date_inconsistent_fails(tmp_path):
    """A dev-labeled row INSIDE the dev window whose label contradicts
    its game_date must fail loud (block/date consistency, via the reused
    ad.add_block rule). Rows dated past the boundary hit the boundary
    gate instead (separate test)."""
    led = _ledger_fixture()
    bad = led.head(1).with_columns(
        pl.lit(date(2024, 8, 15)).alias("game_date"),
        pl.lit("block_2025H1").alias("block"))  # derived: block_2024H2
    with pytest.raises(sa.StageAFailure,
                       match="block_date_inconsistent"):
        sa.run_stage_a(pl.concat([led, bad]), _lineups(), _pa_history(),
                       _bf(), _models(), tmp_path / "bdate")
    assert (tmp_path / "bdate" / "failure_record.json").exists()


def test_stage_a_dev_rows_past_target_date_boundary(tmp_path):
    """A dev-labeled row dated after the 2025-06-30 target boundary is
    refused (explicit protected-partition/target-date boundary)."""
    led = _ledger_fixture()
    bad = led.head(1).with_columns(
        pl.lit(date(2025, 8, 1)).alias("game_date"))  # derived: confirm
    with pytest.raises(sa.StageAFailure,
                       match="dev_rows_past_target_date_boundary"):
        sa.run_stage_a(pl.concat([led, bad]), _lineups(), _pa_history(),
                       _bf(), _models(), tmp_path / "bound")
    assert (tmp_path / "bound" / "failure_record.json").exists()


def test_stage_a_i4_aggregation_divergence_gate(tmp_path, monkeypatch):
    """White-box aggregation-divergence mutation: I1 and I2 pass, but a
    perturbed PMF aggregation on route B only must fire the I4 control
    gate -- proving the gate fires independently of I1/I2."""
    orig = ad.start_count_pmfs
    calls = {"n": 0}

    def spy(p9_h3, p9_l5, bf37):
        calls["n"] += 1
        out = orig(p9_h3, p9_l5, bf37)
        if calls["n"] % 2 == 0:  # every route-B call
            out = dict(out)
            out["pmf_h3_raw"] = out["pmf_h3_raw"].copy()
            out["pmf_h3_raw"][0] += 1e-9
        return out

    monkeypatch.setattr(sa.ad, "start_count_pmfs", spy)
    with pytest.raises(sa.StageAFailure, match="I4_control_max_diff"):
        sa.run_stage_a(_ledger_fixture(), _lineups(), _pa_history(),
                       _bf(), _models(), tmp_path / "i4")
    out = tmp_path / "i4"
    rec = json.loads((out / "failure_record.json").read_text(
        encoding="utf-8"))
    assert rec["gate"] == "I4_control_max_diff"
    assert rec["detail"]["control_max_abs_pmf_diff"] > 1e-12
    assert not (out / "receipt_final.json").exists()


def test_stage_a_route_b_slot_drop_fails_keying(tmp_path):
    """Route B losing a slot (uncovered lineup slot) while route A has 9
    usable slots must fail the keyed join gate (I1_keying), never a
    silent partial comparison."""
    lineups = _lineups().with_columns(
        pl.when(pl.col("game_pk") == 900002)
        .then(pl.lit(None)).otherwise(pl.col("u_slot_9"))
        .alias("u_slot_9"))
    with pytest.raises(sa.StageAFailure, match="I1_keying"):
        sa.run_stage_a(_ledger_fixture(), lineups, _pa_history(), _bf(),
                       _models(), tmp_path / "keying")
    rec = json.loads((tmp_path / "keying" / "failure_record.json")
                     .read_text(encoding="utf-8"))
    assert rec["gate"] == "I1_keying"


def test_stage_a_route_b_never_reconstructs_protected_targets(tmp_path):
    """Boundary regression (confirmed defect on real artifacts: the
    projected-lineups artifact extends to 2025-09-28, i.e. 2,328 starts
    past the dev boundary): route B must reconstruct ONLY the permitted
    dev-window target population. A confirm-period start present in the
    lineups artifact is never reconstructed, never predicted, and never
    compared."""
    extra_row = {"game_pk": 900003, "side": "Top", "pitcher": 700003,
                 "game_date": date(2025, 8, 1), "nine_distinct": True}
    for s in range(1, 10):
        extra_row[f"u_slot_{s}"] = 800200 + s
    lineups = pl.concat([
        _lineups(),
        pl.DataFrame([extra_row], schema=_lineups().schema),
    ])
    res = sa.run_stage_a(_ledger_fixture(), lineups, _pa_history(),
                         _bf(), _models(), tmp_path / "btarget")
    m = res["metrics"]
    # protected target: reconstructed count == permitted dev targets only
    assert m["route_b_target_population"] == 2
    assert m["n_dev_starts"] == 2 and m["n_compared"] == 2
    assert res["status"] == "PASS"
    # the protected start appears in no keyed output
    i1 = pl.read_parquet(tmp_path / "btarget"
                         / "i1_feature_comparison.parquet")
    assert set(i1["game_pk"].unique().to_list()) == {900001, 900002}


# ----------------------------------------------------- CLI integration
def _run_cli(tmp_path: Path, monkeypatch, ledger=None):  # noqa: ANN001
    paths, shas, models = None, None, None
    ledger = ledger if ledger is not None else _ledger_fixture()
    d = tmp_path / "cli_in"
    d.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, frame in (("ledger", ledger), ("lineups", _lineups()),
                        ("pa-table", _pa_history()), ("bf", _bf())):
        p = d / f"{name}.parquet"
        frame.write_parquet(p)
        files[name] = p
    ckpt = d / "checkpoint.json"
    ad.serialize_checkpoint(_models(), None, ckpt)
    files["checkpoint"] = ckpt
    shas = {name: sa._sha_file(p) for name, p in files.items()}
    seen = {}

    def fake_load_models(path):
        seen["path"] = path
        return _models(), {"synthetic": True}

    monkeypatch.setattr(sa, "_load_models", fake_load_models)
    argv = [
        "--ledger", str(files["ledger"]),
        "--lineups", str(files["lineups"]),
        "--pa-table", str(files["pa-table"]),
        "--checkpoint", str(files["checkpoint"]),
        "--bf", str(files["bf"]),
        "--out-dir", str(tmp_path / "cli_out"),
    ]
    for name in ("ledger", "lineups", "pa-table", "bf", "checkpoint"):
        argv += [f"--expected-{name}-sha", shas[name]]
    return argv, seen, shas, files


def test_stage_a_cli_synthetic_pass(tmp_path, monkeypatch, capsys):
    argv, seen, shas, files = _run_cli(tmp_path, monkeypatch)
    rc = sa.main(argv)
    assert rc == 0
    assert seen["path"] == files["checkpoint"]
    out = tmp_path / "cli_out"
    assert (out / "receipt_final.json").exists()
    fin = json.loads(
        (out / "receipt_final.json").read_text(encoding="utf-8"))
    assert fin["acceptance"]["status"] == "PASS"
    assert fin["inputs"]["file_sha256"]["ledger"] == shas["ledger"]
    assert "prediction_path_equivalent" in capsys.readouterr().out


def test_stage_a_cli_sha_mismatch_refuses(tmp_path, monkeypatch):
    argv, seen, shas, files = _run_cli(tmp_path, monkeypatch)
    argv[argv.index("--expected-ledger-sha") + 1] = "0" * 64
    rc = sa.main(argv)
    assert rc == 2
    assert not (tmp_path / "cli_out").exists()


def test_stage_a_cli_gate_failure_exit_1(tmp_path, monkeypatch, capsys):
    argv, seen, shas, files = _run_cli(
        tmp_path, monkeypatch,
        ledger=_ledger_fixture().with_columns(
            pl.when((pl.col("game_pk") == 900001) & (pl.col("slot") == 4))
            .then(pl.col("p_h3_raw") + 1e-6)
            .otherwise(pl.col("p_h3_raw")).alias("p_h3_raw")))
    rc = sa.main(argv)
    assert rc == 1
    assert "STAGE A FAIL" in capsys.readouterr().err
    assert (tmp_path / "cli_out" / "failure_record.json").exists()
    assert not (tmp_path / "cli_out" / "receipt_final.json").exists()


def test_stage_a_cli_prohibited_label_refuses(tmp_path, monkeypatch,
                                              capsys):
    bad = _ledger_fixture().with_columns(pl.lit(7).alias("realized_k"))
    d = tmp_path / "cli_bad"
    d.mkdir()
    p = d / "ledger.parquet"
    bad.write_parquet(p)
    led_sha = sa._sha_file(p)
    argv, _, _, files = _run_cli(tmp_path, monkeypatch)
    argv[argv.index("--ledger") + 1] = str(p)
    argv[argv.index("--expected-ledger-sha") + 1] = led_sha
    rc = sa.main(argv)
    assert rc == 2
    assert "PROHIBITED_REALIZED_LABELS" in capsys.readouterr().err
    assert not (tmp_path / "cli_out").exists()



# --------------------------------- empty comparison population refused
def test_stage_a_empty_comparison_population_refused(tmp_path):
    """A workload artifact covering ZERO dev starts must refuse with the
    explicit empty_comparison_population gate - never a vacuous
    prediction_path_equivalent PASS (the pre-repair behavior refused
    only via an incidental TypeError in the I2 aggregation)."""
    bf_none = _bf().clear()
    with pytest.raises(sa.StageAFailure, match="empty_comparison_population"):
        sa.run_stage_a(_ledger_fixture(), _lineups(), _pa_history(),
                       bf_none, _models(), tmp_path / "empty_pop")
    out = tmp_path / "empty_pop"
    failure = json.loads((out / "failure_record.json").read_text())
    assert failure["gate"] == "empty_comparison_population"
    assert failure["detail"]["n_dev_starts"] > 0
    assert failure["detail"]["n_compared"] == 0
    assert not (out / "receipt_final.json").exists()
    assert not (out / "i1_feature_comparison.parquet").exists()



# --------------------------- temporal invariants + same-game key identity
def _remap_second_start_to_same_game(led, lin, bf):
    """Fold start 900002 (Bot, P2) into game_pk 900001: two starters in
    ONE game must remain distinct full keys (side, pitcher)."""
    def remap(frame):
        return frame.with_columns(
            pl.when(pl.col("game_pk") == 900002).then(900001)
            .otherwise(pl.col("game_pk")).alias("game_pk"))
    return remap(led), remap(lin), remap(bf)


def test_stage_a_same_game_two_starters_distinct_keys(tmp_path):
    led2, lin2, bf2 = _remap_second_start_to_same_game(
        _ledger_fixture(), _lineups(), _bf())
    res = sa.run_stage_a(led2, lin2, _pa_history(), bf2, _models(),
                         tmp_path / "same_game")
    assert res["status"] == "PASS"
    assert res["metrics"]["n_compared"] == 2
    i1 = pl.read_parquet(Path(res["out_dir"])
                         / "i1_feature_comparison.parquet")
    keys = {(r["game_pk"], r["side"], r["pitcher"])
            for r in i1.iter_rows(named=True)}
    assert keys == {(900001, "Top", P1), (900001, "Bot", P2)}


def test_stage_a_future_pa_rows_cannot_change_outputs(tmp_path):
    """Contamination invariance: PA rows dated STRICTLY AFTER the target
    game date must not move any route-B output (the backward as-of at
    the start's game_date cannot reach them)."""
    res_a = sa.run_stage_a(_ledger_fixture(), _lineups(), _pa_history(),
                           _bf(), _models(), tmp_path / "clean")
    contaminated = pl.concat([
        _pa_history(),
        pl.DataFrame(
            [(date(2024, 9, 1), P1, 800001, 1),
             (date(2024, 9, 1), P2, 800101, 0),
             (date(2025, 1, 1), P1, 800003, 1)],
            schema={"game_date": pl.Date, "pitcher": pl.Int64,
                    "batter": pl.Int64, "y": pl.Int64},
            orient="row")])
    res_b = sa.run_stage_a(_ledger_fixture(), _lineups(), contaminated,
                           _bf(), _models(), tmp_path / "contaminated")
    assert res_a["status"] == "PASS" and res_b["status"] == "PASS"
    for name in ("i1_feature_comparison.parquet",
                 "i2_prob_comparison.parquet",
                 "i3_pmf_comparison.parquet"):
        a = pl.read_parquet(Path(res_a["out_dir"]) / name).sort(
            ["game_pk", "side", "pitcher", "bucket"]
            if "i3" in name else
            ["game_pk", "side", "pitcher", "slot"])
        b = pl.read_parquet(Path(res_b["out_dir"]) / name).sort(
            ["game_pk", "side", "pitcher", "bucket"]
            if "i3" in name else
            ["game_pk", "side", "pitcher", "slot"])
        assert a.rows() == b.rows(), name


def test_stage_a_same_date_pa_y_cannot_enter_state(tmp_path):
    """Same-date PA rows are excluded from the prior state by the
    registered shift(1) (declared date-level convention, mirrors
    pregame-state-v1): their PRESENCE may legitimately create the
    target-date state row (surfacing strictly-earlier history), but
    their y VALUES must not enter any state. Two runs identical except
    for the same-date rows' y must produce byte-identical outputs."""
    same_date_rows = pl.DataFrame(
        [(GAME_DATE, P1, 800001, 1), (GAME_DATE, P1, 800002, 1),
         (GAME_DATE, P2, 800101, 1), (GAME_DATE, P2, 800102, 0)],
        schema={"game_date": pl.Date, "pitcher": pl.Int64,
                "batter": pl.Int64, "y": pl.Int64},
        orient="row")
    pa_y1 = pl.concat([_pa_history(), same_date_rows])
    pa_y0 = same_date_rows.with_columns(
        (pl.lit(1, pl.Int64) - pl.col("y")).alias("y"))
    pa_y0 = pl.concat([_pa_history(), pa_y0])
    # Both runs REFUSE: the appended target-date rows create a state row
    # AT the target date whose shift(1) prior legitimately surfaces the
    # 07-15 rows, which disagrees with the ledger fixture's hand features
    # (built for the baseline no-later-state scenario). The INVARIANT is
    # that flipping the same-date y values changes nothing at all: the
    # two runs' comparison artifacts must be byte-identical, and the
    # refusal gate must be the same I1 representation disagreement in
    # both - never a same-date-outcome effect.
    with pytest.raises(sa.StageAFailure):
        sa.run_stage_a(_ledger_fixture(), _lineups(), pa_y1,
                       _bf(), _models(), tmp_path / "same_y1")
    with pytest.raises(sa.StageAFailure):
        sa.run_stage_a(_ledger_fixture(), _lineups(), pa_y0,
                       _bf(), _models(), tmp_path / "same_y0")
    f_a = json.loads((tmp_path / "same_y1" / "failure_record.json")
                     .read_text())
    f_b = json.loads((tmp_path / "same_y0" / "failure_record.json")
                     .read_text())
    assert f_a["gate"] == "I1_feature_mismatch"
    assert f_b["gate"] == "I1_feature_mismatch"
    # the I1 refusal fires before i2/i3 are written; the i1 artifact
    # carries the full route-A vs route-B per-slot feature rows, which is
    # where a same-date y leak would have to appear
    assert (tmp_path / "same_y1" / "i2_prob_comparison.parquet").exists() \
        is False
    a = pl.read_parquet(tmp_path / "same_y1"
                        / "i1_feature_comparison.parquet").sort(
        ["game_pk", "side", "pitcher", "slot"])
    b = pl.read_parquet(tmp_path / "same_y0"
                        / "i1_feature_comparison.parquet").sort(
        ["game_pk", "side", "pitcher", "slot"])
    assert a.rows() == b.rows()


def test_stage_a_mutating_latest_prior_pa_row_changes_forecasts(tmp_path):
    """Positive control: the latest STRICTLY-PRIOR contributing row is
    live state. Changing batter 800003's 07-01 row (the prior source for
    its 07-15 state) must break route-A/route-B equivalence -> the
    reconciliation refuses with I1_feature_mismatch. If it did NOT
    refuse, the as-of would not be consuming prior history."""
    pa2 = _pa_history().with_columns(
        pl.when((pl.col("game_date") == D1)
                & (pl.col("pitcher") == P2)
                & (pl.col("batter") == 800003))
        .then(0).otherwise(pl.col("y")).alias("y"))
    with pytest.raises(sa.StageAFailure, match="I1_feature_mismatch"):
        sa.run_stage_a(_ledger_fixture(), _lineups(), pa2,
                       _bf(), _models(), tmp_path / "mutated")
    failure = json.loads((tmp_path / "mutant_record" / "failure_record.json")
                         .read_text()) if False else json.loads(
        (tmp_path / "mutated" / "failure_record.json").read_text())
    assert failure["gate"] == "I1_feature_mismatch"
