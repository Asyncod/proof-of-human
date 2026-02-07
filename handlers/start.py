from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import settings
from database.user_table import get_user, add_user
from handlers.owner import show_owner_panel
from utils.time_helpers import get_timestamp
from logs.logger import logger


# ~~~~ ROUTER ~~~~
start_router = Router()


# ~~~~ START COMMAND HANDLER ~~~~
@start_router.message(CommandStart())
async def start_command(message: Message) -> None:
    """Обработка команды /start (только в личных сообщениях)"""
    if message.chat.type != "private":
        return

    user = message.from_user
    user_id = user.id

    if user_id == settings.owner_id:
        await show_owner_panel(message=message)
        return

    db_user = await get_user(user_id=user_id)
    if db_user is None:
        try:
            db_user = await add_user(
                user_id=user_id,
                user_username=user.username or "",
                user_name=user.full_name,
                user_first_seen_at=get_timestamp(),
                user_language=user.language_code or ""
            )
        except RuntimeError as e:
            logger.error(f"[Start] Failed to add user {user_id} to database: {e}")

    text = (
        "🤖 <b>Chat Defender Bot</b>\n\n"
        "Этот бот защищает чаты от спама с помощью глобальной верификации пользователей.\n\n"
        "🔹 <b>Возможности:</b>\n"
        "• Inline-капча для верификации\n"
        "• Глобальная база пользователей\n"
        "• Настройки для каждого чата\n\n"
        "🔸 Поддержка\n"
        "•  Писать: @asynco\n"
        "•  Код: https://github.com/Asyncod/proof-of-human\n\n"
        "Добавь бота в чат с правами на удаление сообщений 👇"
    )

    builder = InlineKeyboardBuilder()
    if message.bot is not None:
        bot_info = await message.bot.get_me()
        builder.button(
            text="➕ Добавить в группу",
            url=f"https://t.me/{bot_info.username}?startgroup=true"
        )
    keyboard = builder.as_markup()

    await message.answer(text=text, reply_markup=keyboard)
