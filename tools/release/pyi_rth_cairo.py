"""PyInstaller runtime hook: make bundled cairo libs discoverable.

Runs before any pippin import inside the frozen binary:

- Windows: the onefile bundle extracts to sys._MEIPASS; register it for DLL
  search so libcairo-2.dll and friends resolve.
- Linux/macOS: cairocffi dlopens cairo/pango by soname. Pre-load the bundled
  copies RTLD_GLOBAL so the later dlopen hits the already-loaded handle
  instead of the (possibly absent) system copy.
"""

import ctypes
import os
import sys

LOAD_ORDER = (
    "libffi",
    "libglib",
    "libgobject",
    "libgmodule",
    "libgio",
    "libpng",
    "libfreetype",
    "libfontconfig",
    "libharfbuzz",
    "libfribidi",
    "libpixman",
    "libexpat",
    "libxcb",
    "libX11",
    "libpango",
    "libpangocairo",
    "libpangoft2",
    "libgdk_pixbuf",
    "libgdk-pixbuf",
    "libcairo",
)


def _preload(meipass: str) -> None:
    try:
        names = os.listdir(meipass)
    except OSError:
        return

    def rank(name: str) -> int:
        for i, frag in enumerate(LOAD_ORDER):
            if name.startswith(frag):
                return i
        return len(LOAD_ORDER)

    for name in sorted(names, key=rank):
        if ".so" not in name and ".dylib" not in name:
            continue
        if not name.startswith(("libcairo", "libpango", "libgdk", "libglib",
                                "libgobject", "libgmodule", "libgio", "libffi",
                                "libpng", "libfreetype", "libfontconfig",
                                "libharfbuzz", "libfribidi", "libpixman",
                                "libexpat", "libX", "libxcb", "libuuid",
                                "libmount", "libblkid", "libpcre", "libbrotli",
                                "libbz2", "libgraphite", "libthai", "libdatrie")):
            continue
        try:
            ctypes.CDLL(os.path.join(meipass, name), mode=ctypes.RTLD_GLOBAL)
        except OSError:
            continue


meipass = getattr(sys, "_MEIPASS", None)
if meipass:
    if os.name == "nt":
        try:
            os.add_dll_directory(meipass)
        except (OSError, AttributeError):
            pass
        # Best-effort preload too: helps when dependents use full filenames.
        _preload(meipass)
    else:
        _preload(meipass)
