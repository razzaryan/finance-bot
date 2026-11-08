"""Halaman anggaran bulanan per kategori."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from bot.formatting import money
from bot.ledger import LedgerError
from bot.timeutil import add_months, local_now, month_label
from desktop.dialogs import BudgetDialog
from desktop.pages.base import Page
from desktop.widgets import Card, EmptyState


class BudgetsPage(Page):
    def __init__(self, service, palette, parent=None) -> None:
        super().__init__(service, palette, parent)
        self.set_header("Anggaran", "Batas pengeluaran per kategori setiap bulan.")
        now = local_now(self.service.tz)
        self.year, self.month = now.year, now.month
        self._rows = []
        self._build()

    # ---------------------------------------------------------- UI

    def _build(self) -> None:
        add_button = QPushButton("+  Atur Anggaran")
        add_button.setObjectName("Primary")
        add_button.clicked.connect(self._add)
        self.header_actions.addWidget(add_button)

        nav = Card()
        bar = QHBoxLayout()
        bar.setSpacing(8)

        prev_button = QPushButton("‹")
        prev_button.setFixedWidth(38)
        prev_button.clicked.connect(lambda: self._shift(-1))
        next_button = QPushButton("›")
        next_button.setFixedWidth(38)
        next_button.clicked.connect(lambda: self._shift(1))
        self.month_label = QLabel("")
        self.month_label.setStyleSheet("font-size: 15px; font-weight: 700;")
        current = QPushButton("Bulan ini")
        current.clicked.connect(self._go_current)

        bar.addWidget(prev_button)
        bar.addWidget(self.month_label)
        bar.addWidget(next_button)
        bar.addSpacing(8)
        bar.addWidget(current)
        bar.addStretch(1)

        self.total_label = QLabel("")
        self.total_label.setObjectName("Muted")
        bar.addWidget(self.total_label)
        nav.add_layout(bar)
        self.content.addWidget(nav)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Kategori", "Anggaran", "Terpakai", "Sisa", "Pemakaian"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.horizontalHeader().setHighlightSections(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 160)
        self.table.doubleClicked.connect(lambda _i: self._edit())
        self.table.setMinimumHeight(260)
        self.content.addWidget(self.table, 1)

        self.empty = EmptyState(
            "Belum ada anggaran",
            "Tekan “Atur Anggaran” untuk memberi batas bulanan pada kategori, "
            "mis. Makan Rp 1.500.000.",
        )
        self.content.addWidget(self.empty)

        footer = QHBoxLayout()
        footer.addStretch(1)
        edit_button = QPushButton("Ubah")
        edit_button.clicked.connect(self._edit)
        delete_button = QPushButton("Hapus")
        delete_button.setObjectName("Danger")
        delete_button.clicked.connect(self._delete)
        footer.addWidget(edit_button)
        footer.addWidget(delete_button)
        self.content.addLayout(footer)

        hint = QLabel("Peringatan otomatis muncul di Dashboard saat pemakaian mencapai 80%.")
        hint.setObjectName("Faint")
        self.content.addWidget(hint)

    # ---------------------------------------------------------- navigasi

    def _shift(self, delta: int) -> None:
        self.year, self.month = add_months(self.year, self.month, delta)
        self.refresh()

    def _go_current(self) -> None:
        now = local_now(self.service.tz)
        self.year, self.month = now.year, now.month
        self.refresh()

    # ---------------------------------------------------------- data

    def refresh(self) -> None:
        self.month_label.setText(month_label(self.year, self.month))
        self._rows = self.service.budgets(self.year, self.month)

        self.table.setRowCount(len(self._rows))
        total_limit = 0
        total_used = 0

        for index, budget in enumerate(self._rows):
            total_limit += budget.limit
            total_used += budget.used

            self.table.setItem(index, 0, QTableWidgetItem(budget.category))
            self.table.setItem(index, 1, self._right(money(budget.limit)))
            self.table.setItem(index, 2, self._right(money(budget.used)))

            remaining = budget.remaining
            sisa = self._right(money(remaining))
            if remaining < 0:
                sisa.setForeground(self._brush(self.palette["expense"]))
            self.table.setItem(index, 3, sisa)

            self.table.setCellWidget(index, 4, self._progress(budget))

        self.table.setVisible(bool(self._rows))
        self.empty.setVisible(not self._rows)

        if self._rows:
            self.total_label.setText(
                f"Total anggaran {money(total_limit)} · terpakai {money(total_used)}"
            )
        else:
            self.total_label.setText("")

    @staticmethod
    def _right(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    @staticmethod
    def _brush(color: str):
        from PySide6.QtGui import QBrush, QColor

        return QBrush(QColor(color))

    def _progress(self, budget) -> QWidget:
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(8, 0, 8, 0)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(min(100, int(round(budget.ratio * 100))))
        bar.setTextVisible(False)
        bar.setFixedHeight(8)

        color = self.palette["accent"]
        if budget.status == "lewat":
            color = self.palette["expense"]
        elif budget.status == "hampir":
            color = self.palette["warn"]
        bar.setStyleSheet(
            "QProgressBar { background: %s; border: none; border-radius: 4px; }"
            "QProgressBar::chunk { background: %s; border-radius: 4px; }"
            % (self.palette["surface_alt"], color)
        )
        layout.addWidget(bar)
        return holder

    # ---------------------------------------------------------- aksi

    def _selected_budget(self):
        indexes = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not indexes:
            return None
        row = indexes[0].row()
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def _add(self) -> None:
        dialog = BudgetDialog(self, categories=self.service.categories())
        if dialog.exec() != BudgetDialog.DialogCode.Accepted or not dialog.result_values:
            return
        self._apply(**dialog.result_values)

    def _edit(self) -> None:
        budget = self._selected_budget()
        if budget is None:
            QMessageBox.information(self, "Pilih anggaran", "Pilih satu baris dulu.")
            return
        dialog = BudgetDialog(
            self,
            categories=self.service.categories(),
            current_category_id=budget.category_id,
            current_amount=budget.limit,
        )
        if dialog.exec() != BudgetDialog.DialogCode.Accepted or not dialog.result_values:
            return
        self._apply(**dialog.result_values)

    def _apply(self, category_id: int, amount: int) -> None:
        try:
            self.service.set_budget(category_id, amount)
        except (LedgerError, ValueError) as exc:
            QMessageBox.warning(self, "Tidak bisa", str(exc))
            return
        self.changed.emit()

    def _delete(self) -> None:
        budget = self._selected_budget()
        if budget is None:
            QMessageBox.information(self, "Pilih anggaran", "Pilih satu baris dulu.")
            return
        answer = QMessageBox.question(
            self,
            "Hapus anggaran",
            f"Hapus batas anggaran untuk {budget.category}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.set_budget(budget.category_id, 0)
        except LedgerError as exc:
            QMessageBox.warning(self, "Tidak bisa", str(exc))
            return
        self.changed.emit()

    def restyle(self) -> None:
        self.refresh()
