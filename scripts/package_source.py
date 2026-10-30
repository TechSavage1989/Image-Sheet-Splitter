import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release" / "Image_Sheet_Splitter_Source.zip"
EXCLUDED_DIRS = {
    ".git", ".build-venv", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    "dist", "release", "build-output"
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log"}
GENERATED_FILES = {"assets/icons/Image_Sheet_Splitter.ico"}


def included(path):
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return False
    if rel.as_posix() in GENERATED_FILES:
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return path.is_file()


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(ROOT.rglob("*")):
            if included(path):
                zf.write(path, Path("Image-Sheet-Splitter") / path.relative_to(ROOT))
    print(OUT)


if __name__ == "__main__":
    main()
