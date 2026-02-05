import asyncio
import logging
from apscheduler.triggers.cron import CronTrigger
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeDefault,
)
from aiogram.exceptions import TelegramNetworkError

from app.logging_setup import setup_logging
from app.config import settings as env_settings
from app.db.connection import async_session_maker, ensure_schema
from app.db.repos.settings_repo import SettingsRepo
from app.services.scheduler_service import init_scheduler, ensure_periodic_job, scheduler
from app.services.catchup_service import run_catchup
from app.services.alerts_service import daily_coverage_check
from app.bot.dispatcher import bot, dp

async def main():
    # 1. Setup Logging
    setup_logging()
    logging.info("Initializing Bot...")

    # 1.5. Verify bot token
    try:
        bot_info = await bot.get_me()
        logging.info(f"Bot verified: @{bot_info.username} (id={bot_info.id})")
    except TelegramNetworkError as e:
        logging.error(f"Failed to verify bot token due to network error: {e}")
        logging.error("If api.telegram.org is blocked, set TELEGRAM_PROXY in .env.")
    except Exception as e:
        logging.error(f"Failed to verify bot token: {e}")
        logging.error("Please check your BOT_TOKEN in .env file")
        raise

    # 2. Init DB / Load Settings
    await ensure_schema()

    # 2.5. Set bot commands (shows up in UI)
    group_commands = [
        BotCommand(command="setup", description="\u041d\u0430\u0441\u0442\u0440\u043e\u0438\u0442\u044c \u0431\u043e\u0442\u0430 \u0432 \u0433\u0440\u0443\u043f\u043f\u0435"),
        BotCommand(command="bind", description="\u041f\u0440\u0438\u0432\u044f\u0437\u0430\u0442\u044c \u0447\u0430\u0442"),
        BotCommand(command="settings", description="\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438"),
        BotCommand(command="status", description="\u0421\u0442\u0430\u0442\u0443\u0441"),
        BotCommand(command="today", description="\u0420\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043d\u0430 \u0441\u0435\u0433\u043e\u0434\u043d\u044f"),
        BotCommand(command="tomorrow", description="\u0420\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043d\u0430 \u0437\u0430\u0432\u0442\u0440\u0430"),
        BotCommand(command="week", description="\u0420\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043d\u0430 \u043d\u0435\u0434\u0435\u043b\u044e (\u0441\u0435\u0433\u043e\u0434\u043d\u044f \u2014 \u0441\u0443\u0431\u0431\u043e\u0442\u0430)"),
        BotCommand(command="weekbrief", description="\u041a\u0440\u0430\u0442\u043a\u043e: \u0442\u0435\u043a\u0443\u0449\u0430\u044f \u043d\u0435\u0434\u0435\u043b\u044f"),
        BotCommand(command="nextweek", description="\u0420\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043d\u0430 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0443\u044e \u043d\u0435\u0434\u0435\u043b\u044e"),
        BotCommand(command="nextweekbrief", description="\u041a\u0440\u0430\u0442\u043a\u043e: \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0430\u044f \u043d\u0435\u0434\u0435\u043b\u044f"),
    ]
    private_commands = [
        BotCommand(command="start", description="\u0421\u0442\u0430\u0440\u0442 / \u043e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438"),
        BotCommand(command="admin", description="\u041c\u0435\u043d\u044e"),
        BotCommand(command="menu", description="\u041c\u0435\u043d\u044e"),
    ]
    try:
        await bot.set_my_commands(group_commands, scope=BotCommandScopeDefault())
        await bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())
        await bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())
        logging.info("Bot commands updated.")
    except Exception:
        logging.exception("Failed to set bot commands.")

    async with async_session_maker() as session:
        settings_repo = SettingsRepo(session)
        all_settings = await settings_repo.get_all_settings()
        settings_count = len(all_settings)
        logging.info("Loaded settings rows=%d", settings_count)
        if settings_count == 0:
            logging.warning(
                "No settings rows found. If this is NOT a first run, the bot likely started with an empty DB. "
                "Check DB_PATH and that the Docker volume is mounted to /app/data (and you didn't run `docker compose down -v`)."
            )

        # 3. Init Scheduler
        init_scheduler(timezone=env_settings.TZ)
        
        # 4. Ensure periodic sender is registered
        ensure_periodic_job()
        
        # 5. Register Daily Coverage Check (e.g. 10:00 every day)
        scheduler.add_job(
            daily_coverage_check,
            CronTrigger(hour=10, minute=0, timezone=env_settings.TZ),
            id="daily_coverage_check",
            replace_existing=True
        )

        # 6. Run Catch-up Logic per chat
        logging.info("Running catch-up...")
        for db_settings in all_settings:
            try:
                await run_catchup(db_settings)
            except Exception:
                logging.exception("Catch-up failed for chat_id=%s", getattr(db_settings, "chat_id", None))

    # 7. Start Scheduler
    scheduler.start()
    
    # 8. Start Polling
    logging.info("Starting polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    try:
        # On Windows, the SelectorEventLoop is default, which supports subprocesses but sometimes ProactorEventLoop is better for simple IO. 
        # However, asyncio.run() handles it.
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user!")
    except SystemExit:
        logging.info("Bot stopped!")
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        raise
