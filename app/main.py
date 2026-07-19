import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app import __version__, db
from app.config import get_settings
from app.handlers import admin, common, review, submissions, team
from app.middleware import DatabaseMiddleware
from app.services.container import Services
from app.services.deepseek import DeepSeekEditor
from app.services.speechkit import SpeechKitTranscriber
from app.services.wordpress import WordPressClient


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="new", description="Создать новость"),
            BotCommand(command="queue", description="Мои материалы"),
            BotCommand(command="cancel", description="Отменить текущий материал"),
            BotCommand(command="myid", description="Показать мой Telegram ID"),
            BotCommand(command="help", description="Помощь"),
        ]
    )


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("mrpl-newsroom")
    settings.temp_dir.mkdir(parents=True, exist_ok=True)

    db.configure_database(settings)
    await db.init_database()
    if not await db.acquire_poller_lock():
        logger.error("Another MRPL Newsroom poller already holds the database lock.")
        await db.close_database()
        sys.exit(2)

    if db.session_factory is None:
        raise RuntimeError("Database session factory was not initialized")

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True,
        ),
    )
    services = Services(
        deepseek=DeepSeekEditor(settings),
        speechkit=SpeechKitTranscriber(settings),
        wordpress=WordPressClient(settings),
    )
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(
        DatabaseMiddleware(db.session_factory, settings)
    )
    dispatcher.include_routers(
        common.router,
        admin.router,
        team.router,
        review.router,
        submissions.router,
    )

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await set_commands(bot)
        me = await bot.get_me()
        logger.info(
            "MRPL Newsroom %s started as @%s; publish_enabled=%s",
            __version__,
            me.username,
            settings.publish_enabled,
        )
        if not settings.admin_telegram_id:
            logger.warning(
                "ADMIN_TELEGRAM_ID=0. Use /myid, then set the variable and redeploy."
            )
        await dispatcher.start_polling(
            bot,
            settings=settings,
            services=services,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        await services.close()
        await bot.session.close()
        await db.close_database()


if __name__ == "__main__":
    asyncio.run(main())
