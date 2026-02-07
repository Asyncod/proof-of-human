from dataclasses import dataclass
from aiosqlite import connect, OperationalError
from config import BASE_PATH, settings
from logs.logger import logger


# ~~~~ TABLE MODEL ~~~~
@dataclass
class ChatModel:
    """
    Параметры:
        chat_id (int): уникальный Telegram ID чата
        chat_title (str): название чата
        chat_captcha_enabled (int): 0 - выключена, 1 - включена
        chat_timeout (int): время на капчу в секундах
        chat_max_attempts (int): максимальное количество неправильных попыток
    """
    chat_id: int
    chat_title: str
    chat_captcha_enabled: int
    chat_timeout: int
    chat_max_attempts: int


# ~~~~ BASE CREATING ~~~~
async def create_db() -> None:
    async with connect(BASE_PATH) as db:
        try:
            await db.execute("""
                CREATE TABLE chat_table (
                    chat_id INTEGER PRIMARY KEY,
                    chat_title TEXT,
                    chat_captcha_enabled INTEGER DEFAULT 1,
                    chat_timeout INTEGER DEFAULT 30,
                    chat_max_attempts INTEGER DEFAULT 2
                )
            """)
            await db.commit()
        except OperationalError:
            pass


# ~~~~ DATA GETTING ~~~~
async def get_chat(chat_id: int) -> ChatModel | None:
    async with connect(BASE_PATH) as db:
        cursor = await db.execute(
            "SELECT chat_id, chat_title, chat_captcha_enabled, chat_timeout, chat_max_attempts "
            "FROM chat_table WHERE chat_id = ?",
            (chat_id,)
        )
        row = await cursor.fetchone()
        return ChatModel(*row) if row else None


# ~~~~ DATA ADDING ~~~~
async def add_chat(
    chat_id: int,
    chat_title: str,
    chat_captcha_enabled: int = 1,
    chat_timeout: int = settings.default_captcha_timeout,
    chat_max_attempts: int = settings.default_max_attempts
) -> ChatModel | None:
    existing_chat = await get_chat(chat_id=chat_id)
    if existing_chat is not None:
        return existing_chat

    async with connect(BASE_PATH) as db:
        await db.execute(
            "INSERT INTO chat_table (chat_id, chat_title, chat_captcha_enabled, chat_timeout, chat_max_attempts) "
            "VALUES (?, ?, ?, ?, ?)",
            (chat_id, chat_title, chat_captcha_enabled, chat_timeout, chat_max_attempts)
        )
        await db.commit()
        result = await get_chat(chat_id=chat_id)
        if result is None:
            logger.error(f"Failed to retrieve chat {chat_id} after insert")
            raise RuntimeError(f"Database inconsistency: chat {chat_id} was inserted but not found")
        return result


# ~~~~ DATA UPDATING ~~~~
ALLOWED_CHAT_FIELDS = {"chat_title", "chat_captcha_enabled", "chat_timeout", "chat_max_attempts"}

async def update_chat(field: str, data: str | int, chat_id: int) -> None:
    if field not in ALLOWED_CHAT_FIELDS:
        return logger.error(f"Invalid field name: {field}")

    async with connect(BASE_PATH) as db:
        await db.execute(
            f"UPDATE chat_table SET {field} = ? WHERE chat_id = ?",
            (data, chat_id)
        )
        await db.commit()


# ~~~~ STATISTICS ~~~~
async def get_chats_count() -> int:
    """Получить общее количество чатов"""
    async with connect(BASE_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM chat_table")
        result = await cursor.fetchone()
        return result[0] if result else 0


# ~~~~ MIGRATION ~~~~
async def migrate_chat_table() -> None:
    """Добавить chat_max_attempts в существующие таблицы"""
    async with connect(BASE_PATH) as db:
        try:
            await db.execute("ALTER TABLE chat_table ADD COLUMN chat_max_attempts INTEGER DEFAULT 2")
            await db.commit()
            logger.info("chat_table migrated: added chat_max_attempts")
        except OperationalError:
            pass
