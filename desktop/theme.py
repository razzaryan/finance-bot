"""Tema warna & stylesheet aplikasi.

Satu sumber kebenaran untuk warna: palet Python dipakai juga oleh widget yang
menggambar sendiri (kartu, bar anggaran), sementara QSS dirakit dari palet
yang sama. Jadi mode gelap tidak pernah setengah jalan.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QApplication

LIGHT = {
    "bg": "#F1F5F9",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFC",
    "border": "#E2E8F0",
    "text": "#0F172A",
    "muted": "#64748B",
    "faint": "#94A3B8",
    "sidebar": "#0F172A",
    "sidebar_text": "#94A3B8",
    "sidebar_active": "#1E293B",
    "sidebar_hover": "#172033",
    "accent": "#2563EB",
    "accent_hover": "#1D4ED8",
    "accent_soft": "#DBEAFE",
    "income": "#059669",
    "expense": "#DC2626",
    "warn": "#D97706",
    "input": "#FFFFFF",
    "scroll": "#CBD5E1",
    "selection": "#EFF6FF",
}

DARK = {
    "bg": "#0B1220",
    "surface": "#111A2C",
    "surface_alt": "#16213A",
    "border": "#1F2A44",
    "text": "#E2E8F0",
    "muted": "#94A3B8",
    "faint": "#64748B",
    "sidebar": "#070D18",
    "sidebar_text": "#8FA3BF",
    "sidebar_active": "#16213A",
    "sidebar_hover": "#0F1A2E",
    "accent": "#3B82F6",
    "accent_hover": "#2563EB",
    "accent_soft": "#1E3A8A",
    "income": "#34D399",
    "expense": "#F87171",
    "warn": "#FBBF24",
    "input": "#0E1729",
    "scroll": "#334155",
    "selection": "#1E293B",
}


@dataclass(frozen=True)
class Palette:
    name: str
    colors: dict[str, str]

    def __getitem__(self, key: str) -> str:
        return self.colors[key]


def palette_for(mode: str) -> Palette:
    return Palette(name="dark", colors=DARK) if mode == "dark" else Palette(name="light", colors=LIGHT)


def build_stylesheet(p: Palette) -> str:
    c = p.colors
    return f"""
* {{
    font-family: "Segoe UI", "Segoe UI Variable Text", "Inter", sans-serif;
}}

QWidget {{
    color: {c['text']};
    font-size: 13px;
}}

QWidget#Root, QWidget#Page, QScrollArea#PageScroll, QWidget#ScrollBody {{
    background: {c['bg']};
}}

QLabel {{
    background: transparent;
}}

QLabel#PageTitle {{
    font-size: 24px;
    font-weight: 700;
}}

QLabel#PageSubtitle {{
    color: {c['muted']};
    font-size: 13px;
}}

QLabel#CardTitle {{
    color: {c['muted']};
    font-size: 11px;
    font-weight: 700;
}}

QLabel#BigMoney {{
    font-size: 28px;
    font-weight: 700;
}}

QLabel#StatValue {{
    font-size: 20px;
    font-weight: 700;
}}

QLabel#Muted {{
    color: {c['muted']};
}}

QLabel#Faint {{
    color: {c['faint']};
    font-size: 12px;
}}

QLabel#FieldLabel {{
    color: {c['muted']};
    font-size: 12px;
    font-weight: 600;
}}

QLabel#Hint {{
    color: {c['muted']};
    font-size: 12px;
}}

QLabel#ErrorText {{
    color: {c['expense']};
    font-size: 12px;
}}

QLabel#OkText {{
    color: {c['income']};
    font-size: 12px;
}}

QFrame#Card {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 12px;
}}

QFrame#Sidebar {{
    background: {c['sidebar']};
    border: none;
}}

QFrame#Divider {{
    background: {c['border']};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

QLabel#BrandMark {{
    color: #FFFFFF;
    font-size: 15px;
    font-weight: 700;
}}

QLabel#BrandSub {{
    color: {c['faint']};
    font-size: 11px;
}}

QListWidget#Nav {{
    background: transparent;
    border: none;
    outline: none;
}}

QListWidget#Nav::item {{
    color: {c['sidebar_text']};
    padding: 10px 14px;
    margin: 2px 8px;
    border-radius: 8px;
}}

