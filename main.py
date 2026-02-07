import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from logs.logger import logger

from config import settings
from database.captcha_table import create_db as create_captcha_db, migrate_captcha_table
from database.chat_table import create_db as create_chat_db, migrate_chat_table
from database.user_table import create_db as create_user_db
from handlers.captcha import captcha_router
from handlers.chat_member import chat_member_router
from handlers.settings import settings_router
from handlers.start import start_router
from handlers.owner import owner_router
from middleware.verification import VerificationMiddleware
from middleware.error_handler import ErrorHandlerMiddleware
from tasks.cleanup import cleanup_expired_captchas


# ~~~~ CREATE DATABASES ~~~~
async def create_databases() -> None:
    """Создание всех таблиц базы данных"""
    await create_user_db()
    await create_captcha_db()
    await create_chat_db()

    await migrate_captcha_table()
    await migrate_chat_table()

    logger.info("All database tables created and migrated")


# ~~~~ STARTUP ~~~~
async def on_startup(dispatcher: Dispatcher, bot: Bot) -> None:
    """Действия при запуске бота"""
    bot_info = await bot.get_me()
    logger.info(f"Bot started as @{bot_info.username}")

    try:
        await bot.send_message(
            chat_id=settings.owner_id,
            text=f"🟢 Бот запущен\n🤖 @{bot_info.username}"
        )
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")


# ~~~~ SHUTDOWN ~~~~
async def on_shutdown(dispatcher: Dispatcher, bot: Bot) -> None:
    """Действия при остановке бота"""

    try:
        await bot.send_message(
            chat_id=settings.owner_id,
            text="🔴 Бот остановлен"
        )
    except Exception as e:
        logger.error(f"Failed to send shutdown notification: {e}")


# ~~~~ MAIN ~~~~
async def main() -> None:
    """Главная функция запуска бота"""
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode="HTML", link_preview_is_disabled=True),
    )
    dp = Dispatcher()
    cleanup_stop_event = asyncio.Event()

    await create_databases()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    dp.message.outer_middleware(VerificationMiddleware())
    dp.update.outer_middleware(ErrorHandlerMiddleware())

    dp.include_router(chat_member_router)
    dp.include_router(start_router)
    dp.include_router(settings_router)
    dp.include_router(captcha_router)
    dp.include_router(owner_router)

    cleanup_task = asyncio.create_task(cleanup_expired_captchas(bot, cleanup_stop_event))

    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"[Main] Failed to drop pending updates: {e}")

    try:
        await dp.start_polling(bot)
    finally:
        cleanup_stop_event.set()
        try:
            await asyncio.wait_for(cleanup_task, timeout=5.0)
        except asyncio.TimeoutError:
            logger.error("[Main] Cleanup task timeout, forcing shutdown")
        await bot.session.close()


# ~~~~ ENTRY POINT ~~~~
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal error: {e}")
