"""Job terjadwal: rekap harian otomatis."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from sqlmodel import Session, select

from bot.formatting import chunk_message, day_label, recap_text
from bot.ledger import budget_alerts, daily_summary
from bot.models import User
from bot.timeutil import local_now

logger = logging.getLogger(__name__)


def _format_day(day) -> str:
    return day_label(day)


async def send_daily_recaps(bot: Bot, engine) -> None:
    """Kirim rekap untuk user yang jam rekapnya sudah lewat hari ini."""
    with Session(engine) as session:
        users = session.exec(select(User).where(User.recap_hour > 0)).all()

        for user in users:
            now_local = local_now(user.timezone)
            today_key = now_local.date().isoformat()

            if now_local.hour < user.recap_hour:
                continue
            if user.last_recap_date == today_key:
                continue

            try:
                income, expense, items = daily_summary(
                    session, user, now_local.date(), tz_name=user.timezone
                )
                if not items:
                    # Tetap tandai supaya tidak dicek berulang tiap menit.
                    user.last_recap_date = today_key
                    session.add(user)
                    session.commit()
                    continue

                text = recap_text(
                    tz_name=user.timezone,
                    day_label_text=_format_day(now_local.date()),
                    income=income,
                    expense=expense,
                    transactions=items,
                    budget_alerts=budget_alerts(session, user, tz_name=user.timezone),
                )
                for chunk in chunk_message(text):
                    await bot.send_message(user.telegram_id, chunk)

                user.last_recap_date = today_key
                session.add(user)
                session.commit()
                logger.info("Rekap harian terkirim ke %s", user.telegram_id)

            except TelegramForbiddenError:
                logger.warning(
                    "User %s memblokir bot. Rekap dimatikan (recap_hour=0).", user.telegram_id
                )
                user.recap_hour = 0
                session.add(user)
                session.commit()
            except TelegramAPIError:
                logger.exception("Gagal kirim rekap ke %s", user.telegram_id)
            except Exception:
                logger.exception("Error saat menyusun rekap untuk %s", user.telegram_id)
