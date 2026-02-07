from datetime import datetime, timedelta
from collections import defaultdict


class RateLimiter:
    """Простой rate limiter для защиты от спама"""
    
    def __init__(self, max_attempts: int = 10, period_seconds: int = 60):
        self.max_attempts = max_attempts
        self.period = timedelta(seconds=period_seconds)
        self.attempts = defaultdict(list)
    
    def is_allowed(self, user_id: int, chat_id: int) -> bool:
        """Проверить разрешено ли действие"""
        key = (user_id, chat_id)
        now = datetime.now()
        
        # Удалить старые попытки
        self.attempts[key] = [
            attempt_time for attempt_time in self.attempts[key]
            if now - attempt_time < self.period
        ]
        
        # Проверить лимит
        if len(self.attempts[key]) >= self.max_attempts:
            return False
        
        # Добавить новую попытку
        self.attempts[key].append(now)
        return True
    
    def reset(self, user_id: int, chat_id: int) -> None:
        """Сбросить счетчик для пользователя"""
        key = (user_id, chat_id)
        self.attempts.pop(key, None)


# Глобальный инстанс для captcha
captcha_rate_limiter = RateLimiter(max_attempts=10, period_seconds=60)
