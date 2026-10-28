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
