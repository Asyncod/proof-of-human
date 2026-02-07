from aiogram import Router
from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, MEMBER, LEFT
from aiogram.handlers import ChatMemberHandler
from aiogram.types import ChatMemberUpdated
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramForbiddenError
from aiosqlite import IntegrityError
from config import settings
from database.chat_table import add_chat, get_chat
from database.user_table import get_user, add_user, update_user
from utils.time_helpers import get_timestamp
from utils.helpers import get_chat_title
from logs.logger import logger


# ~~~~ ROUTER ~~~~
chat_member_router = Router()


# ~~~~ BOT ADDED TO CHAT HANDLER ~~~~
@chat_member_router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> MEMBER))
class BotAddedHandler(ChatMemberHandler):
    """Обработчик добавления бота в чат"""

    async def handle(self) -> None:
        event: ChatMemberUpdated = self.event
        bot = event.bot

        chat_id = event.chat.id
        chat_type = event.chat.type

        chat_title = get_chat_title(event.chat)
        chat_link = f"https://t.me/{event.chat.username}" if event.chat.username else "Нет ссылки"
        timestamp = get_timestamp(event.date)

        try:
            await add_chat(chat_id=chat_id, chat_title=chat_title)
        except RuntimeError as e:
            logger.error(f"[ChatMember] Failed to add chat {chat_id} to database: {e}")

        if event.from_user:
            try:
                member = await bot.get_chat_member(chat_id=chat_id, user_id=event.from_user.id)
                if member.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR):
                    db_admin = await get_user(user_id=event.from_user.id)
                    if db_admin is None:
                        try:
                            db_admin = await add_user(
                                user_id=event.from_user.id,
                                user_username=event.from_user.username or "",
                                user_name=event.from_user.full_name,
                                user_first_seen_at=get_timestamp(),
                                user_language=event.from_user.language_code or ""
                            )
                        except RuntimeError as e:
                            logger.error(f"[ChatMember] Failed to add admin {event.from_user.id} to database: {e}")
                            return
                        await update_user(field="user_status", data=1, user_id=event.from_user.id)
                    elif db_admin.user_status != 1:
                        await update_user(field="user_status", data=1, user_id=event.from_user.id)
            except TelegramForbiddenError:
                pass
            except Exception as e:
                logger.error(f"[ChatMember] Error checking admin status: {e}")

        notification = (
            f"🔔 <b>Бот добавлен в чат</b>\n"
            f"📌 <b>Chat ID:</b> {chat_id}\n"
            f"📝 <b>Название:</b> {chat_title}\n"
            f"👥 <b>Тип:</b> {chat_type}\n"
            f"🔗 <b>Ссылка:</b> {chat_link}\n"
            f"🕐 <b>Дата:</b> {timestamp}"
        )

        try:
            await bot.send_message(chat_id=settings.owner_id, text=notification)
        except Exception as e:
            logger.error(f"[ChatMember] Error sending notification to owner: {e}")

        try:
            await bot.send_message(chat_id=chat_id, text=settings.welcome_message)
        except TelegramForbiddenError:
            pass
        except Exception as e:
            logger.error(f"[ChatMember] Error sending welcome message: {e}")


# ~~~~ USER ADDED TO CHAT HANDLER ~~~~
@chat_member_router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> MEMBER))
class UserAddedHandler(ChatMemberHandler):
    """Обработчик добавления пользователя в чат"""

    async def handle(self) -> None:
        event: ChatMemberUpdated = self.event
        user = event.new_chat_member.user

        if user.is_bot:
            return

        db_user = await get_user(user_id=user.id)
        if db_user is None:
            try:
                db_user = await add_user(
                    user_id=user.id,
                    user_username=user.username or "",
                    user_name=user.full_name,
                    user_first_seen_at=get_timestamp(),
                    user_language=user.language_code or ""
                )
            except IntegrityError:
                pass
            except RuntimeError as e:
                logger.error(f"[ChatMember] Failed to add user {user.id} to database: {e}")


# ~~~~ BOT KICKED FROM CHAT HANDLER ~~~~
@chat_member_router.my_chat_member(ChatMemberUpdatedFilter(MEMBER >> LEFT))
class BotKickedHandler(ChatMemberHandler):
    """Обработчик удаления бота из чата"""

    async def handle(self) -> None:
        event: ChatMemberUpdated = self.event
        bot = event.bot

        chat_id = event.chat.id
        chat_type = event.chat.type

        chat_title = get_chat_title(event.chat)
        timestamp = get_timestamp(event.date)

        notification = (
            f"👋 <b>Бот удален из чата</b>\n"
            f"📌 <b>Chat ID:</b> {chat_id}\n"
            f"📝 <b>Название:</b> {chat_title}\n"
            f"🕐 <b>Дата:</b> {timestamp}\n"
            f"ℹ️ Настройки сохранены в базе данных"
        )

        try:
            await bot.send_message(chat_id=settings.owner_id, text=notification)
        except Exception as e:
            logger.error(f"[ChatMember] Error sending notification to owner: {e}")


# ~~~~ BOT RETURNED TO CHAT HANDLER ~~~~
@chat_member_router.my_chat_member(ChatMemberUpdatedFilter(LEFT >> MEMBER))
class BotReturnedHandler(ChatMemberHandler):
    """Обработчик возвращения бота в чат"""

    async def handle(self) -> None:
        event: ChatMemberUpdated = self.event
        bot = event.bot

        chat_id = event.chat.id
        chat_type = event.chat.type

        chat_title = get_chat_title(event.chat)
        timestamp = get_timestamp(event.date)

        existing_chat = await get_chat(chat_id=chat_id)

        if existing_chat is None:
            try:
                await add_chat(chat_id=chat_id, chat_title=chat_title)
            except RuntimeError as e:
                logger.error(f"[ChatMember] Failed to add chat {chat_id} to database: {e}")

        notification = (
            f"🔄 <b>Бот возвращен в чат</b>\n"
            f"📌 <b>Chat ID:</b> {chat_id}\n"
            f"📝 <b>Название:</b> {chat_title}\n"
            f"🕐 <b>Дата:</b> {timestamp}\n"
            f"✅ Настройки сохранены"
        )

        try:
            await bot.send_message(chat_id=settings.owner_id, text=notification)
        except Exception as e:
            logger.error(f"[ChatMember] Error sending notification to owner: {e}")

        try:
            await bot.send_message(chat_id=chat_id, text=f"👋 Бот вернулся! Все настройки сохранены.")
        except TelegramForbiddenError:
            pass
        except Exception as e:
            logger.error(f"[ChatMember] Error sending welcome message: {e}")
