"""Test regresi untuk bug yang ditemukan saat QA.

Setiap test di sini mewakili bug nyata yang pernah lolos. Jangan hapus.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message, Update
from aiogram.types import User as TgUser
from sqlmodel import Session

from bot.db import create_db_engine, init_db
from bot.formatting import answer_chunked, chunk_message, report_text
from bot.handlers import get_routers
from bot.ledger import count_transactions, list_categories
from bot.middlewares import (
    AuthMiddleware,
    DatabaseMiddleware,
    ErrorMiddleware,
    UserMiddleware,
)
from bot.parser import parse_entry
from bot.services_defaults import ensure_user

OWNER = 424242
TZ = "Asia/Jakarta"
TOKEN = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


# ============================================================
# BUG 1: "kopi18rb" (tanpa spasi) gagal diparse
# ============================================================
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("kopi18rb", 18000),
        ("gaji5jt", 5_000_000),
        ("bensin25rb", 25000),
        ("makan25000", 25000),
        ("kopi 18rb", 18000),
    ],
)
def test_nominal_nempel_tanpa_spasi(text, expected):
    result = parse_entry(text, datetime(2026, 10, 15, 14, 30))
    assert result.amount == expected


def test_angka_nempel_tidak_menelan_kata_berikut():
    """'2x' bukan nominal; jangan sampai 2x dianggap uang."""
    result = parse_entry("2x kopi 18rb", datetime(2026, 10, 15, 14, 30))
    assert result.amount == 18000


# ============================================================
# BUG 2: pesan > 4096 char ditolak Telegram -> bot diam
# ============================================================
class _FakeMsg:
    def __init__(self):
        self.sent: list[str] = []

    async def answer(self, text, **kwargs):
        self.sent.append(text)


def test_laporan_besar_dipecah_dan_semua_di_bawah_limit():
    big = report_text(
        tz_name=TZ,
        title="Laporan Besar",
        income=9_999_999_999,
        expense=8_888_888_888,
        top_expense=[("🍜", f"Kat {i} " + "x" * 50, 1_000_000) for i in range(60)],
        top_income=[("💼", f"Src {i} " + "y" * 50, 1_000_000) for i in range(60)],
        tx_count=999,
        comparison="vs bulan lalu: naik 12%",
    )
    assert len(big) > 4096  # pastikan memang melewati batas

    fake = _FakeMsg()
    asyncio.run(answer_chunked(fake, big))

    assert len(fake.sent) > 1
    assert all(len(m) <= 4096 for m in fake.sent)


# ============================================================
# BUG 3: chunk_message memotong tag HTML -> "can't parse entities"
# ============================================================
def _html_balanced(text: str) -> bool:
    import re

    stack: list[str] = []
    for m in re.finditer(r"<(/?)([a-zA-Z][\w-]*)[^>]*>", text):
        closing, name = m.group(1) == "/", m.group(2).lower()
        if closing:
            if not stack or stack[-1] != name:
                return False
            stack.pop()
        else:
            stack.append(name)
    return not stack


def test_chunk_tidak_merusak_tag_html():
    lines = "\n".join(f"<b>baris {i}</b> teks panjang di sini" for i in range(400))
    for chunk in chunk_message(lines, limit=1000):
        assert _html_balanced(chunk), f"HTML rusak: {chunk[:80]}"


def test_chunk_satu_baris_sangat_panjang_tetap_valid():
    line = "<b>" + "x" * 5000 + "</b>"
    chunks = chunk_message(line, limit=1000)
    assert len(chunks) > 1
    for chunk in chunks:
        assert _html_balanced(chunk), f"HTML rusak: {chunk[:80]}"
        assert len(chunk) <= 1000


def test_chunk_tag_bersarang():
    text = "<b><i>" + "y" * 3000 + "</i></b>"
    for chunk in chunk_message(text, limit=500):
        assert _html_balanced(chunk)


# ============================================================
# BUG 4: akurasi kategori rendah (79.7%) -> laporan menyesatkan
# ============================================================
@pytest.mark.parametrize(
    ("note", "expected"),
    [
        ("teh", "Makan"),
        ("jus", "Makan"),
        ("boba", "Makan"),
        ("sate", "Makan"),
        ("martabak", "Makan"),
        ("camilan", "Makan"),
        ("kue", "Makan"),
        ("gula", "Belanja"),
        ("buah", "Belanja"),
        ("pertalite", "Transport"),
        ("pertamax", "Transport"),
        ("solar", "Transport"),
        ("iuran", "Tagihan"),
        ("spotify", "Tagihan"),
        ("netflix", "Tagihan"),
        ("pulsa", "Tagihan"),
        ("obat", "Kesehatan"),
        ("sedekah", "Sedekah"),
        ("cicilan", "Cicilan"),
        ("buku", "Pendidikan"),
        ("nonton", "Hiburan"),
    ],
)
def test_keyword_bawaan_mengenali_kata_umum(note, expected):
    from bot.parser import match_category

    engine = create_db_engine(":memory:")
    init_db(engine)
    with Session(engine) as session:
        user, _ = ensure_user(session, 1, "QA")
        cats = list_categories(session, user.id, "expense")
        found = match_category(cats, note)
        assert found is not None, f"{note!r} tidak cocok ke kategori mana pun"
        assert found.name == expected, f"{note!r} -> {found.name}, harusnya {expected}"


# ============================================================
# BUG 5: command tidak dikenal dibalas diam
# ============================================================
class _Rec(AiohttpSession):
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


def _harness(engine):
    sess = _Rec()
    bot = Bot(token=TOKEN, session=sess, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.update.outer_middleware(ErrorMiddleware())
    dp.update.outer_middleware(AuthMiddleware((OWNER,)))
    dp.update.outer_middleware(DatabaseMiddleware(engine))
    dp.update.outer_middleware(UserMiddleware(TZ))
    for r in get_routers():
        dp.include_router(r)
    return dp, bot, sess


async def _say(dp, bot, sess, text, mid):
    before = len(sess.out)
    await dp.feed_update(
        bot,
        Update(
            update_id=mid,
            message=Message(
                message_id=mid,
                date=datetime.now(),
                chat=Chat(id=OWNER, type="private"),
                from_user=TgUser(id=OWNER, is_bot=False, first_name="QA"),
                text=text,
            ),
        ),
    )
    return sess.out[before:]


def test_command_tidak_dikenal_dibalas():
    engine = create_db_engine(":memory:")
    init_db(engine)
    dp, bot, sess = _harness(engine)

    out = asyncio.run(_say(dp, bot, sess, "/tidakada", 1))
    assert out, "bot diam untuk command tidak dikenal"
    assert "tidak dikenal" in out[0].lower()
    engine.dispose()


def test_semua_command_asli_tetap_dikenali():
    """Regresi: catch-all tidak boleh menelan command sungguhan."""
    engine = create_db_engine(":memory:")
    init_db(engine)
    dp, bot, sess = _harness(engine)
    asyncio.run(_say(dp, bot, sess, "/start", 1))

    commands = {
        "/saldo": "saldo",
        "/laporan": "2026",          # judul laporan berisi bulan+tahun
        "/rekap": "rekap",
        "/terakhir": "transaksi",
        "/kategori": "kategori",
        "/budget": "anggaran",
        "/help": "bot laporan",
        "/histori": "bulan terakhir",
        "/id": "user id",
    }
    mid = 1
    for cmd, needle in commands.items():
        mid += 1
        out = asyncio.run(_say(dp, bot, sess, cmd, mid))
        assert out, f"{cmd} tidak dibalas"
        assert "tidak dikenal" not in out[0].lower(), f"{cmd} dianggap command tidak dikenal"
        assert needle in out[0].lower(), f"{cmd} balasannya aneh: {out[0][:120]!r}"
    engine.dispose()


def test_pesan_beruntun_tidak_hilang():
    """20 pesan cepat: semua harus tersimpan, tidak ada yang saling menimpa."""
    engine = create_db_engine(":memory:")
    init_db(engine)
    dp, bot, sess = _harness(engine)

    async def run_all():
        await _say(dp, bot, sess, "/start", 1)
        await asyncio.gather(*[_say(dp, bot, sess, f"kopi {i + 1}rb", 100 + i) for i in range(20)])

    asyncio.run(run_all())
    with Session(engine) as session:
        user = ensure_user(session, OWNER, "QA")[0]
        assert count_transactions(session, user.id) == 20
    engine.dispose()


def test_data_bertahan_setelah_restart(tmp_path):
    """Engine baru pada file yang sama harus melihat data lama."""
    db = tmp_path / "persist.db"

    engine1 = create_db_engine(db)
    init_db(engine1)
    dp1, bot1, sess1 = _harness(engine1)
    asyncio.run(_say(dp1, bot1, sess1, "/start", 1))
    asyncio.run(_say(dp1, bot1, sess1, "gaji 5jt", 2))
    asyncio.run(_say(dp1, bot1, sess1, "kopi 18rb", 3))
    engine1.dispose()

    engine2 = create_db_engine(db)
    init_db(engine2)
    dp2, bot2, sess2 = _harness(engine2)
    out = asyncio.run(_say(dp2, bot2, sess2, "/saldo", 4))

    assert out
    assert "4.982.000" in out[0]
    engine2.dispose()


def test_teks_tanpa_nominal_tidak_tercatat():
    engine = create_db_engine(":memory:")
    init_db(engine)
    dp, bot, sess = _harness(engine)
    asyncio.run(_say(dp, bot, sess, "/start", 1))

    asyncio.run(_say(dp, bot, sess, "halo bot apa kabar", 2))
    with Session(engine) as session:
        user = ensure_user(session, OWNER, "QA")[0]
        assert count_transactions(session, user.id) == 0
    engine.dispose()
