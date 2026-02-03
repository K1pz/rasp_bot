from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import pytest

from app.db.models import Base
from app.db.repos.settings_repo import SettingsRepo


@pytest.mark.asyncio
async def test_settings_persist_across_process_restart(tmp_path) -> None:
    """
    Regression: file-based SQLite DB must preserve settings between restarts.

    This mimics "update image + restart container" where the same DB file is reused.
    """
    chat_id = 424242
    db_file = tmp_path / "bot.db"
    db_url = f"sqlite+aiosqlite:///{db_file.resolve().as_posix()}"

    engine1 = create_async_engine(db_url, echo=False)
    try:
        async with engine1.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_maker1 = async_sessionmaker(engine1, class_=AsyncSession, expire_on_commit=False)
        async with session_maker1() as session:
            repo = SettingsRepo(session)
            await repo.upsert_settings(
                chat_id=chat_id,
                chat_title="Test Chat",
                mode=2,
                morning_time="07:15",
                evening_time="19:30",
                timezone="UTC",
                ical_url="https://example.com/test.ics",
                ical_enabled=True,
                updated_at="2026-02-03T00:00:00",
            )
            await session.commit()
    finally:
        await engine1.dispose()

    assert db_file.exists()
    assert db_file.stat().st_size > 0

    engine2 = create_async_engine(db_url, echo=False)
    try:
        session_maker2 = async_sessionmaker(engine2, class_=AsyncSession, expire_on_commit=False)
        async with session_maker2() as session:
            repo = SettingsRepo(session)
            row = await repo.get_settings(chat_id)
            assert row is not None
            assert row.chat_title == "Test Chat"
            assert row.mode == 2
            assert row.morning_time == "07:15"
            assert row.evening_time == "19:30"
            assert row.timezone == "UTC"
            assert row.ical_url == "https://example.com/test.ics"
            assert row.ical_enabled is True
            assert row.updated_at == "2026-02-03T00:00:00"

            all_rows = await repo.get_all_settings()
            assert [s.chat_id for s in all_rows] == [chat_id]
    finally:
        await engine2.dispose()

