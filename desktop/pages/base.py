"""Kerangka halaman: judul, area gulir, dan hook refresh."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from desktop.service import LedgerService


def clear_layout(layout) -> None:
    """Buang semua widget/anak layout. Dipakai saat daftar digambar ulang."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
            continue
        child = item.layout()
        if child is not None:
            clear_layout(child)


class Page(QWidget):
    changed = Signal()

    def __init__(self, service: LedgerService, palette, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self.service = service
        self.palette = palette

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("PageScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.scroll)

        body = QWidget()
        body.setObjectName("ScrollBody")
        self.scroll.setWidget(body)

        self.root = QVBoxLayout(body)
        self.root.setContentsMargins(28, 24, 28, 28)
        self.root.setSpacing(16)

        self._title = ""
        self._subtitle = ""
        self._header_widget = self._build_header()
        self.root.addWidget(self._header_widget)

        self.content = QVBoxLayout()
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(16)
        self.root.addLayout(self.content, 1)

    def _build_header(self) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        self.title_label = QLabel(self._title)
        self.title_label.setObjectName("PageTitle")
        row.addWidget(self.title_label)
        row.addStretch(1)

        self.header_actions = QHBoxLayout()
        self.header_actions.setContentsMargins(0, 0, 0, 0)
        self.header_actions.setSpacing(8)
        row.addLayout(self.header_actions)

        layout.addLayout(row)

        self.subtitle_label = QLabel(self._subtitle)
        self.subtitle_label.setObjectName("PageSubtitle")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.subtitle_label)
        return holder

    def set_header(self, title: str, subtitle: str = "") -> None:
        self._title = title
        self._subtitle = subtitle
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)

    # ---------------------------------------------------------- hook

    def refresh(self) -> None:
        """Gambar ulang isi halaman dari database."""

    def apply_palette(self, palette) -> None:
        self.palette = palette
        self.restyle()

    def restyle(self) -> None:
        """Dipanggil setelah tema berganti."""

    def on_show(self) -> None:
        self.refresh()
