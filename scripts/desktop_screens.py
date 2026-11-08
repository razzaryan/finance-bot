"""Ambil tangkapan layar tiap halaman (offscreen) untuk pemeriksaan visual."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from desktop.main_window import MainWindow
from desktop.service import LedgerService
from desktop.theme import apply_theme

OUT = Path(__file__).resolve().parent.parent / "screenshots"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    service = LedgerService(tmp / "finance.db", tmp / "exports")

    for text in [
        "kopi 18rb",
        "makan siang 35k",
        "gaji 7.5jt",
        "bensin 25.000",
        "kemarin belanja bulanan 450rb",
        "netflix 54rb",
        "obat 85rb",
    ]:
        service.add_from_text(text)

    for category in service.categories("expense"):
        if category.name in ("Makan", "Transport", "Belanja"):
            service.set_budget(category.id, {"Makan": 1_500_000, "Transport": 500_000, "Belanja": 2_000_000}[category.name])

    app = QApplication.instance() or QApplication([])

    for mode in ("light", "dark"):
        apply_theme(app, mode)
        window = MainWindow(service)
        # Tema harus diganti lewat jendela (bukan hanya app.setStyleSheet),
        # supaya palet halaman ikut berubah — sama seperti tombol di Pengaturan.
        window._set_theme(mode)
        window.resize(1180, 760)
        window.show()
        app.processEvents()

        for row, (key, label) in enumerate(
            [
                ("dashboard", "dashboard"),
                ("transactions", "transaksi"),
                ("reports", "laporan"),
                ("budgets", "anggaran"),
                ("categories", "kategori"),
                ("settings", "pengaturan"),
            ]
        ):
            window.nav.setCurrentRow(row)
            app.processEvents()
            path = OUT / f"{mode}-{label}.png"
            window.grab().save(str(path))
            print("simpan", path.name)

        window.close()
        app.processEvents()

    service.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
