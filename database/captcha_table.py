from dataclasses import dataclass
from aiosqlite import connect, OperationalError
from config import BASE_PATH
from logs.logger import logger


# ~~~~ TABLE MODEL ~~~~
@dataclass
class CaptchaModel:
    """
    Параметры:
        captcha_user_id (int): Telegram ID пользователя
        captcha_chat_id (int): Telegram ID чата
        captcha_expires_at (str): timestamp истечения капчи
        captcha_payload (str): токен правильного ответа
        captcha_message_id (int): ID сообщения капчи
        captcha_correct_emoji (str): правильный эмодзи для отображения в тексте
        captcha_user_message_id (int): ID сообщения пользователя, вызвавшего капчу
        captcha_attempts (int): количество сделанных попыток
    """
    captcha_user_id: int
    captcha_chat_id: int
    captcha_expires_at: str
    captcha_payload: str
    captcha_message_id: int
    captcha_correct_emoji: str
    captcha_user_message_id: int
    captcha_attempts: int


# ~~~~ BASE CREATING ~~~~
async def create_db() -> None:
    async with connect(BASE_PATH) as db:
        try:
            await db.execute("""
                CREATE TABLE captcha_table (
                    captcha_user_id INTEGER,
                    captcha_chat_id INTEGER,
                    captcha_expires_at TEXT,
                    captcha_payload TEXT,
                    captcha_message_id INTEGER,
                    captcha_correct_emoji TEXT,
                    captcha_user_message_id INTEGER,
                    captcha_attempts INTEGER DEFAULT 0,
                    PRIMARY KEY (captcha_user_id, captcha_chat_id)
                )
            """)
            await db.commit()
        except OperationalError:
            pass


# ~~~~ DATA GETTING ~~~~
async def get_captcha(captcha_user_id: int, captcha_chat_id: int) -> CaptchaModel | None:
    async with connect(BASE_PATH) as db:
        cursor = await db.execute(
            "SELECT captcha_user_id, captcha_chat_id, captcha_expires_at, captcha_payload, captcha_message_id, captcha_correct_emoji, captcha_user_message_id, captcha_attempts "
            "FROM captcha_table WHERE captcha_user_id = ? AND captcha_chat_id = ?",
            (captcha_user_id, captcha_chat_id)
        )
        row = await cursor.fetchone()
        return CaptchaModel(*row) if row else None


# ~~~~ DATA ADDING ~~~~
async def add_captcha(
    captcha_user_id: int,
    captcha_chat_id: int,
    captcha_expires_at: str,
    captcha_payload: str,
    captcha_message_id: int,
    captcha_correct_emoji: str,
    captcha_user_message_id: int,
    captcha_attempts: int = 0
) -> CaptchaModel | None:
    async with connect(BASE_PATH) as db:
        await db.execute(
            "INSERT INTO captcha_table (captcha_user_id, captcha_chat_id, captcha_expires_at, captcha_payload, captcha_message_id, captcha_correct_emoji, captcha_user_message_id, captcha_attempts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (captcha_user_id, captcha_chat_id, captcha_expires_at, captcha_payload, captcha_message_id, captcha_correct_emoji, captcha_user_message_id, captcha_attempts)
        )
        await db.commit()
        result = await get_captcha(captcha_user_id=captcha_user_id, captcha_chat_id=captcha_chat_id)
        if result is None:
            logger.error(f"Failed to retrieve captcha for user {captcha_user_id} in chat {captcha_chat_id} after insert")
            raise RuntimeError(f"Database inconsistency: captcha for user {captcha_user_id} in chat {captcha_chat_id} was inserted but not found")
        return result


# ~~~~ DATA DELETING ~~~~
async def delete_captcha(captcha_user_id: int, captcha_chat_id: int) -> None:
    async with connect(BASE_PATH) as db:
        await db.execute(
            "DELETE FROM captcha_table WHERE captcha_user_id = ? AND captcha_chat_id = ?",
            (captcha_user_id, captcha_chat_id)
        )
        await db.commit()


# ~~~~ STATISTICS ~~~~
async def get_captchas_count() -> int:
    """Получить количество активных капч"""
    async with connect(BASE_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM captcha_table")
        result = await cursor.fetchone()
        return result[0] if result else 0


# ~~~~ INCREMENT ATTEMPTS ~~~~
async def increment_captcha_attempts(captcha_user_id: int, captcha_chat_id: int) -> CaptchaModel | None:
    """Увеличить счётчик попыток на 1"""
    async with connect(BASE_PATH) as db:
        await db.execute(
            "UPDATE captcha_table SET captcha_attempts = captcha_attempts + 1 "
            "WHERE captcha_user_id = ? AND captcha_chat_id = ?",
            (captcha_user_id, captcha_chat_id)
        )
        await db.commit()
        return await get_captcha(captcha_user_id=captcha_user_id, captcha_chat_id=captcha_chat_id)


# ~~~~ MIGRATION ~~~~
async def migrate_captcha_table() -> None:
    """Добавить captcha_attempts в существующие таблицы"""
    async with connect(BASE_PATH) as db:
        try:
            await db.execute("ALTER TABLE captcha_table ADD COLUMN captcha_attempts INTEGER DEFAULT 0")
            await db.commit()
            logger.info("captcha_table migrated: added captcha_attempts")
        except OperationalError:
            pass
