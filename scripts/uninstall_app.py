"""Uninstall aplikasi terpasang (uji bersih-bersih).

Dipakai probe installer supaya mesin penguji tidak menyimpan aplikasi.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    install_dir = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Keuangan"
    uninstaller = install_dir / "unins000.exe"
    if not uninstaller.exists():
        print("tidak terpasang")
        return 0

    result = subprocess.run(
        [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
        capture_output=True,
        timeout=300,
    )
    print(f"exit={result.returncode}")

    # Uninstaller menyalin dirinya ke folder temp lalu menghapus folder asal
    # setelah proses induk selesai; beri waktu sebentar.
    import time

    deadline = time.time() + 60
    while time.time() < deadline and install_dir.exists():
        time.sleep(1)

    print("folder masih ada" if install_dir.exists() else "folder sudah dihapus")

    data = Path(os.environ["APPDATA"]) / "Keuangan"
    print(f"data pengguna tetap ada: {data.exists()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
