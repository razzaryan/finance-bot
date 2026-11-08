"""Widget kecil yang dipakai berulang di banyak halaman."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from bot.models import TYPE_INCOME


class Card(QFrame):
    """Kotak putih dengan judul opsional."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(18, 16, 18, 16)
        self._outer.setSpacing(10)

        self.title_label: QLabel | None = None
        if title:
            self.title_label = QLabel(title.upper())
            self.title_label.setObjectName("CardTitle")
            self._outer.addWidget(self.title_label)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(8)
        self._outer.addLayout(self.body)

    def add(self, widget: QWidget) -> QWidget:
        self.body.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self.body.addLayout(layout)


class StatCard(Card):
    """Kartu angka besar: judul kecil, nilai, keterangan."""

    def __init__(self, title: str, value: str = "—", subtitle: str = "", parent=None) -> None:
        super().__init__(title, parent)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("Faint")
        self.subtitle_label.setWordWrap(True)
        self.body.addWidget(self.value_label)
        self.body.addWidget(self.subtitle_label)

    def set_value(self, value: str, subtitle: str | None = None, color: str | None = None) -> None:
        self.value_label.setText(value)
        if color:
            self.value_label.setStyleSheet(f"color: {color};")
        else:
            self.value_label.setStyleSheet("")
        if subtitle is not None:
            self.subtitle_label.setText(subtitle)


class BarWidget(QWidget):
    """Bar horizontal untuk perbandingan nominal / pemakaian anggaran."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ratio = 0.0
        self._fill = QColor("#2563EB")
        self._track = QColor("#E2E8F0")
        self.setFixedHeight(8)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_ratio(self, ratio: float) -> None:
        self._ratio = max(0.0, min(1.0, float(ratio)))
        self.update()

    def set_colors(self, fill: str, track: str) -> None:
        self._fill = QColor(fill)
        self._track = QColor(track)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - nama dari Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        radius = self.height() / 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._track)
        painter.drawRoundedRect(rect, radius, radius)

        if self._ratio > 0:
            filled = QRectF(0, 0, max(self.height(), self.width() * self._ratio), self.height())
            painter.setBrush(self._fill)
            painter.drawRoundedRect(filled, radius, radius)
        painter.end()


class Badge(QLabel):
    """Label kecil berwarna (Masuk/Keluar/status)."""

    def __init__(self, text: str = "", color: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_color(color)

    def set_color(self, color: str, background: str | None = None) -> None:
        if not color:
            self.setStyleSheet("")
            return
        bg = background or "transparent"
        self.setStyleSheet(
            f"color: {color}; background: {bg}; border-radius: 6px;"
            " padding: 2px 8px; font-size: 11px; font-weight: 700;"
        )


def kind_color(kind: str, palette) -> str:
    return palette["income"] if kind == TYPE_INCOME else palette["expense"]


def money_label(amount: int, palette, *, bold: bool = False) -> QLabel:
    from bot.formatting import money

    label = QLabel(money(amount))
    label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    weight = "font-weight: 700;" if bold else ""
    label.setStyleSheet(f"color: {palette['text']}; {weight}")
    return label


def configure_table(table: QTableView) -> QTableView:
    """Setelan tabel yang sama di semua halaman."""
    table.setAlternatingRowColors(False)
    table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
    table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(40)
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    return table


class EmptyState(QWidget):
    """Tampilan ramah saat belum ada data."""

    def __init__(self, title: str, subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 24)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        head = QLabel(title)
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(head)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("Muted")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setWordWrap(True)
            layout.addWidget(sub)


def section_row(*widgets: QWidget) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    for widget in widgets:
        layout.addWidget(widget)
    return layout


def bold_label(text: str, size: int = 13) -> QLabel:
    label = QLabel(text)
    font = QFont()
    font.setPointSize(size)
    font.setBold(True)
    label.setFont(font)
    return label


def transaction_row(row, palette) -> QWidget:
    """Satu baris transaksi: catatan + kategori di kiri, nominal di kanan."""
    from bot.formatting import money
    from bot.models import TYPE_INCOME

    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 6, 0, 6)
    layout.setSpacing(12)

    left = QVBoxLayout()
    left.setContentsMargins(0, 0, 0, 0)
    left.setSpacing(2)

    note = QLabel((row.note or "").strip() or "(tanpa catatan)")
    note.setStyleSheet("font-weight: 600;")
    left.addWidget(note)

    meta = QLabel(f"{row.category} · {row.when:%d/%m %H:%M} · #{row.id}")
    meta.setObjectName("Faint")
    left.addWidget(meta)

    layout.addLayout(left, 1)

    prefix = "+" if row.kind == TYPE_INCOME else "−"
    color = palette["income"] if row.kind == TYPE_INCOME else palette["expense"]
    amount = QLabel(f"{prefix}{money(row.amount)}")
    amount.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    amount.setStyleSheet(f"color: {color}; font-weight: 700;")
    layout.addWidget(amount)

    return holder
