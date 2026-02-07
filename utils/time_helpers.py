from datetime import datetime


def get_timestamp(dt: datetime | None = None) -> str:
    """Получить timestamp в формате YYYY-MM-DD HH:MM:SS"""
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def parse_timestamp(timestamp_str: str) -> datetime:
    """Распарсить timestamp из формата YYYY-MM-DD HH:MM:SS"""
    return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")


def is_expired(timestamp_str: str) -> bool:
    """Проверить истек ли timestamp"""
    try:
        dt = parse_timestamp(timestamp_str)
        return datetime.now() > dt
    except (ValueError, TypeError):
        return True
