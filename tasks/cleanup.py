import asyncio
from datetime import datetime
from aiosqlite import connect
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from logs.logger import logger
from config import BASE_PATH
from database.captcha_table import delete_captcha
from utils.time_helpers import get_timestamp


# ~~~~ CAPTCHA CLEANUP ~~~~
async def cleanup_expired_captchas(bot: Bot, stop_event: asyncio.Event) -> None:
    """Фоновая задача для удаления истекших капч с graceful shutdown"""
    while not stop_event.is_set():
        now = get_timestamp()

        try:
            async with connect(BASE_PATH) as db:
                cursor = await db.execute(
                    "SELECT captcha_user_id, captcha_chat_id, captcha_message_id, captcha_user_message_id "
                    "FROM captcha_table WHERE captcha_expires_at < ?",
                    (now,)
                )
                expired_captchas = await cursor.fetchall()

            for captcha_user_id, captcha_chat_id, captcha_message_id, captcha_user_message_id in expired_captchas:
                if stop_event.is_set():
                    break

                try:
                    await bot.delete_message(chat_id=captcha_chat_id, message_id=captcha_message_id)
                except TelegramForbiddenError:
                    pass
                except Exception as e:
                    logger.error(f"[Cleanup] Error deleting captcha message: {e}")

                if captcha_user_message_id:
                    try:
                        await bot.delete_message(chat_id=captcha_chat_id, message_id=captcha_user_message_id)
                    except TelegramForbiddenError:
                        pass
                    except Exception as e:
                        logger.error(f"[Cleanup] Error deleting user message: {e}")

                await delete_captcha(captcha_user_id=captcha_user_id, captcha_chat_id=captcha_chat_id)

        except Exception as e:
            logger.error(f"Error cleaning up expired captchas: {e}")
        
        # Sleep for 10 seconds or until stop_event is set
        for _ in range(10):
            if stop_event.is_set():
                break
            await asyncio.sleep(1)
