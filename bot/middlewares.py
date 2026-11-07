"""Middleware: whitelist user, sesi database, dan konteks user."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

logger = logging.getLogger(__name__)


@dataclass
class Context:
    """Data per-update yang disuntikkan ke handler lewat data['ctx']."""

    session: Any
    user: Any
    owner_ids: tuple[int, ...]
    tz_name: str


class DatabaseMiddleware(BaseMiddleware):
    """Buka satu Session per update lalu tutup setelah selesai."""

    def __init__(self, engine) -> None:
        self.engine = engine

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from sqlmodel import Session

        with Session(self.engine) as session:
            data["session"] = session
            return await handler(event, data)


class AuthMiddleware(BaseMiddleware):
    """Tolak semua user di luar whitelist. Tanpa ini bot bisa ditulis siapa saja."""

    def __init__(self, owner_ids: tuple[int, ...]) -> None:
        self.owner_ids = set(owner_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        user_id = getattr(user, "id", None)

        if user_id is not None and user_id not in self.owner_ids:
            logger.warning("Akses ditolak untuk user_id=%s", user_id)
            await self._reject(event)
            return None

        return await handler(event, data)

    async def _reject(self, event: TelegramObject) -> None:
        text = "🚫 Bot ini privat. Akses ditolak."
        try:
            if isinstance(event, Update):
                event = event.event
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
        except Exception:  # pragma: no cover - jangan sampai middleware meledak
            logger.exception("Gagal mengirim pesan penolakan")


class UserMiddleware(BaseMiddleware):
    """Pastikan user terdaftar & simpan ctx agar handler tidak perlu query berulang."""

    def __init__(self, default_timezone: str = "Asia/Jakarta") -> None:
        self.default_timezone = default_timezone

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from bot.services_defaults import ensure_user

        session = data.get("session")
        tg_user = data.get("event_from_user")
        if session is None or tg_user is None:
            return await handler(event, data)

        name = " ".join(
            part for part in [getattr(tg_user, "first_name", ""), getattr(tg_user, "last_name", "")] if part
        )
        user, _created = ensure_user(session, tg_user.id, name)
        data["ctx"] = Context(
            session=session,
            user=user,
            owner_ids=tuple(),
            tz_name=user.timezone or self.default_timezone,
        )
        return await handler(event, data)


class ErrorMiddleware(BaseMiddleware):
    """Ubah exception jadi pesan ramah, bukan bot yang diam/mati."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from bot.ledger import LedgerError
        from bot.parser import ParseError

        try:
            return await handler(event, data)
        except (LedgerError, ParseError) as exc:
            await self._notify(event, f"⚠️ {exc}", data)
            return None
        except Exception:
            logger.exception("Error tak terduga saat memproses update")
            await self._notify(
                event,
                "💥 Terjadi kesalahan internal. Coba lagi, atau cek log bot.",
                data,
            )
            return None

    async def _notify(self, event: TelegramObject, text: str, data: dict[str, Any]) -> None:
        try:
            if isinstance(event, Update):
                event = event.event
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.message.answer(text) if event.message else None
                await event.answer()
        except Exception:  # pragma: no cover
            logger.exception("Gagal mengirim pesan error")
