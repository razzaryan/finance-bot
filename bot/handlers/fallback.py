"""Fallback: pesan yang tidak ditangani handler mana pun.

Router ini WAJIB didaftarkan paling akhir. Tujuannya supaya bot tidak pernah
diam total - user selalu dapat balasan yang menjelaskan.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.formatting import esc

HINT = (
    "Kirim /help untuk daftar command, atau langsung ketik transaksi "
    "seperti <code>kopi 18rb</code>."
)


def register(router: Router) -> None:
    @router.message(F.text.startswith("/"))
    async def unknown_command(message: Message) -> None:
        raw = (message.text or "").strip()
        name = raw.split()[0] if raw.split() else "/?"
        await message.answer(
            f"❓ Command <code>{esc(name[:40])}</code> tidak dikenal.\n{HINT}"
        )

    @router.message()
    async def fallback(message: Message) -> None:
        """Tangkap pesan non-teks (stiker, foto, voice, dsb)."""
        await message.answer(
            "🙂 Saya hanya bisa membaca teks.\n"
            "Catat transaksi dengan mengetik, misalnya <code>kopi 18rb</code>.\n" + HINT
        )

    @router.callback_query()
    async def callback_fallback(callback: CallbackQuery) -> None:
        await callback.answer("Tombol ini sudah tidak berlaku.", show_alert=False)
