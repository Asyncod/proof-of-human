from datetime import datetime
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from typing import Any, Callable, Dict, Awaitable
from aiogram.enums import ChatMemberStatus
from aiogram.enums.content_type import ContentType
from logs.logger import logger
from database.user_table import get_user, add_user, update_user
from database.captcha_table import get_captchas_for_user, delete_captcha
from database.chat_table import get_chat
from utils.captcha import send_captcha
from utils.time_helpers import get_timestamp, is_expired
from utils.helpers import is_bot_admin


# Сервисные типы сообщений, которые нужно игнорировать
SERVICE_CONTENT_TYPES = {
    ContentType.NEW_CHAT_MEMBERS,
    ContentType.LEFT_CHAT_MEMBER,
    ContentType.PINNED_MESSAGE,
    ContentType.NEW_CHAT_TITLE,
    ContentType.NEW_CHAT_PHOTO,
    ContentType.DELETE_CHAT_PHOTO,
    ContentType.GROUP_CHAT_CREATED,
    ContentType.SUPERGROUP_CHAT_CREATED,
    ContentType.CHANNEL_CHAT_CREATED,
    ContentType.MIGRATE_TO_CHAT_ID,
    ContentType.MIGRATE_FROM_CHAT_ID,
    ContentType.VIDEO_CHAT_SCHEDULED,
    ContentType.VIDEO_CHAT_STARTED,
    ContentType.VIDEO_CHAT_ENDED,
    ContentType.VIDEO_CHAT_PARTICIPANTS_INVITED,
    ContentType.FORUM_TOPIC_CREATED,
    ContentType.FORUM_TOPIC_EDITED,
    ContentType.FORUM_TOPIC_CLOSED,
    ContentType.FORUM_TOPIC_REOPENED,
    ContentType.GENERAL_FORUM_TOPIC_HIDDEN,
    ContentType.GENERAL_FORUM_TOPIC_UNHIDDEN,
}


# ~~~~ EVENT TYPE ~~~~
Event = Message


# ~~~~ VERIFICATION MIDDLEWARE ~~~~
class VerificationMiddleware(BaseMiddleware):
    """Проверка верификации пользователя"""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        # Игнорируем сервисные сообщения (вступление, выход, закрепление и т.д.)
        if event.content_type in SERVICE_CONTENT_TYPES:
            return await handler(event, data)

        chat = event.chat
        user = event.from_user

        if chat.type == "private":
            return await handler(event, data)

        if user is None:
            return await handler(event, data)

        bot = data.get("bot")
        if bot is not None:
            try:
                bot_member = await bot.get_chat_member(chat_id=chat.id, user_id=bot.id)
                if bot_member.status not in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR):
                    if event.text and (event.text.startswith("/start") or event.text.startswith("/settings")):
                        return await handler(event, data)
                    return
            except TelegramForbiddenError:
                return
            except Exception as e:
                logger.error(f"[Verification] Error checking bot admin status: {e}")
        if bot is not None:
            try:
                member = await bot.get_chat_member(chat_id=chat.id, user_id=user.id)
                if member.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR):
                    db_admin = await get_user(user_id=user.id)
                    if db_admin is None:
                        try:
                            db_admin = await add_user(
                                user_id=user.id,
                                user_username=user.username or "",
                                user_name=user.full_name,
                                user_first_seen_at=get_timestamp(),
                                user_language=user.language_code or ""
                            )
                        except RuntimeError as e:
                            logger.error(f"[Verification] Failed to add admin {user.id} to database: {e}")
                            return await handler(event, data)
                        await update_user(field="user_status", data=1, user_id=user.id)
                    elif db_admin.user_status != 1:
                        await update_user(field="user_status", data=1, user_id=user.id)
                    return await handler(event, data)
            except TelegramForbiddenError:
                return
            except Exception as e:
                logger.error(f"[Verification] Error checking admin status: {e}")

        if event.sender_chat and event.sender_chat.type == "channel":
            return await handler(event, data)

        if event.is_automatic_forward:
            return await handler(event, data)

        if user.is_bot:
            return await handler(event, data)

        db_user = await get_user(user_id=user.id)

        if db_user is None:
            # Получаем аналитические данные о пользователе
            is_premium = 1 if user.is_premium else 0
            
            try:
                db_user = await add_user(
                    user_id=user.id,
                    user_username=user.username or "",
                    user_name=user.full_name,
                    user_first_seen_at=get_timestamp(),
                    user_language=user.language_code or "",
                    user_is_premium=is_premium
                )
                logger.info(
                    f"[Verification] Added user with analytics: user_id={user.id}, "
                    f"is_premium={is_premium}"
                )
            except RuntimeError as e:
                logger.error(f"[Verification] Failed to add user {user.id} to database: {e}, skipping message")
                return

        if db_user.user_status == 1:
            return await handler(event, data)

        # Получаем все активные капчи для пользователя в этом чате
        existing_captchas = await get_captchas_for_user(captcha_user_id=user.id, captcha_chat_id=chat.id)
        
        if existing_captchas:
            # Проверяем, есть ли среди них истёкшие
            expired_captchas = [c for c in existing_captchas if is_expired(c.captcha_expires_at)]
            active_captchas = [c for c in existing_captchas if not is_expired(c.captcha_expires_at)]
            
            # Удаляем истёкшие капчи (сообщения и записи из БД)
            for expired_captcha in expired_captchas:
                # Удаляем сообщение капчи
                try:
                    await bot.delete_message(chat_id=chat.id, message_id=expired_captcha.captcha_message_id)
                except (TelegramForbiddenError, TelegramBadRequest, Exception):
                    pass
                
                # Удаляем сообщение пользователя (если есть)
                if expired_captcha.captcha_user_message_id:
                    try:
                        await bot.delete_message(chat_id=chat.id, message_id=expired_captcha.captcha_user_message_id)
                    except (TelegramForbiddenError, TelegramBadRequest, Exception):
                        pass
                
                # Удаляем запись из БД
                try:
                    await delete_captcha(captcha_id=expired_captcha.captcha_id)
                except Exception:
                    pass
            
            # Если есть активные капчи - удаляем текущее сообщение пользователя
            if active_captchas:
                try:
                    await event.delete()
                except (TelegramForbiddenError, TelegramBadRequest, Exception):
                    pass
                return
        
        # Создаём новую капчу
        try:
            captcha = await send_captcha(message=event, bot=bot)
        except Exception as e:
            logger.error(
                f"[Verification] Error sending captcha: user_id={user.id}, chat_id={chat.id}, "
                f"error_type={type(e).__name__}, error={e}"
            )