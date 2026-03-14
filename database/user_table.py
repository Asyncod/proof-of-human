from dataclasses import dataclass
from aiosqlite import connect, OperationalError
from config import BASE_PATH
from logs.logger import logger


# ~~~~ TABLE MODEL ~~~~
@dataclass
class UserModel:
    """
    Параметры:
        user_id (int): уникальный Telegram ID пользователя
        user_username (str): юзернейм пользователя @username
        user_name (str): полное имя пользователя
        user_status (int): 0 - не верифицирован, 1 - верифицирован
        user_first_seen_at (str): timestamp первого появления
        user_language (str): язык пользователя
        user_is_premium (int | None): 1 - есть Premium, 0 - нет, NULL - неизвестно
    """
    user_id: int
    user_username: str
    user_name: str
    user_status: int
    user_first_seen_at: str
    user_language: str
    user_is_premium: int | None


# ~~~~ BASE CREATING ~~~~
async def create_db() -> None:
    async with connect(BASE_PATH) as db:
        try:
            await db.execute("""
                CREATE TABLE user_table (
                    user_id INTEGER PRIMARY KEY,
                    user_username TEXT,
                    user_name TEXT,
                    user_status INTEGER DEFAULT 0,
                    user_first_seen_at TEXT,
                    user_language TEXT,
                    user_is_premium INTEGER
                )
            """)
            await db.commit()
        except OperationalError:
            pass


# ~~~~ DATA GETTING ~~~~
async def get_user(user_id: int) -> UserModel | None:
    async with connect(BASE_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id, user_username, user_name, user_status, user_first_seen_at, user_language, "
            "user_is_premium "
            "FROM user_table WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        return UserModel(*row) if row else None


# ~~~~ DATA ADDING ~~~~
async def add_user(
    user_id: int,
    user_username: str,
    user_name: str,
    user_first_seen_at: str,
    user_language: str,
    user_is_premium: int | None = None
) -> UserModel:
    """Добавить нового пользователя с аналитическими данными."""
    async with connect(BASE_PATH) as db:
        await db.execute(
            "INSERT INTO user_table (user_id, user_username, user_name, user_status, user_first_seen_at, "
            "user_language, user_is_premium) "
            "VALUES (?, ?, ?, 0, ?, ?, ?)",
            (user_id, user_username, user_name, user_first_seen_at, user_language,
             user_is_premium)
        )
        await db.commit()
        result = await get_user(user_id=user_id)
        if result is None:
            logger.error(f"[UserTable] Failed to retrieve user {user_id} after insert")
            raise RuntimeError(f"Database inconsistency: user {user_id} was inserted but not found")
        pass
        return result


# ~~~~ DATA UPDATING ~~~~
ALLOWED_USER_FIELDS = {
    "user_username", "user_name", "user_status", "user_language",
    "user_is_premium"
}

async def update_user(field: str, data: str | int | None, user_id: int) -> None:
    if field not in ALLOWED_USER_FIELDS:
        return logger.error(f"[UserTable] Invalid field name: {field}")

    async with connect(BASE_PATH) as db:
        await db.execute(
            f"UPDATE user_table SET {field} = ? WHERE user_id = ?",
            (data, user_id)
        )
        await db.commit()


# ~~~~ MIGRATION ~~~~
async def migrate_user_table() -> None:
    """Добавить колонку is_premium для аналитики"""
    async with connect(BASE_PATH) as db:
        try:
            # Проверяем существующие колонки
            cursor = await db.execute("PRAGMA table_info(user_table)")
            columns = await cursor.fetchall()
            column_names = {col[1] for col in columns}
            
            # Добавляем user_is_premium если отсутствует
            if "user_is_premium" not in column_names:
                await db.execute("ALTER TABLE user_table ADD COLUMN user_is_premium INTEGER")
                logger.info("[UserTable] Migration: added user_is_premium column")
            
            await db.commit()
            logger.info("[UserTable] Migration completed successfully")
        except OperationalError as e:
            logger.warning(f"[UserTable] Migration warning: {e}")


# ~~~~ STATISTICS ~~~~
async def get_users_count() -> int:
    """Получить общее количество пользователей"""
    async with connect(BASE_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM user_table")
        result = await cursor.fetchone()
        return result[0] if result else 0


async def get_verified_count() -> int:
    """Получить количество верифицированных пользователей"""
    async with connect(BASE_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM user_table WHERE user_status = 1")
        result = await cursor.fetchone()
        return result[0] if result else 0