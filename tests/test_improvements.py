"""Test untuk perbaikan gelombang 2 + fitur CSV ledger.

Mencakup:
- entitas HTML tidak terbelah saat chunking
- CSV/formula injection dinetralkan
- file CSV ledger hidup (tambah & hapus tersinkron)
- konkurensi update tidak menghabiskan pool koneksi
- timezone user dipakai di budget_alerts & monthly_history
"""

from __future__ import annotations

import asyncio
import csv
import io
import re
from datetime import datetime
from pathlib import Path

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message, Update, User as TgUser
from sqlmodel import Session

from bot.csvsync import (
    LEDGER_HEADER,
    append_transaction,
    ledger_path,
    rewrite_ledger,
    sanitize_cell,
)
from bot.db import create_db_engine, init_db
from bot.formatting import chunk_message, esc
from bot.handlers import get_routers
from bot.ledger import (
    add_transaction,
    budget_alerts,
    count_transactions,
    export_csv,
    find_category,
    get_default_account,
    monthly_history,
    set_budget,
)
from bot.middlewares import AuthMiddleware, DatabaseMiddleware, ErrorMiddleware, UserMiddleware
from bot.models import TYPE_EXPENSE
from bot.services_defaults import ensure_user
from bot.timeutil import local_naive_to_utc, month_bounds

OWNER = 424242
TZ = "Asia/Jakarta"
TOKEN = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


# ============================================================
# 1. ENTITAS HTML TIDAK TERBELAH
# ============================================================
ENTITY_RE = re.compile(r"&(?:amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);")


def _broken_entities(text: str) -> list[str]:
    """Cari potongan entitas rusak seperti '&am' atau '&amp' tanpa ';'."""
    bad = []
    for m in re.finditer(r"&[A-Za-z#0-9]{1,6}", text):
        token = m.group(0)
        if not ENTITY_RE.fullmatch(token + ";"):
            bad.append(token)
    return bad


@pytest.mark.parametrize("pad", [990, 994, 995, 996, 997, 998, 999, 1000])
def test_entitas_tidak_terbelah_saat_dipotong(pad):
    text = "a" * pad + "&amp;" + "b" * 200
    for chunk in chunk_message(text, limit=1000):
        assert not _broken_entities(chunk), f"entitas rusak: {_broken_entities(chunk)}"


def test_entitas_saja_tetap_utuh():
    for chunk in chunk_message("&amp;" * 400, limit=7):
        assert not _broken_entities(chunk)
        assert len(chunk) <= 7


def test_chunk_hasil_esc_tetap_valid():
    """Teks user yang mengandung <, >, & di-escape lalu dipotong."""
    raw = ("harga < 10 & diskon > 5 " * 300).strip()
    text = esc(raw)
    chunks = chunk_message(text, limit=500)
    for chunk in chunks:
        assert not _broken_entities(chunk)
        assert len(chunk) <= 500


# ============================================================
# 2. CSV / FORMULA INJECTION
# ============================================================
@pytest.mark.parametrize(
    "raw",
    [
        "=cmd|'/c calc'!A1",
        "=1+1",
        "+SUM(A1:A9)",
        "-2+3",
        "@SUM(1+1)",
        "\tcmd",
        "\rcmd",
    ],
)
def test_sanitize_cell_menetralkan_formula(raw):
    cleaned = sanitize_cell(raw)
    assert cleaned.startswith("'")
    assert cleaned[1:] == raw


@pytest.mark.parametrize("raw", ["kopi", "makan siang", "100%", "a=b", "", None])
def test_sanitize_cell_aman_untuk_teks_biasa(raw):
    result = sanitize_cell(raw)
    assert not result.startswith("'") if result else True


def test_export_csv_tidak_rentan_injection():
    engine = create_db_engine(":memory:")
    init_db(engine)
    with Session(engine) as s:
        user, _ = ensure_user(s, 1, "QA")
        acc = get_default_account(s, user.id)
        cat = find_category(s, user.id, "Makan", TYPE_EXPENSE)
        dangerous = ["=cmd|'/c calc'!A1", "+SUM(A1)", "@evil", "-2+3"]
        for note in dangerous:
            add_transaction(
                s, user, kind=TYPE_EXPENSE, amount=1000, category=cat, account=acc,
                note=note, occurred_at=local_naive_to_utc(datetime(2026, 10, 5, 9, 0), TZ),
            )

        data, count = export_csv(s, user, *month_bounds(2026, 10, TZ))
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))[1:]
        assert len(rows) == count == len(dangerous)

        for row in rows:
            note = row[6]
            assert not note.startswith(("=", "+", "-", "@")), f"belum disanitasi: {note!r}"
    engine.dispose()


