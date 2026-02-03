import logging
from aiogram import BaseMiddleware
from aiogram.types import Message


def _is_group_command(message: Message) -> bool:
    text = message.text or message.caption
    if not text:
        return False
    command = text.strip().split()[0]
    command_base = command.split("@", 1)[0].lower()
    allowed = {"/bind", "/setup", "/settings", "/status", "/today", "/tomorrow", "/week", "/nextweek", "/start"}
    return command_base in allowed


class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        logging.getLogger(__name__).debug("Incoming event: %s", type(event).__name__)
        if isinstance(event, Message):
            if event.chat.type in ("group", "supergroup") and not _is_group_command(event):
                return
        return await handler(event, data)
