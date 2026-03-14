from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from database.captcha_table import (
    get_captchas_for_user,
    delete_captcha, 
    delete_all_captchas_for_user,
    increment_captcha_attempts
)
from database.user_table import update_user
from database.chat_table import get_chat
from utils.time_helpers import is_expired
from utils.helpers import safe_callback_answer
from utils.notifications import notify_owner_about_error
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

    # Проверяем, что капча для этого пользователя
    if callback.from_user.id != user_id:
        await safe_callback_answer(callback, "❌ Эта капча не для вас", show_alert=True)
        return

    # Ищем все капчи пользователя в этом чате
    captchas = await get_captchas_for_user(captcha_user_id=user_id, captcha_chat_id=chat_id)

    if not captchas:
        await safe_callback_answer(callback, "❌ Капча не найдена или истекла", show_alert=True)
        return

    # Берём первую активную капчу (обычно она одна)
    captcha = captchas[0]

    # Проверяем, не истекла ли капча
    if is_expired(captcha.captcha_expires_at):
        # Удаляем сообщение капчи
        try:
            await callback.message.delete()
        except (TelegramForbiddenError, TelegramBadRequest, Exception) as e:
            if callback.bot:
                await notify_owner_about_error(
                    bot=callback.bot,
                    error_type="delete_expired_captcha_failed",
                    chat_id=chat_id,
                    message_id=captcha.captcha_message_id,
                    error_description=f"Failed to delete expired captcha: {e}"
                )
        
        # Удаляем запись из БД
        try:
            await delete_captcha(captcha_id=captcha.captcha_id)
        except Exception:
            pass
        
        await safe_callback_answer(callback, "❌ Время капчи истекло", show_alert=True)
        return

    # Проверяем правильность ответа
    if token == captcha.captcha_payload:
        logger.info(
            f"[Captcha] User verified: user_id={user_id}, chat_id={chat_id}"
        )
        
        # Удаляем ВСЕ капчи пользователя в этом чате (чтобы очистить спам)
        try:
            await delete_all_captchas_for_user(
                captcha_user_id=user_id, 
                captcha_chat_id=chat_id
            )
        except Exception:
            pass
        
        # Обновляем статус пользователя
        try:
            await update_user(field="user_status", data=1, user_id=user_id)
        except Exception:
            pass
        
        # Удаляем сообщение с капчей
        try:
            await callback.message.delete()
        except (TelegramForbiddenError, TelegramBadRequest, Exception) as e:
            if callback.bot:
                await notify_owner_about_error(
                    bot=callback.bot,
                    error_type="delete_captcha_failed",
                    chat_id=chat_id,
                    message_id=captcha.captcha_message_id,
                    error_description=f"Failed to delete captcha: {e}"
                )
        
        await safe_callback_answer(callback, "✅ Верификация пройдена!")
        return

    # Неправильный ответ - увеличиваем счётчик попыток
    updated_captcha = await increment_captcha_attempts(captcha_id=captcha.captcha_id)

    if updated_captcha is None:
        await safe_callback_answer(callback, "❌ Ошибка капчи", show_alert=True)
        return

    # Получаем настройки чата
    chat = await get_chat(chat_id=chat_id)

    if chat is None:
        await safe_callback_answer(callback, "❌ Чат не найден", show_alert=True)
        return

    max_attempts = chat.chat_max_attempts
    attempts_used = updated_captcha.captcha_attempts
    attempts_remaining = max_attempts - attempts_used

    # Проверяем лимит попыток
    if attempts_remaining <= 0:
        logger.info(f"[Captcha] Max attempts exceeded: user_id={user_id}")
        
        # Удаляем сообщение капчи
        try:
            await callback.message.delete()
        except (TelegramForbiddenError, TelegramBadRequest, Exception) as e:
            if callback.bot:
                await notify_owner_about_error(
                    bot=callback.bot,
                    error_type="delete_captcha_max_attempts_failed",
                    chat_id=chat_id,
                    message_id=captcha.captcha_message_id,
                    error_description=f"Failed to delete captcha on max attempts: {e}"
                )

        # Удаляем сообщение пользователя
        if updated_captcha.captcha_user_message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=chat_id,
                    message_id=updated_captcha.captcha_user_message_id
                )
            except (TelegramForbiddenError, TelegramBadRequest, Exception) as e:
                if callback.bot:
                    await notify_owner_about_error(
                        bot=callback.bot,
                        error_type="delete_user_message_max_attempts_failed",
                        chat_id=chat_id,
                        message_id=updated_captcha.captcha_user_message_id,
                        error_description=f"Failed to delete user message on max attempts: {e}"
                    )

        # Удаляем капчу из БД
        try:
            await delete_captcha(captcha_id=captcha.captcha_id)
        except Exception:
            pass

        await safe_callback_answer(callback, "❌ Превышен лимит попыток", show_alert=True)
        return

    # Отвечаем о неправильном ответе
    await safe_callback_answer(
        callback,
        f"❌ Неправильно! Осталось попыток: {attempts_remaining}"
    )