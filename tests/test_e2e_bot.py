"""End-to-end test: jalankan dispatcher aiogram asli dengan Telegram palsu.

Tujuannya memastikan handler, middleware, parser, dan ledger benar-benar
nyambung — bukan cuma unit test per fungsi.
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
from bot.handlers import get_routers
from bot.ledger import count_transactions, get_totals, list_categories
from bot.middlewares import (
    AuthMiddleware,
    DatabaseMiddleware,
    ErrorMiddleware,
    UserMiddleware,
)
from bot.services_defaults import ensure_user
from bot.timeutil import local_now

OWNER_ID = 424242
TZ = "Asia/Jakarta"


class FakeSession(AiohttpSession):
    """Session palsu: menangkap semua pesan keluar, tidak pernah ke jaringan."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[dict] = []

    async def make_request(self, bot, method: TelegramMethod, timeout=None):
        name = type(method).__name__
        payload = method.model_dump(exclude_none=True)
        self.sent.append({"method": name, **payload})
        if name in {"SendMessage", "SendDocument"}:
            return Message(
                message_id=1000 + len(self.sent),
                date=datetime.now(),
                chat=Chat(id=OWNER_ID, type="private"),
                text=payload.get("text", ""),
            )
        if name == "GetMe":
            return TgUser(id=1, is_bot=True, first_name="FinanceBot", username="finance_bot")
        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    async def close(self) -> None:
        return None


