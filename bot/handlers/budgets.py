"""Anggaran bulanan: /budget [daftar|set|hapus]."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.formatting import category_name, chunk_message, esc, money, progress_bar
from bot.ledger import budget_status, find_category, set_budget
from bot.models import TYPE_EXPENSE
from bot.parser import parse_amount
from bot.timeutil import local_now, month_label


def register(router: Router) -> None:
    @router.message(Command("budget", "anggaran"))
    async def cmd_budget(message: Message, command: CommandObject, ctx) -> None:
        args = (command.args or "").strip()
        parts = args.split(maxsplit=1)
        action = parts[0].lower() if parts else "daftar"

        if action in {"daftar", "list"}:
            await _show(message, ctx)
        elif action in {"set", "atur"}:
            await _set(message, parts, ctx)
        elif action in {"hapus", "del", "delete", "reset"}:
            await _delete(message, parts, ctx)
        else:
            await message.answer(
                "Format:\n"
                "<code>/budget</code> — lihat status\n"
                "<code>/budget set Makan 1.500.000</code>\n"
                "<code>/budget hapus Makan</code>"
            )

    async def _show(message: Message, ctx) -> None:
        user = ctx.user
        now = local_now(user.timezone)
        rows = budget_status(ctx.session, user, now.year, now.month, tz_name=user.timezone)

        if not rows:
            await message.answer(
                "Belum ada anggaran.\nContoh: <code>/budget set Makan 1.500.000</code>"
            )
            return

        lines = [f"🎯 <b>Anggaran {esc(month_label(now.year, now.month))}</b>", "━━━━━━━━━━━━━━━━━━"]
        total_limit = total_used = 0
        for category, limit, used in rows:
            total_limit += limit
            total_used += used
            ratio = used / limit if limit else 0
            icon = "🚨" if ratio >= 1 else ("⚠️" if ratio >= 0.8 else "✅")
            lines.append(
                f"{icon} {esc(category_name(category))}\n"
                f"   {progress_bar(ratio)} {int(round(ratio * 100))}%\n"
                f"   {money(used)} / {money(limit)} · sisa {money(limit - used)}"
            )

        if total_limit:
            ratio = total_used / total_limit
            lines += [
                "",
                f"<b>Total</b> {progress_bar(ratio)} {int(round(ratio * 100))}%\n"
                f"{money(total_used)} / {money(total_limit)}",
            ]

        for chunk in chunk_message("\n".join(lines)):
            await message.answer(chunk)

    async def _set(message: Message, parts: list[str], ctx) -> None:
        if len(parts) < 2:
            await message.answer("Format: <code>/budget set Makan 1.500.000</code>")
            return

        tokens = parts[1].split()
        if len(tokens) < 2:
            await message.answer(
                "Format: <code>/budget set Makan 1.500.000</code>\n"
                "Nama kategori di depan, nominal di akhir."
            )
            return

        amount = parse_amount(tokens[-1])
        name = " ".join(tokens[:-1]).strip()
        if amount is None:
            await message.answer(
                "Nominal tidak terbaca. Contoh: <code>/budget set Makan 1.5jt</code>"
            )
            return

        category = find_category(ctx.session, ctx.user.id, name, TYPE_EXPENSE)
        if category is None:
            await message.answer(
                f"Kategori pengeluaran '{esc(name)}' tidak ada.\n"
                "Lihat <code>/kategori</code> atau buat baru."
            )
            return

        set_budget(ctx.session, ctx.user, category, amount)
        await message.answer(f"✅ Anggaran {esc(category_name(category))} diset {money(amount)}/bulan.")

    async def _delete(message: Message, parts: list[str], ctx) -> None:
        if len(parts) < 2:
            await message.answer("Format: <code>/budget hapus Makan</code>")
            return
        name = parts[1].strip()
        category = find_category(ctx.session, ctx.user.id, name, TYPE_EXPENSE)
        if category is None:
            await message.answer(f"Kategori '{esc(name)}' tidak ditemukan.")
            return
        set_budget(ctx.session, ctx.user, category, 0)
        await message.answer(f"🗑️ Anggaran {esc(category_name(category))} dihapus.")
