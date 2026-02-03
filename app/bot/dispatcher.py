from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import (
    admin_menu,
    admin_preview_send,
    admin_settings_fsm,
    admin_settings_transfer,
    admin_status,
    admin_upload,
    group_setup,
    start,
)
from app.bot.middlewares import LoggingMiddleware
from app.config import settings

if settings.TELEGRAM_PROXY:
    session = AiohttpSession(proxy=settings.TELEGRAM_PROXY)
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"), session=session)
else:
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

dp.message.middleware(LoggingMiddleware())

dp.include_router(admin_menu.router)
dp.include_router(admin_status.router)
dp.include_router(admin_settings_fsm.router)
dp.include_router(admin_settings_transfer.router)
dp.include_router(admin_upload.router)
dp.include_router(admin_preview_send.router)
dp.include_router(group_setup.router)
dp.include_router(start.router)
