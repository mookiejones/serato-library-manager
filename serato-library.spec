# -*- mode: python ; coding: utf-8 -*-
"""Build a windowed Serato Library app for the machine running PyInstaller.

The static files are the directory server.py serves. The spec fails when
index.html points at a local file that is not in that directory, or when
pywebview is not installed. On macOS it also fails when the WebKit
frameworks are not installed. The window uses the system web view.
CEF and Qt WebEngine are excluded so the bundle does not contain Chromium.
"""

import importlib.util
import sys
from pathlib import Path

root = Path(SPECPATH)
sys.path.insert(0, str(root))

import app_config
from static_assets import missing_static_files

missing = missing_static_files(root / "static")
if missing:
    raise SystemExit("Missing build inputs: " + ", ".join(missing))

if importlib.util.find_spec("webview") is None:
    raise SystemExit("Missing build inputs: pywebview")


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


from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

hidden = [
    "webview",
    "webview.guilib",
    "webview.http",
    "webview.window",
    "bottle",
    "proxy_tools",
    "typing_extensions",
]
binaries = collect_dynamic_libs("webview")
datas = [
    (str(root / "static"), "static"),
]
datas += collect_data_files("webview")
# CEF bundles Chromium. Qt WebEngine does too. Neither is a system web view.
excludes = [
    "webview.platforms.cef",
    "webview.platforms.android",
    "cefpython3",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "qtpy",
    "PIL",
    "pystray",
]
if sys.platform == "darwin":
    frameworks = (
        "objc",
        "AppKit",
        "Foundation",
        "WebKit",
        "Quartz",
        "Security",
        "UniformTypeIdentifiers",
        "PyObjCTools",
    )
    absent = [
        name
        for name in ("AppKit", "Foundation", "objc", "WebKit")
        if importlib.util.find_spec(name) is None
    ]
    if absent:
        raise SystemExit("Missing macOS web view frameworks: " + ", ".join(absent))
    for name in frameworks:
        if importlib.util.find_spec(name) is not None:
            binaries += collect_dynamic_libs(name)
    hidden += [
        "webview.platforms.cocoa",
        "AppKit",
        "Foundation",
        "WebKit",
        "objc",
        "Quartz",
        "Security",
        "UniformTypeIdentifiers",
        "PyObjCTools",
        "PyObjCTools.AppHelper",
    ]
elif sys.platform == "win32":
    if importlib.util.find_spec("clr") is None:
        raise SystemExit("Missing build inputs: pythonnet")
    hidden += [
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
        "webview.platforms.win32",
        "clr",
        "clr_loader",
        "pythonnet",
    ]
else:
    hidden += ["webview.platforms.gtk", "gi"]
hidden.extend(telemetry_hiddenimports())

a = Analysis(
    ["desktop.py"],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
        info_plist={
            "CFBundleShortVersionString": app_config.APP_VERSION,
            "CFBundleVersion": app_config.APP_VERSION,
            "NSHighResolutionCapable": True,
            "NSRemovableVolumesUsageDescription": (
                "Serato Library reads music files on external drives."
            ),
        },
    )
