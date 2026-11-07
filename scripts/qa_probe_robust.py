"""PROBE KETAHANAN - konkurensi, DB terkunci, input tak terduga di level bot.

Mensimulasikan kondisi nyata: user mengetik cepat (pesan beruntun), DB
sedang di-backup (terkunci), dan pesan aneh dari Telegram.
"""

from __future__ import annotations

import asyncio
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
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message, Update
from aiogram.types import User as TgUser
from sqlmodel import Session

from bot.db import create_db_engine, init_db
from bot.handlers import get_routers
from bot.ledger import count_transactions, get_totals
from bot.middlewares import (
    AuthMiddleware,
    DatabaseMiddleware,
    ErrorMiddleware,
    UserMiddleware,
)
from bot.services_defaults import ensure_user

OWNER = 424242
TZ = "Asia/Jakarta"
TOKEN = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

findings: list[str] = []


def bug(label: str, detail: str = "") -> None:
    findings.append(f"{label} :: {detail}")
    print(f"  BUG  {label}  {detail}")


def ok(label: str) -> None:
    print(f"  ok   {label}")


class Rec(AiohttpSession):
    def __init__(self):
        super().__init__()
        self.out: list[str] = []

    async def make_request(self, bot, method: TelegramMethod, timeout=None):
        p = method.model_dump(exclude_none=True)
        if type(method).__name__ == "SendMessage":
            self.out.append(p.get("text", ""))
        return Message(message_id=1, date=datetime.now(), chat=Chat(id=OWNER, type="private"))

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        return None


