from datetime import datetime
from aiogram import Bot
from aiogram.types import Chat, CallbackQuery
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from logs.logger import logger


# ~~~~ ADMIN CHECK ~~~~
async def is_admin(user_id: int, chat_id: int, bot: Bot) -> bool:
    """
    Проверка прав администратора.

    Параметры:
        user_id (int): Telegram ID пользователя
        chat_id (int): Telegram ID чата
        bot (Bot): экземпляр бота

    Возвращает:
        bool: True если пользователь админ, иначе False
    """
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR)
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id} in chat {chat_id}: {e}")
        return False


# ~~~~ BOT ADMIN CHECK ~~~~
async def is_bot_admin(bot: Bot, chat_id: int) -> bool:
    """
    Проверка, является ли бот администратором чата.

    Параметры:
        bot (Bot): экземпляр бота
        chat_id (int): Telegram ID чата

    Возвращает:
        bool: True если бот админ, иначе False
    """
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=bot.id)
        return member.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR)
    except Exception as e:
        logger.error(f"Error checking bot admin status in chat {chat_id}: {e}")
        return False


# ~~~~ CHAT TITLE HELPER ~~~~
def get_chat_title(chat: Chat) -> str:
    """
    Получение безопасного названия чата.

    Параметры:
        chat (Chat): объект чата из aiogram

    Возвращает:
        str: название чата или безопасное значение по умолчанию
    """
    if chat.type == "private":
        return f"Private Chat {chat.id}"
    elif chat.title:
        return chat.title
    else:
        return f"Chat {chat.id}"


# ~~~~ SAFE CALLBACK ANSWER ~~~~
async def safe_callback_answer(callback: CallbackQuery, text: str = "", show_alert: bool = False) -> None:
    """
    Безопасный ответ на callback query (игнорирует ошибку 'query is too old').

    Параметры:
        callback (CallbackQuery): объект callback query
        text (str): текст ответа (пустая строка по умолчанию)
        show_alert (bool): показать как alert (False по умолчанию)

    Возвращает:
        None
    """
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as e:
        if "query is too old" in str(e).lower():
            pass
        else:
            raise
