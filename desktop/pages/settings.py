"""Halaman pengaturan: profil, tampilan, data, impor, tentang."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bot.ledger import LedgerError
from desktop.pages.base import Page, clear_layout
from desktop.widgets import Card

TIMEZONES = [
    ("WIB — Asia/Jakarta", "Asia/Jakarta"),
    ("WITA — Asia/Makassar", "Asia/Makassar"),
    ("WIT — Asia/Jayapura", "Asia/Jayapura"),
    ("Asia/Singapore", "Asia/Singapore"),
    ("Asia/Kuala_Lumpur", "Asia/Kuala_Lumpur"),
    ("Asia/Bangkok", "Asia/Bangkok"),
    ("Asia/Tokyo", "Asia/Tokyo"),
    ("Australia/Sydney", "Australia/Sydney"),
    ("Europe/London", "Europe/London"),
    ("America/New_York", "America/New_York"),
    ("UTC", "UTC"),
]

THEMES = [("Terang", "light"), ("Gelap", "dark")]


class SettingsPage(Page):
    theme_changed = Signal(str)

    def __init__(self, service, palette, parent=None) -> None:
        super().__init__(service, palette, parent)
        self.set_header("Pengaturan", "Profil, tampilan, dan lokasi penyimpanan data.")
        self._settings = QSettings("Keuangan", "Keuangan")
        self._build()

    # ---------------------------------------------------------- UI

    def _build(self) -> None:
        # ---------------- profil
        profile = Card("Profil")
        row = QHBoxLayout()
        row.setSpacing(10)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Namamu")
        save_name = QPushButton("Simpan")
        save_name.clicked.connect(self._save_name)
        row.addWidget(QLabel("Nama"))
        row.addWidget(self.name_input, 1)
        row.addWidget(save_name)
        profile.add_layout(row)

        tz_row = QHBoxLayout()
        tz_row.setSpacing(10)
        self.tz_combo = QComboBox()
        for label, value in TIMEZONES:
            self.tz_combo.addItem(label, value)
        save_tz = QPushButton("Simpan")
        save_tz.clicked.connect(self._save_timezone)
        tz_row.addWidget(QLabel("Zona waktu"))
        tz_row.addWidget(self.tz_combo, 1)
        tz_row.addWidget(save_tz)
        profile.add_layout(tz_row)
        self.content.addWidget(profile)

        # ---------------- tampilan
        appearance = Card("Tampilan")
        theme_row = QHBoxLayout()
        theme_row.setSpacing(10)
        self.theme_combo = QComboBox()
        for label, value in THEMES:
            self.theme_combo.addItem(label, value)
        self.theme_combo.currentIndexChanged.connect(self._apply_theme_choice)
        theme_row.addWidget(QLabel("Tema"))
        theme_row.addWidget(self.theme_combo, 1)
        theme_row.addStretch(1)
        appearance.add_layout(theme_row)
        self.content.addWidget(appearance)

        # ---------------- data
        self.storage_card = Card("Data")
        self.storage_body = QVBoxLayout()
        self.storage_body.setSpacing(10)
        self.storage_card.add_layout(self.storage_body)
        self.content.addWidget(self.storage_card)

        # ---------------- impor
        importer = Card("Impor dari versi Telegram")
        description = QLabel(
            "Punya database dari versi bot Telegram? Pilih file <b>finance.db</b>-nya. "
            "Database sekarang dibackup dulu sebelum diganti, jadi tidak ada yang hilang."
        )
        description.setWordWrap(True)
        description.setObjectName("Muted")
        importer.add(description)

        import_row = QHBoxLayout()
        import_row.addStretch(1)
        import_button = QPushButton("Impor database…")
        import_button.clicked.connect(self._import)
        import_row.addWidget(import_button)
        importer.add_layout(import_row)
        self.content.addWidget(importer)

        # ---------------- tentang
        about = Card("Tentang")
        from desktop import __version__

        about_text = QLabel(
            f"<b>Keuangan {__version__}</b><br>"
            "Aplikasi pencatatan keuangan pribadi untuk Windows.<br>"
            "Data disimpan lokal di komputermu — tidak ada yang dikirim ke internet."
        )
        about_text.setWordWrap(True)
        about_text.setObjectName("Muted")
        about.add(about_text)
        self.content.addWidget(about)
        self.content.addStretch(1)

    # ---------------------------------------------------------- profil

    def _save_name(self) -> None:
        self.service.set_user_name(self.name_input.text())
        QMessageBox.information(self, "Tersimpan", "Nama sudah diperbarui.")

    def _save_timezone(self) -> None:
        tz = self.tz_combo.currentData()
        try:
            self.service.set_timezone(tz)
        except LedgerError as exc:
            QMessageBox.warning(self, "Tidak bisa", str(exc))
            return
        QMessageBox.information(
            self,
            "Tersimpan",
            "Zona waktu diperbarui. Tanggal transaksi sekarang dihitung "
            f"dengan {tz}.",
        )
        self.changed.emit()

    # ---------------------------------------------------------- tema

    def _apply_theme_choice(self) -> None:
        mode = self.theme_combo.currentData() or "light"
        self._settings.setValue("theme", mode)
        self.theme_changed.emit(mode)

    def sync_theme(self) -> None:
        mode = self._settings.value("theme", "light")
        index = self.theme_combo.findData(mode)
        if index >= 0:
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(index)
            self.theme_combo.blockSignals(False)

    # ---------------------------------------------------------- data

    def refresh(self) -> None:
        self.name_input.setText(self.service.user_name())

        index = self.tz_combo.findData(self.service.tz)
        if index < 0:
            self.tz_combo.addItem(self.service.tz, self.service.tz)
            index = self.tz_combo.count() - 1
        self.tz_combo.blockSignals(True)
        self.tz_combo.setCurrentIndex(index)
        self.tz_combo.blockSignals(False)

        self.sync_theme()

        info = self.service.storage_info()
        clear_layout(self.storage_body)

        self.storage_body.addWidget(
            self._path_row("Database", info.db_path, extra=f"{_human_size(info.db_bytes)}")
        )
        self.storage_body.addWidget(self._path_row("Folder CSV", info.export_path))
        self.storage_body.addWidget(
            self._path_row("Folder backup", info.backup_path, backup_button=True)
        )

        ledger_file = self.service.ledger_file()
        status = QLabel(
            f"{info.tx_count} transaksi"
            + (f" · {info.first_date} sampai {info.last_date}" if info.first_date else "")
        )
        status.setObjectName("Muted")
        self.storage_body.addWidget(status)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        open_data = QPushButton("Buka folder data")
        open_data.clicked.connect(lambda: self._open(info.db_path.parent))
        rebuild = QPushButton("Tulis ulang CSV")
        rebuild.clicked.connect(self._rebuild_csv)
        open_csv = QPushButton("Buka file CSV")
        open_csv.clicked.connect(lambda: self._open(ledger_file))
        actions.addWidget(open_data)
        actions.addWidget(open_csv)
        actions.addWidget(rebuild)
        actions.addStretch(1)
        self.storage_body.addLayout(actions)

    def _path_row(self, title: str, path: Path, *, extra: str = "", backup_button: bool = False) -> QWidget:
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        label = QLabel(title)
        label.setFixedWidth(110)
        label.setObjectName("FieldLabel")
        layout.addWidget(label)

        value = QLineEdit(str(path))
        value.setReadOnly(True)
        layout.addWidget(value, 1)

        if extra:
            size = QLabel(extra)
            size.setObjectName("Faint")
            layout.addWidget(size)

        open_button = QPushButton("Buka")
        open_button.clicked.connect(lambda: self._open(path))
        layout.addWidget(open_button)

        if backup_button:
            backup_button_widget = QPushButton("Backup sekarang")
            backup_button_widget.clicked.connect(self._backup)
            layout.addWidget(backup_button_widget)

        return holder

    def _open(self, path: Path) -> None:
        target = Path(path)
        if not target.exists():
            target = target.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _backup(self) -> None:
        target = self.service.backup_now()
        if target is None:
            QMessageBox.warning(self, "Gagal", "Backup tidak bisa dibuat. Cek folder data.")
            return
        QMessageBox.information(self, "Backup dibuat", f"Tersimpan di:\n{target}")

    def _rebuild_csv(self) -> None:
        try:
            path, count = self.service.rebuild_ledger()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Gagal", f"Tidak bisa menulis CSV: {exc}")
            return
        QMessageBox.information(
            self, "CSV diperbarui", f"{count} transaksi ditulis ke:\n{path}"
        )

    # ---------------------------------------------------------- impor

    def _import(self) -> None:
        source, _filter = QFileDialog.getOpenFileName(
            self,
            "Pilih database",
            str(Path.home()),
            "Database (*.db *.sqlite *.sqlite3);;Semua file (*.*)",
        )
        if not source:
            return

        answer = QMessageBox.question(
            self,
            "Impor database",
            "Semua data yang ada sekarang akan DIGANTI dengan isi file itu.\n\n"
            "Database sekarang tetap dibackup dulu di folder backup.\n\nLanjutkan?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.service.import_database(source)
        except LedgerError as exc:
            QMessageBox.warning(self, "Gagal impor", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Gagal impor", f"Terjadi kesalahan: {exc}")
            return

        QMessageBox.information(self, "Berhasil", "Database berhasil diimpor.")
        self.changed.emit()

    def restyle(self) -> None:
        self.refresh()


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"
