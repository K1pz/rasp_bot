import logging
from app.db.models import Settings
from app.services.date_service import get_local_now, get_today, get_tomorrow, parse_hhmm
from app.services.sender import send_schedule
from app.services.alerts_service import alert_admin
from app.db.connection import async_session_maker
from app.db.repos.sendlog_repo import SendLogRepo

async def run_catchup(settings: Settings):
    """
    Checks if any scheduled messages were missed while the bot was offline and sends them.
    Also checks for stuck 'reserved' tasks in the logs.
    """
    if not settings.chat_id:
        await alert_admin("Chat not bound, skip catch-up (chat_id missing).")
        return
    if settings.mode == 0:
        logging.info("Catch-up skipped: mode=0.")
        return

    tz = settings.timezone
    now = get_local_now(tz)
    now_time = now.time()
    
    today = get_today(tz)
    
    msgs = []

    # Parse morning time
    # settings.morning_time is expected to be HH:MM
    try:
        morning_time = parse_hhmm(settings.morning_time)
    except ValueError:
        logging.error(f"Invalid morning_time format: {settings.morning_time}")
        return

    # 1. Morning catch-up (Send schedule for TODAY)
    if settings.mode in (1, 2) and now_time >= morning_time:
        # send_schedule handles anti-duplication logic internally
        sent = await send_schedule(
            chat_id=settings.chat_id,
            target_date=today,
            kind="morning"
        )
        if sent:
            msgs.append(f"morning on {today}")

    # 2. Evening catch-up (Send schedule for TOMORROW)
    # Only if mode=2 and evening_time is set
    if settings.mode == 2 and settings.evening_time:
        try:
            evening_time = parse_hhmm(settings.evening_time)
            if now_time >= evening_time:
                tomorrow = get_tomorrow(tz)
                sent = await send_schedule(
                    chat_id=settings.chat_id,
                    target_date=tomorrow,
                    kind="evening"
                )
                if sent:
                    msgs.append(f"evening on {tomorrow}")
        except ValueError:
            logging.error(f"Invalid evening_time format: {settings.evening_time}")

    # 3. Notify admin if a catch-up action physically occurred (newly sent/attempted)
    if msgs:
        await alert_admin(
            f"Bot was offline, catch-up executed for chat_id={settings.chat_id}: {', '.join(msgs)}"
        )

    # 4. Check for stuck reserved tasks (reserved without sent_at for > 15 mins)
    try:
        async with async_session_maker() as session:
            repo = SendLogRepo(session)
            # Find tasks stuck in 'reserved' for more than 15 minutes
            stuck_logs = await repo.find_stuck_reserved(older_than_minutes=15)
            
            if stuck_logs:
                details = []
                for log in stuck_logs:
                    details.append(f"- {log.kind} for {log.target_date} (reserved: {log.reserved_at})")
                
                await alert_admin(
                    f"⚠️ Found {len(stuck_logs)} stuck reserved tasks (no sent_at):\n" + 
                    "\n".join(details)
                )
    except Exception as e:
        logging.error(f"Error checking stuck reserved tasks: {e}")
