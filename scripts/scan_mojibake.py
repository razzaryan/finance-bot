"""Cari teks yang encodingnya rusak (mojibake) di seluruh file proyek.

Mojibake muncul kalau file UTF-8 ditulis ulang oleh alat yang menganggapnya
ANSI (mis. `Set-Content` di PowerShell). Gejalanya emoji dan tanda pisah
berubah menjadi rangkaian huruf Latin beraksen yang aneh.

    .\\.venv\\Scripts\\python.exe scripts\\scan_mojibake.py
"""

from __future__ import annotations

import pathlib
import sys

# Hanya teks proyek; artefak build berisi data biner (tzdata, Qt) yang wajar
# bukan UTF-8 dan akan menghasilkan ribuan laporan palsu.
SKIP_DIRS = {".venv", "__pycache__", ".git", ".pytest_cache", ".ruff_cache", "build", "dist", "node_modules"}
TEXT_SUFFIXES = {".py", ".md", ".ps1", ".iss", ".ini", ".txt", ".example", ".spec", ".json", ".yml", ".yaml", ".cfg", ".toml"}
TEXT_NAMES = {".env.example", "portable.txt"}

MARKERS = (
    "\u00f0\u0178",  # emoji yang salah decode
    "\u00e2\u20ac",  # dash/quote
    "\u00c3\u00a2",
    "\u00c2\u00b1",
    "\ufffd",        # replacement character
)


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    problems = 0
    checked = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
            continue

        checked += 1
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            print(f"BUKAN-UTF8 {path.relative_to(root)}: {exc}")
            problems += 1
            continue

        for marker in MARKERS:
            if marker in text:
                line = text.count("\n", 0, text.index(marker)) + 1
                print(f"MOJIBAKE {path.relative_to(root)}:{line} {marker!r}")
                problems += 1
                break

    print(f"diperiksa {checked} file teks, temuan: {problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
