"""Logika bersama: parse input -> simpan transaksi -> balas."""

from __future__ import annotations

import logging

from aiogram.types import Message

from bot.entry import KIND_EMOJI, save_from_text
from bot.formatting import category_name, esc, money
from bot.ledger import budget_status
from bot.models import TYPE_EXPENSE, TYPE_INCOME
from bot.timeutil import local_now, utc_to_local_naive

logger = logging.getLogger(__name__)



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


async def reply_saved(message: Message, session, user, text: str, forced_kind: str | None = None, ctx=None) -> None:
    """Alur lengkap: parse, simpan, tulis CSV, balas konfirmasi + alert anggaran."""
    result, added, category, kind = save_from_text(
        session, user, text, message.message_id, forced_kind
    )

    if added.duplicate:
        await message.answer(
            f"ℹ️ Transaksi #{added.transaction.id} sudah tercatat sebelumnya, tidak dobel."
        )
        return

    # Tulis ke file CSV ledger (kalau fitur ini aktif).
    if ctx is not None:
        path = ctx.ledger_file()
        if path is not None:
            try:
                from bot.csvsync import append_transaction
                from bot.ledger import get_default_account

                append_transaction(
                    path,
                    added.transaction,
                    category,
                    get_default_account(session, user.id),
                    user.timezone,
                )
            except Exception:  # pragma: no cover - jangan gagalkan pencatatan
                logger.exception("Gagal menulis ke CSV ledger")

    await message.answer(confirmation_text(result, added.transaction, category, kind, user.timezone))

    note = budget_note_for(session, user, category)
    if note:
        await message.answer(note)
