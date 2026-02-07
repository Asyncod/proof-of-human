from aiogram import BaseMiddleware
from aiogram.types import Message, ErrorEvent
from aiogram.exceptions import TelegramForbiddenError
from typing import Any, Callable, Dict, Awaitable
from config import settings
from logs.logger import logger


# ~~~~ EVENT TYPE ~~~~
Event = Message | ErrorEvent


# ~~~~ ERROR HANDLER MIDDLEWARE ~~~~
class ErrorHandlerMiddleware(BaseMiddleware):
    """Логирование API ошибок и отправка критических владельцу"""

    async def __call__(
        self,
        handler: Callable[[Event, Dict[str, Any]], Awaitable[Any]],
        event: Event,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await handler(event, data)
        except TelegramForbiddenError as e:
            chat_info = ""
            if isinstance(event, ErrorEvent) and hasattr(event, 'update'):
                update = event.update
                if hasattr(update, 'chat_id'):
                    chat_info = f"Chat ID: {update.chat_id}\n"
            
            logger.error(f"[ErrorHandler] TelegramForbiddenError: {e}\n{chat_info}")

            if isinstance(event, ErrorEvent):
                try:
                    await event.bot.send_message(
                        chat_id=settings.owner_id,
                        text=f"⚠️ <b>Bot Kicked</b>\n\n"
                             f"Bot was kicked from a chat or blocked by a user.\n"
                             f"{chat_info}"
                             f"Error: {str(e)}\n\n"
                             f"ℹ️ Settings preserved in database."
                    )
                except Exception:
                    pass
            
            return None
        except Exception as e:
            logger.error(f"Error in handler: {e}", exc_info=True)

            if isinstance(event, ErrorEvent):
                try:
                    await event.bot.send_message(
                        chat_id=settings.owner_id,
                        text=f"🚨 <b>API Error</b>\n\n{str(e)}"
                    )
                except Exception:
                    pass

            raise
