from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from logs.logger import logger
from database.chat_table import get_chat, update_chat
from utils.helpers import is_admin, is_bot_admin, safe_callback_answer
from config import settings


# ~~~~ ROUTER ~~~~
settings_router = Router()


# ~~~~ SETTINGS COMMAND HANDLER ~~~~
@settings_router.message(Command("settings"))
async def settings_command(message: Message) -> None:
    """Команда /settings (только для администраторов чата)"""
    chat = message.chat

    if chat.type == "private":
        try:
            await message.answer("Эта команда работает только в группах и супергруппах.")
        except TelegramForbiddenError:
            pass
        except Exception as e:
            logger.error(f"[Settings] Error sending message: {e}")
        return

    if message.bot is None or message.from_user is None:
        try:
            await message.answer("❌ Внутренняя ошибка бота")
        except Exception as e:
            logger.error(f"[Settings] Error sending message: {e}")
        return

    try:
        bot_is_admin = await is_bot_admin(bot=message.bot, chat_id=chat.id)
    except TelegramForbiddenError:
        return
    except Exception as e:
        logger.error(f"[Settings] Error checking bot admin: {e}")
        return

    if not bot_is_admin:
        try:
            await message.answer(settings.bot_not_admin_message)
        except TelegramForbiddenError:
            pass
        except Exception as e:
            logger.error(f"[Settings] Error sending message: {e}")
        return

    try:
        is_admin_result = await is_admin(user_id=message.from_user.id, chat_id=chat.id, bot=message.bot)
    except TelegramForbiddenError:
        return
    except Exception as e:
        logger.error(f"[Settings] Error checking admin: {e}")
        return

    if not is_admin_result:
        try:
            await message.answer("Эта команда доступна только администраторам чата.")
        except TelegramForbiddenError:
            pass
        except Exception as e:
            logger.error(f"[Settings] Error sending message: {e}")
        return

    chat_data = await get_chat(chat_id=chat.id)

    if chat_data is None:
        try:
            await message.answer("Чат не найден в базе данных.")
        except TelegramForbiddenError:
            pass
        except Exception as e:
            logger.error(f"[Settings] Error sending message: {e}")
        return

    text = (
        f"⚙️ <b>Настройки чата: {chat_data.chat_title}</b>\n\n"
        f"🔹 <b>Капча:</b> {'✅ Включена' if chat_data.chat_captcha_enabled else '❌ Выключена'}\n"
        f"🔹 <b>Таймаут:</b> {chat_data.chat_captcha_timeout} сек"
    )

    keyboard = get_settings_keyboard(chat_id=chat.id)
    try:
        await message.answer(text=text, reply_markup=keyboard)
    except TelegramForbiddenError:
        pass
    except Exception as e:
        logger.error(f"[Settings] Error sending message: {e}")


# ~~~~ SETTINGS KEYBOARD ~~~~
def get_settings_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Создание клавиатуры настроек"""
    builder = InlineKeyboardBuilder()

    builder.button(text="🔔 Вкл/Выкл капчу", callback_data=f"settings:toggle_captcha:{chat_id}")
    builder.button(text="⏱️ Таймаут", callback_data=f"settings:timeout:{chat_id}")
    builder.button(text="🗑️ Удалить", callback_data=f"settings:delete:{chat_id}")

    builder.adjust(1)
    return builder.as_markup()


# ~~~~ TIMEOUT KEYBOARD ~~~~
def get_timeout_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора таймаута"""
    builder = InlineKeyboardBuilder()

    for timeout in settings.captcha_timeout_options:
        builder.button(
            text=f"{timeout // 60} мин" if timeout >= 60 else f"{timeout} сек",
            callback_data=f"settings:set_timeout:{chat_id}:{timeout}"
        )

    builder.adjust(2)
    builder.button(text="🔙 Назад", callback_data=f"settings:main:{chat_id}")
    return builder.as_markup()


