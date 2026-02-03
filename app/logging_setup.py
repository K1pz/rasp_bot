import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_TELEGRAM_TOKEN_RE = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b")
_KEY_VALUE_RE = re.compile(
    r"(?i)\b(BOT_TOKEN|TG_TOKEN|TELEGRAM_TOKEN|API_HASH|API_ID|DATABASE_URL|DB_URL|SECRET|PASSWORD|PASS|ACCESS_TOKEN|REFRESH_TOKEN)\s*[:=]\s*([^\s]+)"
)
_AUTH_BEARER_RE = re.compile(r"(?i)\bAuthorization:\s*Bearer\s+([A-Za-z0-9._-]+)")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+([A-Za-z0-9._-]+)")


def _redact(text: str) -> str:
    redacted = _TELEGRAM_TOKEN_RE.sub("[REDACTED]", text)
    redacted = _KEY_VALUE_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
    redacted = _AUTH_BEARER_RE.sub("Authorization: Bearer [REDACTED]", redacted)
    redacted = _BEARER_RE.sub("Bearer [REDACTED]", redacted)
    return redacted


class RedactingFormatter(logging.Formatter):
    def formatException(self, ei):
        return _redact(super().formatException(ei))

    def formatStack(self, stack_info):
        return _redact(super().formatStack(stack_info))


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = _redact(message)
        record.args = ()
        return True

def setup_logging():
    """
    Configures logging for the application.
    output: stdout + file (bot.log)
    level: INFO
    """
    Path("data").mkdir(parents=True, exist_ok=True)
    formatter = RedactingFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handlers = [
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler("data/bot.log", maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8"),
    ]
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(RedactingFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    for handler in handlers:
        root_logger.addHandler(handler)
    
    # Mute some noisy loggers if needed
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
