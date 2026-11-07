"""Logika bersama: parse input -> simpan transaksi -> balas."""

from __future__ import annotations

import logging

from aiogram.types import Message

from bot.formatting import category_name, esc, money
from bot.ledger import (
    LedgerError,
    add_transaction,
    budget_status,
    fallback_category,
    find_category,
    get_default_account,
    list_categories,
)
from bot.models import TYPE_EXPENSE, TYPE_INCOME
from bot.parser import match_category, parse_entry
from bot.timeutil import local_naive_to_utc, local_now, utc_to_local_naive

logger = logging.getLogger(__name__)

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
                f"Kategori '@{esc(result.category_hint)}' tidak ada untuk {KIND_EMOJI[kind]}.\n"
                f"Pilihan: {esc(available)}"
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


def confirmation_text(result, trx, category, kind: str, tz_name: str) -> str:
    note = (trx.note or "").strip() or "(tanpa catatan)"
    sign = "+" if kind == TYPE_INCOME else "−"
    local_dt = utc_to_local_naive(trx.occurred_at, tz_name)

    return "\n".join(
        [
            "✅ <b>Tercatat</b>",
            f"{KIND_EMOJI[kind]} · {esc(category_name(category))}",
            f"{sign}{money(trx.amount)} — {esc(note)}",
            f"📅 {esc(result.date_label)} {local_dt:%H:%M} · <code>#{trx.id}</code>",
        ]
    )


def budget_note_for(session, user, category) -> str | None:
    """Peringatan anggaran setelah transaksi pengeluaran (>=80% atau lewat)."""
    if category is None or category.kind != TYPE_EXPENSE:
        return None

    now = local_now(user.timezone)
    rows = budget_status(session, user, now.year, now.month, tz_name=user.timezone)
    match = next((row for row in rows if row[0].id == category.id), None)
    if match is None:
        return None

    _cat, limit, used = match
    if limit <= 0:
        return None

    ratio = used / limit
    if ratio >= 1:
        return f"🚨 Anggaran {esc(category.name)} lewat: {money(used)} / {money(limit)}"
    if ratio >= 0.8:
        return (
            f"⚠️ Anggaran {esc(category.name)} terpakai {int(round(ratio * 100))}%. "
            f"Sisa {money(limit - used)}."
        )
    return None


async def reply_saved(message: Message, session, user, text: str, forced_kind: str | None = None) -> None:
    """Alur lengkap: parse, simpan, balas konfirmasi + peringatan anggaran."""
    result, added, category, kind = save_from_text(
        session, user, text, message.message_id, forced_kind
    )

    if added.duplicate:
        await message.answer(
            f"ℹ️ Transaksi #{added.transaction.id} sudah tercatat sebelumnya, tidak dobel."
        )
        return

    await message.answer(confirmation_text(result, added.transaction, category, kind, user.timezone))

    note = budget_note_for(session, user, category)
    if note:
        await message.answer(note)
