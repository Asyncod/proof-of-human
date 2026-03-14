from dataclasses import dataclass
from aiosqlite import connect, OperationalError, IntegrityError
from config import BASE_PATH
from logs.logger import logger


# ~~~~ TABLE MODEL ~~~~
@dataclass
class CaptchaModel:
    """
    Параметры:
        captcha_id (int): Уникальный ID капчи
        captcha_user_id (int): Telegram ID пользователя
        captcha_chat_id (int): Telegram ID чата
        captcha_expires_at (str): timestamp истечения капчи
        captcha_payload (str): токен правильного ответа
        captcha_message_id (int): ID сообщения капчи
        captcha_correct_emoji (str): правильный эмодзи для отображения в тексте
        captcha_user_message_id (int): ID сообщения пользователя, вызвавшего капчу
        captcha_attempts (int): количество сделанных попыток
    """
    captcha_id: int
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
                    captcha_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    captcha_user_id INTEGER,
                    captcha_chat_id INTEGER,
                    captcha_expires_at TEXT,
                    captcha_payload TEXT,
                    captcha_message_id INTEGER,
                    captcha_correct_emoji TEXT,
                    captcha_user_message_id INTEGER,
                    captcha_attempts INTEGER DEFAULT 0
                )
            """)
            await db.execute(
                "CREATE INDEX idx_captcha_user_chat ON captcha_table(captcha_user_id, captcha_chat_id)"
            )
            await db.commit()
        except OperationalError:
            pass


# ~~~~ DATA GETTING ~~~~
async def get_captcha(captcha_id: int) -> CaptchaModel | None:
    """Получить капчу по ID"""
    async with connect(BASE_PATH) as db:
        cursor = await db.execute(
            "SELECT captcha_id, captcha_user_id, captcha_chat_id, captcha_expires_at, captcha_payload, "
            "captcha_message_id, captcha_correct_emoji, captcha_user_message_id, captcha_attempts "
            "FROM captcha_table WHERE captcha_id = ?",
            (captcha_id,)
        )
        row = await cursor.fetchone()
        return CaptchaModel(*row) if row else None


async def get_captchas_for_user(captcha_user_id: int, captcha_chat_id: int) -> list[CaptchaModel]:
    """Получить все активные капчи для пользователя в чате"""
    async with connect(BASE_PATH) as db:
        cursor = await db.execute(
            "SELECT captcha_id, captcha_user_id, captcha_chat_id, captcha_expires_at, captcha_payload, "
            "captcha_message_id, captcha_correct_emoji, captcha_user_message_id, captcha_attempts "
            "FROM captcha_table WHERE captcha_user_id = ? AND captcha_chat_id = ?",
            (captcha_user_id, captcha_chat_id)
        )
        rows = await cursor.fetchall()
        return [CaptchaModel(*row) for row in rows]


async def get_captcha_by_payload(captcha_payload: str) -> CaptchaModel | None:
    """Получить капчу по токену payload"""
    async with connect(BASE_PATH) as db:
        cursor = await db.execute(
            "SELECT captcha_id, captcha_user_id, captcha_chat_id, captcha_expires_at, captcha_payload, "
            "captcha_message_id, captcha_correct_emoji, captcha_user_message_id, captcha_attempts "
            "FROM captcha_table WHERE captcha_payload = ?",
            (captcha_payload,)
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
) -> CaptchaModel:
    """Добавить новую капчу. Возвращает созданную капчу или выбрасывает RuntimeError."""
    async with connect(BASE_PATH) as db:
        try:
            cursor = await db.execute(
                "INSERT INTO captcha_table (captcha_user_id, captcha_chat_id, captcha_expires_at, "
                "captcha_payload, captcha_message_id, captcha_correct_emoji, captcha_user_message_id, captcha_attempts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (captcha_user_id, captcha_chat_id, captcha_expires_at, captcha_payload, 
                 captcha_message_id, captcha_correct_emoji, captcha_user_message_id, captcha_attempts)
            )
            await db.commit()
            captcha_id = cursor.lastrowid
            
            result = await get_captcha(captcha_id=captcha_id)
            if result is None:
                logger.error(
                    f"[CaptchaTable] Failed to retrieve captcha after insert: "
                    f"captcha_id={captcha_id}, user_id={captcha_user_id}, chat_id={captcha_chat_id}"
                )
                raise RuntimeError(
                    f"Database inconsistency: captcha_id={captcha_id} was inserted but not found"
                )
            
            pass
            return result
            
        except IntegrityError as e:
            logger.error(
                f"[CaptchaTable] IntegrityError while adding captcha: "
                f"user_id={captcha_user_id}, chat_id={captcha_chat_id}, error={e}"
            )
            raise RuntimeError(f"Failed to add captcha: integrity constraint violated") from e
        except Exception as e:
            logger.error(
                f"[CaptchaTable] Unexpected error while adding captcha: "
                f"user_id={captcha_user_id}, chat_id={captcha_chat_id}, error={e}"
            )
            raise RuntimeError(f"Failed to add captcha: {e}") from e


# ~~~~ DATA DELETING ~~~~
async def delete_captcha(captcha_id: int) -> bool:
    """Удалить капчу по ID. Возвращает True если запись была удалена."""
    async with connect(BASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM captcha_table WHERE captcha_id = ?",
            (captcha_id,)
        )
        await db.commit()
        deleted = cursor.rowcount > 0
        return deleted


async def delete_all_captchas_for_user(captcha_user_id: int, captcha_chat_id: int) -> int:
    """Удалить все капчи пользователя в чате. Возвращает количество удалённых записей."""
    async with connect(BASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM captcha_table WHERE captcha_user_id = ? AND captcha_chat_id = ?",
            (captcha_user_id, captcha_chat_id)
        )
        await db.commit()
        deleted_count = cursor.rowcount
        return deleted_count


# ~~~~ STATISTICS ~~~~
async def get_captchas_count() -> int:
    """Получить количество активных капч"""
    async with connect(BASE_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM captcha_table")
        result = await cursor.fetchone()
        return result[0] if result else 0


# ~~~~ INCREMENT ATTEMPTS ~~~~
async def increment_captcha_attempts(captcha_id: int) -> CaptchaModel | None:
    """Увеличить счётчик попыток на 1"""
    async with connect(BASE_PATH) as db:
        await db.execute(
            "UPDATE captcha_table SET captcha_attempts = captcha_attempts + 1 "
            "WHERE captcha_id = ?",
            (captcha_id,)
        )
        await db.commit()
        return await get_captcha(captcha_id=captcha_id)


# ~~~~ MIGRATION ~~~~
async def migrate_captcha_table_v2() -> None:
    """Миграция: добавить captcha_id и убрать PRIMARY KEY с (user_id, chat_id)"""
    async with connect(BASE_PATH) as db:
        try:
            # Проверяем, есть ли уже колонка captcha_id
            cursor = await db.execute("PRAGMA table_info(captcha_table)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if "captcha_id" not in column_names:
                # Создаём новую таблицу с правильной схемой
                await db.execute("""
                    CREATE TABLE captcha_table_new (
                        captcha_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        captcha_user_id INTEGER,
                        captcha_chat_id INTEGER,
                        captcha_expires_at TEXT,
                        captcha_payload TEXT,
                        captcha_message_id INTEGER,
                        captcha_correct_emoji TEXT,
                        captcha_user_message_id INTEGER,
                        captcha_attempts INTEGER DEFAULT 0
                    )
                """)
                
                # Копируем данные
                await db.execute("""
                    INSERT INTO captcha_table_new (
                        captcha_user_id, captcha_chat_id, captcha_expires_at,
                        captcha_payload, captcha_message_id, captcha_correct_emoji,
                        captcha_user_message_id, captcha_attempts
                    )
                    SELECT captcha_user_id, captcha_chat_id, captcha_expires_at,
                           captcha_payload, captcha_message_id, captcha_correct_emoji,
                           captcha_user_message_id, captcha_attempts
                    FROM captcha_table
                """)
                
                # Удаляем старую таблицу
                await db.execute("DROP TABLE captcha_table")
                
                # Переименовываем новую
                await db.execute("ALTER TABLE captcha_table_new RENAME TO captcha_table")
                
                # Создаём индекс
                await db.execute(
                    "CREATE INDEX idx_captcha_user_chat ON captcha_table(captcha_user_id, captcha_chat_id)"
                )
                
                await db.commit()
                logger.info("[CaptchaTable] Migrated to v2: added captcha_id, removed composite PK")
        except OperationalError as e:
            logger.warning(f"[CaptchaTable] Migration v2 warning: {e}")
            pass


async def migrate_captcha_table() -> None:
    """Добавить captcha_attempts в существующие таблицы (старая миграция)"""
    async with connect(BASE_PATH) as db:
        try:
            await db.execute("ALTER TABLE captcha_table ADD COLUMN captcha_attempts INTEGER DEFAULT 0")
            await db.commit()
            logger.info("[CaptchaTable] Migrated: added captcha_attempts")
        except OperationalError:
            pass