# ~~~~ SETTINGS CALLBACK HANDLER ~~~~
@settings_router.callback_query(F.data.startswith("settings:"))
async def settings_callback(callback: CallbackQuery) -> None:
    """Обработка нажатий на кнопки настроек"""
    if callback.message is None or callback.data is None:
        return

    parts = callback.data.split(":")
    action = parts[1]
    chat_id = int(parts[2])

    if callback.bot is None or callback.from_user is None:
        try:
            await safe_callback_answer(callback, "❌ Внутренняя ошибка бота")
        except Exception as e:
            logger.error(f"[Settings] Error answering callback: {e}")
        return

    try:
        bot_is_admin = await is_bot_admin(bot=callback.bot, chat_id=chat_id)
    except TelegramForbiddenError:
        return
    except Exception as e:
        logger.error(f"[Settings] Error checking bot admin: {e}")
        return

    if not bot_is_admin:
        try:
            await safe_callback_answer(
                callback,
                "❌ Бот не является администратором этого чата",
                show_alert=True
            )
        except Exception as e:
            logger.error(f"[Settings] Error answering callback: {e}")
        return

    try:
        is_admin_result = await is_admin(user_id=callback.from_user.id, chat_id=chat_id, bot=callback.bot)
    except TelegramForbiddenError:
        return
    except Exception as e:
        logger.error(f"[Settings] Error checking admin: {e}")
        return

    if not is_admin_result:
        try:
            await safe_callback_answer(callback, "❌ Только для администраторов", show_alert=True)
        except Exception as e:
            logger.error(f"[Settings] Error answering callback: {e}")
        return

    chat = await get_chat(chat_id=chat_id)

    if chat is None:
        try:
            await safe_callback_answer(callback, "❌ Чат не найден", show_alert=True)
        except Exception as e:
            logger.error(f"[Settings] Error answering callback: {e}")
        return

    if action == "toggle_captcha":
        new_value = 0 if chat.chat_captcha_enabled else 1
        await update_chat(field="chat_captcha_enabled", data=new_value, chat_id=chat_id)
        await safe_callback_answer(callback, f"✅ Капча {'включена' if new_value else 'выключена'}")

    elif action == "timeout":
        keyboard = get_timeout_keyboard(chat_id=chat_id)
        try:
            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await safe_callback_answer(callback)
        except TelegramForbiddenError:
            pass
        except Exception as e:
            logger.error(f"[Settings] Error editing keyboard: {e}")
        return

    elif action == "set_timeout":
        value = int(parts[3])
        await update_chat(field="chat_captcha_timeout", data=value, chat_id=chat_id)
        await safe_callback_answer(callback, f"✅ Таймаут: {value} сек")

    elif action == "main":
        keyboard = get_settings_keyboard(chat_id=chat_id)
        try:
            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await safe_callback_answer(callback)
        except TelegramForbiddenError:
            pass
        except Exception as e:
            logger.error(f"[Settings] Error editing keyboard: {e}")
        return

    elif action == "delete":
        try:
            await callback.message.delete()
        except TelegramForbiddenError:
            pass
        except Exception as e:
            logger.error(f"[Settings] Error deleting message: {e}")
        return

    updated_chat = await get_chat(chat_id=chat_id)

    text = (
        f"⚙️ <b>Настройки чата: {updated_chat.chat_title}</b>\n\n"
        f"🔹 <b>Капча:</b> {'✅ Включена' if updated_chat.chat_captcha_enabled else '❌ Выключена'}\n"
        f"🔹 <b>Таймаут:</b> {updated_chat.chat_captcha_timeout} сек"
    )

    keyboard = get_settings_keyboard(chat_id=chat_id)
    try:
        await callback.message.edit_text(text=text, reply_markup=keyboard)
    except TelegramForbiddenError:
        pass
    except Exception as e:
        logger.error(f"[Settings] Error editing message: {e}")
