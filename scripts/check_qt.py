"""Cek versi Qt yang dipakai, dan apakah .exe memakai Qt yang sama.

Dipakai untuk memastikan aplikasi tidak diam-diam jalan dengan Qt sistem yang
versi berbeda (sumber bug tampilan yang sulit dilacak).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6 import __version__ as version
from PySide6.QtCore import qVersion


def main() -> int:
    print(f"PySide6 : {version}")
    print(f"Qt      : {qVersion()}")

    exe = Path(__file__).resolve().parent.parent / "dist" / "Keuangan" / "Keuangan.exe"
    print(f"exe     : {'ada' if exe.exists() else 'belum dibuild'}")

    if exe.exists():
        plugin_dir = exe.parent / "_internal" / "PySide6" / "plugins"
        if plugin_dir.exists():
            platforms = list((plugin_dir / "platforms").glob("qwindows*.dll"))
            print(f"  ok   plugin qwindows ikut terpaket: {len(platforms)} file")
        else:
            print("  GAGAL folder plugin Qt tidak ada di _internal")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
