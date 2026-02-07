from loguru import logger
from sys import stderr
from os import path

# ~~~~ LOGGER SETTING ~~~~
logger.remove()

# Console output
logger.add(
    sink=stderr,
    backtrace=True,
    diagnose=True,
    format="<white>{time:HH:mm:ss}</white>"
           " | <level>{level: <8}</level>"
           " - <white>{message}</white>",
)

# File output with rotation
log_path = path.join(path.dirname(path.dirname(__file__)), "logs")
logger.add(
    sink=f"{log_path}/bot.log",
    rotation="10 MB",
    retention="7 days",
    compression="zip",
    backtrace=True,
    diagnose=True,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="INFO"
)
