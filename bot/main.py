"""Entry point bot."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import ConfigError, Settings, load_settings
from bot.db import create_db_engine, init_db
from bot.handlers import get_routers
from bot.jobs.backup import backup_database
from bot.jobs.rekap import send_daily_recaps
from bot.middlewares import (
    AuthMiddleware,
    DatabaseMiddleware,
    ErrorMiddleware,
    UserMiddleware,
)

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Mulai & daftar"),
    BotCommand(command="help", description="Bantuan"),
    BotCommand(command="saldo", description="Saldo & ringkasan bulan ini"),
    BotCommand(command="laporan", description="Laporan bulanan"),
    BotCommand(command="terakhir", description="Transaksi terakhir"),
    BotCommand(command="rekap", description="Rekap hari ini"),
    BotCommand(command="cari", description="Cari transaksi"),
    BotCommand(command="undo", description="Batalkan transaksi terakhir"),
    BotCommand(command="hapus", description="Hapus transaksi by id"),
    BotCommand(command="kategori", description="Kelola kategori"),
    BotCommand(command="budget", description="Anggaran bulanan"),
    BotCommand(command="export", description="Export CSV bulanan"),
    BotCommand(command="id", description="Lihat user id"),
]


def setup_logging(debug: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


def build_dispatcher(settings: Settings, engine) -> Dispatcher:
    dp = Dispatcher()

    # Middleware luar: error handling -> auth -> database -> user context
    dp.update.outer_middleware(ErrorMiddleware())
    dp.update.outer_middleware(AuthMiddleware(settings.owner_ids))
    dp.update.outer_middleware(DatabaseMiddleware(engine))
    dp.update.outer_middleware(UserMiddleware(settings.timezone))

    for router in get_routers():
        dp.include_router(router)
    return dp


def build_scheduler(bot: Bot, settings: Settings, engine) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    scheduler.add_job(
        send_daily_recaps,
        trigger="interval",
        minutes=5,
        args=[bot, engine],
        id="daily_recap",
        max_instances=1,
        coalesce=True,
        next_run_time=None,
    )

    if settings.backup_enabled:
        scheduler.add_job(
            backup_database,
            trigger="cron",
            hour=3,
            minute=0,
            args=[engine, settings.data_dir / "backups", settings.backup_keep],
            id="backup_db",
            max_instances=1,
            coalesce=True,
        )

    return scheduler


async def run(settings: Settings) -> None:
    engine = create_db_engine(settings.db_path)
    init_db(engine)
    logger.info("Database siap: %s", settings.db_path)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher(settings, engine)

    scheduler = build_scheduler(bot, settings, engine)
    scheduler.start()

    me = await bot.get_me()
    logger.info("Bot @%s siap. Owner: %s", me.username, settings.owner_ids)

    try:
        await bot.set_my_commands(COMMANDS)
    except Exception:  # pragma: no cover - bukan fatal
        logger.warning("Gagal set daftar command", exc_info=True)

    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=False,
        )
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        engine.dispose()
        logger.info("Bot berhenti.")


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        setup_logging(False)
        logger.error("Konfigurasi bermasalah: %s", exc)
        return 1

    setup_logging(settings.debug)

    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        logger.info("Dihentikan oleh pengguna.")
        return 0
    except Exception:
        logger.exception("Bot berhenti karena error fatal")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
