"""Simulasi sesi pemakaian nyata: kirim pesan, lihat balasan bot apa adanya."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message, Update
from aiogram.types import User as TgUser

from bot.db import create_db_engine, init_db
from bot.handlers import get_routers
from bot.middlewares import (
    AuthMiddleware,
    DatabaseMiddleware,
    ErrorMiddleware,
    UserMiddleware,
)

OWNER = 424242
TZ = "Asia/Jakarta"


class Recorder(AiohttpSession):
    def __init__(self):
        super().__init__()
        self.out: list[str] = []

    async def make_request(self, bot, method: TelegramMethod, timeout=None):
        payload = method.model_dump(exclude_none=True)
        if type(method).__name__ == "SendMessage":
            self.out.append(payload.get("text", ""))
        elif type(method).__name__ == "SendDocument":
            self.out.append(f"[file CSV terkirim: {payload.get('caption', '')}]")
        return Message(
            message_id=len(self.out) + 1,
            date=datetime.now(),
            chat=Chat(id=OWNER, type="private"),
            text="ok",
        )

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        return None


async def main() -> None:
    engine = create_db_engine(":memory:")
    init_db(engine)

    session = Recorder()
    bot = Bot(
        token="123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = __import__("aiogram").Dispatcher()
    dp.update.outer_middleware(ErrorMiddleware())
    dp.update.outer_middleware(AuthMiddleware((OWNER,)))
    dp.update.outer_middleware(DatabaseMiddleware(engine))
    dp.update.outer_middleware(UserMiddleware(TZ))
    for r in get_routers():
        dp.include_router(r)

    msg_id = 0

    async def say(text: str) -> None:
        nonlocal msg_id
        msg_id += 1
        update = Update(
            update_id=msg_id,
            message=Message(
                message_id=msg_id,
                date=datetime.now(),
                chat=Chat(id=OWNER, type="private"),
                from_user=TgUser(id=OWNER, is_bot=False, first_name="Razz"),
                text=text,
            ),
        )
        before = len(session.out)
        await dp.feed_update(bot, update)
        print(f"\n>>> {text}")
        for reply in session.out[before:]:
            print(reply.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "").replace("<i>", "").replace("</i>", ""))

    await say("/start")
    print("\n" + "=" * 60)
    print("MULAI CATAT TRANSAKSI")
    print("=" * 60)

    await say("/budget set Makan 2000000")
    await say("kopi 18rb")
    await say("makan siang 35k")
    await say("gaji 7500000")
    await say("kemarin bensin 25.000")
    await say("terima transfer 200rb dari budi")
    await say("Indomaret 47.500")
    await say("belanja bulanan 1.850.000")
    await say("/saldo")
    await say("/laporan")
    await say("/rekap")
    await say("/terakhir 3")
    await say("/undo")
    await say("teks aneh tanpa nominal")
    await say("/export")

    print("\n" + "=" * 60)
    print("CEK: semua perintah dibalas tanpa error")
    print("=" * 60)

    engine.dispose()
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