class Harness:
    def __init__(self, engine, owner: int = OWNER_ID):
        self.engine = engine
        self.owner = owner
        self.session = FakeSession()
        self.bot = Bot(
            token="123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            session=self.session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self.dp = Dispatcher()
        self.dp.update.outer_middleware(ErrorMiddleware())
        self.dp.update.outer_middleware(AuthMiddleware((owner,)))
        self.dp.update.outer_middleware(DatabaseMiddleware(engine))
        self.dp.update.outer_middleware(UserMiddleware(TZ))
        for router in get_routers():
            self.dp.include_router(router)
        self._msg_id = 0

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def send(self, text: str, user_id: int | None = None) -> list[str]:
        """Kirim pesan teks sebagai user; kembalikan balasan bot."""
        before = len(self.session.sent)
        uid = user_id if user_id is not None else self.owner
        message = Message(
            message_id=self._next_id(),
            date=datetime.now(),
            chat=Chat(id=uid, type="private"),
            from_user=TgUser(id=uid, is_bot=False, first_name="Razz"),
            text=text,
        )
        update = Update(update_id=self._next_id(), message=message)
        await self.dp.feed_update(self.bot, update)
        replies = [
            m.get("text", "") for m in self.session.sent[before:] if m["method"] == "SendMessage"
        ]
        return replies

    async def close(self) -> None:
        await self.bot.session.close()


@pytest.fixture()
def harness():
    engine = create_db_engine(":memory:")
    init_db(engine)
    h = Harness(engine)
    yield h
    asyncio.get_event_loop_policy()


def run(coro):
    return asyncio.run(coro)


# --- tes -------------------------------------------------------------------


def test_start_creates_user_and_replies(harness):
    replies = run(harness.send("/start"))
    assert len(replies) >= 1
    assert "Bot Laporan Keuangan" in replies[0]

    with Session(harness.engine) as session:
        user = ensure_user(session, OWNER_ID, "Razz")[0]
        assert len(list_categories(session, user.id)) >= 15


def test_free_text_records_expense(harness):
    run(harness.send("/start"))
    replies = run(harness.send("kopi 18rb"))
    assert len(replies) == 1
    assert "Tercatat" in replies[0]
    assert "18.000" in replies[0]
    assert "Makan" in replies[0]

    with Session(harness.engine) as session:
        user = ensure_user(session, OWNER_ID, "Razz")[0]
        income, expense = get_totals(session, user.id)
        assert expense == 18000
        assert income == 0


def test_income_keyword_detected(harness):
    run(harness.send("/start"))
    run(harness.send("gaji 5jt"))
    with Session(harness.engine) as session:
        user = ensure_user(session, OWNER_ID, "Razz")[0]
        income, expense = get_totals(session, user.id)
        assert income == 5_000_000
        assert expense == 0


def test_keluar_and_masuk_commands(harness):
    run(harness.send("/start"))
    run(harness.send("/keluar 25000 makan siang"))
    run(harness.send("/masuk 100000 jual barang"))

    with Session(harness.engine) as session:
        user = ensure_user(session, OWNER_ID, "Razz")[0]
        income, expense = get_totals(session, user.id)
        assert expense == 25000
        assert income == 100_000


def test_forced_kind_overrides_keyword(harness):
    run(harness.send("/start"))
    # "jual" biasanya pemasukan, tapi /keluar memaksa pengeluaran
    run(harness.send("/keluar 50000 jual rugi"))
    with Session(harness.engine) as session:
        user = ensure_user(session, OWNER_ID, "Razz")[0]
        income, expense = get_totals(session, user.id)
        assert expense == 50000
        assert income == 0


def test_saldo_report(harness):
    run(harness.send("/start"))
    run(harness.send("gaji 5jt"))
    run(harness.send("kopi 18rb"))
    replies = run(harness.send("/saldo"))
    assert len(replies) == 1
    assert "Saldo" in replies[0]
    assert "4.982.000" in replies[0]


def test_laporan_shows_categories(harness):
    run(harness.send("/start"))
    run(harness.send("makan siang 35k"))
    run(harness.send("bensin 25rb"))
    replies = run(harness.send("/laporan"))
    text = replies[0]
    assert "Laporan" in text
    assert "Makan" in text
    assert "Transport" in text
    assert "60.000" in text


def test_laporan_empty_month(harness):
    run(harness.send("/start"))
    replies = run(harness.send("/laporan 2020-01"))
    assert "Belum ada transaksi" in replies[0]


def test_undo_removes_last(harness):
    run(harness.send("/start"))
    run(harness.send("kopi 18rb"))
    replies = run(harness.send("/undo"))
    assert "Dihapus" in replies[0]

    with Session(harness.engine) as session:
        user = ensure_user(session, OWNER_ID, "Razz")[0]
        assert count_transactions(session, user.id) == 0


def test_undo_when_empty(harness):
    run(harness.send("/start"))
    replies = run(harness.send("/undo"))
    assert "Belum ada transaksi" in replies[0]


def test_terakhir_lists(harness):
    run(harness.send("/start"))
    run(harness.send("kopi 18rb"))
    replies = run(harness.send("/terakhir"))
    assert "kopi" in replies[0].lower()


def test_cari_finds_transaction(harness):
    run(harness.send("/start"))
    run(harness.send("kopi susu 20rb"))
    run(harness.send("bensin 25rb"))
    replies = run(harness.send("/cari kopi"))
    assert "kopi susu" in replies[0].lower()
    assert "bensin" not in replies[0].lower()


def test_category_mention_override(harness):
    run(harness.send("/start"))
    run(harness.send("beli sesuatu 50rb @Transport"))
    replies = run(harness.send("/laporan"))
    assert "Transport" in replies[0]


def test_unknown_category_mention_is_friendly(harness):
    run(harness.send("/start"))
    replies = run(harness.send("beli 50rb @Ngawur"))
    assert "tidak ada" in replies[0].lower()


def test_kategori_add_and_list(harness):
    run(harness.send("/start"))
    run(harness.send("/kategori tambah keluar Kopi \u2615 kopi,latte"))
    replies = run(harness.send("/kategori"))
    assert "Kopi" in replies[0]


def test_budget_set_and_status(harness):
    run(harness.send("/start"))
    run(harness.send("makan 900rb"))
    replies = run(harness.send("/budget set Makan 1.000.000"))
    assert "diset" in replies[0]

    replies = run(harness.send("/budget"))
    assert "90%" in replies[0] or "900.000" in replies[0]


def test_budget_warning_after_transaction(harness):
    run(harness.send("/start"))
    run(harness.send("/budget set Makan 100000"))
    replies = run(harness.send("makan 95000"))
    assert len(replies) >= 2
    assert "Anggaran" in replies[1]


def test_junk_text_no_crash(harness):
    run(harness.send("/start"))
    replies = run(harness.send("halo bot"))
    assert len(replies) == 1
    assert "18rb" in replies[0]


def test_text_without_number(harness):
    run(harness.send("/start"))
    replies = run(harness.send("makan siang di kantor"))
    assert "Nominal tidak ditemukan" in replies[0]


def test_rekap(harness):
    run(harness.send("/start"))
    run(harness.send("kopi 18rb"))
    replies = run(harness.send("/rekap"))
    assert "Rekap" in replies[0]
    assert "18.000" in replies[0]


def test_hapus_by_id(harness):
    run(harness.send("/start"))
    run(harness.send("kopi 18rb"))
    with Session(harness.engine) as session:
        from bot.ledger import last_transaction

        user = ensure_user(session, OWNER_ID, "Razz")[0]
        trx_id = last_transaction(session, user.id).id

    replies = run(harness.send(f"/hapus {trx_id}"))
    assert "Dihapus" in replies[0]

    with Session(harness.engine) as session:
        user = ensure_user(session, OWNER_ID, "Razz")[0]
        assert count_transactions(session, user.id) == 0


def test_stranger_is_rejected(harness):
    replies = run(harness.send("/start", user_id=999999))
    assert len(replies) == 1
    assert "privat" in replies[0].lower()

    with Session(harness.engine) as session:
        assert session.exec(
            __import__("sqlmodel").select(__import__("bot.models", fromlist=["User"]).User)
        ).first() is None


def test_yesterday_recorded_in_previous_day(harness):
    run(harness.send("/start"))
    run(harness.send("kemarin makan 45k"))
    with Session(harness.engine) as session:
        user = ensure_user(session, OWNER_ID, "Razz")[0]
        from bot.ledger import last_transaction

        trx = last_transaction(session, user.id)
        from bot.timeutil import utc_to_local_naive

        local_day = utc_to_local_naive(trx.occurred_at, TZ).date()
        assert local_day < local_now(TZ).date()


def test_duplicate_message_id_not_double_counted(harness):
    """Telegram bisa mengirim ulang update yang sama; jangan dicatat 2x."""
    run(harness.send("/start"))
    before = len(harness.session.sent)
    message = Message(
        message_id=777,
        date=datetime.now(),
        chat=Chat(id=OWNER_ID, type="private"),
        from_user=TgUser(id=OWNER_ID, is_bot=False, first_name="Razz"),
        text="kopi 18rb",
    )
    update = Update(update_id=9001, message=message)

    run(harness.dp.feed_update(harness.bot, update))
    first_reply = [m["text"] for m in harness.session.sent[before:] if m["method"] == "SendMessage"]
    assert any("Tercatat" in t for t in first_reply)

    # update yang sama dikirim ulang
    run(harness.dp.feed_update(harness.bot, update))
    retry_reply = [
        m["text"]
        for m in harness.session.sent[before + len(first_reply) :]
        if m["method"] == "SendMessage"
    ]
    assert any("sudah tercatat" in t.lower() for t in retry_reply)

    with Session(harness.engine) as session:
        user = ensure_user(session, OWNER_ID, "Razz")[0]
        assert count_transactions(session, user.id) == 1


def test_export_sends_document(harness):
    run(harness.send("/start"))
    run(harness.send("kopi 18rb"))
    before = len(harness.session.sent)
    run(harness.send("/export"))
    docs = [
        m for m in harness.session.sent[before:] if m["method"] == "SendDocument"
    ]
    assert len(docs) == 1
    assert docs[0]["document"].filename.endswith(".csv") if hasattr(docs[0]["document"], "filename") else True
