"""Read-only verification: check data/Odds-Historical against its sha manifest.
Usage: python scripts/verify_odds_historical.py [--manifest PATH] [--data-dir PATH]
No data changes. Exits 0 on success, 1 on any mismatch.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_manifest(data_dir: Path) -> Path | None:
    for candidate in sorted(data_dir.rglob("*.sha256")):
        return candidate
    for candidate in sorted(data_dir.rglob("*manifest*.json")):
        return candidate
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Odds-Historical against sha manifest")
    parser.add_argument("--data-dir", default="data/Odds-Historical", help="Data directory to verify")
    parser.add_argument("--manifest", default=None, help="Manifest file (auto-detected if omitted)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        print(f"ERROR: directory not found: {data_dir}")
        sys.exit(1)

    manifest = Path(args.manifest) if args.manifest else find_manifest(data_dir)
    if manifest is None or not manifest.is_file():
        print("ERROR: no manifest found (looked for *.sha256 or *manifest*.json)")
        sys.exit(1)

    print(f"Data dir:  {data_dir}")
    print(f"Manifest:  {manifest}")

    if manifest.suffix == ".sha256":
        mismatches = 0
        checked = 0
        for line in manifest.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                continue
            expected_hash, filename = parts[0], parts[1].strip()
            target = data_dir / filename
            if not target.is_file():
                print(f"  MISSING: {filename}")
                mismatches += 1
                continue
            actual = sha256_file(target)
            checked += 1
            if actual != expected_hash:
                print(f"  MISMATCH: {filename} (expected {expected_hash[:16]}..., got {actual[:16]}...)")
                mismatches += 1
        print(f"Checked {checked} files; {mismatches} mismatches.")
        sys.exit(1 if mismatches else 0)

    # JSON manifest
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    entries = manifest_data if isinstance(manifest_data, list) else manifest_data.get("files", [])
    checked, mismatches = 0, 0
    for entry in entries:
        if isinstance(entry, dict):
            filename = entry.get("path") or entry.get("filename") or entry.get("name", "")
            expected = entry.get("sha256") or entry.get("hash") or entry.get("checksum", "")
        elif isinstance(entry, str):
            filename, expected = entry, ""
        else:
            continue
        if not filename or not expected:
            continue
        target = data_dir / filename
        if not target.is_file():
            print(f"  MISSING: {filename}")
            mismatches += 1
            continue
        actual = sha256_file(target)
        checked += 1
        if actual != expected:
            print(f"  MISMATCH: {filename}")
            mismatches += 1
    print(f"Checked {checked} files; {mismatches} mismatches.")
    sys.exit(1 if mismatches else 0)


if __name__ == "__main__":
    main()