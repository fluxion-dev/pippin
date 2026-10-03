"""Collect cairo-stack shared libraries for bundling into the PyInstaller binary.

cairosvg renders through cairocffi, which dlopens libcairo/libpango at
runtime. A single-file binary must carry those libs with it, otherwise SVG
input only works where cairo is installed system-wide.

Usage (imported by pippin.spec at build time)::

    from collect_cairo import cairo_binaries
    binaries = cairo_binaries()  # list of (src_path, ".") for a.binaries

Platforms:
  - linux   — resolve via `ldd libcairo.so.2`, keep cairo-stack entries
  - macos   — resolve via `otool -L libcairo.2.dylib`
  - windows — resolve via `ldd libcairo-2.dll` under msys2/mingw64
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

# Soname fragments belonging to the cairo/pango/pixbuf stack. Anything else
# (libc, libm, libstdc++, kernel vdso, ...) stays on the host system.
KEEP = (
    "libcairo",
    "libpango",
    "libpangocairo",
    "libpangoft2",
    "libgdk_pixbuf",
    "libgdk-pixbuf",
    "libglib",
    "libgobject",
    "libgmodule",
    "libgio",
    "libffi",
    "libpng",
    "libfreetype",
    "libfontconfig",
    "libharfbuzz",
    "libfribidi",
    "libpixman",
    "libexpat",
    "libbrotli",
    "libbz2",
    "libgraphite",
    "libthai",
    "libdatrie",
    "libblkid",
    "libmount",
    "libuuid",
    "libpcre",
    "libX11",
    "libXext",
    "libXrender",
    "libxcb",
    "libXau",
    "libXdmcp",
    "libselinux",
    "libsepol",
)


def _keep(path: str) -> bool:
    base = os.path.basename(path)
    return base.startswith(KEEP)


def _ldd_deps(lib: str, env: dict | None = None) -> list[str]:
    out = subprocess.run(["ldd", lib], capture_output=True, text=True, env=env, check=False).stdout
    deps: list[str] = []
    for line in out.splitlines():
        m = re.search(r"=>\s+(\S+)", line)
        if m and os.path.isfile(m.group(1)):
            deps.append(m.group(1))
            continue
        m = re.match(r"\s*(\/\S+)", line)  # linux-vdso style or bare path
        if m and os.path.isfile(m.group(1)):
            deps.append(m.group(1))
    return deps


def _otool_deps(lib: str) -> list[str]:
    out = subprocess.run(["otool", "-L", lib], capture_output=True, text=True, check=False).stdout
    deps: list[str] = []
    for line in out.splitlines()[1:]:
        m = re.match(r"\s*(\S+)\s+\(", line)
        if m and os.path.isfile(m.group(1)):
            deps.append(m.group(1))
    return deps


def _resolve_recursive(root: str, children: callable) -> list[str]:
    seen: dict[str, None] = {}
    stack = [root]
    while stack:
        lib = stack.pop()
        if lib in seen or not os.path.isfile(lib):
            continue
        seen[lib] = None
        stack.extend(children(lib))
    return sorted(seen)


def _find_root(candidates: list[str]) -> str:
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    raise FileNotFoundError(f"cairo library not found, tried: {candidates}")


def _locate(names: list[str]) -> str | None:
    """Locate a shared lib by soname using ld cache / find_library."""
    from ctypes.util import find_library
    for name in names:
        found = find_library(name)
        if found:
            if os.path.isfile(found):
                return found
            for prefix in ("/usr/lib/x86_64-linux-gnu", "/usr/lib64", "/usr/lib",
                           "/lib64", "/lib/x86_64-linux-gnu"):
                for suffix in ("", ".0", ".2"):
                    p = os.path.join(prefix, found + suffix if not found.endswith(".so") else found)
                    if os.path.isfile(p):
                        return p
            for path in _ldconfig_paths(os.path.basename(found)):
                return path
    return None


def _ldconfig_paths(soname: str) -> list[str]:
    try:
        out = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True, check=False).stdout
    except OSError:
        return []
    paths = []
    for line in out.splitlines():
        if soname in line:
            m = re.search(r"=>\s+(\S+)", line)
            if m and os.path.isfile(m.group(1)):
                paths.append(m.group(1))
    return paths


def _brew_prefix(pkg: str) -> str | None:
    brew = shutil.which("brew")
    if not brew:
        return None
    try:
        out = subprocess.run([brew, "--prefix", pkg], capture_output=True, text=True, check=False)
        if out.returncode == 0:
            return out.stdout.strip()
    except OSError:
        pass
    return None


def cairo_binaries() -> list[tuple[str, str]]:
    """Return PyInstaller (src, dest_dir) tuples for the cairo stack."""
    if sys.platform.startswith("linux"):
        roots = [
            _find_root(["/usr/lib/x86_64-linux-gnu/libcairo.so.2",
                        "/usr/lib64/libcairo.so.2",
                        "/usr/lib/libcairo.so.2"]),
            # cairocffi also dlopens these directly (pixbuf.py); each may be
            # absent on minimal systems, so locate best-effort.
            _locate(["gdk_pixbuf-2.0"]),
            _locate(["gobject-2.0"]),
            _locate(["glib-2.0"]),
        ]
        libs: list[str] = []
        for root in roots:
            if root:
                libs.extend(_resolve_recursive(root, lambda lib: _ldd_deps(lib)))
        libs = sorted(set(libs))
    elif sys.platform == "darwin":
        prefix = _brew_prefix("cairo") or "/opt/homebrew"
        root = _find_root([os.path.join(prefix, "lib", "libcairo.2.dylib"),
                           "/opt/homebrew/lib/libcairo.2.dylib",
                           "/usr/local/lib/libcairo.2.dylib"])
        libs = _resolve_recursive(root, _otool_deps)
        # keep only brew/mSys libs, never /usr/lib system dylibs
        libs = [l for l in libs if not l.startswith("/usr/lib/") and not l.startswith("/System/")]
    elif os.name == "nt":
        mingw = os.environ.get("MSYSTEM_PREFIX", r"C:\msys64\mingw64")
        root = _find_root([os.path.join(mingw, "bin", "libcairo-2.dll")])
        libs = _resolve_recursive(root, lambda lib: _ldd_deps(lib))
        libs = [l for l in libs if l.startswith(mingw)]
    else:
        raise RuntimeError(f"unsupported platform for cairo bundling: {sys.platform}")

    bundled = [(lib, ".") for lib in libs if _keep(lib)]
    # The root libs themselves always qualify via KEEP, but be explicit.
    if sys.platform.startswith("linux"):
        have = {src for src, _ in bundled}
        for root in roots:
            if root and root not in have:
                bundled.append((root, "."))
    else:
        if root not in [src for src, _ in bundled]:
            bundled.append((root, "."))
    print(f"[collect_cairo] bundling {len(bundled)} libs")
    for src, _ in bundled:
        print(f"[collect_cairo]   {src}")
    return bundled


if __name__ == "__main__":
    for src, dest in cairo_binaries():
        print(f"{src} -> {dest}")
