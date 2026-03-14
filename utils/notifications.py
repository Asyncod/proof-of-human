from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from config import settings
from logs.logger import logger
from utils.time_helpers import get_timestamp


async def notify_owner_about_error(
    bot: Bot,
    error_type: str,
    chat_id: int,
    message_id: int | None,
    error_description: str,
) -> None:
    """
    Отправить уведомление владельцу об ошибке бота.

    Args:
        bot: Экземпляр бота
        error_type: Тип ошибки (например, "delete_message_failed")
        chat_id: ID чата где произошла ошибка
        message_id: ID сообщения (если применимо)
        error_description: Описание ошибки
    """
    try:
        # Получаем информацию о чате
        chat_info = await bot.get_chat(chat_id)
        chat_title = chat_info.title or f"Private {chat_id}"
        chat_type = chat_info.type

        # Формируем сообщение
        text = (
            f"⚠️ <b>Ошибка</b>\n\n"
            f"<code>{error_type}</code>\n\n"
            f"<b>Chat Title:</b> <code>{chat_title}</code>\n"
            f"<b>Chat ID:</b> <code>{chat_id}</code>\n"
            f"<b>Chat Type:</b> <code>{chat_type}</code>\n"
        )

        if message_id:
            text += f"<b>Message ID:</b> <code>{message_id}</code>\n"

        text += (
            f"\n<b>Error Description:</b>\n<pre>{error_description}</pre>\n\n"
            f"<code>{get_timestamp()}</code>"
        )

        # Отправляем владельцу
        await bot.send_message(chat_id=settings.owner_id, text=text)
        logger.info(f"[Notify] Sent error notification to owner: {error_type}")

    except TelegramForbiddenError:
        logger.error("[Notify] Cannot send notification - owner blocked bot")
    except Exception as e:
        logger.error(f"[Notify] Failed to send notification: {e}")
