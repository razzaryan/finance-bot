"""Handler bot.

Router dibuat lewat `get_routers()` supaya setiap Dispatcher mendapat instance
baru. aiogram melarang satu Router dipasang ke dua Dispatcher, jadi jangan
memakai router tingkat modul sebagai global.
"""

from __future__ import annotations

from aiogram import Router

from bot.handlers import budgets, categories, fallback, misc, reports, transactions

_BUILDERS = (
    ("misc", misc.register),
    ("transactions", transactions.register),
    ("reports", reports.register),
    ("categories", categories.register),
    ("budgets", budgets.register),
    # WAJIB paling akhir: menangkap semua pesan yang tidak dikenali.
    ("fallback", fallback.register),
)


def get_routers() -> list[Router]:
    """Router baru, urut: command dulu, free-text paling akhir."""
    routers: list[Router] = []
    for name, register in _BUILDERS:
        router = Router(name=name)
        register(router)
        routers.append(router)
    return routers


__all__ = ["get_routers"]
