"""Uji hasil instalasi: aplikasi terpasang, jalan, dan data tidak di folder app.

Dijalankan setelah `Keuangan-Setup-1.0.0.exe /VERYSILENT`.

    .\\.venv\\Scripts\\python.exe scripts\\probe_installed.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

problems: list[str] = []


def fail(message: str) -> None:
    problems.append(message)
    print(f"  GAGAL {message}")


def main() -> int:
    install_dir = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Keuangan"
    exe = install_dir / "Keuangan.exe"

    print(f"folder instalasi: {install_dir}")
    if not exe.exists():
        print("Aplikasi belum terpasang.")
        return 1
    print(f"  ok   exe ada ({exe.stat().st_size / 1024 / 1024:.1f} MB)")

    if (install_dir / "PANDUAN.txt").exists():
        print("  ok   panduan ikut terpasang")
    else:
        fail("PANDUAN.txt tidak terpasang")

    if (install_dir / "unins000.exe").exists():
        print("  ok   uninstaller ada")
    else:
        fail("uninstaller tidak ada")

    # Data asli user tidak boleh tersentuh oleh pengujian ini.
    real_data = Path(os.environ["APPDATA"]) / "Keuangan"
    if real_data.exists():
        print(f"  info data pengguna sudah ada di {real_data} — memakai folder sementara")
        data_dir = Path(os.environ["TEMP"]) / "keuangan-probe-data"
        shutil.rmtree(data_dir, ignore_errors=True)
    else:
        data_dir = real_data

    env = dict(os.environ)
    env["KEUANGAN_DATA_DIR"] = str(data_dir)

    process = subprocess.Popen([str(exe)], cwd=str(install_dir), env=env)

    db = data_dir / "finance.db"
    deadline = time.time() + 45
    while time.time() < deadline and process.poll() is None and not db.exists():
        time.sleep(0.5)

    if process.poll() is not None:
        fail(f"aplikasi terpasang langsung mati (exit={process.returncode})")
    elif not db.exists():
        fail("database tidak dibuat")
    else:
        print(f"  ok   database dibuat di {db.parent}")

    time.sleep(2)
    title = ""
    if process.poll() is None:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-Process -Id {process.pid}).MainWindowTitle",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        title = (result.stdout or "").strip()

    if title:
        print(f"  ok   jendela tampil: '{title}'")
    else:
        fail("jendela tidak terdeteksi")

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()

    if list(install_dir.glob("*.db")):
        fail("database ikut tertulis di folder instalasi")
    else:
        print("  ok   folder instalasi tetap bersih")

    if data_dir != real_data:
        shutil.rmtree(data_dir, ignore_errors=True)

    print()
    if problems:
        print(f"TOTAL MASALAH: {len(problems)}")
        return 1
    print("SEMUA OK: aplikasi terpasang benar dan berjalan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
