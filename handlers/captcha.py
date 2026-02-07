from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramForbiddenError
from database.captcha_table import get_captcha, delete_captcha, increment_captcha_attempts
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
    """Обработка нажатий на кнопки капчи"""
    if callback.message is None:
        return

    try:
        parts = callback.data.split(":")
        if len(parts) != 5:
            raise ValueError("Invalid callback data format")
        _, action, token, user_id_str, chat_id_str = parts
        user_id = int(user_id_str)
        chat_id = int(chat_id_str)
    except (ValueError, IndexError) as e:
        logger.error(f"[Captcha] Invalid callback data: {callback.data}, error: {e}")
        await safe_callback_answer(callback, "❌ Неверный формат данных", show_alert=True)
        return

    if callback.from_user.id != user_id:
        await safe_callback_answer(callback, "❌ Эта капча не для вас", show_alert=True)
        return

    captcha = await get_captcha(captcha_user_id=user_id, captcha_chat_id=chat_id)

    if captcha is None:
        await safe_callback_answer(callback, "❌ Капча не найдена", show_alert=True)
        return

    if is_expired(captcha.captcha_expires_at):
        try:
            await callback.message.delete()
        except TelegramForbiddenError:
            pass
        except Exception as e:
            logger.error(f"[Captcha] Error deleting captcha message: {e}")
        await delete_captcha(captcha_user_id=user_id, captcha_chat_id=chat_id)
        await safe_callback_answer(callback, "❌ Время капчи истекло", show_alert=True)
        return

    if token == captcha.captcha_payload:
        await delete_captcha(captcha_user_id=user_id, captcha_chat_id=chat_id)
        await update_user(field="user_status", data=1, user_id=user_id)
        try:
            await callback.message.delete()
        except TelegramForbiddenError:
            pass
        except Exception as e:
            logger.error(f"[Captcha] Error deleting message: {e}")
        await safe_callback_answer(callback, "✅ Верификация пройдена!")
        return

    updated_captcha = await increment_captcha_attempts(
        captcha_user_id=user_id,
        captcha_chat_id=chat_id
    )

    if updated_captcha is None:
        await safe_callback_answer(callback, "❌ Ошибка капчи", show_alert=True)
        return

    chat = await get_chat(chat_id=chat_id)

    if chat is None:
        await safe_callback_answer(callback, "❌ Чат не найден", show_alert=True)
        return

    max_attempts = chat.chat_max_attempts
    attempts_used = updated_captcha.captcha_attempts
    attempts_remaining = max_attempts - attempts_used

    if attempts_remaining <= 0:
        try:
            await callback.message.delete()
        except TelegramForbiddenError:
            pass
        except Exception as e:
            logger.error(f"[Captcha] Error deleting captcha on max attempts: {e}")

        if updated_captcha.captcha_user_message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=chat_id,
                    message_id=updated_captcha.captcha_user_message_id
                )
            except TelegramForbiddenError:
                pass
            except Exception as e:
                logger.error(f"[Captcha] Error deleting user message on max attempts: {e}")

        await delete_captcha(captcha_user_id=user_id, captcha_chat_id=chat_id)
        await safe_callback_answer(callback, "❌ Превышен лимит попыток", show_alert=True)
        return

    await safe_callback_answer(
        callback,
        f"❌ Неправильно! Осталось попыток: {attempts_remaining}"
    )
