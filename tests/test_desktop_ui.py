"""Test antarmuka desktop (Qt offscreen, tanpa jendela sungguhan)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from bot.models import TYPE_EXPENSE, TYPE_INCOME
from desktop.dialogs import CategoryDialog, TransactionDialog
from desktop.models import COL_AMOUNT, COL_KIND, COL_NOTE
from desktop.service import LedgerService
from desktop.theme import apply_theme, palette_for


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def settings_dir(tmp_path, qapp, monkeypatch):
    """QSettings diarahkan ke folder sementara supaya registry tidak kotor."""
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    monkeypatch.setattr(
        "desktop.main_window.QSettings",
        lambda *a, **k: QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "Keuangan", "Keuangan"),
    )
    return tmp_path


@pytest.fixture()
def svc(tmp_path):
    service = LedgerService(tmp_path / "finance.db", tmp_path / "exports")
    yield service
    service.close()


@pytest.fixture()
def window(svc, settings_dir, qapp):
    from desktop.main_window import MainWindow

    apply_theme(qapp, "light")
    win = MainWindow(svc)
    win.resize(1180, 760)
    yield win
    win.close()


# ---------------------------------------------------------------- jendela


def test_jendela_punya_semua_halaman(window):
    assert set(window.pages) == {
        "dashboard",
        "transactions",
        "reports",
        "budgets",
        "categories",
        "settings",
    }


def test_semua_halaman_bisa_dibuka(window, qapp):
    for row in range(window.nav.count()):
        window.nav.setCurrentRow(row)
        qapp.processEvents()
        assert window.stack.currentWidget() is not None


def test_dashboard_terisi_setelah_menambah(window, qapp):
    page = window.pages["dashboard"]
    page.quick_input.setText("kopi 18rb")
    page._submit_quick()
    qapp.processEvents()

    # pengeluaran tanpa pemasukan -> saldo minus, itu memang benar
    assert page.card_balance.value_label.text() == "-Rp 18.000"
    assert "Tercatat" in page.quick_status.text()
    assert page.quick_input.text() == ""


def test_catat_cepat_nominal_tidak_valid_menampilkan_error(window, qapp):
    page = window.pages["dashboard"]
    page.quick_input.setText("makan siang")
    page._submit_quick()
    qapp.processEvents()

    assert not page.quick_status.isHidden()
    assert page.quick_status.text()
    assert "Tercatat" not in page.quick_status.text()


def test_preview_menebak_kategori_sebelum_simpan(window, qapp):
    page = window.pages["dashboard"]
    page.quick_input.setText("kopi 18rb")
    qapp.processEvents()
    assert "Makan" in page.quick_preview.text()
    assert "18.000" in page.quick_preview.text()


def test_preview_pemasukan(window, qapp):
    page = window.pages["dashboard"]
    page.quick_input.setText("gaji 5jt")
    qapp.processEvents()
    assert "Masuk" in page.quick_preview.text()


# ---------------------------------------------------------------- tabel


def test_tabel_transaksi_terisi(window, svc, qapp):
    svc.add_from_text("kopi 18rb")
    svc.add_from_text("gaji 5jt")

    page = window.pages["transactions"]
    page.month_combo.setCurrentIndex(page.month_combo.count() - 1)  # semua waktu
    page.refresh()
    qapp.processEvents()

    assert page.model.rowCount() == 2
    assert page.model.total_income() == 5_000_000
    assert page.model.total_expense() == 18_000
    assert "2 transaksi" in page.summary_label.text()


def test_tabel_memfilter_jenis(window, svc, qapp):
    svc.add_from_text("kopi 18rb")
    svc.add_from_text("gaji 5jt")

    page = window.pages["transactions"]
    page.month_combo.setCurrentIndex(page.month_combo.count() - 1)
    page.kind_combo.setCurrentIndex(1)  # keluar
    qapp.processEvents()

    assert page.model.rowCount() == 1
    assert page.model.rows()[0].kind == TYPE_EXPENSE


def test_pencarian_tabel_menyaring(window, svc, qapp):
    svc.add_from_text("kopi 18rb")
    svc.add_from_text("bensin 25rb")

    page = window.pages["transactions"]
    page.month_combo.setCurrentIndex(page.month_combo.count() - 1)
    page.search_input.setText("bensin")
    page.refresh()
    qapp.processEvents()

    assert page.model.rowCount() == 1
    assert "bensin" in page.model.rows()[0].note


def test_model_format_nominal_dan_warna(window, svc, qapp):
    svc.add_from_text("gaji 5jt")
    page = window.pages["transactions"]
    page.month_combo.setCurrentIndex(page.month_combo.count() - 1)
    page.refresh()

    model = page.model
    index_amount = model.index(0, COL_AMOUNT)
    assert model.data(index_amount, Qt.ItemDataRole.DisplayRole) == "+Rp 5.000.000"
    assert model.data(model.index(0, COL_KIND), Qt.ItemDataRole.DisplayRole) == "Masuk"
    assert model.data(model.index(0, COL_NOTE), Qt.ItemDataRole.DisplayRole) == "gaji"

    brush = model.data(index_amount, Qt.ItemDataRole.ForegroundRole)
    assert brush is not None and brush.color().name().lower() == "#059669"


def test_model_sorting(window, svc, qapp):
    from datetime import datetime

    svc.add_manual(
        kind=TYPE_EXPENSE,
        amount=5_000,
        category_id=svc.categories(TYPE_EXPENSE)[0].id,
        note="kecil",
        when_local=datetime(2026, 1, 1, 9, 0),
    )
    svc.add_from_text("belanja 100rb")

    page = window.pages["transactions"]
    page.month_combo.setCurrentIndex(page.month_combo.count() - 1)
    page.refresh()

    page.model.sort(COL_AMOUNT, Qt.SortOrder.AscendingOrder)
    assert page.model.rows()[0].amount == 5_000

    page.model.sort(COL_AMOUNT, Qt.SortOrder.DescendingOrder)
    assert page.model.rows()[0].amount >= 100_000


def test_undo_dari_halaman_transaksi(window, svc, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    svc.add_from_text("kopi 18rb")
    page = window.pages["transactions"]
    page._undo()
    qapp.processEvents()

    assert svc.list_transactions() == []


# ---------------------------------------------------------------- dialog


def test_dialog_transaksi_menolak_nominal_kosong(window, svc):
    dialog = TransactionDialog(
        window, categories=svc.categories(), accounts=svc.accounts()
    )
    dialog.amount_input.setText("")
    dialog._on_accept()
    assert dialog.result_values is None
    assert not dialog.error.isHidden()


def test_dialog_transaksi_menolak_nominal_nol(window, svc):
    dialog = TransactionDialog(
        window, categories=svc.categories(), accounts=svc.accounts()
    )
    dialog.amount_input.setText("0")
    dialog._on_accept()
    assert dialog.result_values is None


def test_dialog_transaksi_menerima_format_manusia(window, svc):
    dialog = TransactionDialog(
        window, categories=svc.categories(), accounts=svc.accounts()
    )
    dialog.amount_input.setText("1,5jt")
    dialog.note_input.setText("sewa")
    dialog._on_accept()
    assert dialog.result_values is not None
    assert dialog.result_values["amount"] == 1_500_000


def test_dialog_kategori_menolak_nama_kosong(window):
    dialog = CategoryDialog(window)
    dialog.name_input.setText("   ")
    dialog._on_accept()
    assert dialog.result_values is None
    assert not dialog.error.isHidden()


def test_dialog_transaksi_ganti_jenis_mengganti_kategori(window, svc):
    dialog = TransactionDialog(
        window, categories=svc.categories(), accounts=svc.accounts()
    )
    dialog.kind_combo.setCurrentIndex(1)  # masuk
    kinds = {
        next(c.kind for c in svc.categories() if c.id == dialog.category_combo.itemData(i))
        for i in range(dialog.category_combo.count())
    }
    assert kinds == {TYPE_INCOME}


# ---------------------------------------------------------------- tema


def test_ganti_tema_mengubah_palet(window, qapp):
    window._set_theme("dark")
    qapp.processEvents()
    assert window.palette_colors.name == "dark"
    assert window.palette_colors["bg"] == palette_for("dark")["bg"]

    window._set_theme("light")
    qapp.processEvents()
    assert window.palette_colors.name == "light"


def test_tema_tidak_dikenal_jatuh_ke_terang(window, qapp):
    window._set_theme("ungu")
    qapp.processEvents()
    assert window.palette_colors.name == "light"


def test_semua_halaman_punya_refresh_aman(window, qapp):
    for page in window.pages.values():
        page.refresh()
        qapp.processEvents()
