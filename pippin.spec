# PyInstaller spec for the pippin single-file binary.
#
#   PIPPIN_BIN_NAME=pippin-linux-x64 pyinstaller pippin.spec --clean --noconfirm
#
# Cairo system libs are collected by tools/release/collect_cairo.py and
# pre-loaded at startup by tools/release/pyi_rth_cairo.py, so SVG input works
# with no system cairo installed.

import os
import sys

sys.path.insert(0, os.path.join(SPECPATH, "tools", "release"))
from collect_cairo import cairo_binaries

BIN_NAME = os.environ.get("PIPPIN_BIN_NAME", "pippin")
PATHEX_SRC = os.path.join(SPECPATH, "src")

a = Analysis(
    [os.path.join(SPECPATH, "tools", "release", "pippin_entry.py")],
    pathex=[PATHEX_SRC],
    binaries=cairo_binaries(),
    datas=[],
    hiddenimports=[
        "cffi",
        "cairocffi",
        "cairosvg",
        "cssselect2",
        "tinycss2",
        "defusedxml",
        "PIL",
        "PIL.Image",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(SPECPATH, "tools", "release", "pyi_rth_cairo.py")],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=BIN_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
