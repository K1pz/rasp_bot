from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from app.bot.handlers.common import get_active_chat_id as _get_active_chat_id


router = Router()

# Button texts reused across handlers so they react both to slash-commands
# and to the readable keyboard labels from the README.
BTN_STATUS = "📊 Статус"
BTN_SETTINGS = "⚙️ Настройки"
BTN_UPLOAD = "🔄 Обновить расписание"
BTN_PREVIEW = "👁️ Превью"
BTN_TEST = "🧪 Тест"


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_UPLOAD), KeyboardButton(text=BTN_SETTINGS)],
            [KeyboardButton(text=BTN_STATUS), KeyboardButton(text=BTN_PREVIEW)],
            [KeyboardButton(text=BTN_TEST)],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


@router.message(Command("admin", "menu"), F.chat.type == "private")
async def admin_menu(message: Message, state: FSMContext) -> None:
    chat_id = await _get_active_chat_id(state, message)
    if not chat_id:
        return
    await message.answer(
        "Меню настроек. Выберите действие:",
        reply_markup=admin_menu_keyboard(),
    )
