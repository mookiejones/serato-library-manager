# -*- mode: python ; coding: utf-8 -*-
"""Build a windowed Serato Library app for the machine running PyInstaller.

The static files are the directory server.py serves. The spec fails when
index.html points at a local file that is not in that directory.
"""

import importlib.util
import sys
from pathlib import Path

root = Path(SPECPATH)
sys.path.insert(0, str(root))

from static_assets import missing_static_files

missing = missing_static_files(root / "static")
if missing:
    raise SystemExit("Missing build inputs: " + ", ".join(missing))

def telemetry_hiddenimports():
    """Return telemetry modules PyInstaller would otherwise miss.

    Sentry loads its standard-library integrations by name. PostHog is
    imported only after the person opts in, so analysis does not see that
    import. A build environment without the packages skips them, and
    sharing stays off in that build. Framework integrations are not
    collected. Sentry is initialized with auto-enabling turned off.

    Returns:
        Module names to pass as hidden imports. Empty when the packages
        are not installed.
    """
    names = []
    if importlib.util.find_spec("sentry_sdk") is not None:
        names.extend(
            [
                "sentry_sdk",
                "sentry_sdk.integrations.argv",
                "sentry_sdk.integrations.atexit",
                "sentry_sdk.integrations.dedupe",
                "sentry_sdk.integrations.excepthook",
                "sentry_sdk.integrations.logging",
                "sentry_sdk.integrations.modules",
                "sentry_sdk.integrations.stdlib",
                "sentry_sdk.integrations.threading",
            ]
        )
    if importlib.util.find_spec("posthog") is not None:
        names.append("posthog")
    return names


# pywebview picks its backend at runtime. The windowed build must still
# bundle the one this OS imports: WKWebView on macOS, WebView2 through
# WinForms on Windows, and GTK elsewhere.
if sys.platform == "darwin":
    hidden = ["webview.platforms.cocoa"]
elif sys.platform == "win32":
    hidden = ["webview.platforms.edgechromium", "webview.platforms.winforms"]
else:
    hidden = ["webview.platforms.gtk"]
hidden.extend(telemetry_hiddenimports())

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
