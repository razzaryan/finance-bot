"""Model tabel untuk daftar transaksi."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor

from bot.formatting import money
from bot.models import TYPE_INCOME
from desktop.service import TxRow

COL_DATE, COL_NOTE, COL_CATEGORY, COL_KIND, COL_AMOUNT = range(5)
HEADERS = ["Tanggal", "Catatan", "Kategori", "Jenis", "Nominal"]


class TransactionModel(QAbstractTableModel):
    def __init__(self, rows: list[TxRow] | None = None, palette=None, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[TxRow] = list(rows or [])
        self._palette = palette
        self._sort_column = COL_DATE
        self._sort_order = Qt.SortOrder.DescendingOrder

    # ---------------------------------------------------------- Qt API

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]
        return str(section + 1)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if column == COL_DATE:
                return row.when.strftime("%d/%m/%Y %H:%M")
            if column == COL_NOTE:
                return row.note or "(tanpa catatan)"
            if column == COL_CATEGORY:
                return row.category
            if column == COL_KIND:
                return row.kind_label
            if column == COL_AMOUNT:
                prefix = "+" if row.kind == TYPE_INCOME else "−"
                return f"{prefix}{money(row.amount)}"
            return None

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if column == COL_AMOUNT:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if column == COL_KIND:
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.ForegroundRole and self._palette is not None:
            if column == COL_AMOUNT or column == COL_KIND:
                color = (
                    self._palette["income"]
                    if row.kind == TYPE_INCOME
                    else self._palette["expense"]
                )
                return QBrush(QColor(color))
            if column == COL_DATE:
                return QBrush(QColor(self._palette["muted"]))
            return None

        if role == Qt.ItemDataRole.UserRole:
            return row.id

        if role == Qt.ItemDataRole.ToolTipRole:
            return f"#{row.id} · {row.note or '(tanpa catatan)'}"

        return None

    # ---------------------------------------------------------- data

    def set_rows(self, rows: list[TxRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self._apply_sort()
        self.endResetModel()

    def set_palette(self, palette) -> None:
        self._palette = palette
        if self._rows:
            top = self.index(0, 0)
            bottom = self.index(len(self._rows) - 1, len(HEADERS) - 1)
            self.dataChanged.emit(top, bottom)

    def rows(self) -> list[TxRow]:
        return list(self._rows)

    def row_at(self, index: QModelIndex) -> TxRow | None:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        return self._rows[index.row()]

    def total_income(self) -> int:
        return sum(r.amount for r in self._rows if r.kind == TYPE_INCOME)

    def total_expense(self) -> int:
        return sum(r.amount for r in self._rows if r.kind != TYPE_INCOME)

    # ---------------------------------------------------------- sorting

    def sort(self, column: int, order=Qt.SortOrder.AscendingOrder) -> None:
        self.layoutAboutToBeChanged.emit()
        self._sort_column = column
        self._sort_order = order
        self._apply_sort()
        self.layoutChanged.emit()

    def _apply_sort(self) -> None:
        reverse = self._sort_order == Qt.SortOrder.DescendingOrder
        keys = {
            COL_DATE: lambda r: (r.when, r.id),
            COL_NOTE: lambda r: (r.note or "").lower(),
            COL_CATEGORY: lambda r: r.category.lower(),
            COL_KIND: lambda r: r.kind,
            COL_AMOUNT: lambda r: r.amount,
        }
        key = keys.get(self._sort_column, keys[COL_DATE])
        self._rows.sort(key=key, reverse=reverse)
