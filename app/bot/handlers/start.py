from datetime import datetime

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.chat_access import is_user_chat_member
from app.bot.handlers.admin_menu import admin_menu_keyboard
from app.bot.handlers.common import MISSING_ACTIVE_CHAT_TEXT, restore_last_active_chat_id
from app.db.connection import async_session_maker
from app.db.repos.setup_tokens_repo import SetupTokenRepo
from app.db.repos.settings_repo import SettingsRepo

router = Router()


def _parse_setup_token(arg: str | None) -> str | None:
    if not arg:
        return None
    if arg.startswith("setup_"):
        return arg[len("setup_") :]
    return None



async def _send_active_chat_menu(message: Message, chat_id: int) -> None:
    chat_title = None
    try:
        chat = await message.bot.get_chat(chat_id)
        chat_title = chat.title or chat.full_name
    except Exception:
        pass

    title_text = chat_title or str(chat_id)
    await message.answer(
        "Чат выбран: "
        f"{title_text}\n"
        "Меню настроек ниже.",
        reply_markup=admin_menu_keyboard(),
    )

@router.message(CommandStart(), F.chat.type == "private")
async def start_private(message: Message, state: FSMContext) -> None:
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Received /start command from user {message.from_user.id if message.from_user else 'unknown'}")
    
    text = message.text or ""
    parts = text.split(maxsplit=1)
    payload = parts[1].strip() if len(parts) > 1 else None
    setup_token = _parse_setup_token(payload)

    if not setup_token:
        logger.info("No setup token provided, trying last active chat")
        restored_chat_id = await restore_last_active_chat_id(state, message)
        if restored_chat_id:
            await _send_active_chat_menu(message, restored_chat_id)
            return
        await message.answer(MISSING_ACTIVE_CHAT_TEXT)
        return

    user = message.from_user
    if not user:
        await message.answer("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0438\u0442\u044c \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f.")
        return

    async with async_session_maker() as session:
        token_repo = SetupTokenRepo(session)
        token_row = await token_repo.get_token(setup_token)

    if not token_row:
        await message.answer(
            "\u0421\u0441\u044b\u043b\u043a\u0430 \u043d\u0435\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0442\u0435\u043b\u044c\u043d\u0430 \u0438\u043b\u0438 \u0443\u0441\u0442\u0430\u0440\u0435\u043b\u0430. "
            "\u041f\u0435\u0440\u0435\u0439\u0434\u0438\u0442\u0435 \u0432 \u043d\u0443\u0436\u043d\u044b\u0439 \u0447\u0430\u0442, \u0432\u044b\u0437\u043e\u0432\u0438\u0442\u0435 /settings \u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u043a\u043d\u043e\u043f\u043a\u0443."
        )
        return

    if token_row.used_at:
        await message.answer(
            "\u0421\u0441\u044b\u043b\u043a\u0430 \u0443\u0436\u0435 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0430. "
            "\u041f\u0435\u0440\u0435\u0439\u0434\u0438\u0442\u0435 \u0432 \u043d\u0443\u0436\u043d\u044b\u0439 \u0447\u0430\u0442, \u0432\u044b\u0437\u043e\u0432\u0438\u0442\u0435 /settings \u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u043a\u043d\u043e\u043f\u043a\u0443."
        )
        return

    expires_at = None
    try:
        expires_at = datetime.fromisoformat(token_row.expires_at)
    except ValueError:
        expires_at = None

    if expires_at and expires_at < datetime.utcnow():
        await message.answer(
            "\u0421\u0441\u044b\u043b\u043a\u0430 \u0443\u0436\u0435 \u0443\u0441\u0442\u0430\u0440\u0435\u043b\u0430. "
            "\u041f\u0435\u0440\u0435\u0439\u0434\u0438\u0442\u0435 \u0432 \u043d\u0443\u0436\u043d\u044b\u0439 \u0447\u0430\u0442, \u0432\u044b\u0437\u043e\u0432\u0438\u0442\u0435 /settings \u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u043a\u043d\u043e\u043f\u043a\u0443."
        )
        return

    chat_id = token_row.chat_id
    if not await is_user_chat_member(message.bot, chat_id, user.id):
        await message.answer(
            "\u0412\u044b \u043d\u0435 \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a \u044d\u0442\u043e\u0433\u043e \u0447\u0430\u0442\u0430, \u043f\u043e\u0442\u043e\u043c\u0443 \u043d\u0435 \u043c\u043e\u0436\u0435\u0442\u0435 \u043d\u0430\u0441\u0442\u0440\u0430\u0438\u0432\u0430\u0442\u044c \u0435\u0433\u043e."
        )
        return

    async with async_session_maker() as session:
        token_repo = SetupTokenRepo(session)
        repo = SettingsRepo(session)
        _ = await repo.ensure_settings(chat_id)
        await token_repo.mark_used(setup_token, user.id)
        await session.commit()

    await state.update_data(active_chat_id=chat_id)

    await _send_active_chat_menu(message, chat_id)


@router.message(F.chat.type == "private", F.text)
async def private_fallback(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text.startswith("/"):
        return
    data = await state.get_data()
    if data.get("active_chat_id"):
        return
    await message.answer(MISSING_ACTIVE_CHAT_TEXT)
