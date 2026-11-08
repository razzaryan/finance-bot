"""Uji .exe hasil build: benar-benar jalan, membuat data, lalu ditutup.

Dipakai setelah `pyinstaller packaging/keuangan.spec`.

    .\\.venv\\Scripts\\python.exe scripts\\probe_exe.py
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
EXE = ROOT / "dist" / "Keuangan" / "Keuangan.exe"

problems: list[str] = []


def fail(message: str) -> None:
    problems.append(message)
    print(f"  GAGAL {message}")


def main() -> int:
    if not EXE.exists():
        print(f"exe tidak ada: {EXE}")
        return 1

    workdir = Path(tempfile.mkdtemp(prefix="keuangan-exe-"))
    data_dir = workdir / "data"
    env = dict(os.environ)
    env["KEUANGAN_DATA_DIR"] = str(data_dir)

    print(f"menjalankan {EXE.name} …")
    process = subprocess.Popen(
        [str(EXE)],
        cwd=str(EXE.parent),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    db = data_dir / "finance.db"
    log = data_dir / "keuangan.log"

    deadline = time.time() + 40
    started = False
    while time.time() < deadline:
        if process.poll() is not None:
            out, err = process.communicate(timeout=5)
            fail(
                f"proses keluar sendiri (exit={process.returncode})\n"
                f"stdout={out.decode('utf-8', 'replace')[:800]}\n"
                f"stderr={err.decode('utf-8', 'replace')[:800]}"
            )
            break
        if db.exists() and db.stat().st_size > 0:
            started = True
            break
        time.sleep(0.5)

    if process.poll() is None:
        print("  ok   proses masih berjalan setelah database dibuat" if started else "  ?    proses berjalan")

    if not started and process.poll() is None:
        fail("database tidak dibuat dalam 40 detik")

    # biarkan UI sempat selesai inisialisasi
    time.sleep(3)

    if process.poll() is None:
        print("  ok   aplikasi tetap hidup (tidak crash)")
        title = ""
        try:
            import subprocess as sp

            result = sp.run(
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
        except Exception as exc:  # noqa: BLE001
            print(f"  info tidak bisa membaca judul jendela: {exc}")

        if title:
            print(f"  ok   jendela benar-benar tampil: '{title}'")
            if "Keuangan" not in title:
                fail(f"judul jendela tidak sesuai: {title!r}")
        else:
            fail("jendela tidak terdeteksi (judul kosong) — aplikasi mungkin jalan tanpa UI")

        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    else:
        out, err = process.communicate(timeout=5)
        fail(
            f"aplikasi mati setelah start (exit={process.returncode})\n"
            f"stderr={err.decode('utf-8', 'replace')[:800]}"
        )

    if db.exists():
        print(f"  ok   database dibuat ({db.stat().st_size} byte)")
    else:
        fail("database tidak ada")

    exports = data_dir / "exports"
    print(f"  info folder exports: {'ada' if exports.exists() else 'belum dibuat (normal, dibuat saat transaksi pertama)'}")

    if log.exists():
        text = log.read_text(encoding="utf-8", errors="replace")
        if "Traceback" in text or "CRITICAL" in text:
            fail(f"log berisi error:\n{text[-1500:]}")
        else:
            print("  ok   log bersih")
    else:
        print("  info log belum dibuat (aplikasi mungkin belum sempat menulis)")

    # cek tidak ada file sampah di folder exe
    stray = list(EXE.parent.glob("*.db")) + list(EXE.parent.glob("data"))
    if stray:
        fail(f"ada file data di folder instalasi: {[p.name for p in stray]}")
    else:
        print("  ok   folder instalasi tetap bersih (data di luar)")

    shutil.rmtree(workdir, ignore_errors=True)

    print()
    if problems:
        print(f"TOTAL MASALAH: {len(problems)}")
        for item in problems:
            print(" -", item.splitlines()[0])
        return 1
    print("SEMUA OK: .exe berjalan, membuat database di folder data, dan berhenti bersih.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
