from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import BufferedInputFile
from logs.logger import logger
from config import settings, BASE_PATH
from database.user_table import get_users_count, get_verified_count
from database.chat_table import get_chats_count
from database.captcha_table import get_captchas_count
from utils.helpers import safe_callback_answer


# ~~~~ ROUTER ~~~~
owner_router = Router()


# ~~~~ OWNER PANEL KEYBOARD ~~~~
def get_owner_keyboard() -> InlineKeyboardMarkup:
    """Создание клавиатуры панели владельца"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="owner:stats")
    builder.button(text="📁 Экспорт БД", callback_data="owner:export_db")
    builder.adjust(1)
    return builder.as_markup()


# ~~~~ STATS KEYBOARD ~~~~
def get_stats_keyboard() -> InlineKeyboardMarkup:
    """Создание клавиатуры для статистики с кнопкой Назад"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="owner:main")
    builder.adjust(1)
    return builder.as_markup()


# ~~~~ OWNER PANEL ~~~~
async def show_owner_panel(message: Message) -> None:
    """Показать панель владельца с inline keyboard"""
    text = (
        "👑 <b>Панель владельца</b>\n\n"
        "Добро пожаловать! Выберите действие:"
    )

    keyboard = get_owner_keyboard()
    await message.answer(text=text, reply_markup=keyboard)


# ~~~~ OWNER CALLBACK HANDLER ~~~~
@owner_router.callback_query(F.data.startswith("owner:"))
async def owner_callback(callback: CallbackQuery) -> None:
    """Обработка нажатий на кнопки панели владельца"""
    if callback.from_user.id != settings.owner_id:
        await safe_callback_answer(callback, "❌ Доступ запрещен", show_alert=True)
        return

    if callback.message is None:
        return

    action = callback.data.split(":")[1]

    if action == "stats":
        total_users = await get_users_count()
        verified_users = await get_verified_count()
        total_chats = await get_chats_count()
        active_captchas = await get_captchas_count()

        text = (
            "📊 <b>Статистика бота</b>\n\n"
            f"👥 <b>Пользователей:</b> {total_users}\n"
            f"✅ <b>Верифицировано:</b> {verified_users}\n"
            f"💬 <b>Чатов:</b> {total_chats}\n"
            f"🔒 <b>Активных капч:</b> {active_captchas}"
        )

        keyboard = get_stats_keyboard()
        await callback.message.edit_text(text=text, reply_markup=keyboard)
        await safe_callback_answer(callback)

    elif action == "export_db":
        try:
            with open(BASE_PATH, "rb") as f:
                file = BufferedInputFile(file=f.read(), filename="data.db")

            await callback.message.answer_document(document=file, caption="📁 Экспорт базы данных")
            await safe_callback_answer(callback, "✅ База данных экспортирована")
        except Exception as e:
            await safe_callback_answer(callback, f"❌ Ошибка при экспорте: {e}", show_alert=True)
            logger.error(f"Error exporting database: {e}")

    elif action == "main":
        text = (
            "👑 <b>Панель владельца</b>\n\n"
            "Добро пожаловать! Выберите действие:"
        )

        keyboard = get_owner_keyboard()
        await callback.message.edit_text(text=text, reply_markup=keyboard)
        await safe_callback_answer(callback)
