"""Logika pencatatan yang dipakai bersama oleh bot Telegram & aplikasi desktop.

Modul ini sengaja TIDAK mengimpor aiogram: Telegram hanyalah salah satu
antarmuka, aplikasi desktop adalah antarmuka lainnya. Keduanya memakai jalur
parse -> pilih jenis -> pilih kategori -> simpan yang sama, sehingga perilaku
pencatatan tidak pernah berbeda di antara dua UI.
"""

from __future__ import annotations

from html import escape as _escape

from bot.ledger import (
    LedgerError,
    add_transaction,
    fallback_category,
    find_category,
    get_default_account,
    list_categories,
)
from bot.models import TYPE_EXPENSE, TYPE_INCOME
from bot.parser import match_category, parse_entry
from bot.timeutil import local_naive_to_utc, local_now

KIND_EMOJI = {TYPE_INCOME: "🟢 Masuk", TYPE_EXPENSE: "🔴 Keluar"}

# Kata yang dipakai untuk menebak kategori kalau tidak ada keyword yang cocok
# dan tidak ada @mention. Teks catatan sudah cukup; ini hanya penguat.
_NOTE_ONLY_FALLBACK = True


def resolve_kind(result, forced: str | None, default: str = TYPE_EXPENSE) -> str:
    """Tentukan jenis transaksi: paksaan command > tanda +/- > kata kunci."""
    if forced in (TYPE_INCOME, TYPE_EXPENSE):
        return forced
    if result.sign == "+":
        return TYPE_INCOME
    if result.sign == "-":
        return TYPE_EXPENSE
    if result.kind_hint in (TYPE_INCOME, TYPE_EXPENSE):
        return result.kind_hint
    return default


def pick_category(session, user, kind: str, result):
    """Pilih kategori: @mention > keyword terpanjang > kategori fallback."""
    categories = list_categories(session, user.id, kind)

    if result.category_hint:
        found = find_category(session, user.id, result.category_hint, kind)
        if found is None:
            available = ", ".join(c.name for c in categories[:8])
            raise LedgerError(
                f"Kategori '@{_escape(result.category_hint)}' tidak ada untuk {KIND_EMOJI[kind]}.\n"
                f"Pilihan: {_escape(available)}"
            )
        return found

    if _NOTE_ONLY_FALLBACK and result.note:
        found = match_category(categories, result.note)
        if found is not None:
            return found

    return fallback_category(session, user, kind)


def save_from_text(session, user, text: str, message_id: int | None, forced_kind: str | None = None):
    """Parse teks & simpan. Mengembalikan (result, addresult, category, kind)."""
    now_local = local_now(user.timezone)
    result = parse_entry(text, now_local, default_kind=forced_kind)
    kind = resolve_kind(result, forced_kind)
    category = pick_category(session, user, kind, result)
    account = get_default_account(session, user.id)

    added = add_transaction(
        session,
        user,
        kind=kind,
        amount=result.amount,
        category=category,
        account=account,
        note=result.note,
        occurred_at=local_naive_to_utc(result.occurred_at, user.timezone),
        message_id=message_id,
    )
    return result, added, category, kind
