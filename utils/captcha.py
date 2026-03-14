import secrets
import random
from datetime import datetime, timedelta
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.captcha_table import add_captcha, CaptchaModel
from database.chat_table import get_chat, add_chat
from config import settings
from utils.helpers import get_chat_title
from utils.emoji_descriptions import EMOJI_DESCRIPTIONS
from logs.logger import logger


CAPTCHA_PROMPTS = [
    "Выберите эмодзи:",
    "Найдите эмодзи:",
    "Укажите эмодзи:",
    "Выберите кнопку с эмодзи:",
    "Нажмите на эмодзи:",
    "Покажите эмодзи:",
]


# ~~~~ SEND CAPTCHA ~~~~
async def send_captcha(message: Message, bot) -> CaptchaModel | None:
    """
    Отправка капчи пользователю.
    
    Returns:
        CaptchaModel: созданная капча
        None: если отправка не удалась или капча отключена
    
    Raises:
        RuntimeError: если не удалось сохранить капчу в БД (после успешной отправки в Telegram)
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_message_id = message.message_id



    # Получаем или создаём чат
    chat = await get_chat(chat_id=chat_id)

    if chat is None:
        try:
            chat = await add_chat(chat_id=chat_id, chat_title=get_chat_title(message.chat))
        except RuntimeError as e:
            logger.error(
                f"[Captcha] Failed to create chat in database: chat_id={chat_id}, error={e}"
            )
            return None

    if chat.chat_captcha_enabled == 0:
        return None

    # Генерируем параметры капчи
    expires_at = (datetime.now() + timedelta(seconds=chat.chat_captcha_timeout)).strftime("%Y-%m-%d %H:%M:%S")
    correct_token = secrets.token_urlsafe(16)
    correct_emoji = secrets.SystemRandom().choice(settings.captcha_emojis)

    emoji_options = secrets.SystemRandom().sample(settings.captcha_emojis, k=6)
    if correct_emoji not in emoji_options:
        emoji_options[0] = correct_emoji
    secrets.SystemRandom().shuffle(emoji_options)

    buttons = []
    for emoji in emoji_options:
        if emoji == correct_emoji:
            token = correct_token
        else:
            token = secrets.token_urlsafe(16)
        buttons.append((emoji, f"captcha:verify:{token}:{user_id}:{chat_id}"))

    builder = InlineKeyboardBuilder()
    for text, callback_data in buttons:
        builder.button(text=text, callback_data=callback_data)
    builder.adjust(3)
    keyboard = builder.as_markup()

    prompt = random.choice(CAPTCHA_PROMPTS)
    description = EMOJI_DESCRIPTIONS.get(correct_emoji, correct_emoji)
    text = (
        f"🔒 <b>Верификация</b>\n\n"
        f"{prompt} {description}\n"
        f"У вас есть {chat.chat_captcha_timeout} секунд."
    )

    # Отправляем сообщение в Telegram
    captcha_message = None
    try:
        captcha_message = await message.reply(text=text, reply_markup=keyboard)
    except TelegramForbiddenError:
        logger.warning(
            f"[Captcha] TelegramForbiddenError when sending captcha: "
            f"chat_id={chat_id}, user_id={user_id}"
        )
        return None
    except Exception as e:
        logger.error(
            f"[Captcha] Error sending captcha to Telegram: "
            f"chat_id={chat_id}, user_id={user_id}, error={e}"
        )
        raise

    # Сохраняем в БД
    try:
        captcha = await add_captcha(
            captcha_user_id=user_id,
            captcha_chat_id=chat_id,
            captcha_expires_at=expires_at,
            captcha_payload=correct_token,
            captcha_message_id=captcha_message.message_id,
            captcha_correct_emoji=correct_emoji,
            captcha_user_message_id=user_message_id,
            captcha_attempts=0
        )
        return captcha
        
    except RuntimeError as e:
        # БД упала после отправки сообщения - нужно удалить сообщение из чата
        logger.error(
            f"[Captcha] Database error after sending message: "
            f"chat_id={chat_id}, captcha_message_id={captcha_message.message_id}, error={e}"
        )
        
        # Пытаемся удалить отправленное сообщение
        try:
            await captcha_message.delete()
            logger.info(
                f"[Captcha] Cleaned up orphaned message after DB error: "
                f"chat_id={chat_id}, message_id={captcha_message.message_id}"
            )
        except TelegramForbiddenError:
            logger.warning(
                f"[Captcha] Cannot delete orphaned message (no permissions): "
                f"chat_id={chat_id}, message_id={captcha_message.message_id}"
            )
        except Exception as cleanup_error:
            logger.error(
                f"[Captcha] Failed to cleanup orphaned message: "
                f"chat_id={chat_id}, message_id={captcha_message.message_id}, error={cleanup_error}"
            )
        
        # Перевыбрасываем RuntimeError
        raise RuntimeError(
            f"Failed to save captcha to database after sending message: {e}"
        ) from e