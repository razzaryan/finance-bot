"""Smoke test: bot benar-benar start, siap polling, lalu shutdown bersih.

Tidak menyentuh jaringan Telegram (session diganti fake) dan tidak menulis
ke database asli.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.methods import TelegramMethod

from bot.config import load_settings
from bot.db import create_db_engine, init_db
from bot.main import build_dispatcher, build_scheduler, setup_logging


class RecordingSession(AiohttpSession):
    def __init__(self):
        super().__init__()
        self.calls: list[str] = []

    async def make_request(self, bot, method: TelegramMethod, timeout=None):
        self.calls.append(type(method).__name__)
        return True

    async def stream_content(self, *args, **kwargs):
        yield b""

    async def close(self) -> None:
        return None


async def main() -> int:
    setup_logging(True)
    tmp = Path(tempfile.mkdtemp())

    env = {
        "BOT_TOKEN": "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "TELEGRAM_OWNER_ID": "424242",
        "TIMEZONE": "Asia/Jakarta",
        "DATA_DIR": str(tmp / "data"),
        "DB_PATH": str(tmp / "data" / "finance.db"),
        "RECAP_HOUR": "21",
    }
    settings = load_settings(env)
    print(f"[ok] settings tok: db={settings.db_path.name} tz={settings.timezone} "
          f"owner={settings.owner_ids} recap={settings.recap_hour}")

    engine = create_db_engine(settings.db_path)
    init_db(engine)
    print(f"[ok] database dibuat: {settings.db_path.exists()}")

    dp = build_dispatcher(settings, engine)
    print(f"[ok] dispatcher: {len(dp.sub_routers)} router")
    for router in dp.sub_routers:
        print(f"       - {router.name}: {len(router.message.handlers)} message handler")

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    session = RecordingSession()
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    scheduler = build_scheduler(bot, settings, engine)
    scheduler.start()
    jobs = [j.id for j in scheduler.get_jobs()]
    print(f"[ok] scheduler jalan, jobs: {jobs}")
    assert "daily_recap" in jobs
    assert "backup_db" in jobs
    scheduler.shutdown(wait=False)

    # bangun dua dispatcher berurutan -> memastikan router tidak bentrok
    dp2 = build_dispatcher(settings, engine)
    print(f"[ok] dispatcher kedua bisa dibuat (router factory bersih): {len(dp2.sub_routers)} router")

    await bot.session.close()
    engine.dispose()
    print("[ok] shutdown bersih")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
