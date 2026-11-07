"""Kelola kategori: /kategori daftar|tambah|kw|hapus."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.formatting import category_name, chunk_message, esc
from bot.ledger import (
    create_category,
    delete_category,
    list_categories,
    update_category_keywords,
)
from bot.models import TYPE_EXPENSE, TYPE_INCOME

_KIND_ALIASES = {
    "masuk": TYPE_INCOME,
    "in": TYPE_INCOME,
    "income": TYPE_INCOME,
    "pemasukan": TYPE_INCOME,
    "keluar": TYPE_EXPENSE,
    "out": TYPE_EXPENSE,
    "expense": TYPE_EXPENSE,
    "pengeluaran": TYPE_EXPENSE,
}

# Emoji yang dikenali saat menambah kategori, supaya nama tidak ikut tertelan.
_KNOWN_EMOJI = {
    "☕", "🍜", "🛵", "🛒", "🧾", "💊", "📚", "🎮", "🏦", "🤝", "🏠", "📦",
    "💼", "🎁", "💻", "🏪", "📈", "🛍", "🎀", "➕", "💰", "🚗", "✈️", "🎬",
    "🐱", "👕", "🎓", "💡", "📱", "🏋", "🍔", "🎵", "💅", "🧴", "🔧",
}


def _kind_from(text: str, default: str) -> str:
    return _KIND_ALIASES.get((text or "").strip().lower(), default)


def _split_name_emoji_keywords(rest: str) -> tuple[str, str, str]:
    """'Kopi ☕ kopi,latte' -> ('Kopi', '☕', 'kopi,latte')."""
    name_tokens: list[str] = []
    emoji = ""
    keywords = ""
    for token in rest.split():
        if token in _KNOWN_EMOJI:
            emoji = token
        elif "," in token:
            keywords = token
        else:
            name_tokens.append(token)
    return " ".join(name_tokens).strip(), emoji, keywords


def register(router: Router) -> None:
    @router.message(Command("kategori", "categories", "cat"))
    async def cmd_kategori(message: Message, command: CommandObject, ctx) -> None:
        args = (command.args or "").strip()
        parts = args.split(maxsplit=2)
        action = parts[0].lower() if parts else "daftar"

        if action in {"daftar", "list"}:
            await _show_list(message, ctx)
        elif action in {"tambah", "add", "baru"}:
            await _add(message, parts, ctx)
        elif action in {"kw", "keyword", "kata"}:
            await _keywords(message, parts, ctx)
        elif action in {"hapus", "del", "delete"}:
            await _delete(message, parts, ctx)
        else:
            await message.answer(
                "Format:\n"
                "<code>/kategori</code> — lihat semua\n"
                "<code>/kategori tambah keluar Kopi ☕ kopi,latte</code>\n"
                "<code>/kategori kw Kopi kopi,latte</code>\n"
                "<code>/kategori hapus Kopi</code>"
            )

    async def _show_list(message: Message, ctx) -> None:
        categories = list_categories(ctx.session, ctx.user.id)
        if not categories:
            await message.answer("Belum ada kategori.")
            return

        expense = [c for c in categories if c.kind == TYPE_EXPENSE]
        income = [c for c in categories if c.kind == TYPE_INCOME]

        lines = ["🏷️ <b>Kategori kamu</b>", "", f"🔴 <b>Pengeluaran</b> ({len(expense)})"]
        lines += [f"• {esc(category_name(c))}" for c in expense]
        lines += ["", f"🟢 <b>Pemasukan</b> ({len(income)})"]
        lines += [f"• {esc(category_name(c))}" for c in income]
        lines += ["", "Tambah: <code>/kategori tambah keluar Kopi ☕ kopi,latte</code>"]

        for chunk in chunk_message("\n".join(lines)):
            await message.answer(chunk)

    async def _add(message: Message, parts: list[str], ctx) -> None:
        if len(parts) < 3:
            await message.answer("Format: <code>/kategori tambah keluar Kopi ☕ kopi,latte</code>")
            return

        kind = _kind_from(parts[1], TYPE_EXPENSE)
        name, emoji, keywords = _split_name_emoji_keywords(parts[2])
        if not name:
            await message.answer("Nama kategori belum diisi.")
            return

        category = create_category(ctx.session, ctx.user, name, kind, keywords, emoji or "🏷")
        await message.answer(
            f"✅ Kategori dibuat: {esc(category_name(category))} "
            f"({'masuk' if kind == TYPE_INCOME else 'keluar'})"
        )

    async def _keywords(message: Message, parts: list[str], ctx) -> None:
        if len(parts) < 3 or " " not in parts[2]:
            await message.answer("Format: <code>/kategori kw Kopi kopi,latte,espresso</code>")
            return
        name, keywords = parts[2].split(maxsplit=1)

        category = update_category_keywords(ctx.session, ctx.user, name, keywords)
        await message.answer(
            f"✅ Keyword {esc(category.name)}: <code>{esc(category.keywords)}</code>"
        )

    async def _delete(message: Message, parts: list[str], ctx) -> None:
        if len(parts) < 3:
            await message.answer("Format: <code>/kategori hapus Kopi</code>")
            return
        category = delete_category(ctx.session, ctx.user, parts[2].strip())
        await message.answer(f"🗑️ Kategori '{esc(category.name)}' dihapus.")
