import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from image_sheet_splitter.updater import create_release_manifest
from image_sheet_splitter.version import APP_VERSION, PORTABLE_EXE_NAME


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_notes(version):
    path = ROOT / "docs" / "releases" / f"{version}.md"
    if not path.exists():
        return [], False
    lines = path.read_text(encoding="utf-8").splitlines()
    bullets = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets[:5], len(bullets) > 5 or len(lines) > 20


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True)
    parser.add_argument("--out", default=str(ROOT / "release"))
    args = parser.parse_args()

    exe = Path(args.exe).resolve()
    if not exe.exists():
        raise SystemExit(f"EXE not found: {exe}")

    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    portable_folder = out / "Image Sheet Splitter"
    portable_folder.mkdir()
    target_exe = portable_folder / PORTABLE_EXE_NAME
    shutil.copy2(exe, target_exe)
    shutil.copy2(ROOT / "docs" / "portable-readme.txt", portable_folder / "README.txt")

    asset_name = "Image_Sheet_Splitter_Windows_x64_Portable.zip"
    asset_path = out / asset_name
    with zipfile.ZipFile(asset_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(portable_folder.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(out))

    digest = sha256_file(asset_path)
    notes, has_more = release_notes(APP_VERSION)
    manifest = create_release_manifest(
        APP_VERSION,
        asset_name,
        digest,
        asset_path.stat().st_size,
        notes,
    )
    if not has_more:
        manifest["read_more_url"] = ""
    (out / "update-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "SHA256SUMS.txt").write_text(
        f"{digest}  {asset_name}\n{sha256_file(out / 'update-manifest.json')}  update-manifest.json\n",
        encoding="utf-8",
    )

    print(f"Portable asset: {asset_path}")
    print(f"Manifest: {out / 'update-manifest.json'}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
