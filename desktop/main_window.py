"""Jendela utama: sidebar navigasi, halaman, status bar."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from desktop import APP_NAME, __version__
from desktop.pages import (
    BudgetsPage,
    CategoriesPage,
    DashboardPage,
    ReportsPage,
    SettingsPage,
    TransactionsPage,
)
from desktop.paths import data_dir
from desktop.service import LedgerService
from desktop.theme import apply_theme, palette_for

NAV_ITEMS = [
    ("dashboard", "Dashboard"),
    ("transactions", "Transaksi"),
    ("reports", "Laporan"),
    ("budgets", "Anggaran"),
    ("categories", "Kategori"),
    ("settings", "Pengaturan"),
]


class MainWindow(QMainWindow):
    def __init__(self, service: LedgerService) -> None:
        super().__init__()
        self.service = service
        self._settings = QSettings("Keuangan", "Keuangan")
        self._mode = self._settings.value("theme", "light") or "light"
        self.palette_colors = palette_for(self._mode)

        self.setWindowTitle("Keuangan — Keuangan Pribadi")
        self.resize(1180, 760)
        self.setMinimumSize(940, 620)

        self._build()
        self._wire()

        self._refresh_all()
        self._select("dashboard")

    # ---------------------------------------------------------- bangun UI

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())

        right = QWidget()
        right.setObjectName("Page")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.stack = QStackedWidget()
        right_layout.addWidget(self.stack, 1)
        layout.addWidget(right, 1)

        self.pages = {
            "dashboard": DashboardPage(self.service, self.palette_colors),
            "transactions": TransactionsPage(self.service, self.palette_colors),
            "reports": ReportsPage(self.service, self.palette_colors),
            "budgets": BudgetsPage(self.service, self.palette_colors),
            "categories": CategoriesPage(self.service, self.palette_colors),
            "settings": SettingsPage(self.service, self.palette_colors),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

        status = QStatusBar()
        status.setSizeGripEnabled(True)
        self.setStatusBar(status)
        self.status_label = QLabel("")
        status.addWidget(self.status_label)
        self.db_label = QLabel(str(self.service.db_path))
        self.db_label.setObjectName("Faint")
        status.addPermanentWidget(self.db_label)

        self._build_menu()

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(212)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 22, 0, 18)
        layout.setSpacing(4)

        brand = QWidget()
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(22, 0, 16, 14)
        brand_layout.setSpacing(1)
        mark = QLabel("💰  Keuangan")
        mark.setObjectName("BrandMark")
        sub = QLabel(f"v{__version__} · pribadi")
        sub.setObjectName("BrandSub")
        brand_layout.addWidget(mark)
        brand_layout.addWidget(sub)
        layout.addWidget(brand)

        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for key, label in NAV_ITEMS:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setSizeHint(QSize(0, 42))
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._on_nav)
        layout.addWidget(self.nav, 1)

        footer = QLabel("Ctrl+N tambah transaksi")
        footer.setObjectName("BrandSub")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)

        return sidebar

    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&Berkas")
        add_action = QAction("Tambah Transaksi", self)
        add_action.setShortcut(QKeySequence("Ctrl+N"))
        add_action.triggered.connect(self._add_transaction)
        file_menu.addAction(add_action)

        refresh_action = QAction("Muat Ulang Data", self)
        refresh_action.setShortcut(QKeySequence.StandardKey.Refresh)
        refresh_action.triggered.connect(self._refresh_all)
        file_menu.addAction(refresh_action)

        file_menu.addSeparator()
        quit_action = QAction("Keluar", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = bar.addMenu("&Tampilan")
        for label, mode in (("Tema Terang", "light"), ("Tema Gelap", "dark")):
            action = QAction(label, self)
            action.triggered.connect(lambda _checked=False, m=mode: self._set_theme(m))
            view_menu.addAction(action)

        help_menu = bar.addMenu("&Bantuan")
        data_action = QAction("Buka Folder Data", self)
        data_action.triggered.connect(self._open_data_dir)
        help_menu.addAction(data_action)
        about_action = QAction("Tentang Keuangan", self)
        about_action.triggered.connect(self._about)
        help_menu.addAction(about_action)

    def _wire(self) -> None:
        for page in self.pages.values():
            page.changed.connect(self._refresh_all)
        self.pages["settings"].theme_changed.connect(self._set_theme)

        self.shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        self.shortcut.activated.connect(self._add_transaction)

    # ---------------------------------------------------------- navigasi

    def _on_nav(self, row: int) -> None:
        if 0 <= row < len(NAV_ITEMS):
            key = NAV_ITEMS[row][0]
            page = self.pages[key]
            self.stack.setCurrentWidget(page)
            page.on_show()
            self._update_status(key)

    def _select(self, key: str) -> None:
        for row, (name, _label) in enumerate(NAV_ITEMS):
            if name == key:
                self.nav.setCurrentRow(row)
                return

    def _update_status(self, key: str) -> None:
        messages = {
            "dashboard": "Ringkasan hari ini. Ketik transaksi di kotak Catat cepat, lalu Enter.",
            "transactions": "Klik dua kali untuk mengubah, Delete untuk menghapus.",
            "reports": "Geser bulan dengan tombol ‹ dan ›.",
            "budgets": "Isi 0 untuk menghapus batas sebuah kategori.",
            "categories": "Kata kunci menentukan tebakan kategori otomatis.",
            "settings": "Data tersimpan lokal di komputermu.",
        }
        self.status_label.setText(messages.get(key, ""))

    # ---------------------------------------------------------- aksi

    def _refresh_all(self) -> None:
        for page in self.pages.values():
            page.refresh()
        self._update_status(NAV_ITEMS[max(0, self.nav.currentRow())][0])

    def _add_transaction(self) -> None:
        self._select("transactions")
        self.pages["transactions"].add_transaction()

    def _set_theme(self, mode: str) -> None:
        if mode not in ("light", "dark"):
            mode = "light"
        self._mode = mode
        self._settings.setValue("theme", mode)

        colours = apply_theme(QApplication.instance(), mode)
        self.palette_colors = colours
        for page in self.pages.values():
            page.apply_palette(colours)
        self.status_label.setText(f"Tema: {'Gelap' if mode == 'dark' else 'Terang'}")

    def _open_data_dir(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir())))

    def _about(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.about(
            self,
            f"Tentang {APP_NAME}",
            f"<b>{APP_NAME} {__version__}</b><br>"
            "Pencatatan keuangan pribadi.<br><br>"
            f"Database: <code>{self.service.db_path}</code><br>"
            f"Folder CSV: <code>{Path(self.service.export_dir)}</code><br><br>"
            "Semua data tersimpan di komputermu sendiri.",
        )

    # ---------------------------------------------------------- siklus hidup

    def closeEvent(self, event) -> None:  # noqa: N802 - nama dari Qt
        try:
            self.service.close()
        finally:
            event.accept()
