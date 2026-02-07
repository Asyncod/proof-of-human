from os import path, makedirs
from dataclasses import dataclass, field
from dotenv import load_dotenv
import os
import sys


# ~~~~ LOAD ENV ~~~~
load_dotenv()

# ~~~~ VALIDATE ENV ~~~~
def validate_and_get_env() -> tuple[str, str, int]:
    """Валидация и получение переменных окружения"""
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        print("❌ Error: BOT_TOKEN is missing or invalid")
        sys.exit(1)
    
    owner_id = os.getenv("OWNER_ID", "").strip()
    try:
        owner_id_int = int(owner_id)
        if owner_id_int <= 0:
            raise ValueError
    except (ValueError, TypeError):
        print("❌ Error: Invalid OWNER_ID (must be positive integer)")
        sys.exit(1)
    
    bot_username = os.getenv("BOT_USERNAME", "").strip()
    if not bot_username:
        print("❌ Error: BOT_USERNAME is required")
        sys.exit(1)
    
    return bot_token, bot_username, owner_id_int


_validated_token, _validated_username, _validated_owner_id = validate_and_get_env()


# ~~~~ PATH SETTINGS ~~~~
CORE = path.dirname(path.abspath(__file__))
BASE_DIR = path.join(CORE, "database", "base")
BASE_PATH = path.join(BASE_DIR, "data.db")

# ~~~~ CREATE DATABASE DIRECTORY ~~~~
makedirs(BASE_DIR, exist_ok=True)


# ~~~~ CONFIG MODEL ~~~~
@dataclass
class Config:
    """
    Параметры:
        bot_token (str): токен бота Telegram
        bot_username (str): юзернейм бота Telegram
        owner_id (int): Telegram ID владельца бота
        default_captcha_timeout (int): время на капчу в секундах
        welcome_message (str): приветственное сообщение при добавлении бота
        captcha_timeout_options (list[int]): опции таймаута для настроек
    """
    bot_token: str
    bot_username: str
    owner_id: int
    default_captcha_timeout: int = 10
    welcome_message: str = (
        "Привет! 👋 Я бот защиты от спама.\n"
        "Все новые участники должны пройти верификацию.\n"
        "Напишите /settings для настроек.\n\n"
        "<i>По всем вопросам: @asynco</i>\n"
        "<i>Бот в бета версии, могут быть баги</i>"
    )
    bot_not_admin_message: str = (
        "❌ Бот не является администратором этого чата.\n\n"
        "Пожалуйста, добавьте бота в администраторы, прежде чем использовать команду /settings."
    )
    captcha_emojis: list[str] = field(default_factory=lambda: [
        "🍎", "🍊", "🍋", "🌶", "🐸", "🐹",
        "🐻", "🐼", "🐽", "🌺", "🌻", "🌼",
        "🌽", "🌾", "🌷", "⚡", "⭐", "💎", "💡",
        "🔥", "⚓", "🎁", "🎈", "🎉", "🎊", "🎯", "🎲"
    ])
    captcha_timeout_options: list[int] = field(default_factory=lambda: [10, 30, 60, 120])
    default_max_attempts: int = 2
    max_attempts_options: list[int] = field(default_factory=lambda: [1, 2, 3, 5])


# ~~~~ SETTINGS ~~~~
settings = Config(
    bot_token=_validated_token,
    bot_username=_validated_username,
    owner_id=_validated_owner_id,
)
