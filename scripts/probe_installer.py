"""Uji siklus instalasi penuh: install → jalankan → uninstall → data aman.

Dipakai untuk memastikan installer tidak merusak apa pun:

    .\\.venv\\Scripts\\python.exe scripts\\probe_installer.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETUP = sorted((ROOT / "dist" / "installer").glob("Keuangan-Setup-*.exe"))
INSTALL_DIR = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Keuangan"
REAL_DATA = Path(os.environ["APPDATA"]) / "Keuangan"

problems: list[str] = []


def fail(message: str) -> None:
    problems.append(message)
    print(f"  GAGAL {message}")


def run_uninstaller() -> None:
    uninstaller = INSTALL_DIR / "unins000.exe"
    if not uninstaller.exists():
        return
    subprocess.run(
        [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
        capture_output=True,
        timeout=300,
    )
    deadline = time.time() + 60
    while time.time() < deadline and INSTALL_DIR.exists():
        time.sleep(1)


def main() -> int:
    if not SETUP:
        print("installer belum dibuat")
        return 1
    setup = SETUP[-1]
    print(f"installer: {setup.name} ({setup.stat().st_size / 1024 / 1024:.1f} MB)")

    # Bersihkan sisa uji sebelumnya.
    run_uninstaller()
    shutil.rmtree(INSTALL_DIR, ignore_errors=True)

    log = Path(tempfile.gettempdir()) / "keuangan-install-probe.log"
    result = subprocess.run(
        [
            str(setup),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/NOICONS",
            f"/LOG={log}",
        ],
        capture_output=True,
        timeout=600,
    )
    if result.returncode != 0:
        fail(f"installer gagal (exit={result.returncode})")
        return 1
    print("  ok   installer selesai tanpa error")

    exe = INSTALL_DIR / "Keuangan.exe"
    if not exe.exists():
        fail("exe tidak terpasang")
        return 1
    print(f"  ok   exe terpasang ({exe.stat().st_size / 1024 / 1024:.1f} MB)")

    if not (INSTALL_DIR / "PANDUAN.txt").exists():
        fail("PANDUAN.txt tidak terpasang")
    else:
        print("  ok   panduan ikut terpasang")

    if not (INSTALL_DIR / "unins000.exe").exists():
        fail("uninstaller tidak ada")
    else:
        print("  ok   uninstaller tersedia")

    # Data diarahkan ke folder sementara supaya data asli tidak tersentuh.
    data_dir = Path(tempfile.mkdtemp(prefix="keuangan-data-"))
    env = dict(os.environ)
    env["KEUANGAN_DATA_DIR"] = str(data_dir)

    process = subprocess.Popen([str(exe)], cwd=str(INSTALL_DIR), env=env)
    db = data_dir / "finance.db"

    deadline = time.time() + 45
    while time.time() < deadline and process.poll() is None and not db.exists():
        time.sleep(0.5)

    if process.poll() is not None:
        fail(f"aplikasi mati saat dijalankan (exit={process.returncode})")
    elif not db.exists():
        fail("database tidak dibuat")
    else:
        print("  ok   aplikasi berjalan dan membuat database")

    time.sleep(2)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()

    # Installer kedua harus bisa menimpa tanpa kehilangan data.
    result = subprocess.run(
        [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS"],
        capture_output=True,
        timeout=600,
    )
    if result.returncode != 0:
        fail(f"instalasi ulang gagal (exit={result.returncode})")
    else:
        print("  ok   instalasi ulang berhasil (update menimpa)")

    if db.exists():
        print("  ok   data tidak tersentuh oleh instalasi ulang")
    else:
        fail("data hilang setelah instalasi ulang")

    run_uninstaller()
    if INSTALL_DIR.exists():
        fail("folder instalasi masih ada setelah uninstall")
    else:
        print("  ok   uninstall menghapus folder aplikasi")

    if db.exists():
        print("  ok   data pengguna tetap ada setelah uninstall (sesuai pilihan default)")
    else:
        fail("data ikut terhapus padahal pilihan default adalah menyimpan")

    shutil.rmtree(data_dir, ignore_errors=True)

    print()
    if problems:
        print(f"TOTAL MASALAH: {len(problems)}")
        return 1
    print("SEMUA OK: install, jalan, update, uninstall, data tetap aman.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
