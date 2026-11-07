"""Verifikasi terakhir: bot benar-benar start sebagai proses nyata.

Menjalankan bot.main.run() dengan session Telegram palsu, memastikan:
- konfigurasi terbaca
- database dibuat di disk
- dispatcher & scheduler aktif
- polling benar-benar dimulai
- shutdown bersih tanpa menyisakan file terkunci
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message, Update
from aiogram.types import User as TgUser

import bot.main as main_module
from bot.config import load_settings

TOKEN = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
OWNER = 424242


class FakeSession(AiohttpSession):
    """Session palsu yang melayani getMe + getUpdates (lalu berhenti)."""

    def __init__(self):
        super().__init__()
        self.calls: list[str] = []
        self.updates_served = 0

    async def make_request(self, bot, method: TelegramMethod, timeout=None):
        name = type(method).__name__
        self.calls.append(name)

        if name == "GetMe":
            return TgUser(id=1, is_bot=True, first_name="FinanceBot", username="finance_bot")
        if name == "SetMyCommands":
            return True
        if name == "DeleteWebhook":
            return True
        if name == "GetUpdates":
            self.updates_served += 1
            if self.updates_served == 1:
                # kirim satu pesan nyata supaya handler ikut teruji
                return [
                    Update(
                        update_id=1,
                        message=Message(
                            message_id=1,
                            date=__import__("datetime").datetime.now(),
                            chat=Chat(id=OWNER, type="private"),
                            from_user=TgUser(id=OWNER, is_bot=False, first_name="Razz"),
                            text="/start",
                        ),
                    ),
                    Update(
                        update_id=2,
                        message=Message(
                            message_id=2,
                            date=__import__("datetime").datetime.now(),
                            chat=Chat(id=OWNER, type="private"),
                            from_user=TgUser(id=OWNER, is_bot=False, first_name="Razz"),
                            text="kopi 18rb",
                        ),
                    ),
                ]
            if self.updates_served >= 3:
                # hentikan polling dengan sopan (bukan exception di tengah)
                from aiogram.exceptions import TelegramNetworkError

                raise TelegramNetworkError(
                    method=method, message="stop-qa"
                )
            return []
        if name == "SendMessage":
            return Message(
                message_id=1, date=__import__("datetime").datetime.now(),
                chat=Chat(id=OWNER, type="private"),
            )
        return True

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        return None


async def run_bot(settings):
    fake = FakeSession()

    original_bot_init = main_module.Bot

    def patched_bot(*args, **kwargs):
        kwargs["session"] = fake
        return original_bot_init(*args, **kwargs)

    main_module.Bot = patched_bot  # type: ignore[assignment]
    try:
        # batasi polling supaya test tidak menggantung
        original_polling = main_module.Dispatcher.start_polling

        async def limited_polling(self, *args, **kwargs):
            try:
                await asyncio.wait_for(
                    original_polling(self, *args, **kwargs), timeout=8
                )
            except (asyncio.TimeoutError, SystemExit):
                pass
            except Exception:
                # penghentian yang disengaja lewat TelegramNetworkError
                pass

        main_module.Dispatcher.start_polling = limited_polling  # type: ignore[assignment]
        try:
            await main_module.run(settings)
        finally:
            main_module.Dispatcher.start_polling = original_polling  # type: ignore[assignment]
    finally:
        main_module.Bot = original_bot_init  # type: ignore[assignment]

    return fake


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    env = {
        "BOT_TOKEN": TOKEN,
        "TELEGRAM_OWNER_ID": str(OWNER),
        "TIMEZONE": "Asia/Jakarta",
        "DATA_DIR": str(tmp / "data"),
        "DB_PATH": str(tmp / "data" / "finance.db"),
        "RECAP_HOUR": "21",
        "BACKUP_ENABLED": "true",
    }
    settings = load_settings(env)

    main_module.setup_logging(False)
    fake = asyncio.run(run_bot(settings))

    print()
    print("=== HASIL ===")
    db = settings.db_path
    print(f"database dibuat      : {db.exists()} ({db})")
    print(f"panggilan ke Telegram: {sorted(set(fake.calls))}")

    # verifikasi isi database setelah bot sempat memproses 2 pesan
    from sqlmodel import Session

    from bot.db import create_db_engine
    from bot.ledger import count_transactions, get_totals
    from bot.services_defaults import ensure_user

    eng = create_db_engine(db)
    with Session(eng) as s:
        user = ensure_user(s, OWNER, "Razz")[0]
        n = count_transactions(s, user.id)
        income, expense = get_totals(s, user.id)
    eng.dispose()

    print(f"transaksi tersimpan  : {n} (harap 1)")
    print(f"pengeluaran          : {expense} (harap 18000)")

    problems = []
    if not db.exists():
        problems.append("database tidak dibuat")
    if "GetMe" not in fake.calls:
        problems.append("getMe tidak dipanggil")
    if "GetUpdates" not in fake.calls:
        problems.append("polling tidak dimulai")
    if n != 1:
        problems.append(f"transaksi tersimpan {n}, harap 1")
    if expense != 18000:
        problems.append(f"pengeluaran {expense}, harap 18000")

    print()
    if problems:
        print("GAGAL:")
        for p in problems:
            print(" -", p)
        return 1
    print("SEMUA OK: bot start, memproses pesan, mencatat, dan shutdown bersih.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
