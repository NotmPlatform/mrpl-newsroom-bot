from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.config import Settings
from app.repository import upsert_user


class DatabaseMiddleware(BaseMiddleware):
    def __init__(self, session_factory, settings: Settings):
        self.session_factory = session_factory
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            telegram_user = data.get("event_from_user")
            if telegram_user is not None:
                data["db_user"] = await upsert_user(
                    session,
                    telegram_user,
                    self.settings.admin_telegram_id,
                )
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

