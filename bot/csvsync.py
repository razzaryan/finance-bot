"""Sinkronisasi ledger ke file CSV yang bisa langsung dibuka di Excel.

Dua fungsi:
1. Sanitasi sel CSV -> mencegah CSV/formula injection.
2. Ledger hidup: setiap transaksi ditambahkan ke `data/exports/ledger.csv`,
   dan file ditulis ulang saat ada penghapusan.

Kenapa sanitasi perlu: Excel mengeksekusi sel yang diawali `=`, `+`, `-`, `@`,
tab, atau CR sebagai formula. Kalau catatan transaksi berisi
`=cmd|'/c calc'!A1`, membuka CSV bisa menjalankan perintah di komputer.
Awalan `'` membuat Excel memperlakukannya sebagai teks biasa.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import threading
from pathlib import Path

from bot.models import TYPE_INCOME

logger = logging.getLogger(__name__)

LEDGER_HEADER = ["id", "tanggal", "jenis", "kategori", "akun", "nominal", "catatan"]

# Karakter yang membuat Excel/Sheets menganggap sel sebagai formula.
_DANGEROUS_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell(value) -> str:
    """Netralkan sel yang bisa dieksekusi sebagai formula oleh Excel."""
    text = "" if value is None else str(value)
    if text and text.startswith(_DANGEROUS_PREFIX):
        return "'" + text
    return text


def ledger_path(export_dir: Path, user_id: int) -> Path:
    return Path(export_dir) / f"ledger-{user_id}.csv"


def _write_rows(path: Path, rows: list[list]) -> None:
    """Tulis atomik: file sementara lalu replace, supaya tidak pernah setengah."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(LEDGER_HEADER)
    writer.writerows(rows)
    tmp.write_text("\ufeff" + buffer.getvalue(), encoding="utf-8", newline="")
    os.replace(tmp, path)


_lock = threading.Lock()


def append_transaction(path: Path, trx, category, account, tz_name: str) -> None:
    """Tambahkan satu transaksi ke akhir file CSV (langsung, tanpa export ulang)."""
    from bot.timeutil import format_datetime_local

    row = [
        trx.id,
        format_datetime_local(trx.occurred_at, tz_name),
        "masuk" if trx.kind == TYPE_INCOME else "keluar",
        sanitize_cell(getattr(category, "name", "")),
        sanitize_cell(getattr(account, "name", "")),
        trx.amount,
        sanitize_cell(trx.note or ""),
    ]

    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        exists = path.exists() and path.stat().st_size > 0
        mode = "a" if exists else "w"
        with path.open(mode, encoding="utf-8", newline="") as handle:
            if not exists:
                handle.write("\ufeff")
            writer = csv.writer(handle, lineterminator="\n")
            if not exists:
                writer.writerow(LEDGER_HEADER)
            writer.writerow(row)


def rewrite_ledger(path: Path, session, user) -> int:
    """Bangun ulang seluruh file CSV dari database (dipakai setelah hapus)."""
    from sqlmodel import select

    from bot.ledger import list_accounts
    from bot.models import Category, Transaction
    from bot.timeutil import format_datetime_local

    accounts = {acc.id: acc.name for acc in list_accounts(session, user.id)}
    stmt = (
        select(Transaction, Category)
        .join(Category, Category.id == Transaction.category_id, isouter=True)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.occurred_at, Transaction.id)
    )

    rows: list[list] = []
    for trx, category in session.exec(stmt).all():
        rows.append(
            [
                trx.id,
                format_datetime_local(trx.occurred_at, user.timezone),
                "masuk" if trx.kind == TYPE_INCOME else "keluar",
                sanitize_cell(getattr(category, "name", "")),
                sanitize_cell(accounts.get(trx.account_id, "")),
                trx.amount,
                sanitize_cell(trx.note or ""),
            ]
        )
    with _lock:
        _write_rows(path, rows)
    return len(rows)
