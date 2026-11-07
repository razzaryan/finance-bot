"""Command dasar: /start /help /ping /id /cancel."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.formatting import esc, money
from bot.ledger import total_balance
from bot.services_defaults import ensure_user

HELP_TEXT = """🤖 <b>Bot Laporan Keuangan Pribadi</b>

<b>Cara cepat</b>
Kirim teks bebas, nominal bisa pakai <code>rb</code>/<code>k</code>/<code>jt</code>:
<code>kopi 18rb</code> → pengeluaran
<code>gaji 5jt</code> → pemasukan
<code>kemarin bensin 25.000</code>
<code>makan siang 35k @Makan</code> → kategori dipaksa

<b>Command</b>
/keluar &lt;teks&gt; — catat pengeluaran
/masuk &lt;teks&gt; — catat pemasukan
/saldo — saldo &amp; ringkasan bulan ini
/laporan [bulan] — laporan bulanan (contoh: <code>/laporan 2026-10</code>)
/terakhir [n] — transaksi terakhir
/cari &lt;kata&gt; — cari transaksi
/undo — hapus transaksi terakhir
/hapus &lt;id&gt; — hapus transaksi tertentu
/kategori — kelola kategori
/budget — atur anggaran bulanan
/export [bulan] — unduh CSV
/rekap — rekap hari ini
/help — bantuan ini

<i>Semua nominal dalam Rupiah.</i>"""


def register(router: Router) -> None:
    @router.message(CommandStart())
    async def cmd_start(message: Message, ctx) -> None:
        user, created = ensure_user(ctx.session, message.from_user.id, message.from_user.full_name or "")
        balance = total_balance(ctx.session, user)

        name = esc(message.from_user.first_name or "kamu")
        if created:
            greeting = (
                f"Halo <b>{name}</b>! 👋\n\n"
                "Akun <b>Dompet</b> dan kategori bawaan sudah saya siapkan.\n"
                f"Saldo awal: <b>{money(balance)}</b>\n\n"
            )
        else:
            greeting = (
                f"Halo lagi, <b>{name}</b>! 👋\n"
                f"Saldo saat ini: <b>{money(balance)}</b>\n\n"
            )

        await message.answer(greeting + HELP_TEXT)

    @router.message(Command("help", "bantuan"))
    async def cmd_help(message: Message) -> None:
        await message.answer(HELP_TEXT)

    @router.message(Command("ping"))
    async def cmd_ping(message: Message) -> None:
        await message.answer("🏓 Pong! Bot aktif.")

    @router.message(Command("cancel", "batal2"))
    async def cmd_cancel(message: Message) -> None:
        await message.answer("Oke, tidak ada yang disimpan. 👍")

    @router.message(Command("id"))
    async def cmd_id(message: Message) -> None:
        await message.answer(
            f"User ID kamu: <code>{message.from_user.id}</code>\n"
            f"Chat ID: <code>{message.chat.id}</code>"
        )
