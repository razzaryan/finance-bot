"""Ikon aplikasi digambar saat runtime (tanpa file aset)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap

ACCENT_TOP = "#3B82F6"
ACCENT_BOTTOM = "#1D4ED8"


def _draw(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor(ACCENT_TOP))
    gradient.setColorAt(1.0, QColor(ACCENT_BOTTOM))

    radius = size * 0.24
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)

    font = QFont("Segoe UI", int(size * 0.38))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(
        QRectF(0, 0, size, size),
        int(Qt.AlignmentFlag.AlignCenter),
        "Rp",
    )
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_draw(size))
    return icon
