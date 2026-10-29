"""Windows: preload the Visual C++ 14.51 runtime that torch and chromadb require.

`msvc-runtime` installs those DLLs into the venv's Scripts directory, next to
``python.exe``. torch loads its native libraries with an altered DLL search path, so
neither ``os.add_dll_directory`` nor ``PATH`` is consulted when resolving their
transitive imports. Loading the DLLs here first makes the loader reuse the resident
modules by base name, instead of falling back to the older copies in System32
(e.g. 14.36, which fails with WinError 1114 / 126).
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

_DLL_NAMES = (
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "vcruntime140_threads.dll",
)


def preload_vc_runtime() -> None:
    if os.name != "nt":
        return
    runtime_dir = Path(sys.executable).resolve().parent
    for name in _DLL_NAMES:
        path = runtime_dir / name
        if path.exists():
            try:
                ctypes.WinDLL(str(path))
            except OSError:
                pass
