"""Frozen-binary entry point (PyInstaller compiles the entry script as top-level
``__main__``, so the package-relative ``src/pippin/__main__.py`` cannot be
used directly — absolute import instead)."""

import multiprocessing as mp

from pippin.cli import main

if __name__ == "__main__":
    mp.freeze_support()  # required for spawn-based frame workers in frozen builds
    raise SystemExit(main())
