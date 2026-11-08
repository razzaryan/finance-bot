"""Halaman daftar transaksi: filter, ubah, hapus."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
)

from bot.formatting import money
from bot.ledger import LedgerError
from bot.models import TYPE_EXPENSE, TYPE_INCOME
from bot.timeutil import add_months, local_now, month_bounds, month_label
from desktop.dialogs import TransactionDialog
from desktop.models import COL_AMOUNT, COL_CATEGORY, COL_DATE, COL_KIND, COL_NOTE
from desktop.models import TransactionModel
from desktop.pages.base import Page
from desktop.widgets import Card, configure_table


class TransactionsPage(Page):
    # Batas baris yang dimuat sekaligus. Tabel dengan 2000 baris tetap mulus;
    # di atas itu gunakan filter bulan supaya angka ringkasan tidak menyesatkan.
    PAGE_LIMIT = 2000

    def __init__(self, service, palette, parent=None) -> None:
        super().__init__(service, palette, parent)
        self.set_header("Transaksi", "Semua catatan pengeluaran dan pemasukan.")
        self._build()
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self.refresh)

    # ---------------------------------------------------------- UI

    def _build(self) -> None:
        add_button = QPushButton("+  Tambah Transaksi")
        add_button.setObjectName("Primary")
        add_button.clicked.connect(self._add)
        self.header_actions.addWidget(add_button)

        undo_button = QPushButton("Undo terakhir")
        undo_button.clicked.connect(self._undo)
        self.header_actions.addWidget(undo_button)

        filters = Card()
        bar = QHBoxLayout()
        bar.setSpacing(10)

        self.month_combo = QComboBox()
        self.month_combo.setMinimumWidth(150)
        now = local_now(self.service.tz)
        year, month = now.year, now.month
        for _ in range(30):
            self.month_combo.addItem(month_label(year, month), (year, month))
            year, month = add_months(year, month, -1)
        self.month_combo.addItem("Semua waktu", None)
        self.month_combo.currentIndexChanged.connect(self.refresh)

        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Semua jenis", None)
        self.kind_combo.addItem("Keluar", TYPE_EXPENSE)
        self.kind_combo.addItem("Masuk", TYPE_INCOME)
        self.kind_combo.currentIndexChanged.connect(self.refresh)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cari catatan…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(lambda _t: self._search_timer.start())

        bar.addWidget(QLabel("Bulan"))
        bar.addWidget(self.month_combo)
        bar.addWidget(self.kind_combo)
        bar.addWidget(self.search_input, 1)
        filters.add_layout(bar)
        self.content.addWidget(filters)

        self.table = QTableView()
        configure_table(self.table)
        self.model = TransactionModel([], palette=self.palette)
        self.table.setModel(self.model)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(COL_DATE, Qt.SortOrder.DescendingOrder)
        self.table.doubleClicked.connect(lambda _i: self._edit())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_DATE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_NOTE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_CATEGORY, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_KIND, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_AMOUNT, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(320)
        self.content.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("Muted")
        footer.addWidget(self.summary_label)
        footer.addStretch(1)

        edit_button = QPushButton("Ubah")
        edit_button.clicked.connect(self._edit)
        delete_button = QPushButton("Hapus")
        delete_button.setObjectName("Danger")
        delete_button.clicked.connect(self._delete)
        footer.addWidget(edit_button)
        footer.addWidget(delete_button)
        self.content.addLayout(footer)

        hint = QLabel("Klik dua kali untuk mengubah. Tombol Delete menghapus transaksi terpilih.")
        hint.setObjectName("Faint")
        self.content.addWidget(hint)

        self._shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table)
        self._shortcut.activated.connect(self._delete)

    # ---------------------------------------------------------- data

    def _current_range(self):
        value = self.month_combo.currentData()
        if value is None:
            return None, None
        year, month = value
        return month_bounds(year, month, self.service.tz)

    def refresh(self) -> None:
        start, end = self._current_range()
        rows = self.service.list_transactions(
            start=start,
            end=end,
            kind=self.kind_combo.currentData(),
            keyword=self.search_input.text(),
            limit=self.PAGE_LIMIT,
        )
        self.model.set_palette(self.palette)
        self.model.set_rows(rows)

        income = self.model.total_income()
        expense = self.model.total_expense()
        summary = (
            f"{len(rows)} transaksi · masuk {money(income)} · keluar {money(expense)}"
            f" · selisih {money(income - expense)}"
        )
        if len(rows) >= self.PAGE_LIMIT:
            summary += f" · menampilkan {self.PAGE_LIMIT} terbaru"
        self.summary_label.setText(summary)

    def restyle(self) -> None:
        self.model.set_palette(self.palette)
        self.refresh()

    # ---------------------------------------------------------- aksi

    def _selected_row(self):
        indexes = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not indexes:
            return None
        return self.model.row_at(indexes[0])

    def _add(self) -> None:
        self.add_transaction()

    def add_transaction(self) -> None:
        """Buka dialog tambah transaksi (dipakai juga oleh pintasan Ctrl+N)."""
        dialog = TransactionDialog(
            self,
            categories=self.service.categories(),
            accounts=self.service.accounts(),
            default_kind=TYPE_EXPENSE,
        )
        if dialog.exec() != TransactionDialog.DialogCode.Accepted or not dialog.result_values:
            return
        try:
            self.service.add_manual(**dialog.result_values)
        except (LedgerError, ValueError) as exc:
            self._error(str(exc))
            return
        self.changed.emit()

    def _edit(self) -> None:
        row = self._selected_row()
        if row is None:
            self._error("Pilih satu transaksi dulu.")
            return

        dialog = TransactionDialog(
            self,
            categories=self.service.categories(),
            accounts=self.service.accounts(),
            row=row,
        )
        if dialog.exec() != TransactionDialog.DialogCode.Accepted or not dialog.result_values:
            return
        try:
            self.service.update_transaction(row.id, **dialog.result_values)
        except (LedgerError, ValueError) as exc:
            self._error(str(exc))
            return
        self.changed.emit()

    def _delete(self) -> None:
        row = self._selected_row()
        if row is None:
            self._error("Pilih satu transaksi dulu.")
            return

        answer = QMessageBox.question(
            self,
            "Hapus transaksi",
            f"Hapus transaksi #{row.id}?\n\n{row.note or '(tanpa catatan)'}\n"
            f"{row.category} · {money(row.amount)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.service.delete_transaction(row.id)
        except LedgerError as exc:
            self._error(str(exc))
            return
        self.changed.emit()

    def _undo(self) -> None:
        try:
            row = self.service.undo_last()
        except LedgerError as exc:
            self._error(str(exc))
            return
        if row is None:
            self._info("Belum ada transaksi untuk dibatalkan.")
            return
        self._info(
            f"Dibatalkan: #{row.id} {row.category} · {row.note or '(tanpa catatan)'}"
        )
        self.changed.emit()

    def _context_menu(self, position) -> None:
        from PySide6.QtWidgets import QMenu

        row = self._selected_row()
        if row is None:
            return
        menu = QMenu(self)
        edit_action = menu.addAction("Ubah")
        delete_action = menu.addAction("Hapus")
        chosen = menu.exec(self.table.viewport().mapToGlobal(position))
        if chosen is edit_action:
            self._edit()
        elif chosen is delete_action:
            self._delete()

    def _error(self, message: str) -> None:
        QMessageBox.warning(self, "Tidak bisa", message)

    def _info(self, message: str) -> None:
        QMessageBox.information(self, "Informasi", message)
