from aiogram.fsm.state import State, StatesGroup


class SettingsStates(StatesGroup):
    mode = State()
    morning_time = State()
    evening_time = State()
    timezone = State()
    ical_url = State()
