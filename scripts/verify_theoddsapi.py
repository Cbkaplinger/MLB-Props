"""Verify data/Odds-Historical/theoddsapi/ against archive_manifest_2026-10-06.json.
Read-only. Uses chunked hashing (1 MB blocks) to handle large parquets."""
import hashlib
import json
from pathlib import Path

DATA = Path(r'C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Odds-Historical\theoddsapi')
MANIFEST = DATA / 'archive_manifest_2026-10-06.json'
CHUNK = 1 << 20  # 1 MB

d = json.loads(MANIFEST.read_text(encoding='utf-8'))
expected = d.get('sha256_16', {})
files_meta = d.get('files', {})

mismatches, missing, ok = [], [], 0
print(f'archive: {d.get("archive")}')
print(f'built: {d.get("built")}')
print()

for fname, meta in files_meta.items():
    fpath = DATA / fname
    expected_sha = meta.get('sha256_16', '')
    expected_rows = meta.get('rows', '?')
    if not fpath.is_file():
        print(f'  MISSING: {fname}')
        missing.append(fname)
        continue
    # chunked hash (first 16 hex chars to match sha256_16)
    h = hashlib.sha256()
    with open(fpath, 'rb') as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            h.update(block)
    actual = h.hexdigest()[:16]
    if actual == expected_sha:
        print(f'  OK: {fname} ({expected_rows:,} rows, sha256_16={actual})')
        ok += 1
    else:
        print(f'  MISMATCH: {fname} (expected {expected_sha}, got {actual})')
        mismatches.append(fname)

print(f'\nResult: {ok} OK, {len(mismatches)} mismatched, {len(missing)} missing')
