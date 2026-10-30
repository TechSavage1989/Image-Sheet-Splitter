import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from image_sheet_splitter.updater import validate_windows_identity
from image_sheet_splitter.version import APP_VERSION, PORTABLE_EXE_NAME


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("exe")
    args = parser.parse_args()
    exe = Path(args.exe)
    if exe.name != PORTABLE_EXE_NAME:
        raise SystemExit(f"Unexpected executable filename: {exe.name}")
    if not validate_windows_identity(exe, APP_VERSION):
        raise SystemExit("Native Windows identity validation did not run")
    print(f"Verified Windows ProductName/FileVersion for {exe.name} {APP_VERSION}")


if __name__ == "__main__":
    main()
