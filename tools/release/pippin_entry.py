"""Frozen-binary entry point (PyInstaller compiles the entry script as top-level
``__main__``, so the package-relative ``src/pippin/__main__.py`` cannot be
used directly — absolute import instead)."""

from pippin.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
