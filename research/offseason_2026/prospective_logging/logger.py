"""prospective-logging-v1: logger for 2027 pregame capture.

Implements LOGGING_SPEC.md - NO network I/O, NO live calls, NO scheduler.
Append-only JSONL, one file per (record_type, game_date); daily hash
chain where each record's `record_id` is the sha256 of the canonical
JSON of the record WITHOUT `record_id` (so `prev_hash` is covered by the
hash and any mutation of a written record is detectable by recomputing).

Extensions in this version (prospective-logging-v1 implementation pass):
- raw vendor-response hashing: `hash_raw` + `raw=` kwargs stamp
  `raw_payload_sha256` at append time (backlog 2026-10-09 finding).
- typed append helpers validate the nested structures the spec requires:
  forecast records must carry bundle sha, BF PMF (37 cats), p_bar, count
  PMF, and cutoff; settlement records must carry final BF, void/push
  semantics, and the probable-vs-realized reconciliation field.
- cross-day chain linkage: the first record of a new day stamps the
  previous day's head as `prev_day_head` (covered by its record_id), so
  `verify_chain` checks within-day continuity AND day-to-day continuity.
- `record_daily_head` writes `chain_state.json` per the spec.

CLI smoke test: python logger.py
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA_VERSIONS = {
    "lineup_snapshot": "lineup_snapshot/1",
    "forecast_record": "forecast_record/1",
    "market_snapshot": "market_snapshot/1",
    "settlement_record": "settlement_record/1",
}
REQUIRED_FIELDS = {
    "lineup_snapshot": ["fetched_at", "forecast_cutoff", "game_date",
                        "game_pk", "team", "lineup_status", "slots"],
    "forecast_record": ["forecast_cutoff", "game_date", "game_pk",
                        "side", "pitcher_id", "model", "inputs"],
    "market_snapshot": ["captured_at", "game_date", "game_pk",
                        "pitcher_id", "book", "line", "side",
                        "over_price", "under_price"],
    "settlement_record": ["game_pk", "pitcher_id", "final_k", "final_bf",
                          "settled_at", "push_semantics",
                          "probable_pitcher_reconciliation"],
}
NESTED_REQUIRED_FIELDS = {
    "forecast_record": {
        "model": ["bundle_sha256", "recipe_hash", "arm"],
        "inputs": ["lineup_snapshot_ids", "bf_pmf37", "p_bar_per_slot",
                   "count_pmf"],
    },
    "settlement_record": {
        "push_semantics": ["half_lines_cannot_push", "integer_line_push"],
        "probable_pitcher_reconciliation": ["probable_pitcher_id",
                                            "matches_probable"],
    },
}
BF_PMF37_LEN = 37
COUNT_PMF_KEYS = ["k_max", "probs"]


def canonical_json(record: dict) -> str:
    """Canonical form: sorted keys, no whitespace, UTF-8."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def content_hash(record: dict) -> str:
    """sha256 over the canonical JSON of the record WITHOUT record_id.
    prev_hash IS included, so the chain is tamper-evident end to end."""
    body = {k: v for k, v in record.items() if k != "record_id"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def hash_raw(raw: bytes) -> str:
    """sha256 of the raw vendor-response bytes, taken at append time.
    The bytes themselves are never stored - only this digest."""
    if not isinstance(raw, (bytes, bytearray)):
        raise ValueError("raw must be raw bytes, not str or other")
    return hashlib.sha256(bytes(raw)).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_probs(probs, name: str, require_sum_one: bool,
                    tol: float = 1e-6) -> None:
    if not isinstance(probs, (list, tuple)) or not probs:
        raise ValueError(f"{name} must be a non-empty list of floats")
    for p in probs:
        if not isinstance(p, (int, float)) or isinstance(p, bool):
            raise ValueError(f"{name} entries must be numbers")
        if p < 0.0 or p > 1.0:
            raise ValueError(f"{name} entries must lie in [0, 1]")
    if require_sum_one and abs(sum(probs) - 1.0) > tol:
        raise ValueError(f"{name} must sum to 1 (got {sum(probs)})")


def _validate_payload(record_type: str, payload: dict) -> None:
    for parent, fields in NESTED_REQUIRED_FIELDS.get(record_type, {}).items():
        sub = payload.get(parent)
        if not isinstance(sub, dict):
            raise ValueError(f"{record_type}.{parent} must be an object")
        missing = [f for f in fields if f not in sub]
        if missing:
            raise ValueError(
                f"{record_type}.{parent} missing required fields: {missing}")
    if record_type == "forecast_record":
        inputs = payload["inputs"]
        bf = inputs.get("bf_pmf37")
        if not isinstance(bf, (list, tuple)) or len(bf) != BF_PMF37_LEN:
            raise ValueError(
                f"inputs.bf_pmf37 must have {BF_PMF37_LEN} categories "
                f"(36 exact + 1 overflow), got {len(bf) if isinstance(bf, (list, tuple)) else type(bf).__name__}")
        _validate_probs(bf, "inputs.bf_pmf37", require_sum_one=True)
        # p_bar_per_slot is a probability VECTOR (9 per-PA rates), not a
        # distribution - range-checked, not sum-checked.
        _validate_probs(inputs.get("p_bar_per_slot"),
                        "inputs.p_bar_per_slot", require_sum_one=False)
        cp = inputs.get("count_pmf")
        if not isinstance(cp, dict):
            raise ValueError("inputs.count_pmf must be an object")
        missing = [k for k in COUNT_PMF_KEYS if k not in cp]
        if missing:
            raise ValueError(
                f"inputs.count_pmf missing required fields: {missing}")
        k_max = cp["k_max"]
        if not isinstance(k_max, int) or isinstance(k_max, bool) or k_max < 1:
            raise ValueError("inputs.count_pmf.k_max must be a positive int")
        if not isinstance(cp["probs"], (list, tuple)) \
                or len(cp["probs"]) != k_max:
            raise ValueError(
                "inputs.count_pmf.probs length must equal k_max "
                f"({len(cp['probs']) if isinstance(cp['probs'], (list, tuple)) else type(cp['probs']).__name__} "
                f"!= {k_max})")
        _validate_probs(cp["probs"], "inputs.count_pmf.probs",
                        require_sum_one=True)
        model = payload["model"]
        bundle_sha = model.get("bundle_sha256")
        if (not isinstance(bundle_sha, str) or len(bundle_sha) != 64
                or any(c not in "0123456789abcdef" for c in bundle_sha)):
            raise ValueError(
                "model.bundle_sha256 must be a 64-char lowercase hex sha256")
    if record_type == "settlement_record":
        for f in ("final_k", "final_bf"):
            v = payload.get(f)
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise ValueError(f"{f} must be a non-negative integer")
        rec_ = payload["probable_pitcher_reconciliation"]
        if not isinstance(rec_.get("matches_probable"), bool):
            raise ValueError(
                "probable_pitcher_reconciliation.matches_probable "
                "must be a boolean")


class Logger:
    """Append-only JSONL logger with daily hash chaining. File I/O only;
    the caller owns scheduling and any network fetch."""

    def __init__(self, base_dir):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def _file(self, record_type: str, d: date) -> Path:
        d_dir = self.base / "records" / record_type
        d_dir.mkdir(parents=True, exist_ok=True)
        return d_dir / f"{d.isoformat()}.jsonl"

    def _daily_files(self, record_type: str) -> list:
        d_dir = self.base / "records" / record_type
        if not d_dir.exists():
            return []
        return sorted(d_dir.glob("*.jsonl"))

    def _last_hash(self, path: Path):
        if not path.exists():
            return None
        prev = None
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    prev = json.loads(line)["record_id"]
        return prev

    def _prior_day_head(self, record_type: str, d: date):
        """Head (last record_id) of the latest daily file STRICTLY BEFORE
        d, or None. Used for the cross-day `prev_day_head` stamp."""
        prior = None
        for p in self._daily_files(record_type):
            try:
                file_date = date.fromisoformat(p.stem)
            except ValueError:
                continue
            if file_date < d:
                prior = p
        if prior is None:
            return None
        return self._last_hash(prior)

    def append(self, record_type: str, d: date, payload: dict,
               raw: bytes | None = None) -> str:
        if record_type not in SCHEMA_VERSIONS:
            raise ValueError(f"unknown record type: {record_type}")
        missing = [f for f in REQUIRED_FIELDS.get(record_type, [])
                   if f not in payload]
        if missing:
            raise ValueError(
                f"{record_type} missing required fields: {missing}")
        _validate_payload(record_type, payload)
        rec = {
            "record_type": record_type,
            "schema_version": SCHEMA_VERSIONS[record_type],
            "prev_hash": self._last_hash(self._file(record_type, d)),
            **payload,
        }
        if raw is not None:
            rec["raw_payload_sha256"] = hash_raw(raw)
        path = self._file(record_type, d)
        if not path.exists():
            rec["prev_day_head"] = self._prior_day_head(record_type, d)
        rec["record_id"] = content_hash(rec)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(canonical_json(rec) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return rec["record_id"]

    # typed append helpers (one per record type in the spec) -----------
    def append_lineup_snapshot(self, d: date, payload: dict,
                               raw: bytes | None = None) -> str:
        return self.append("lineup_snapshot", d, payload, raw=raw)

    def append_forecast_record(self, d: date, payload: dict) -> str:
        return self.append("forecast_record", d, payload)

    def append_market_snapshot(self, d: date, payload: dict,
                               raw: bytes | None = None) -> str:
        return self.append("market_snapshot", d, payload, raw=raw)

    def append_settlement_record(self, d: date, payload: dict) -> str:
        return self.append("settlement_record", d, payload)

    # verification -----------------------------------------------------
    def verify_chain(self, record_type: str, d: date,
                     check_day_link: bool = True) -> dict:
        """Recompute the full daily chain; raises on any break. When
        check_day_link is true, also verifies the first record's
        `prev_day_head` equals the head of the latest earlier day."""
        path = self._file(record_type, d)
        prev = None
        n = 0
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                n += 1
                rec = json.loads(line)
                rid = rec.get("record_id")
                if content_hash(rec) != rid:
                    raise AssertionError(
                        f"record_id mismatch at row {n} of {path}")
                if rec.get("prev_hash") != prev:
                    raise AssertionError(
                        f"chain break at row {n} of {path}")
                prev = rid
        if check_day_link and n > 0:
            first = self.read_records(record_type, d)[0]
            # Recompute the prior day's head through its own verify, so a
            # tampered earlier day fails later-day verification too.
            prior = None
            for p in self._daily_files(record_type):
                try:
                    file_date = date.fromisoformat(p.stem)
                except ValueError:
                    continue
                if file_date < d:
                    prior = file_date
            if prior is not None:
                prior_res = self.verify_chain(record_type, prior,
                                              check_day_link=True)
                if first.get("prev_day_head") != prior_res["head"]:
                    raise AssertionError(
                        f"day linkage break at {record_type} "
                        f"{d.isoformat()}: prev_day_head "
                        f"{first.get('prev_day_head')} != head of "
                        f"{prior.isoformat()} {prior_res['head']}")
        return {"record_type": record_type, "date": d.isoformat(),
                "n_records": n, "head": prev, "verified": True}

    def record_daily_head(self, record_type: str, d: date) -> dict:
        """Write the chain head to chain_state.json (spec: after the last
        append of the day). Returns the state row written."""
        res = self.verify_chain(record_type, d)
        state_path = self.base / "chain_state.json"
        state = []
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        entry = {"record_type": record_type, "date": d.isoformat(),
                 "last_hash": res["head"], "n_records": res["n_records"]}
        state = [s for s in state
                 if not (s["record_type"] == record_type
                         and s["date"] == entry["date"])]
        state.append(entry)
        state_path.write_text(json.dumps(state, indent=2) + "\n",
                              encoding="utf-8")
        return entry

    def read_records(self, record_type: str, d: date) -> list:
        path = self._file(record_type, d)
        if not path.exists():
            return []
        out = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    out.append(json.loads(line))
        return out


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        log = Logger(td)
        d0 = date(2027, 4, 1)
        r1 = log.append_lineup_snapshot(d0, {
            "fetched_at": utc_now_iso(), "forecast_cutoff": utc_now_iso(),
            "game_date": d0.isoformat(), "game_pk": 745001,
            "team": "NYY", "lineup_status": "confirmed",
            "probable_pitcher_id": 677944,
            "slots": [{"slot": 1, "batter_id": 680757,
                       "batter_name": "Player One"}],
            "n_slots": 1,
        }, raw=b'{"vendor":"payload-1"}')
        r2 = log.append_lineup_snapshot(d0, {
            "fetched_at": utc_now_iso(), "forecast_cutoff": utc_now_iso(),
            "game_date": d0.isoformat(), "game_pk": 745002,
            "team": "BOS", "lineup_status": "projected",
            "probable_pitcher_id": 622491,
            "slots": [{"slot": 1, "batter_id": 608070,
                       "batter_name": "Player Two"}],
            "n_slots": 1,
        })
        assert r1 != r2
        res = log.verify_chain("lineup_snapshot", d0)
        print("smoke verify:", res)
        assert res["n_records"] == 2
        # tamper: mutate a written record in place -> verify must fail
        p = (Path(td) / "records" / "lineup_snapshot"
             / f"{d0.isoformat()}.jsonl")
        rec = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
        rec["n_slots"] = 99
        lines = [canonical_json(rec)]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            log.verify_chain("lineup_snapshot", d0)
            raise SystemExit("TAMPER NOT DETECTED - BAD")
        except AssertionError as exc:
            print("tamper detected as expected:", exc)
        print("smoke test PASSED")
