from aiogram import Bot


async def is_user_chat_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False

    status = getattr(member, "status", None)
    if status in ("left", "kicked"):
        return False
    if getattr(member, "is_member", True) is False:
        return False
    return True


async def is_user_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False

    status = getattr(member, "status", None)
    return status in ("administrator", "creator")
