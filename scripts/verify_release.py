import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from image_sheet_splitter.updater import validate_manifest
from image_sheet_splitter.version import APP_VERSION, PORTABLE_EXE_NAME


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", default=str(ROOT / "release"))
    args = parser.parse_args()
    release = Path(args.release_dir)
    manifest_path = release / "update-manifest.json"
    sums_path = release / "SHA256SUMS.txt"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parsed = validate_manifest(manifest)
    if parsed["version"] != APP_VERSION:
        raise SystemExit(f"Manifest version mismatch: {parsed['version']} != {APP_VERSION}")
    asset = release / parsed["asset_name"]
    if not asset.exists():
        raise SystemExit(f"Missing portable asset: {asset}")
    if sha256_file(asset) != parsed["asset_sha256"]:
        raise SystemExit("Portable asset hash mismatch")
    if asset.stat().st_size != parsed["asset_size"]:
        raise SystemExit("Portable asset size mismatch")
    with zipfile.ZipFile(asset) as zf:
        files = [PurePosixPath(n.replace("\\", "/")) for n in zf.namelist() if not n.endswith("/")]
    roots = {p.parts[0] for p in files if p.parts}
    if roots != {"Image Sheet Splitter"}:
        raise SystemExit(f"Portable ZIP must contain one top-level folder: {roots}")
    expected_exe = PurePosixPath("Image Sheet Splitter") / PORTABLE_EXE_NAME
    if expected_exe not in files:
        raise SystemExit(f"Portable ZIP missing {expected_exe}")
    if PurePosixPath("Image Sheet Splitter/README.txt") not in files:
        raise SystemExit("Portable ZIP missing README.txt")
    if not sums_path.exists():
        raise SystemExit("Missing SHA256SUMS.txt")
    expected = {asset.name: sha256_file(asset), manifest_path.name: sha256_file(manifest_path)}
    recorded = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        recorded[name.lstrip("*")] = digest
    if recorded != expected:
        raise SystemExit("SHA256SUMS.txt does not match the portable ZIP and manifest")
    print("Release package structure and manifest hashes verified.")


if __name__ == "__main__":
    main()
