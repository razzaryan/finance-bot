"""Titik masuk aplikasi desktop."""

from __future__ import annotations

import ctypes
import logging
import sys
import traceback
from datetime import date
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from desktop import APP_NAME
from desktop.branding import app_icon
from desktop.paths import backup_dir, data_dir, db_path, export_dir
from desktop.service import LedgerService
from desktop.theme import apply_theme

logger = logging.getLogger(__name__)

SINGLE_INSTANCE_KEY = "keuangan-pribadi-single-instance"


def _setup_logging(folder: Path) -> None:
    handler = RotatingFileHandler(
        folder / "keuangan.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _install_excepthook() -> None:
    def hook(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical(
            "Kesalahan tak tertangani:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        try:
            QMessageBox.critical(
                None,
                "Terjadi kesalahan",
                "Aplikasi menemui kesalahan tak terduga.\n\n"
                f"{exc_type.__name__}: {exc_value}\n\n"
                "Detail tersimpan di folder data (keuangan.log).",
            )
        except Exception:  # pragma: no cover - dialog pun bisa gagal
            pass

    sys.excepthook = hook


def _already_running() -> bool:
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_KEY)
    if socket.waitForConnected(300):
        socket.disconnectFromServer()
        return True
    return False


def _take_single_instance_lock() -> QLocalServer | None:
    server = QLocalServer()
    if not server.listen(SINGLE_INSTANCE_KEY):
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
        if not server.listen(SINGLE_INSTANCE_KEY):
            return None
    return server


def _daily_backup(service: LedgerService) -> None:
    """Backup sekali sehari, tanpa perlu scheduler."""
    settings = QSettings("Keuangan", "Keuangan")
    today = date.today().isoformat()
    if settings.value("last_backup", "") == today:
        return
    try:
        target = service.backup_now()
    except Exception:  # noqa: BLE001 - backup tidak boleh menghalangi start
        logger.exception("Backup harian gagal")
        return
    if target is not None:
        settings.setValue("last_backup", today)
        logger.info("Backup harian: %s", target.name)


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Keuangan.Pribadi.1"
            )
        except Exception:  # pragma: no cover - kosmetik saja
            pass

    folder = data_dir()
    _setup_logging(folder)
    _install_excepthook()
    logger.info("Mulai %s (%s)", APP_NAME, folder)

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName("")
    app.setOrganizationName("Keuangan")
    app.setDesktopFileName("Keuangan")
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(app_icon())

    if _already_running():
        QMessageBox.information(
            None,
            APP_NAME,
            f"{APP_NAME} sudah berjalan.\n"
            "Cek taskbar — jendelanya mungkin tertutup jendela lain.",
        )
        return 0

    server = _take_single_instance_lock()

    mode = QSettings("Keuangan", "Keuangan").value("theme", "light") or "light"
    apply_theme(app, mode)

    try:
        service = LedgerService(db_path(), export_dir(), backup_dir=backup_dir())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Gagal membuka database")
        QMessageBox.critical(
            None,
            f"{APP_NAME} tidak bisa dibuka",
            f"Database tidak bisa diakses.\n\n{exc}\n\nLokasi: {db_path()}",
        )
        return 1

    _daily_backup(service)

    from desktop.main_window import MainWindow

    window = MainWindow(service)
    window.show()

    exit_code = app.exec()
    if server is not None:
        server.close()
    logger.info("Selesai dengan kode %s", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
