"""Halaman kategori: daftar, tambah, ubah, hapus."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from bot.ledger import LedgerError
from bot.models import TYPE_EXPENSE, TYPE_INCOME
from desktop.dialogs import CategoryDialog
from desktop.pages.base import Page
from desktop.widgets import Card


class CategoriesPage(Page):
    def __init__(self, service, palette, parent=None) -> None:
        super().__init__(service, palette, parent)
        self.set_header(
            "Kategori",
            "Kategori dan kata kuncinya menentukan tebakan otomatis saat mencatat.",
        )
        self._rows = []
        self._build()

    def _build(self) -> None:
        add_button = QPushButton("+  Kategori Baru")
        add_button.setObjectName("Primary")
        add_button.clicked.connect(self._add)
        self.header_actions.addWidget(add_button)

        filters = Card()
        bar = QHBoxLayout()
        bar.setSpacing(10)

        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Semua", None)
        self.kind_combo.addItem("Keluar", TYPE_EXPENSE)
        self.kind_combo.addItem("Masuk", TYPE_INCOME)
        self.kind_combo.currentIndexChanged.connect(self.refresh)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cari kategori…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.refresh)

        bar.addWidget(self.kind_combo)
        bar.addWidget(self.search_input, 1)
        filters.add_layout(bar)
        self.content.addWidget(filters)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Kategori", "Jenis", "Kata kunci", "Dipakai"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setHighlightSections(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(lambda _i: self._edit())
        self.table.setMinimumHeight(300)
        self.content.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.hint_label = QLabel(
            "Contoh kata kunci: kopi, latte, ngopi — pisahkan dengan koma."
        )
        self.hint_label.setObjectName("Faint")
        footer.addWidget(self.hint_label)
        footer.addStretch(1)

        edit_button = QPushButton("Ubah")
        edit_button.clicked.connect(self._edit)
        delete_button = QPushButton("Hapus")
        delete_button.setObjectName("Danger")
        delete_button.clicked.connect(self._delete)
        footer.addWidget(edit_button)
        footer.addWidget(delete_button)
        self.content.addLayout(footer)

    # ---------------------------------------------------------- data

    def refresh(self) -> None:
        keyword = self.search_input.text().strip().lower()
        rows = self.service.categories(self.kind_combo.currentData())
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in row.name.lower() or keyword in row.keywords.lower()
            ]
        self._rows = rows

        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            name_item = QTableWidgetItem(f"{row.emoji} {row.name}".strip())
            if row.is_default:
                name_item.setToolTip("Kategori bawaan")
            self.table.setItem(index, 0, name_item)

            kind_item = QTableWidgetItem("Masuk" if row.kind == TYPE_INCOME else "Keluar")
            kind_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(index, 1, kind_item)

            self.table.setItem(index, 2, QTableWidgetItem(row.keywords or "—"))

            used_item = QTableWidgetItem(str(row.used))
            used_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(index, 3, used_item)

    def _selected(self):
        indexes = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not indexes:
            return None
        row = indexes[0].row()
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    # ---------------------------------------------------------- aksi

    def _add(self) -> None:
        dialog = CategoryDialog(
            self, default_kind=self.kind_combo.currentData() or TYPE_EXPENSE
        )
        if dialog.exec() != CategoryDialog.DialogCode.Accepted or not dialog.result_values:
            return
        try:
            self.service.add_category(**dialog.result_values)
        except (LedgerError, ValueError) as exc:
            QMessageBox.warning(self, "Tidak bisa", str(exc))
            return
        self.changed.emit()

    def _edit(self) -> None:
        row = self._selected()
        if row is None:
            QMessageBox.information(self, "Pilih kategori", "Pilih satu baris dulu.")
            return

        dialog = CategoryDialog(self, row=row)
        if dialog.exec() != CategoryDialog.DialogCode.Accepted or not dialog.result_values:
            return
        values = dialog.result_values
        try:
            self.service.update_category(
                row.id,
                name=values["name"],
                emoji=values["emoji"],
                keywords=values["keywords"],
            )
        except (LedgerError, ValueError) as exc:
            QMessageBox.warning(self, "Tidak bisa", str(exc))
            return
        self.changed.emit()

    def _delete(self) -> None:
        row = self._selected()
        if row is None:
            QMessageBox.information(self, "Pilih kategori", "Pilih satu baris dulu.")
            return

        if row.used:
            QMessageBox.information(
                self,
                "Masih dipakai",
                f"Kategori “{row.name}” dipakai {row.used} transaksi.\n"
                "Ubah atau hapus transaksinya dulu supaya datanya tidak menggantung.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Hapus kategori",
            f"Hapus kategori “{row.name}”?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.service.delete_category(row.id)
        except LedgerError as exc:
            QMessageBox.warning(self, "Tidak bisa", str(exc))
            return
        self.changed.emit()

    def restyle(self) -> None:
        self.refresh()
