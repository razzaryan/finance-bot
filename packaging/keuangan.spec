# -*- mode: python ; coding: utf-8 -*-
"""Konfigurasi PyInstaller untuk aplikasi Keuangan.

Dibuat sebagai spec (bukan sekadar CLI) supaya hasil build bisa diulang persis
dan mudah dirawat.

Catatan penting:
- `--onedir` dipakai, bukan `--onefile`. Satu file mengekstrak 150 MB ke folder
  temp setiap kali dijalankan (lambat) dan lebih sering memicu false positive
  antivirus.
- Modul Telegram (aiogram) dan handler bot sengaja tidak diikutkan: aplikasi
  desktop tidak memakainya, jadi tidak perlu masuk ke installer.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

# PyInstaller mendefinisikan SPECPATH sebagai folder tempat spec dieksekusi,
# yang bisa berupa cwd tergantung cara pemanggilan. Cari root repo dari situ,
# lalu jatuh ke cwd kalau tidak ketemu.
_candidate = Path(SPECPATH).resolve()  # noqa: F821 - disediakan PyInstaller
if (_candidate / "desktop").is_dir():
    ROOT = _candidate
elif (_candidate.parent / "desktop").is_dir():
    ROOT = _candidate.parent
else:
    ROOT = Path.cwd().resolve()
if not (ROOT / "desktop" / "__main__.py").is_file():
    raise SystemExit(f"Root proyek tidak ditemukan dari {_candidate}")

hiddenimports = [
    "bot.models",
    "bot.entry",
    "bot.jobs.backup",
    "bot.services_defaults",
    "desktop.app",
    "desktop.main_window",
    "desktop.branding",
]
hiddenimports += collect_submodules("sqlmodel")
hiddenimports += collect_submodules("pydantic")
hiddenimports += ["tzdata", "zoneinfo"]

# Modul Qt yang tidak dipakai aplikasi ini.
excludes = [
    "aiogram",
    "apscheduler",
    "dotenv",
    "pytest",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuick3D",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtWebSockets",
    "PySide6.QtBluetooth",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtSvgWidgets",
    "PySide6.QtUiTools",
    "tkinter",
    "unittest",
    "pydoc",
]

a = Analysis(
    [str(ROOT / "desktop" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Keuangan",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "packaging" / "keuangan.ico"),
    version=str(ROOT / "packaging" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Keuangan",
)
