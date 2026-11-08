"""Demo nyata fitur CSV: catat beberapa transaksi lalu lihat isi file CSV."""

import asyncio
import csv
import io
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import Chat, Message, Update, User as TgUser

from bot.csvsync import ledger_path
from bot.db import create_db_engine, init_db
from bot.handlers import get_routers
from bot.middlewares import AuthMiddleware, DatabaseMiddleware, ErrorMiddleware, UserMiddleware

OWNER = 424242
TOKEN = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


class Rec(AiohttpSession):
    def __init__(self):
        super().__init__()
        self.out = []

    async def make_request(self, bot, method, timeout=None):
        p = method.model_dump(exclude_none=True)
        if type(method).__name__ == "SendMessage":
            self.out.append(p.get("text", ""))
        elif type(method).__name__ == "SendDocument":
            self.out.append(f"[DOKUMEN: {p.get('caption', '')[:60]}]")
        return Message(message_id=1, date=datetime.now(), chat=Chat(id=OWNER, type="private"))

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        return None


async def main():
    tmp = Path(tempfile.mkdtemp())
    export_dir = tmp / "data" / "exports"
    eng = create_db_engine(tmp / "data" / "finance.db")
    init_db(eng)

    sess = Rec()
    bot = Bot(token=TOKEN, session=sess, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.update.outer_middleware(ErrorMiddleware())
    dp.update.outer_middleware(AuthMiddleware((OWNER,)))
    dp.update.outer_middleware(DatabaseMiddleware(eng))
    dp.update.outer_middleware(UserMiddleware("Asia/Jakarta", export_dir))
    for r in get_routers():
        dp.include_router(r)

    mid = 0

    async def say(text):
        nonlocal mid
        mid += 1
        before = len(sess.out)
        await dp.feed_update(
            bot,
            Update(update_id=mid, message=Message(
                message_id=mid, date=datetime.now(), chat=Chat(id=OWNER, type="private"),
                from_user=TgUser(id=OWNER, is_bot=False, first_name="Razz"), text=text,
            )),
        )
        print(f">>> {text}")
        for r in sess.out[before:]:
            print("   ", r.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "").replace("\n", " | ")[:110])

    await say("/start")
    await say("kopi 18rb")
    await say("makan siang 35k")
    await say("gaji 7.5jt")
    await say("kemarin bensin 25.000")
    await say("=cmd|'/c calc'!A1 5000")   # uji injeksi
    await say("/undo")

    path = ledger_path(export_dir, OWNER)
    print()
    print("=" * 70)
    print(f"FILE CSV: {path}")
    print(f"ada: {path.exists()}")
    print("=" * 70)
    if path.exists():
        text = path.read_text(encoding="utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        width = [8, 18, 8, 14, 8, 12, 24]
        for i, row in enumerate(rows):
            cells = [str(c)[:w].ljust(w) for c, w in zip(row, width)]
            print(" | ".join(cells))
            if i == 0:
                print("-" * 70)

    print()
    print("=== /ledger (unduh CSV lengkap) ===")
    await say("/ledger")
    eng.dispose()


asyncio.run(main())
