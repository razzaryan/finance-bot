"""Hasilkan packaging/keuangan.ico dari ikon yang digambar runtime.

Qt tidak bisa menulis .ico langsung, jadi file ICO dirakit sendiri: setiap
ukuran disimpan sebagai PNG di dalam kontainer ICO (didukung Windows Vista ke
atas).

    .\\.venv\\Scripts\\python.exe scripts\\make_icon.py
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtWidgets import QApplication

from desktop.branding import _draw

SIZES = (16, 24, 32, 48, 64, 128, 256)


def png_bytes(size: int) -> bytes:
    pixmap = _draw(size)
    # QByteArray harus hidup selama QBuffer dipakai; kalau dibuat sebagai
    # argumen langsung, Python menghapusnya lebih dulu dan Qt menulis ke
    # memori yang sudah bebas (access violation).
    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not pixmap.save(buffer, "PNG"):
        raise RuntimeError(f"gagal menulis PNG {size}px")
    buffer.close()
    return bytes(storage)


def build_ico(images: list[tuple[int, bytes]]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = bytearray()
    payload = bytearray()

    for size, data in images:
        entries += struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0,
            size if size < 256 else 0,
            0,
            0,
            1,
            32,
            len(data),
            offset,
        )
        payload += data
        offset += len(data)

    return bytes(header + entries + payload)


def main() -> int:
    target = Path(__file__).resolve().parent.parent / "packaging" / "keuangan.ico"
    target.parent.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    images = [(size, png_bytes(size)) for size in SIZES]
    target.write_bytes(build_ico(images))

    print(f"ikon disimpan: {target} ({target.stat().st_size} byte, {len(SIZES)} ukuran)")
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
