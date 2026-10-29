"""Windows: make the venv's Visual C++ 14.51 runtime visible to native extensions.

`pip install msvc-runtime` drops the DLLs next to ``python.exe`` (venv/Scripts) and in
the venv root. Windows does not search those directories for an extension module's
transitive DLLs: it searches the extension's own directory, then System32. System32's
copy here is 14.36, which torch 2.14 and chromadb 1.5 fail to initialize against
(WinError 1114 / 126 / silent exit code 5), so copy the newer files where the loader
actually looks:

    venv/Lib/site-packages/          chromadb_rust_bindings.pyd
    venv/Lib/site-packages/torch/lib/    c10.dll, torch_cpu.dll, shm.dll

Idempotent; re-run after upgrading torch/chromadb. Installing the latest Microsoft
Visual C++ Redistributable (x64) makes this unnecessary.
"""

from __future__ import annotations

import os
import shutil
import sys
import sysconfig
from pathlib import Path

DLL_NAMES = (
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "vcruntime140_threads.dll",
)


def main() -> int:
    if os.name != "nt":
        print("Not Windows; nothing to do.")
        return 0

    source_dir = Path(sys.executable).resolve().parent
    available = [name for name in DLL_NAMES if (source_dir / name).exists()]
    if not available:
        print("No Visual C++ runtime found next to python.exe.")
        print("Run: pip install -r requirements.txt  (msvc-runtime provides it)")
        return 1

    site_packages = Path(sysconfig.get_paths()["purelib"])
    targets = [site_packages]
    for relative in ("chromadb_rust_bindings", "torch/lib"):
        candidate = site_packages / relative
        if candidate.is_dir():
            targets.append(candidate)

    for target in targets:
        for name in available:
            shutil.copy2(source_dir / name, target / name)
        print(f"Copied {len(available)} runtime DLLs to {target}")

    print("Done. Verify with: python -c \"import torch, chromadb; print('ok')\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
