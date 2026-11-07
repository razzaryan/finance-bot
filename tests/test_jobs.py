"""Test job terjadwal: rekap harian & backup database."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from sqlalchemy import text
from sqlmodel import Session

from bot.db import create_db_engine, init_db
from bot.jobs.backup import backup_database
from bot.jobs.rekap import send_daily_recaps
from bot.ledger import add_transaction, find_category, get_default_account
from bot.models import TYPE_EXPENSE
from bot.services_defaults import ensure_user
from bot.timeutil import local_naive_to_utc


@pytest.fixture()
def engine():
    eng = create_db_engine(":memory:")
    init_db(eng)
    return eng


class FailingBot:
    """Bot palsu: mencatat pesan, bisa disetel untuk melempar error."""

    def __init__(self, fail: bool = False):
        self.messages: list[tuple[int, str]] = []
        self.fail = fail

    async def send_message(self, chat_id: int, text: str, **kwargs):
        if self.fail:
            from aiogram.exceptions import TelegramForbiddenError

            raise TelegramForbiddenError(method=None, message="Forbidden: bot was blocked by the user")
        self.messages.append((chat_id, text))
        return True


def run(coro):
    return asyncio.run(coro)


def fixed_local_now(tz_name: str = "Asia/Jakarta") -> datetime:
    """Waktu lokal tetap 22:30 supaya test tidak bergantung jam mesin."""
    return datetime(2026, 10, 20, 22, 30, 0)


@pytest.fixture()
def frozen_clock(monkeypatch):
    import bot.jobs.rekap as rekap_module

    monkeypatch.setattr(rekap_module, "local_now", fixed_local_now)
    return datetime(2026, 10, 20, 22, 30, 0)


def test_recap_sent_once_per_day(engine, frozen_clock):
    with Session(engine) as session:
        user, _ = ensure_user(session, 555001, "Razz")
        user.recap_hour = 21  # 21:00, sekarang 22:30 -> sudah lewat
        session.add(user)
        account = get_default_account(session, user.id)
        category = find_category(session, user.id, "Makan", TYPE_EXPENSE)
        add_transaction(
            session,
            user,
            kind=TYPE_EXPENSE,
            amount=25_000,
            category=category,
            account=account,
            note="kopi pagi",
            occurred_at=local_naive_to_utc(datetime(2026, 10, 20, 9, 0), user.timezone),
        )
        session.commit()
        tg_id = user.telegram_id

    bot = FailingBot()
    run(send_daily_recaps(bot, engine))
    assert len(bot.messages) == 1
    chat_id, text = bot.messages[0]
    assert chat_id == tg_id
    assert "Rekap" in text
    assert "kopi pagi" in text
    assert "25.000" in text

    # panggilan kedua di hari yang sama tidak boleh kirim lagi
    run(send_daily_recaps(bot, engine))
    assert len(bot.messages) == 1


def test_recap_not_sent_before_hour(engine, frozen_clock):
    with Session(engine) as session:
        user, _ = ensure_user(session, 555005, "Razz")
        user.recap_hour = 23  # 23:00, sekarang 22:30 -> belum waktunya
        session.add(user)
        account = get_default_account(session, user.id)
        category = find_category(session, user.id, "Makan", TYPE_EXPENSE)
        add_transaction(
            session,
            user,
            kind=TYPE_EXPENSE,
            amount=5_000,
            category=category,
            account=account,
            note="teh",
            occurred_at=local_naive_to_utc(datetime(2026, 10, 20, 9, 0), user.timezone),
        )
        session.commit()

    bot = FailingBot()
    run(send_daily_recaps(bot, engine))
    assert bot.messages == []


def test_recap_skips_when_no_transaction(engine, frozen_clock):
    with Session(engine) as session:
        user, _ = ensure_user(session, 555002, "Razz")
        user.recap_hour = 21
        session.add(user)
        session.commit()

    bot = FailingBot()
    run(send_daily_recaps(bot, engine))
    assert bot.messages == []

    with Session(engine) as session:
        user = ensure_user(session, 555002, "Razz")[0]
        # ditandai sudah dicek supaya tidak di-query terus tiap 5 menit
        assert user.last_recap_date == "2026-10-20"


def test_recap_disabled_when_blocked(engine, frozen_clock):
    with Session(engine) as session:
        user, _ = ensure_user(session, 555003, "Razz")
        user.recap_hour = 21
        session.add(user)
        account = get_default_account(session, user.id)
        category = find_category(session, user.id, "Makan", TYPE_EXPENSE)
        add_transaction(
            session,
            user,
            kind=TYPE_EXPENSE,
            amount=10_000,
            category=category,
            account=account,
            note="x",
            occurred_at=local_naive_to_utc(datetime(2026, 10, 20, 9, 0), user.timezone),
        )
        session.commit()

    bot = FailingBot(fail=True)
    run(send_daily_recaps(bot, engine))  # tidak boleh meledak

    with Session(engine) as session:
        user = ensure_user(session, 555003, "Razz")[0]
        assert user.recap_hour == 0  # dimatikan otomatis


def test_backup_creates_file(engine, tmp_path):
    with Session(engine) as session:
        ensure_user(session, 555004, "Razz")

    # VACUUM INTO butuh file database nyata; :memory: tidak mendukung
    real_db = tmp_path / "finance.db"
    real_engine = create_db_engine(real_db)
    init_db(real_engine)
    with Session(real_engine) as session:
        ensure_user(session, 555004, "Razz")

    backup_dir = tmp_path / "backups"
    result = backup_database(real_engine, backup_dir, keep=3)
    assert result is not None
    assert result.exists()
    assert result.stat().st_size > 0

    # backup bisa dibuka dan berisi data
    check_engine = create_db_engine(result)
    with Session(check_engine) as session:
        count = session.exec(text("SELECT COUNT(*) FROM users")).one()
        assert count[0] == 1
    real_engine.dispose()
    check_engine.dispose()


def test_backup_prunes_old_files(engine, tmp_path):
    real_db = tmp_path / "finance.db"
    real_engine = create_db_engine(real_db)
    init_db(real_engine)

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for i in range(5):
        old = backup_dir / f"finance-2020010{i + 1}-000000.db"
        old.write_bytes(b"x")

    result = backup_database(real_engine, backup_dir, keep=3)
    assert result is not None

    remaining = sorted(backup_dir.glob("finance-*.db"))
    assert len(remaining) == 3  # 3 terbaru disimpan
    real_engine.dispose()
