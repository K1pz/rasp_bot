from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.chat_access import is_user_chat_member
from app.db.connection import async_session_maker
from app.db.repos.setup_tokens_repo import SetupTokenRepo

MISSING_ACTIVE_CHAT_TEXT = (
    "Для настройки зайдите в нужную группу и отправьте /setup (или /settings).\n"
    "Затем откройте личку с ботом по ссылке из группы."
)


async def restore_last_active_chat_id(state: FSMContext, message: Message) -> int | None:
    user = message.from_user
    if not user:
        return None

    async with async_session_maker() as session:
        token_repo = SetupTokenRepo(session)
        chat_id = await token_repo.get_last_used_chat_id(user.id)

    if not chat_id:
        return None

    if not await is_user_chat_member(message.bot, chat_id, user.id):
        return None

    await state.update_data(active_chat_id=chat_id)
    return chat_id


async def get_active_chat_id(state: FSMContext, message: Message) -> int | None:
    user = message.from_user
    if not user:
        await message.answer(
            "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0438\u0442\u044c \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f."
        )
        return None
    data = await state.get_data()
    chat_id = data.get("active_chat_id")
    if not chat_id:
        chat_id = await restore_last_active_chat_id(state, message)
        if not chat_id:
            await message.answer(MISSING_ACTIVE_CHAT_TEXT)
            return None
        return chat_id
    if not await is_user_chat_member(message.bot, chat_id, user.id):
        await message.answer(
            "\u0412\u044b \u043d\u0435 \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a \u044d\u0442\u043e\u0433\u043e \u0447\u0430\u0442\u0430, \u043f\u043e\u0442\u043e\u043c\u0443 \u043d\u0435 \u043c\u043e\u0436\u0435\u0442\u0435 \u043d\u0430\u0441\u0442\u0440\u0430\u0438\u0432\u0430\u0442\u044c \u0435\u0433\u043e."
        )
        return None
    return chat_id
