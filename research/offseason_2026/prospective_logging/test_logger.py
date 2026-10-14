"""prospective-logging-v1 fixture tests.

Synthetic fixtures only: no network I/O, no production promotion, no
real-money execution. Covers chain integrity, tamper detection at every
record type, missing-field rejection, raw-response hash recording, and
hash-chain continuity across days.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from logger import (
    Logger,
    canonical_json,
    content_hash,
    hash_raw,
)

D1 = date(2027, 4, 1)
D2 = date(2027, 4, 2)
D3 = date(2027, 4, 3)

BUNDLE_SHA = "a" * 64
BF_PMF37 = [0.001] * 36 + [1.0 - 0.001 * 36]


def _pmf(k_max: int = 24) -> dict:
    p = 1.0 / k_max
    return {"k_max": k_max, "probs": [p] * k_max}


@pytest.fixture
def log(tmp_path):
    return Logger(tmp_path)


def lineup_payload(**over):
    base = {
        "fetched_at": "2027-04-01T12:00:00Z",
        "forecast_cutoff": "2027-04-01T16:05:00Z",
        "game_date": "2027-04-01",
        "game_pk": 745001,
        "team": "NYY",
        "lineup_status": "confirmed",
        "probable_pitcher_id": 677944,
        "slots": [{"slot": 1, "batter_id": 680757, "batter_name": "P1"}],
        "n_slots": 1,
    }
    return {**base, **over}


def forecast_payload(**over):
    base = {
        "forecast_cutoff": "2027-04-01T16:05:00Z",
        "game_date": "2027-04-01",
        "game_pk": 745001,
        "side": "home",
        "pitcher_id": 669302,
        "model": {
            "bundle_name": "bf-bundle-2027-x",
            "bundle_sha256": BUNDLE_SHA,
            "recipe_hash": "b" * 64,
            "arm": "h3_logistic",
        },
        "inputs": {
            "lineup_snapshot_ids": ["c" * 64],
            "bf_pmf37": list(BF_PMF37),
            "p_bar_per_slot": [0.21] * 9,
            "count_pmf": _pmf(24),
        },
        "exposure": {"e_n": 18.4, "point_exposure_n": 18},
    }
    return {**base, **over}


def market_payload(**over):
    base = {
        "captured_at": "2027-04-01T16:00:00Z",
        "game_date": "2027-04-01",
        "game_pk": 745001,
        "pitcher_id": 669302,
        "book": "fanduel",
        "line": 6.5,
        "side": "over_under",
        "over_price": -115,
        "under_price": -105,
        "source": "sharpapi",
    }
    return {**base, **over}


def settlement_payload(**over):
    base = {
        "game_pk": 745001,
        "pitcher_id": 669302,
        "final_k": 7,
        "final_bf": 23,
        "game_status": "final",
        "void_reason": None,
        "push_semantics": {
            "half_lines_cannot_push": True,
            "integer_line_push": "void_refund",
        },
        "corrects_record_id": None,
        "probable_pitcher_reconciliation": {
            "probable_pitcher_id": 669302,
            "matches_probable": True,
        },
        "settled_at": "2027-04-02T12:00:00Z",
    }
    return {**base, **over}


PAYLOADS = {
    "lineup_snapshot": lineup_payload,
    "forecast_record": forecast_payload,
    "market_snapshot": market_payload,
    "settlement_record": settlement_payload,
}
ALL_TYPES = list(PAYLOADS)


# ---------------------------------------------------------------- chain
# integrity, every record type


@pytest.mark.parametrize("rtype", ALL_TYPES)
def test_chain_integrity_per_record_type(log, rtype):
    for i in range(3):
        rid = log.append(rtype, D1, PAYLOADS[rtype](game_pk=745001 + i))
        assert isinstance(rid, str) and len(rid) == 64
    res = log.verify_chain(rtype, D1)
    assert res["verified"] is True
    assert res["n_records"] == 3
    recs = log.read_records(rtype, D1)
    assert recs[0]["prev_hash"] is None
    for a, b in zip(recs, recs[1:]):
        assert b["prev_hash"] == a["record_id"]


def test_record_id_excludes_itself_but_covers_prev_hash(log):
    rid = log.append("lineup_snapshot", D1, lineup_payload())
    rec = log.read_records("lineup_snapshot", D1)[0]
    assert rec["record_id"] == rid
    body = {k: v for k, v in rec.items() if k != "record_id"}
    assert content_hash(body) == rid
    assert "prev_hash" in body
    tampered = dict(body)
    tampered["prev_hash"] = "0" * 64
    assert content_hash(tampered) != rid


# ---------------------------------------------------------- raw hashing


def test_raw_response_hash_recorded_at_append(log):
    import hashlib

    raw = b'{"vendor":"rotogrinders","rows":[1,2,3]}'
    log.append_lineup_snapshot(D1, lineup_payload(), raw=raw)
    rec = log.read_records("lineup_snapshot", D1)[0]
    assert rec["raw_payload_sha256"] == hashlib.sha256(raw).hexdigest()


def test_raw_hash_changes_with_bytes_and_is_chain_covered(log):
    log.append_lineup_snapshot(D1, lineup_payload(), raw=b"payload-a")
    log.append_lineup_snapshot(D1, lineup_payload(game_pk=2), raw=b"payload-b")
    recs = log.read_records("lineup_snapshot", D1)
    assert recs[0]["raw_payload_sha256"] != recs[1]["raw_payload_sha256"]
    # raw hash is part of the hashed body -> tampering raw hash detected
    path = log._file("lineup_snapshot", D1)
    rec = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    rec["raw_payload_sha256"] = "d" * 64
    lines = [canonical_json(rec)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="record_id mismatch"):
        log.verify_chain("lineup_snapshot", D1)


def test_hash_raw_rejects_non_bytes():
    with pytest.raises(ValueError, match="raw bytes"):
        hash_raw("not bytes")


# --------------------------------------------------- tamper detection,
# every record type


def _mutate_row(log, rtype, d, row_idx, mutate):
    path = log._file(rtype, d)
    lines = path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[row_idx])
    mutate(rec)
    lines[row_idx] = canonical_json(rec)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.parametrize("rtype", ALL_TYPES)
@pytest.mark.parametrize("mode", ["payload_field", "prev_hash",
                                  "drop_row", "reorder"])
def test_tamper_detection_every_type_every_mode(log, rtype, mode):
    for i in range(3):
        log.append(rtype, D1, PAYLOADS[rtype](game_pk=745001 + i))

    def mutate(rec):
        if mode == "payload_field":
            if rtype == "lineup_snapshot":
                rec["n_slots"] = 99
            elif rtype == "forecast_record":
                rec["exposure"]["e_n"] = 99.0
            elif rtype == "market_snapshot":
                rec["over_price"] = 999
            else:
                rec["final_k"] = 99
        elif mode == "prev_hash":
            rec["prev_hash"] = "e" * 64
        elif mode == "drop_row":
            rec["record_type"] = rec["record_type"]  # no-op marker
        return rec

    if mode == "drop_row":
        path = log._file(rtype, D1)
        lines = path.read_text(encoding="utf-8").splitlines()
        del lines[1]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif mode == "reorder":
        path = log._file(rtype, D1)
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[0], lines[1] = lines[1], lines[0]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        _mutate_row(log, rtype, D1, 1, mutate)

    with pytest.raises(AssertionError):
        log.verify_chain(rtype, D1)


def test_tamper_last_record_still_detected(log):
    log.append("market_snapshot", D1, market_payload())
    rid1 = log.append("market_snapshot", D1,
                      market_payload(game_pk=745002))
    _mutate_row(log, "market_snapshot", D1, 1,
                lambda r: r.update(over_price=-120))
    with pytest.raises(AssertionError, match="record_id mismatch"):
        log.verify_chain("market_snapshot", D1)
    # head alone cannot be trusted after tamper
    assert rid1 is not None


def test_settlement_correction_is_new_record_not_edit(log):
    rid1 = log.append_settlement_record(D1, settlement_payload())
    correction = settlement_payload(
        game_status="final", void_reason=None, final_k=8,
        corrects_record_id=rid1)
    rid2 = log.append_settlement_record(D1, correction)
    assert rid1 != rid2
    res = log.verify_chain("settlement_record", D1)
    assert res["n_records"] == 2
    recs = log.read_records("settlement_record", D1)
    assert recs[1]["corrects_record_id"] == rid1
    assert recs[0]["final_k"] == 7  # original untouched


# ------------------------------------------------- missing-field rejection


@pytest.mark.parametrize("rtype", ALL_TYPES)
def test_missing_top_level_field_rejected(log, rtype):
    required = {
        "lineup_snapshot": "team",
        "forecast_record": "pitcher_id",
        "market_snapshot": "book",
        "settlement_record": "final_k",
    }[rtype]
    payload = PAYLOADS[rtype]()
    del payload[required]
    with pytest.raises(ValueError, match="missing required fields"):
        log.append(rtype, D1, payload)
    assert log.read_records(rtype, D1) == []


@pytest.mark.parametrize(
    "parent,field",
    [("model", "bundle_sha256"), ("model", "arm"),
     ("inputs", "bf_pmf37"), ("inputs", "count_pmf")])
def test_forecast_missing_nested_field_rejected(log, parent, field):
    payload = forecast_payload()
    del payload[parent][field]
    with pytest.raises(ValueError, match=f"{parent}.*missing required"):
        log.append_forecast_record(D1, payload)
    assert log.read_records("forecast_record", D1) == []


def test_forecast_bad_bf_pmf37_rejected(log):
    with pytest.raises(ValueError, match="bf_pmf37"):
        log.append_forecast_record(
            D1, forecast_payload(**{"inputs": {
                "lineup_snapshot_ids": ["c" * 64],
                "bf_pmf37": [0.5] * 10,  # wrong length
                "p_bar_per_slot": [0.21] * 9,
                "count_pmf": _pmf(24)}}))
    with pytest.raises(ValueError, match="must sum to 1"):
        log.append_forecast_record(
            D1, forecast_payload(**{"inputs": {
                "lineup_snapshot_ids": ["c" * 64],
                "bf_pmf37": [0.5] * 37,
                "p_bar_per_slot": [0.21] * 9,
                "count_pmf": _pmf(24)}}))
    assert log.read_records("forecast_record", D1) == []


def test_forecast_count_pmf_shape_rejected(log):
    bad = _pmf(24)
    bad["probs"] = bad["probs"][:-1]
    with pytest.raises(ValueError, match="length must equal k_max"):
        log.append_forecast_record(
            D1, forecast_payload(**{"inputs": {
                "lineup_snapshot_ids": ["c" * 64],
                "bf_pmf37": list(BF_PMF37),
                "p_bar_per_slot": [0.21] * 9,
                "count_pmf": bad}}))


def test_forecast_bad_bundle_sha_rejected(log):
    with pytest.raises(ValueError, match="bundle_sha256"):
        log.append_forecast_record(
            D1, forecast_payload(**{"model": {
                "bundle_name": "x", "bundle_sha256": "not-a-hash",
                "recipe_hash": "b" * 64, "arm": "h3_logistic"}}))


def test_settlement_missing_reconciliation_rejected(log):
    payload = settlement_payload()
    del payload["probable_pitcher_reconciliation"]["matches_probable"]
    with pytest.raises(ValueError,
                       match="probable_pitcher_reconciliation"):
        log.append_settlement_record(D1, payload)


def test_settlement_non_integer_final_k_rejected(log):
    with pytest.raises(ValueError, match="final_k"):
        log.append_settlement_record(D1, settlement_payload(final_k=7.5))


def test_unknown_record_type_rejected(log):
    with pytest.raises(ValueError, match="unknown record type"):
        log.append("gossip", D1, {"x": 1})


# ------------------------------------------- cross-day chain continuity


@pytest.mark.parametrize("rtype", ALL_TYPES)
def test_chain_continuity_across_days(log, rtype):
    heads = {}
    for d in (D1, D2, D3):
        for i in range(2):
            log.append(rtype, d, PAYLOADS[rtype](game_pk=745001 + i))
        res = log.verify_chain(rtype, d)
        assert res["verified"] is True
        heads[d] = res["head"]
    recs_d2 = log.read_records(rtype, D2)
    recs_d3 = log.read_records(rtype, D3)
    assert recs_d2[0]["prev_day_head"] == heads[D1]
    assert recs_d2[0]["prev_hash"] is None  # each day re-anchors
    assert recs_d3[0]["prev_day_head"] == heads[D2]
    assert recs_d3[0]["prev_day_head"] != heads[D1]


def test_cross_day_tamper_detected_from_later_day(log):
    log.append_lineup_snapshot(D1, lineup_payload())
    log.append_lineup_snapshot(D2, lineup_payload(game_pk=745002))
    assert log.verify_chain("lineup_snapshot", D2)["verified"]
    # mutate day 1 in place -> day 1 chain breaks
    _mutate_row(log, "lineup_snapshot", D1, 0,
                lambda r: r.update(n_slots=99))
    with pytest.raises(AssertionError):
        log.verify_chain("lineup_snapshot", D1)
    # day 2 verification now fails too: the prior day's recomputed chain
    # head is checked through its own verify (record_id mismatch there).
    with pytest.raises(AssertionError):
        log.verify_chain("lineup_snapshot", D2)


def test_backfill_between_days_detected(log):
    log.append("market_snapshot", D1, market_payload())
    log.append("market_snapshot", D3, market_payload(game_pk=745003))
    assert log.verify_chain("market_snapshot", D3)["verified"]
    # a late backfill of D2 changes what D3's prev_day_head should be
    log.append("market_snapshot", D2, market_payload(game_pk=745002))
    with pytest.raises(AssertionError, match="day linkage break"):
        log.verify_chain("market_snapshot", D3)


def test_day_link_check_can_be_disabled(log):
    log.append("market_snapshot", D1, market_payload())
    log.append("market_snapshot", D2, market_payload(game_pk=745002))
    log.record_daily_head("market_snapshot", D1)
    res = log.verify_chain("market_snapshot", D2, check_day_link=False)
    assert res["verified"] is True


def test_record_daily_head_state_file(log):
    log.append("lineup_snapshot", D1, lineup_payload())
    log.append("lineup_snapshot", D1, lineup_payload(game_pk=745002))
    entry = log.record_daily_head("lineup_snapshot", D1)
    assert entry["n_records"] == 2
    state = json.loads((log.base / "chain_state.json").read_text(
        encoding="utf-8"))
    assert state == [entry]
    # verify head matches the file's last record_id
    recs = log.read_records("lineup_snapshot", D1)
    assert entry["last_hash"] == recs[-1]["record_id"]
