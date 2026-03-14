import asyncio
from aiosqlite import connect
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from logs.logger import logger
from config import BASE_PATH
from database.captcha_table import delete_captcha
from utils.time_helpers import get_timestamp


# ~~~~ CAPTCHA CLEANUP ~~~~
async def cleanup_expired_captchas(bot: Bot, stop_event: asyncio.Event) -> None:
    """
    Фоновая задача для удаления истекших капч с graceful shutdown.
    
    Для каждой истёкшей капчи:
    1. Удаляет сообщение капчи из чата
    2. Удаляет сообщение пользователя (если есть)
    3. Удаляет запись из БД
    
    При ошибках удаления сообщений логирует детали, но всё равно удаляет запись из БД
    (чтобы не оставлять "зомби"-записи).
    """
    while not stop_event.is_set():
        now = get_timestamp()
        logger.debug(f"[Cleanup] Starting cleanup cycle at {now}")

        try:
            async with connect(BASE_PATH) as db:
                cursor = await db.execute(
                    "SELECT captcha_id, captcha_user_id, captcha_chat_id, captcha_message_id, captcha_user_message_id "
                    "FROM captcha_table WHERE captcha_expires_at < ?",
                    (now,)
                )
                expired_captchas = await cursor.fetchall()

            expired_list = list(expired_captchas)
            if expired_list:
                logger.info(f"[Cleanup] Found {len(expired_list)} expired captchas")

            for captcha_id, captcha_user_id, captcha_chat_id, captcha_message_id, captcha_user_message_id in expired_captchas:
                if stop_event.is_set():
                    logger.info("[Cleanup] Stop event received, breaking cleanup loop")
                    break

                logger.debug(
                    f"[Cleanup] Processing expired captcha: captcha_id={captcha_id}, "
                    f"user_id={captcha_user_id}, chat_id={captcha_chat_id}, "
                    f"message_id={captcha_message_id}, user_message_id={captcha_user_message_id}"
                )

                # Удаляем сообщение капчи
                captcha_deleted = False
                try:
                    await bot.delete_message(chat_id=captcha_chat_id, message_id=captcha_message_id)
                    captcha_deleted = True
                    logger.debug(
                        f"[Cleanup] Deleted captcha message: captcha_id={captcha_id}, "
                        f"chat_id={captcha_chat_id}, message_id={captcha_message_id}"
                    )
                except TelegramForbiddenError:
                    logger.warning(
                        f"[Cleanup] No permission to delete captcha message: "
                        f"captcha_id={captcha_id}, chat_id={captcha_chat_id}, message_id={captcha_message_id}"
                    )
                except TelegramBadRequest as e:
                    if "message to delete not found" in str(e).lower():
                        logger.info(
                            f"[Cleanup] Captcha message already deleted: "
                            f"captcha_id={captcha_id}, chat_id={captcha_chat_id}, message_id={captcha_message_id}"
                        )
                        captcha_deleted = True  # Сообщение уже удалено, считаем успехом
                    elif "message can't be deleted" in str(e).lower():
                        logger.warning(
                            f"[Cleanup] Cannot delete captcha message (too old or no rights): "
                            f"captcha_id={captcha_id}, chat_id={captcha_chat_id}, message_id={captcha_message_id}, "
                            f"error={e}"
                        )
                    else:
                        logger.error(
                            f"[Cleanup] TelegramBadRequest deleting captcha message: "
                            f"captcha_id={captcha_id}, chat_id={captcha_chat_id}, message_id={captcha_message_id}, "
                            f"error={e}"
                        )
                except Exception as e:
                    logger.error(
                        f"[Cleanup] Unexpected error deleting captcha message: "
                        f"captcha_id={captcha_id}, chat_id={captcha_chat_id}, message_id={captcha_message_id}, "
                        f"error_type={type(e).__name__}, error={e}"
                    )

                # Удаляем сообщение пользователя
                user_message_deleted = False
                if captcha_user_message_id:
                    try:
                        await bot.delete_message(chat_id=captcha_chat_id, message_id=captcha_user_message_id)
                        user_message_deleted = True
                        logger.debug(
                            f"[Cleanup] Deleted user message: captcha_id={captcha_id}, "
                            f"chat_id={captcha_chat_id}, user_message_id={captcha_user_message_id}"
                        )
                    except TelegramForbiddenError:
                        logger.warning(
                            f"[Cleanup] No permission to delete user message: "
                            f"captcha_id={captcha_id}, chat_id={captcha_chat_id}, user_message_id={captcha_user_message_id}"
                        )
                    except TelegramBadRequest as e:
                        if "message to delete not found" in str(e).lower():
                            logger.info(
                                f"[Cleanup] User message already deleted: "
                                f"captcha_id={captcha_id}, chat_id={captcha_chat_id}, user_message_id={captcha_user_message_id}"
                            )
                            user_message_deleted = True
                        elif "message can't be deleted" in str(e).lower():
                            logger.warning(
                                f"[Cleanup] Cannot delete user message (too old or no rights): "
                                f"captcha_id={captcha_id}, chat_id={captcha_chat_id}, user_message_id={captcha_user_message_id}, "
                                f"error={e}"
                            )
                        else:
                            logger.error(
                                f"[Cleanup] TelegramBadRequest deleting user message: "
                                f"captcha_id={captcha_id}, chat_id={captcha_chat_id}, user_message_id={captcha_user_message_id}, "
                                f"error={e}"
                            )
                    except Exception as e:
                        logger.error(
                            f"[Cleanup] Unexpected error deleting user message: "
                            f"captcha_id={captcha_id}, chat_id={captcha_chat_id}, user_message_id={captcha_user_message_id}, "
                            f"error_type={type(e).__name__}, error={e}"
                        )

                # Удаляем запись из БД в любом случае
                try:
                    deleted = await delete_captcha(captcha_id=captcha_id)
                    if deleted:
                        logger.info(
                            f"[Cleanup] Deleted captcha record from DB: captcha_id={captcha_id}, "
                            f"captcha_message_deleted={captcha_deleted}, user_message_deleted={user_message_deleted}"
                        )
                    else:
                        logger.warning(
                            f"[Cleanup] Captcha record not found in DB (already deleted?): captcha_id={captcha_id}"
                        )
                except Exception as e:
                    logger.error(
                        f"[Cleanup] Error deleting captcha from DB: "
                        f"captcha_id={captcha_id}, error_type={type(e).__name__}, error={e}"
                    )

        except Exception as e:
            logger.error(f"[Cleanup] Error in cleanup cycle: error_type={type(e).__name__}, error={e}")
        
        # Sleep for 10 seconds or until stop_event is set
        for _ in range(10):
            if stop_event.is_set():
                break
            await asyncio.sleep(1)