from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "src" / "image_sheet_splitter" / "version.py"
OUT = ROOT / "build" / "windows" / "version_info.txt"

text = VERSION_FILE.read_text(encoding="utf-8")
match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
if not match:
    raise SystemExit("APP_VERSION not found")
version = match.group(1)
parts = version.split(".")
if len(parts) != 3 or not all(p.isdigit() for p in parts):
    raise SystemExit(f"Windows release version must be MAJOR.MINOR.PATCH: {version}")
major, minor, patch = [int(p) for p in parts]

payload = f'''VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'TechSavage1989'),
          StringStruct('FileDescription', 'Portable image sheet splitter'),
          StringStruct('FileVersion', '{version}'),
          StringStruct('InternalName', 'Image Sheet Splitter'),
          StringStruct('OriginalFilename', 'Image Sheet Splitter.exe'),
          StringStruct('ProductName', 'Image Sheet Splitter'),
          StringStruct('ProductVersion', '{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
'''
OUT.write_text(payload, encoding="utf-8")
print(f"Wrote {OUT} for {version}")
