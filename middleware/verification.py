from datetime import datetime
from aiogram import BaseMiddleware
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError
from typing import Any, Callable, Dict, Awaitable
from aiogram.enums import ChatMemberStatus
from logs.logger import logger
from database.user_table import get_user, add_user, update_user
from database.captcha_table import get_captcha
from database.chat_table import get_chat
from utils.captcha import send_captcha
from utils.time_helpers import get_timestamp, is_expired
from utils.helpers import is_bot_admin


# ~~~~ EVENT TYPE ~~~~
Event = Message


# ~~~~ VERIFICATION MIDDLEWARE ~~~~
class VerificationMiddleware(BaseMiddleware):
    """Проверка верификации пользователя"""

    async def __call__(
        self,
        handler: Callable[[Event, Dict[str, Any]], Awaitable[Any]],
        event: Event,
        data: Dict[str, Any]
    ) -> Any:
        if not isinstance(event, Message):
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
            try:
                db_user = await add_user(
                    user_id=user.id,
                    user_username=user.username or "",
                    user_name=user.full_name,
                    user_first_seen_at=get_timestamp(),
                    user_language=user.language_code or ""
                )
            except RuntimeError as e:
                logger.error(f"[Verification] Failed to add user {user.id} to database: {e}, skipping message")
                return

        if db_user.user_status == 1:
            return await handler(event, data)

        existing_captcha = await get_captcha(captcha_user_id=user.id, captcha_chat_id=chat.id)
        if existing_captcha is not None:
            if is_expired(existing_captcha.captcha_expires_at):
                await send_captcha(message=event, bot=bot)
                return

            try:
                await event.delete()
            except TelegramForbiddenError:
                return
            except Exception as e:
                logger.error(f"[Verification] Error deleting message: {e}")
            return

        await send_captcha(message=event, bot=bot)