QListWidget#Nav::item:hover {{
    background: {c['sidebar_hover']};
    color: #FFFFFF;
}}

QListWidget#Nav::item:selected {{
    background: {c['sidebar_active']};
    color: #FFFFFF;
    font-weight: 600;
}}

QPushButton {{
    background: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
}}

QPushButton:hover {{
    background: {c['surface_alt']};
}}

QPushButton:pressed {{
    background: {c['border']};
}}

QPushButton:disabled {{
    color: {c['faint']};
    background: {c['surface_alt']};
}}

QPushButton#Primary {{
    background: {c['accent']};
    color: #FFFFFF;
    border: none;
}}

QPushButton#Primary:hover {{
    background: {c['accent_hover']};
}}

QPushButton#Primary:disabled {{
    background: {c['border']};
    color: {c['faint']};
}}

QPushButton#Ghost {{
    background: transparent;
    border: 1px solid {c['border']};
}}

QPushButton#Ghost:hover {{
    background: {c['surface_alt']};
}}

QPushButton#Danger {{
    color: {c['expense']};
}}

QPushButton#Danger:hover {{
    background: {c['surface_alt']};
}}

QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox, QPlainTextEdit {{
    background: {c['input']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 8px 10px;
    selection-background-color: {c['accent']};
    selection-color: #FFFFFF;
}}

QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus,
QSpinBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {c['accent']};
}}

QLineEdit:disabled, QComboBox:disabled {{
    color: {c['faint']};
    background: {c['surface_alt']};
}}

QLineEdit#QuickEntry {{
    font-size: 16px;
    padding: 12px 14px;
    border-radius: 10px;
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox QAbstractItemView {{
    background: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
    selection-background-color: {c['accent_soft']};
    selection-color: {c['text']};
    outline: none;
}}

QTableView {{
    background: {c['surface']};
    alternate-background-color: {c['surface_alt']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: {c['selection']};
    selection-color: {c['text']};
    outline: none;
}}

QTableView::item {{
    padding: 6px 8px;
    border: none;
}}

QHeaderView::section {{
    background: {c['surface_alt']};
    color: {c['muted']};
    border: none;
    border-bottom: 1px solid {c['border']};
    padding: 8px;
    font-weight: 700;
    font-size: 11px;
}}

QTableCornerButton::section {{
    background: {c['surface_alt']};
    border: none;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {c['scroll']};
    border-radius: 5px;
    min-height: 28px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c['muted']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    background: transparent;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background: {c['scroll']};
    border-radius: 5px;
    min-width: 28px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {c['muted']};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
    background: transparent;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}

QProgressBar {{
    background: {c['surface_alt']};
    border: none;
    border-radius: 5px;
    height: 8px;
}}

QProgressBar::chunk {{
    background: {c['accent']};
    border-radius: 5px;
}}

QToolTip {{
    background: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
    padding: 6px;
}}

QMessageBox {{
    background: {c['surface']};
}}

QDialog {{
    background: {c['bg']};
}}

QCheckBox {{
    spacing: 8px;
}}

QMenu {{
    background: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 18px;
    border-radius: 6px;
}}

QMenu::item:selected {{
    background: {c['accent_soft']};
    color: {c['text']};
}}

QMenuBar {{
    background: {c['surface']};
    color: {c['text']};
    border-bottom: 1px solid {c['border']};
    padding: 2px 4px;
}}

QMenuBar::item {{
    background: transparent;
    color: {c['text']};
    padding: 5px 10px;
    border-radius: 6px;
}}

QMenuBar::item:selected {{
    background: {c['surface_alt']};
    color: {c['text']};
}}

QMenuBar::item:pressed {{
    background: {c['border']};
}}

QMenu::separator {{
    height: 1px;
    background: {c['border']};
    margin: 4px 8px;
}}

QStatusBar {{
    background: {c['surface']};
    color: {c['muted']};
    border-top: 1px solid {c['border']};
}}

QStatusBar::item {{
    border: none;
}}

QStatusBar QLabel {{
    color: {c['muted']};
    padding: 2px 6px;
}}

QStatusBar QLabel#Faint {{
    color: {c['faint']};
}}
"""


def apply_theme(app: QApplication, mode: str) -> Palette:
    palette = palette_for(mode)
    app.setStyleSheet(build_stylesheet(palette))
    return palette
