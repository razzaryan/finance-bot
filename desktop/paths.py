"""Lokasi penyimpanan aplikasi desktop.

Aturan:
- Kalau ada file `portable.txt` di sebelah .exe, data disimpan di
  `<folder exe>/data` (bisa dibawa di flashdisk).
- Kalau tidak, data disimpan di `%APPDATA%\\Keuangan` supaya tetap bisa
  menulis walaupun aplikasi dipasang di `Program Files`.
- Environment `KEUANGAN_DATA_DIR` menang atas keduanya (dipakai test).

Kenapa tidak memakai folder kerja seperti versi bot: aplikasi yang dipasang
di Program Files tidak punya izin menulis ke foldernya sendiri, sehingga
database akan gagal dibuat dan transaksi hilang tanpa jejak.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Keuangan"
PORTABLE_MARKER = "portable.txt"


def app_root() -> Path:
    """Folder .exe (atau root repo saat dijalankan dari source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def is_portable() -> bool:
    return (app_root() / PORTABLE_MARKER).exists()


def _roaming_base() -> Path:
    raw = os.environ.get("APPDATA")
    if raw:
        return Path(raw)
    return Path.home() / "AppData" / "Roaming"


def data_dir() -> Path:
    """Folder data aktif; dibuat kalau belum ada."""
    override = (os.environ.get("KEUANGAN_DATA_DIR") or "").strip()
    if override:
        target = Path(override).expanduser()
    elif is_portable():
        target = app_root() / "data"
    else:
        target = _roaming_base() / APP_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def db_path() -> Path:
    return data_dir() / "finance.db"


def export_dir() -> Path:
    return data_dir() / "exports"


def backup_dir() -> Path:
    return data_dir() / "backups"
