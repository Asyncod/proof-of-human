from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from database.captcha_table import (
    get_captcha_by_payload, 
    delete_captcha, 
    delete_all_captchas_for_user,
    increment_captcha_attempts
)
from database.user_table import update_user
from database.chat_table import get_chat
from utils.time_helpers import is_expired
from utils.helpers import safe_callback_answer
from logs.logger import logger


# ~~~~ ROUTER ~~~~
captcha_router = Router()


# ~~~~ CAPTCHA CALLBACK HANDLER ~~~~
@captcha_router.callback_query(F.data.startswith("captcha:verify:"))
async def captcha_callback(callback: CallbackQuery) -> None:
    """
    Обработка нажатий на кнопки капчи.
    
    При успешной верификации удаляет ВСЕ капчи пользователя в чате,
    чтобы очистить спам-сообщения.
    """
    if callback.message is None:
        logger.warning("[Captcha] Callback message is None, skipping")
        return

    # Парсим callback_data
    try:
        parts = callback.data.split(":")
        if len(parts) != 5:
            raise ValueError(f"Invalid callback data format: expected 5 parts, got {len(parts)}")
        _, action, token, user_id_str, chat_id_str = parts
        user_id = int(user_id_str)
        chat_id = int(chat_id_str)
    except (ValueError, IndexError) as e:
        logger.error(f"[Captcha] Invalid callback data: {callback.data}, error={e}")
        await safe_callback_answer(callback, "❌ Неверный формат данных", show_alert=True)
        return

    logger.debug(
        f"[Captcha] Processing callback: user_id={user_id}, chat_id={chat_id}, "
        f"callback_user_id={callback.from_user.id}"
    )

    # Проверяем, что капча для этого пользователя
    if callback.from_user.id != user_id:
        logger.debug(
            f"[Captcha] Wrong user clicked: expected={user_id}, got={callback.from_user.id}"
        )
        await safe_callback_answer(callback, "❌ Эта капча не для вас", show_alert=True)
        return

    # Ищем капчу по токену (payload)
    captcha = await get_captcha_by_payload(captcha_payload=token)

    if captcha is None:
        logger.info(
            f"[Captcha] Captcha not found by payload: user_id={user_id}, chat_id={chat_id}"
        )
        await safe_callback_answer(callback, "❌ Капча не найдена", show_alert=True)
        return

    logger.debug(
        f"[Captcha] Found captcha: captcha_id={captcha.captcha_id}, "
        f"user_id={captcha.captcha_user_id}, chat_id={captcha.captcha_chat_id}"
    )

    # Проверяем, что капча соответствует пользователю и чату из callback
    if captcha.captcha_user_id != user_id or captcha.captcha_chat_id != chat_id:
        logger.warning(
            f"[Captcha] Captcha mismatch: expected user={user_id}/chat={chat_id}, "
            f"got user={captcha.captcha_user_id}/chat={captcha.captcha_chat_id}"
        )
        await safe_callback_answer(callback, "❌ Неверная капча", show_alert=True)
        return

    # Проверяем, не истекла ли капча
    if is_expired(captcha.captcha_expires_at):
        logger.info(
            f"[Captcha] Captcha expired: captcha_id={captcha.captcha_id}, "
            f"expires_at={captcha.captcha_expires_at}"
        )
        
        # Удаляем сообщение капчи
        try:
            await callback.message.delete()
            logger.debug(
                f"[Captcha] Deleted expired captcha message: captcha_id={captcha.captcha_id}"
            )
        except TelegramForbiddenError:
            logger.warning(
                f"[Captcha] No permission to delete expired captcha message: "
                f"captcha_id={captcha.captcha_id}"
            )
        except TelegramBadRequest as e:
            if "message to delete not found" in str(e).lower():
                logger.debug(
                    f"[Captcha] Expired captcha message already deleted: "
                    f"captcha_id={captcha.captcha_id}"
                )
            else:
                logger.error(
                    f"[Captcha] TelegramBadRequest deleting expired captcha: "
                    f"captcha_id={captcha.captcha_id}, error={e}"
                )
        except Exception as e:
            logger.error(
                f"[Captcha] Unexpected error deleting expired captcha: "
                f"captcha_id={captcha.captcha_id}, error_type={type(e).__name__}, error={e}"
            )
        
        # Удаляем запись из БД
        try:
            await delete_captcha(captcha_id=captcha.captcha_id)
            logger.info(f"[Captcha] Deleted expired captcha from DB: captcha_id={captcha.captcha_id}")
        except Exception as e:
            logger.error(
                f"[Captcha] Error deleting expired captcha from DB: "
                f"captcha_id={captcha.captcha_id}, error={e}"
            )
        
        await safe_callback_answer(callback, "❌ Время капчи истекло", show_alert=True)
        return

    # Проверяем правильность ответа
    if token == captcha.captcha_payload:
        logger.info(
            f"[Captcha] Correct answer! Verifying user: user_id={user_id}, chat_id={chat_id}, "
            f"captcha_id={captcha.captcha_id}"
        )
        
        # Удаляем ВСЕ капчи пользователя в этом чате (чтобы очистить спам)
        try:
            deleted_count = await delete_all_captchas_for_user(
                captcha_user_id=user_id, 
                captcha_chat_id=chat_id
            )
            logger.info(
                f"[Captcha] Deleted all captchas for user: user_id={user_id}, "
                f"chat_id={chat_id}, count={deleted_count}"
            )
        except Exception as e:
            logger.error(
                f"[Captcha] Error deleting all captchas for user: "
                f"user_id={user_id}, chat_id={chat_id}, error={e}"
            )
        
        # Обновляем статус пользователя
        try:
            await update_user(field="user_status", data=1, user_id=user_id)
            logger.info(f"[Captcha] User verified: user_id={user_id}")
        except Exception as e:
            logger.error(f"[Captcha] Error updating user status: user_id={user_id}, error={e}")
        
        # Удаляем сообщение с капчей
        try:
            await callback.message.delete()
            logger.debug(f"[Captcha] Deleted captcha message: captcha_id={captcha.captcha_id}")
        except TelegramForbiddenError:
            logger.warning(
                f"[Captcha] No permission to delete captcha message: captcha_id={captcha.captcha_id}"
            )
        except TelegramBadRequest as e:
            if "message to delete not found" in str(e).lower():
                logger.debug(
                    f"[Captcha] Captcha message already deleted: captcha_id={captcha.captcha_id}"
                )
            else:
                logger.error(
                    f"[Captcha] TelegramBadRequest deleting captcha message: "
                    f"captcha_id={captcha.captcha_id}, error={e}"
                )
        except Exception as e:
            logger.error(
                f"[Captcha] Unexpected error deleting captcha message: "
                f"captcha_id={captcha.captcha_id}, error_type={type(e).__name__}, error={e}"
            )
        
        await safe_callback_answer(callback, "✅ Верификация пройдена!")
        return

    # Неправильный ответ - увеличиваем счётчик попыток
    logger.debug(
        f"[Captcha] Wrong answer: captcha_id={captcha.captcha_id}, "
        f"user_id={user_id}, expected_payload={captcha.captcha_payload[:8]}..., "
        f"got_payload={token[:8]}..."
    )
    
    updated_captcha = await increment_captcha_attempts(captcha_id=captcha.captcha_id)

    if updated_captcha is None:
        logger.error(
            f"[Captcha] Failed to increment attempts: captcha_id={captcha.captcha_id}"
        )
        await safe_callback_answer(callback, "❌ Ошибка капчи", show_alert=True)
        return

    # Получаем настройки чата
    chat = await get_chat(chat_id=chat_id)

    if chat is None:
        logger.error(f"[Captcha] Chat not found: chat_id={chat_id}")
        await safe_callback_answer(callback, "❌ Чат не найден", show_alert=True)
        return

    max_attempts = chat.chat_max_attempts
    attempts_used = updated_captcha.captcha_attempts
    attempts_remaining = max_attempts - attempts_used

    logger.debug(
        f"[Captcha] Attempts updated: captcha_id={captcha.captcha_id}, "
        f"attempts={attempts_used}/{max_attempts}, remaining={attempts_remaining}"
    )

    # Проверяем лимит попыток
    if attempts_remaining <= 0:
        logger.info(
            f"[Captcha] Max attempts exceeded: captcha_id={captcha.captcha_id}, "
            f"user_id={user_id}, attempts={attempts_used}"
        )
        
        # Удаляем сообщение капчи
        try:
            await callback.message.delete()
            logger.debug(
                f"[Captcha] Deleted captcha message on max attempts: captcha_id={captcha.captcha_id}"
            )
        except TelegramForbiddenError:
            logger.warning(
                f"[Captcha] No permission to delete captcha on max attempts: "
                f"captcha_id={captcha.captcha_id}"
            )
        except TelegramBadRequest as e:
            if "message to delete not found" in str(e).lower():
                logger.debug(
                    f"[Captcha] Captcha message already deleted: captcha_id={captcha.captcha_id}"
                )
            else:
                logger.error(
                    f"[Captcha] TelegramBadRequest deleting captcha on max attempts: "
                    f"captcha_id={captcha.captcha_id}, error={e}"
                )
        except Exception as e:
            logger.error(
                f"[Captcha] Unexpected error deleting captcha on max attempts: "
                f"captcha_id={captcha.captcha_id}, error_type={type(e).__name__}, error={e}"
            )

        # Удаляем сообщение пользователя
        if updated_captcha.captcha_user_message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=chat_id,
                    message_id=updated_captcha.captcha_user_message_id
                )
                logger.debug(
                    f"[Captcha] Deleted user message on max attempts: "
                    f"captcha_id={captcha.captcha_id}, message_id={updated_captcha.captcha_user_message_id}"
                )
            except TelegramForbiddenError:
                logger.warning(
                    f"[Captcha] No permission to delete user message on max attempts: "
                    f"captcha_id={captcha.captcha_id}"
                )
            except TelegramBadRequest as e:
                if "message to delete not found" in str(e).lower():
                    logger.debug(
                        f"[Captcha] User message already deleted: captcha_id={captcha.captcha_id}"
                    )
                else:
                    logger.error(
                        f"[Captcha] TelegramBadRequest deleting user message on max attempts: "
                        f"captcha_id={captcha.captcha_id}, error={e}"
                    )
            except Exception as e:
                logger.error(
                    f"[Captcha] Unexpected error deleting user message on max attempts: "
                    f"captcha_id={captcha.captcha_id}, error_type={type(e).__name__}, error={e}"
                )

        # Удаляем капчу из БД
        try:
            await delete_captcha(captcha_id=captcha.captcha_id)
            logger.info(f"[Captcha] Deleted captcha from DB on max attempts: captcha_id={captcha.captcha_id}")
        except Exception as e:
            logger.error(
                f"[Captcha] Error deleting captcha from DB on max attempts: "
                f"captcha_id={captcha.captcha_id}, error={e}"
            )

        await safe_callback_answer(callback, "❌ Превышен лимит попыток", show_alert=True)
        return

    # Отвечаем о неправильном ответе
    await safe_callback_answer(
        callback,
        f"❌ Неправильно! Осталось попыток: {attempts_remaining}"
    )