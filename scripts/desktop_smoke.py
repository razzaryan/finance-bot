"""Smoke test aplikasi desktop tanpa membuka jendela sungguhan.

Menjalankan QApplication dengan platform 'offscreen', membangun seluruh
halaman, berpindah tab, mencatat transaksi, dan mengganti tema. Tujuannya
menangkap error konstruksi widget / signal sebelum aplikasi dijalankan user.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PySide6.QtWidgets import QApplication

from desktop.main_window import MainWindow
from desktop.service import LedgerService
from desktop.theme import apply_theme

problems: list[str] = []


def check(label: str, fn) -> None:
    try:
        fn()
        print(f"  ok   {label}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"{label}: {exc}")
        print(f"  GAGAL {label}: {exc}")
        traceback.print_exc()


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    service = LedgerService(tmp / "finance.db", tmp / "exports")
    service.add_from_text("kopi 18rb")
    service.add_from_text("gaji 5jt")

    app = QApplication.instance() or QApplication([])
    apply_theme(app, "light")

    window = MainWindow(service)
    window.show()

    check("jendela terbangun", lambda: None)

    for index, (key, label) in enumerate(
        [
            ("dashboard", "Dashboard"),
            ("transactions", "Transaksi"),
            ("reports", "Laporan"),
            ("budgets", "Anggaran"),
            ("categories", "Kategori"),
            ("settings", "Pengaturan"),
        ]
    ):
        check(f"pindah halaman {label}", lambda i=index: window.nav.setCurrentRow(i))

    check("tambah transaksi cepat", lambda: service.add_from_text("teh 5rb"))
    check("refresh semua halaman", window._refresh_all)

    check("ganti tema gelap", lambda: window._set_theme("dark"))
    check("refresh setelah tema gelap", window._refresh_all)
    check("ganti tema terang", lambda: window._set_theme("light"))

    check("dialog tambah transaksi", lambda: _dialog_smoke(window, service))
    check("dialog anggaran", lambda: _budget_dialog_smoke(window, service))
    check("dialog kategori", lambda: _category_dialog_smoke(window))

    check("halaman transaksi terisi", lambda: _assert_rows(window))

    window.close()
    service.close()
    app.processEvents()

    print()
    if problems:
        print(f"TOTAL MASALAH: {len(problems)}")
        for item in problems:
            print(" -", item)
        return 1
    print("SEMUA OK: aplikasi desktop terbangun, semua halaman bisa dibuka.")
    return 0


def _dialog_smoke(window, service) -> None:
    from desktop.dialogs import TransactionDialog

    dialog = TransactionDialog(
        window,
        categories=service.categories(),
        accounts=service.accounts(),
    )
    dialog.amount_input.setText("25rb")
    dialog.note_input.setText("uji dialog")
    assert dialog._current_kind() == "expense"
    dialog._on_accept()
    assert dialog.result_values is not None
    assert dialog.result_values["amount"] == 25000
    assert dialog.result_values["note"] == "uji dialog"
    service.add_manual(**dialog.result_values)
    dialog.deleteLater()


def _budget_dialog_smoke(window, service) -> None:
    from desktop.dialogs import BudgetDialog

    categories = service.categories()
    dialog = BudgetDialog(window, categories=categories)
    dialog.amount_input.setText("1,5jt")
    dialog._on_accept()
    assert dialog.result_values is not None
    assert dialog.result_values["amount"] == 1_500_000
    service.set_budget(**dialog.result_values)
    dialog.deleteLater()
    assert service.budgets(2026, 11) is not None


def _category_dialog_smoke(window) -> None:
    from desktop.dialogs import CategoryDialog

    dialog = CategoryDialog(window)
    dialog.name_input.setText("Uji Kategori")
    dialog.emoji_input.setText("🧪")
    dialog.keywords_input.setText("uji,tes")
    dialog._on_accept()
    assert dialog.result_values is not None
    assert dialog.result_values["name"] == "Uji Kategori"
    dialog.deleteLater()


def _assert_rows(window) -> None:
    page = window.pages["transactions"]
    page.month_combo.setCurrentIndex(page.month_combo.count() - 1)  # semua waktu
    page.refresh()
    assert page.model.rowCount() >= 3, f"baris={page.model.rowCount()}"
    assert page.model.total_income() == 5_000_000


if __name__ == "__main__":
    sys.exit(main())
