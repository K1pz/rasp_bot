import pytest
from sqlalchemy import select

from app.db.models import SendLog
from app.db.repos.sendlog_repo import SendLogRepo


@pytest.mark.asyncio
async def test_retry_after_send_error_allows_reserve(session):
    repo = SendLogRepo(session)
    chat_id = 42
    target_date = "2025-02-01"
    kind = "morning"

    first = await repo.try_reserve(chat_id, target_date, kind)
    assert first is True

    await repo.mark_error(chat_id, target_date, kind, "boom")
    await session.commit()

    retry = await repo.try_reserve(chat_id, target_date, kind)
    assert retry is True

    result = await session.execute(
        select(SendLog).where(
            SendLog.chat_id == chat_id,
            SendLog.target_date == target_date,
            SendLog.kind == kind,
        )
    )
    log_entry = result.scalar_one()
    assert log_entry.status == "reserved"
    assert log_entry.error is None
