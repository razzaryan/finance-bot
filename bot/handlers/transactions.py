"""Catat transaksi: /keluar, /masuk, /undo, /hapus, dan pesan teks bebas."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.formatting import category_name, esc, money
from bot.handlers.common import reply_saved
from bot.ledger import delete_transaction, last_transaction, transaction_with_category
from bot.models import TYPE_EXPENSE, TYPE_INCOME

logger = logging.getLogger(__name__)

# Sapaan/obrolan singkat: jangan diperlakukan sebagai transaksi.
_NON_ENTRY_WORDS = {
    "halo",
    "hallo",
    "hai",
    "hi",
    "hey",
    "p",
    "ping",
    "test",
    "tes",
    "ok",
    "oke",
    "sip",
    "makasih",
    "makasi",
    "thanks",
    "thank you",
    "terima kasih",
    "pagi",
    "siang",
    "sore",
    "malam",
    "assalamualaikum",
}


def _is_chitchat(text: str) -> bool:
    return text.strip().lower().strip("!?.,") in _NON_ENTRY_WORDS


def _sync_ledger_after_delete(ctx) -> None:
    """Hapus baris dari file CSV ledger setelah transaksi dihapus."""
    path = ctx.ledger_file()
    if path is None:
        return
    try:
        from bot.csvsync import rewrite_ledger

        rewrite_ledger(path, ctx.session, ctx.user)
    except Exception:  # pragma: no cover - jangan gagalkan penghapusan
        logger.exception("Gagal sinkronisasi CSV setelah hapus")


def register(router: Router) -> None:
    @router.message(Command("keluar", "pengeluaran", "out"))
    async def cmd_keluar(message: Message, command: CommandObject, ctx) -> None:
        payload = (command.args or "").strip()
        if not payload:
            await message.answer(
                "Format: <code>/keluar 25000 makan siang</code>\n"
                "Atau langsung: <code>kopi 18rb</code>"
            )
            return
        await reply_saved(
            message, ctx.session, ctx.user, payload,
            forced_kind=TYPE_EXPENSE, ctx=ctx,
        )

    @router.message(Command("masuk", "pemasukan", "in"))
    async def cmd_masuk(message: Message, command: CommandObject, ctx) -> None:
        payload = (command.args or "").strip()
        if not payload:
            await message.answer("Format: <code>/masuk 5jt gaji</code>")
            return
        await reply_saved(
            message, ctx.session, ctx.user, payload,
            forced_kind=TYPE_INCOME, ctx=ctx,
        )

    @router.message(Command("undo"))
    async def cmd_undo(message: Message, ctx) -> None:
        trx = last_transaction(ctx.session, ctx.user.id)
        if trx is None:
            await message.answer("Belum ada transaksi untuk dibatalkan.")
            return

        trx, category = transaction_with_category(ctx.session, ctx.user.id, trx.id)
        label = category_name(category) if category else "Tanpa Kategori"
        note = (trx.note or "").strip() or "(tanpa catatan)"

        delete_transaction(ctx.session, ctx.user.id, trx.id)
        _sync_ledger_after_delete(ctx)

        await message.answer(
            f"🗑️ Dihapus: <code>#{trx.id}</code> {esc(label)}\n"
            f"{esc(note)} — {money(trx.amount)}"
        )

    @router.message(Command("hapus", "del", "delete"))
    async def cmd_hapus(message: Message, command: CommandObject, ctx) -> None:
        raw = (command.args or "").strip().lstrip("#")
        if not raw.isdigit():
            await message.answer("Format: <code>/hapus 12</code> (id dari /terakhir)")
            return

        trx, category = transaction_with_category(ctx.session, ctx.user.id, int(raw))
        label = category_name(category) if category else "Tanpa Kategori"
        note = (trx.note or "").strip() or "(tanpa catatan)"
        delete_transaction(ctx.session, ctx.user.id, trx.id)
        _sync_ledger_after_delete(ctx)

        await message.answer(
            f"🗑️ Dihapus: <code>#{trx.id}</code> {esc(label)}\n{esc(note)} — {money(trx.amount)}"
        )

    @router.message(F.text & ~F.text.startswith("/"))
    async def free_text_entry(message: Message, ctx) -> None:
        """Teks bebas = transaksi (selama ada nominal)."""
        text = (message.text or "").strip()
        if not text:
            return

        if _is_chitchat(text):
            await message.answer(
                "👋 Kirim nominal untuk mencatat, contoh: <code>kopi 18rb</code>.\n"
                "Butuh bantuan? /help"
            )
            return

        if not any(ch.isdigit() for ch in text):
            await message.answer(
                "🤔 Nominal tidak ditemukan. Contoh: <code>kopi 18rb</code> "
                "atau <code>gaji 5jt</code>.\n/help untuk daftar command."
            )
            return

        await reply_saved(message, ctx.session, ctx.user, text, ctx=ctx)
