from types import SimpleNamespace

from app.bot.middlewares import _is_group_command


def _msg(text: str | None):
    return SimpleNamespace(text=text, caption=None)


def test_is_group_command_allows_week_brief_commands():
    assert _is_group_command(_msg("/weekbrief"))
    assert _is_group_command(_msg("/week_short"))
    assert _is_group_command(_msg("/nextweekbrief"))
    assert _is_group_command(_msg("/nextweek_short"))


def test_is_group_command_strips_bot_mention_and_args():
    assert _is_group_command(_msg("/weekbrief@some_bot"))
    assert _is_group_command(_msg("/weekbrief@some_bot arg1 arg2"))


def test_is_group_command_rejects_non_commands():
    assert not _is_group_command(_msg(None))
    assert not _is_group_command(_msg(""))
    assert not _is_group_command(_msg("hello"))

