import pytest
from sqlalchemy import select

from app.db.models import ScheduleItem, Settings, Upload
from app.db.repos.schedule_repo import ScheduleRepo


@pytest.mark.asyncio
async def test_upsert_ical_range_deletes_legacy_rows_with_null_ical_keys(session):
    chat_id = -1001
    session.add(
        Settings(
            chat_id=chat_id,
            mode=0,
            timezone="UTC",
            ical_enabled=True,
            updated_at="2025-01-01T00:00:00",
        )
    )
    await session.commit()

    upload = Upload(chat_id=chat_id, filename="ical", uploaded_at="2025-01-01T00:00:00")
    session.add(upload)
    await session.flush()

    # Simulate legacy Excel/manual import rows that predate iCal support.
    session.add(
        ScheduleItem(
            chat_id=chat_id,
            date="2025-01-01",
            start_time="10:00",
            end_time="11:00",
            subject="OLD",
            ical_uid=None,
            ical_dtstart=None,
        )
    )
    await session.commit()

    repo = ScheduleRepo(session)
    await repo.upsert_ical_range(
        chat_id=chat_id,
        date_from="2025-01-01",
        date_to="2025-01-01",
        items=[
            ScheduleItem(
                date="2025-01-01",
                start_time="10:00",
                end_time="11:00",
                subject="NEW",
                ical_uid="uid-1",
                ical_dtstart="2025-01-01T10:00:00+00:00",
            )
        ],
        upload_id=upload.id,
    )
    await session.commit()

    result = await session.execute(
        select(ScheduleItem).where(ScheduleItem.chat_id == chat_id, ScheduleItem.date == "2025-01-01")
    )
    rows = list(result.scalars().all())
    assert len(rows) == 1
    assert rows[0].ical_uid == "uid-1"
    assert rows[0].subject == "NEW"
