import argparse
import sys
from pathlib import Path

ALLOWED_ROOT_ENTRIES = {
    ".github",
    ".gitignore",
    "AGENTS.md",
    "Build Portable EXE.bat",
    "DEVELOPMENT_HANDOFF.md",
    "README.md",
    "assets",
    "build",
    "docs",
    "pyproject.toml",
    "requirements-build.txt",
    "scripts",
    "src",
    "tests",
}
GENERATED_ROOT_ENTRIES = {
    ".git",
    ".build-venv",
    ".venv",
    ".pytest_cache",
    "build-output",
    "dist",
    "release",
    "__pycache__",
}


def unexpected_entries(root):
    root = Path(root)
    bad = []
    for item in root.iterdir():
        if item.name in GENERATED_ROOT_ENTRIES:
            continue
        if item.name not in ALLOWED_ROOT_ENTRIES:
            bad.append(item.name)
    return sorted(bad)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    bad = unexpected_entries(args.root)
    if bad:
        print("Unexpected repository-root entries:")
        for name in bad:
            print(f"  {name}")
        print("Review the file and add it to scripts/check_root.py only if it is a required root exception.")
        return 1
    print("Repository root matches the approved allowlist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