# ============================================================
# 3. FILE CSV LEDGER HIDUP
# ============================================================
def test_ledger_append_dan_header(tmp_path):
    engine = create_db_engine(":memory:")
    init_db(engine)
    path = ledger_path(tmp_path, 1)

    with Session(engine) as s:
        user, _ = ensure_user(s, 1, "QA")
        acc = get_default_account(s, user.id)
        cat = find_category(s, user.id, "Makan", TYPE_EXPENSE)
        trx = add_transaction(
            s, user, kind=TYPE_EXPENSE, amount=18_000, category=cat, account=acc,
            note="kopi", occurred_at=local_naive_to_utc(datetime(2026, 10, 5, 9, 0), TZ),
        ).transaction

        append_transaction(path, trx, cat, acc, TZ)
        append_transaction(path, trx, cat, acc, TZ)

    assert path.exists()
    text = path.read_text(encoding="utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == LEDGER_HEADER
    assert len(rows) == 3  # header + 2 baris
    assert rows[1][6] == "kopi"
    assert rows[1][5] == "18000"
    engine.dispose()


def test_ledger_rewrite_setelah_hapus(tmp_path):
    engine = create_db_engine(":memory:")
    init_db(engine)
    path = ledger_path(tmp_path, 2)

    with Session(engine) as s:
        user, _ = ensure_user(s, 2, "QA")
        acc = get_default_account(s, user.id)
        cat = find_category(s, user.id, "Makan", TYPE_EXPENSE)
        ids = []
        for i in range(3):
            trx = add_transaction(
                s, user, kind=TYPE_EXPENSE, amount=(i + 1) * 1000, category=cat,
                account=acc, note=f"n{i}",
                occurred_at=local_naive_to_utc(datetime(2026, 10, 5 + i, 9, 0), TZ),
            ).transaction
            ids.append(trx.id)
            append_transaction(path, trx, cat, acc, TZ)

        from bot.ledger import delete_transaction

        delete_transaction(s, user.id, ids[1])
        total = rewrite_ledger(path, s, user)

    assert total == 2
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    assert len(rows) == 3  # header + 2
    assert "n1" not in [r[6] for r in rows]
    engine.dispose()


def test_ledger_sanitasi_catatan_berbahaya(tmp_path):
    engine = create_db_engine(":memory:")
    init_db(engine)
    path = ledger_path(tmp_path, 3)

    with Session(engine) as s:
        user, _ = ensure_user(s, 3, "QA")
        acc = get_default_account(s, user.id)
        cat = find_category(s, user.id, "Makan", TYPE_EXPENSE)
        trx = add_transaction(
            s, user, kind=TYPE_EXPENSE, amount=5000, category=cat, account=acc,
            note="=cmd|'/c calc'!A1",
            occurred_at=local_naive_to_utc(datetime(2026, 10, 5, 9, 0), TZ),
        ).transaction
        append_transaction(path, trx, cat, acc, TZ)

    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    assert rows[1][6].startswith("'=")
    engine.dispose()


# ============================================================
# 4. KONKURENSI: pool koneksi tidak boleh habis
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


def _harness(engine, export_dir: Path | None = None):
    sess = _Rec()
    bot = Bot(token=TOKEN, session=sess, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.update.outer_middleware(ErrorMiddleware())
    dp.update.outer_middleware(AuthMiddleware((OWNER,)))
    dp.update.outer_middleware(DatabaseMiddleware(engine))
    dp.update.outer_middleware(UserMiddleware(TZ, export_dir))
    for r in get_routers():
        dp.include_router(r)
    return dp, bot, sess


async def _say(dp, bot, sess, text, mid):
    before = len(sess.out)
    await dp.feed_update(
        bot,
        Update(update_id=mid, message=Message(
            message_id=mid, date=datetime.now(), chat=Chat(id=OWNER, type="private"),
            from_user=TgUser(id=OWNER, is_bot=False, first_name="QA"), text=text,
        )),
    )
    return sess.out[before:]


def test_40_update_bersamaan_tidak_menghabiskan_pool(tmp_path):
    """Dulu: QueuePool limit reached -> TimeoutError 30s (bot menggantung)."""
    engine = create_db_engine(tmp_path / "real.db")
    init_db(engine)
    dp, bot, sess = _harness(engine)

    async def run():
        await _say(dp, bot, sess, "/start", 1)
        await asyncio.wait_for(
            asyncio.gather(*[_say(dp, bot, sess, f"kopi {i + 1}rb", 100 + i) for i in range(40)]),
            timeout=60,
        )

    asyncio.run(run())

    with Session(engine) as s:
        user = ensure_user(s, OWNER, "QA")[0]
        assert count_transactions(s, user.id) == 40
    engine.dispose()


# ============================================================
# 5. TIMEZONE USER DI ANGGARAN & HISTORI
# ============================================================
def test_budget_alerts_pakai_zona_user(monkeypatch):
    """Dulu memakai datetime.now() (zona server) -> bisa salah bulan."""
    import bot.ledger as ledger_mod

    fixed = datetime(2026, 10, 15, 12, 0)
    monkeypatch.setattr(ledger_mod, "local_now", lambda tz: fixed)

    engine = create_db_engine(":memory:")
    init_db(engine)
    with Session(engine) as s:
        user, _ = ensure_user(s, 9, "QA")
        cat = find_category(s, user.id, "Makan", TYPE_EXPENSE)
        set_budget(s, user, cat, 100_000)
        add_transaction(
            s, user, kind=TYPE_EXPENSE, amount=90_000, category=cat,
            account=get_default_account(s, user.id), note="x",
            occurred_at=local_naive_to_utc(datetime(2026, 10, 5, 9, 0), TZ),
        )
        alerts = budget_alerts(s, user, tz_name=TZ)
        assert alerts, "harus ada peringatan 90%"
        assert "90" in alerts[0] or "hampir" in alerts[0]
    engine.dispose()


def test_monthly_history_pakai_zona_user(monkeypatch):
    """Dulu memakai datetime.now() sehingga bulan bisa meleset dari zona user."""
    import bot.timeutil as timeutil

    fixed = datetime(2026, 1, 5, 10, 0)
    # monthly_history mengimpor local_now di dalam fungsi -> patch sumbernya
    monkeypatch.setattr(timeutil, "local_now", lambda tz: fixed)

    engine = create_db_engine(":memory:")
    init_db(engine)
    with Session(engine) as s:
        user, _ = ensure_user(s, 10, "QA")
        rows = monthly_history(s, user, 3, tz_name=TZ)
        labels = [label for label, _, _ in rows]
        assert labels[0].startswith("Jan")
        assert labels[1].startswith("Des")  # Desember tahun sebelumnya
        assert labels[2].startswith("Nov")
    engine.dispose()


# ============================================================
# 6. FITUR /ledger (CSV lengkap)
# ============================================================
def test_command_ledger_mengirim_csv_lengkap(tmp_path):
    engine = create_db_engine(":memory:")
    init_db(engine)
    export_dir = tmp_path / "exports"
    dp, bot, sess = _harness(engine, export_dir)

    async def run():
        await _say(dp, bot, sess, "/start", 1)
        await _say(dp, bot, sess, "kopi 18rb", 2)
        await _say(dp, bot, sess, "gaji 5jt", 3)

    asyncio.run(run())

    path = ledger_path(export_dir, OWNER)
    assert path.exists(), "file CSV ledger tidak dibuat otomatis"
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    assert rows[0] == LEDGER_HEADER
    assert len(rows) == 3
    engine.dispose()


def test_undo_menghapus_baris_csv(tmp_path):
    engine = create_db_engine(":memory:")
    init_db(engine)
    export_dir = tmp_path / "exports"
    dp, bot, sess = _harness(engine, export_dir)

    async def run():
        await _say(dp, bot, sess, "/start", 1)
        await _say(dp, bot, sess, "kopi 18rb", 2)
        await _say(dp, bot, sess, "teh 5rb", 3)
        await _say(dp, bot, sess, "/undo", 4)

    asyncio.run(run())

    path = ledger_path(export_dir, OWNER)
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    assert len(rows) == 2  # header + 1 transaksi
    assert rows[1][6] == "kopi"
    engine.dispose()
