import secrets
import random
from datetime import datetime, timedelta
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.captcha_table import add_captcha
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
async def send_captcha(message: Message, bot) -> None:
    """Отправка капчи пользователю"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    chat = await get_chat(chat_id=chat_id)

    if chat is None:
        try:
            chat = await add_chat(chat_id=chat_id, chat_title=get_chat_title(message.chat))
        except RuntimeError as e:
            logger.error(f"[Captcha] Failed to create chat {chat_id} in database: {e}, aborting captcha")
            return

    if chat.chat_captcha_enabled == 0:
        return

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

    try:
        captcha_message = await message.reply(text=text, reply_markup=keyboard)
    except TelegramForbiddenError:
        return
    except Exception as e:
        logger.error(f"[Captcha] Error sending captcha: {e}")
        raise

    await add_captcha(
        captcha_user_id=user_id,
        captcha_chat_id=chat_id,
        captcha_expires_at=expires_at,
        captcha_payload=correct_token,
        captcha_message_id=captcha_message.message_id,
        captcha_correct_emoji=correct_emoji,
        captcha_user_message_id=message.message_id
    )