def build(engine):
    sess = Rec()
    bot = Bot(token=TOKEN, session=sess, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.update.outer_middleware(ErrorMiddleware())
    dp.update.outer_middleware(AuthMiddleware((OWNER,)))
    dp.update.outer_middleware(DatabaseMiddleware(engine))
    dp.update.outer_middleware(UserMiddleware(TZ))
    for r in get_routers():
        dp.include_router(r)
    return dp, bot, sess


async def send(dp, bot, sess, text, mid):
    before = len(sess.out)
    upd = Update(
        update_id=mid,
        message=Message(
            message_id=mid,
            date=datetime.now(),
            chat=Chat(id=OWNER, type="private"),
            from_user=TgUser(id=OWNER, is_bot=False, first_name="QA"),
            text=text,
        ),
    )
    await dp.feed_update(bot, upd)
    return sess.out[before:]


async def main() -> None:
    # ============================================================
    print("\n=== A. PESAN BERUNTUN (rapid fire) ===")
    # ============================================================
    engine = create_db_engine(":memory:")
    init_db(engine)
    dp, bot, sess = build(engine)

    await send(dp, bot, sess, "/start", 1)

    tasks = []
    for i in range(20):
        tasks.append(send(dp, bot, sess, f"kopi {i + 1}rb", 100 + i))
    results = await asyncio.gather(*tasks, return_exceptions=True)

    errors = [r for r in results if isinstance(r, Exception)]
    if errors:
        bug("pesan beruntun menimbulkan exception", repr(errors[0]))
    else:
        ok("20 pesan beruntun tidak error")

    with Session(engine) as s:
        user = ensure_user(s, OWNER, "QA")[0]
        n = count_transactions(s, user.id)
        # 20 transaksi (nomor 1..20 rb) = 210rb
        _, spent = get_totals(s, user.id)
        expected_n = 20
        expected_sum = sum((i + 1) * 1000 for i in range(20))
        if n == expected_n:
            ok(f"semua 20 transaksi tersimpan (n={n})")
        else:
            bug("ada transaksi hilang saat beruntun", f"n={n}, harap {expected_n}")
        if spent == expected_sum:
            ok(f"total benar: {spent}")
        else:
            bug("total salah saat beruntun", f"{spent} != {expected_sum}")

    # id unik?
    with Session(engine) as s:
        from sqlmodel import select

        from bot.models import Transaction

        user = ensure_user(s, OWNER, "QA")[0]
        rows = s.exec(select(Transaction).where(Transaction.user_id == user.id)).all()
        ids = [r.id for r in rows]
        if len(ids) == len(set(ids)):
            ok("semua id transaksi unik")
        else:
            bug("id transaksi duplikat", str(ids))

    # ============================================================
    print("\n=== B. DB FILE NYATA + BACKUP SAAT JOB LAIN JALAN ===")
    # ============================================================
    tmp = Path(tempfile.mkdtemp())
    db_path = tmp / "f.db"
    eng2 = create_db_engine(db_path)
    init_db(eng2)
    dp2, bot2, sess2 = build(eng2)
    await send(dp2, bot2, sess2, "/start", 1)
    await send(dp2, bot2, sess2, "kopi 10rb", 2)

    from bot.jobs.backup import backup_database

    res = backup_database(eng2, tmp / "bk", keep=3)
    if res and res.exists() and res.stat().st_size > 0:
        ok("backup DB file berhasil")
    else:
        bug("backup gagal", str(res))

    # setelah backup, bot harus masih bisa menulis
    out = await send(dp2, bot2, sess2, "teh 5rb", 3)
    if out and "Tercatat" in out[0]:
        ok("bot tetap bisa menulis setelah backup")
    else:
        bug("bot gagal menulis setelah backup", str(out)[:100])

    # backup bisa dibuka & isinya konsisten.
    # Catatan: /start tidak membuat transaksi, jadi saat backup hanya ada 1
    # transaksi ("kopi 10rb"). "teh 5rb" dibuat SETELAH backup.
    from sqlmodel import create_engine as ce

    ce2 = ce(f"sqlite:///{res.as_posix()}")
    with Session(ce2) as s:
        from sqlmodel import select

        from bot.models import Transaction as T

        n = len(s.exec(select(T)).all())
        if n == 1:
            ok(f"backup berisi data saat backup diambil ({n} transaksi)")
        else:
            bug("isi backup tidak sesuai", f"{n} transaksi, harap 1")
    ce2.dispose()
    eng2.dispose()

    # ============================================================
    print("\n=== C. PESAN ANEH DARI TELEGRAM ===")
    # ============================================================
    engine3 = create_db_engine(":memory:")
    init_db(engine3)
    dp3, bot3, sess3 = build(engine3)
    await send(dp3, bot3, sess3, "/start", 1)

    WEIRD = [
        ("", "teks kosong"),
        ("/", "slash saja"),
        ("/tidakada", "command tidak dikenal"),
        ("/keluar", "keluar tanpa argumen"),
        ("/masuk", "masuk tanpa argumen"),
        ("/hapus", "hapus tanpa id"),
        ("/hapus abc", "hapus id bukan angka"),
        ("/hapus 999999", "hapus id tidak ada"),
        ("/laporan 2099-01", "laporan masa depan"),
        ("/laporan 2026-13", "bulan tidak valid"),
        ("/budget set", "budget tanpa argumen"),
        ("/budget set Makan", "budget tanpa nominal"),
        ("/kategori tambah", "kategori tanpa argumen"),
        ("/cari", "cari tanpa kata"),
        ("/export 2020-01", "export bulan kosong"),
        ("🎉" * 30, "emoji saja"),
        ("10rb", "nominal saja tanpa catatan"),
        ("@Makan", "mention saja"),
        ("-", "strip saja"),
        ("0", "nol"),
        ("0rb", "nol rb"),
        ("999999999999999rb", "nominal overflow"),
        ("a" * 4000, "teks 4000 char tanpa angka"),
    ]
    mid = 10
    for text, label in WEIRD:
        mid += 1
        try:
            out = await send(dp3, bot3, sess3, text, mid)
            # harus ada balasan (tidak diam)
            if not out:
                bug(f"tidak ada balasan: {label}", repr(text[:30]))
            else:
                ok(f"dibalas: {label}")
        except Exception as e:  # noqa: BLE001
            bug(f"crash: {label}", f"{type(e).__name__}: {e}")

    with Session(engine3) as s:
        user = ensure_user(s, OWNER, "QA")[0]
        n = count_transactions(s, user.id)
        print(f"  info: {n} transaksi tercatat dari pesan aneh (harap 1: '10rb')")
        if n == 1:
            ok("hanya input valid yang tercatat")
        else:
            bug("input aneh ikut tercatat", f"n={n}")

    # ============================================================
    print("\n=== D. STATE BERTAHAN (restart) ===")
    # ============================================================
    tmp2 = Path(tempfile.mkdtemp())
    p = tmp2 / "persist.db"
    e1 = create_db_engine(p)
    init_db(e1)
    d1, b1, s1 = build(e1)
    await send(d1, b1, s1, "/start", 1)
    await send(d1, b1, s1, "gaji 5jt", 2)
    await send(d1, b1, s1, "kopi 18rb", 3)
    s1.out.clear()
    e1.dispose()

    # "restart": engine baru dari file yang sama
    e2 = create_db_engine(p)
    init_db(e2)
    d2, b2, s2 = build(e2)
    out = await send(d2, b2, s2, "/saldo", 4)
    if out and "4.982.000" in out[0]:
        ok("data bertahan setelah restart (/saldo = 4.982.000)")
    else:
        bug("data hilang setelah restart", str(out)[:200])
    e2.dispose()

    print("\n" + "=" * 60)
    print(f"TOTAL TEMUAN KETAHANAN: {len(findings)}")
    print("=" * 60)
    for f in findings:
        print(" -", f)


asyncio.run(main())
sys.exit(1 if findings else 0)
