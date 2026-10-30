# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parents[1]
SRC = ROOT / "src"
ASSETS = ROOT / "assets" / "icons"
VERSION_INFO = SPEC_DIR / "version_info.txt"

block_cipher = None


a = Analysis(
    [str(ROOT / "scripts" / "windows_entry.py")],
    pathex=[str(SRC), str(ROOT)],
    binaries=[],
    datas=[
        (str(ASSETS / "Image_Sheet_Splitter.ico"), "."),
        (str(ASSETS / "Image_Sheet_Splitter.png"), "."),
    ],
    hiddenimports=[],
    hookspath=[str(SPEC_DIR)],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Image Sheet Splitter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ASSETS / "Image_Sheet_Splitter.ico"),
    version=str(VERSION_INFO),
)
