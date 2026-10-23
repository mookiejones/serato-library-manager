# -*- mode: python ; coding: utf-8 -*-
"""Build a windowed Serato Library app for the machine running PyInstaller.

The static files are the directory server.py serves. The spec fails when
index.html points at a local file that is not in that directory.
"""

import sys
from pathlib import Path

root = Path(SPECPATH)
sys.path.insert(0, str(root))

from static_assets import missing_static_files

missing = missing_static_files(root / "static")
if missing:
    raise SystemExit("Missing build inputs: " + ", ".join(missing))

if sys.platform == "darwin":
    hidden = ["webview.platforms.cocoa"]
elif sys.platform == "win32":
    hidden = ["webview.platforms.edgechromium", "webview.platforms.winforms"]
else:
    hidden = ["webview.platforms.gtk"]

a = Analysis(
    ["desktop.py"],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "static"), "static")],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Serato Library",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Serato Library",
)
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Serato Library.app",
        icon=None,
        bundle_identifier="local.seratolibrary.browser",
    )
