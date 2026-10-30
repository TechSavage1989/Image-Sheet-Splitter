import argparse
import sys
import struct
from pathlib import Path

import pefile

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
    # Compare compiled icon images with the generated ICO, not just resource presence.
    ico = (ROOT / "assets/icons/Image_Sheet_Splitter.ico").read_bytes()
    count = struct.unpack_from("<H", ico, 4)[0]
    expected_icons = []
    for index in range(count):
        size, offset = struct.unpack_from("<II", ico, 6 + index * 16 + 8)
        expected_icons.append(ico[offset:offset + size])
    with pefile.PE(str(exe)) as pe:
        if pe.FILE_HEADER.Machine != 0x8664:
            raise SystemExit("Portable executable must be Windows x64")
        resources = {entry.id: entry for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries}
        if 3 not in resources or 14 not in resources:
            raise SystemExit("Windows icon/group-icon resources are missing")
        actual_icons = []
        for item in resources[3].directory.entries:
            for language in item.directory.entries:
                data = language.data.struct
                actual_icons.append(pe.get_data(data.OffsetToData, data.Size))
        if sorted(actual_icons) != sorted(expected_icons):
            raise SystemExit("Compiled icons do not match the preserved icon artwork")
    print(f"Verified x64 PE, {count} compiled icons, ProductName/FileVersion for {exe.name} {APP_VERSION}")


if __name__ == "__main__":
    main()
