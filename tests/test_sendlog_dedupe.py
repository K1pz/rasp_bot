import pytest
from app.db.repos.sendlog_repo import SendLogRepo
from app.db.models import SendLog
from sqlalchemy import select

@pytest.mark.asyncio
async def test_try_reserve_dedupe(session):
    repo = SendLogRepo(session)
    chat_id = 123456
    target_date = "2023-10-10"
    kind = "morning"
    
    # 1. First reservation should succeed
    success = await repo.try_reserve(chat_id, target_date, kind)
    assert success is True
    
    # Verify it's in DB with status='reserved'
    result = await session.execute(
        select(SendLog).where(
            SendLog.chat_id == chat_id,
            SendLog.target_date == target_date,
            SendLog.kind == kind
        )
    )
    log_entry = result.scalar_one_or_none()
    assert log_entry is not None
    assert log_entry.status == "reserved"
    assert log_entry.reserved_at is not None
    
    # 2. Second reservation for SAME key should fail (return False)
    success_retry = await repo.try_reserve(chat_id, target_date, kind)
    assert success_retry is False
    
    # 3. Reservation for DIFFERENT kind should succeed
    success_diff = await repo.try_reserve(chat_id, target_date, "evening")
    assert success_diff is True

@pytest.mark.asyncio
async def test_mark_sent(session):
    repo = SendLogRepo(session)
    chat_id = 999
    target_date = "2025-01-01"
    kind = "test"
    
    # Reserve first
    await repo.try_reserve(chat_id, target_date, kind)
    
    # Mark as sent
    sent_time = "2026-01-22T10:00:00"
    await repo.mark_sent(chat_id, target_date, kind, sent_time)
    
    # Verify update
    result = await session.execute(
        select(SendLog).where(
            SendLog.chat_id == chat_id,
            SendLog.target_date == target_date,
            SendLog.kind == kind
        )
    )
    log_entry = result.scalar_one_or_none()
    assert log_entry.status == "ok"
    assert log_entry.sent_at == sent_time

@pytest.mark.asyncio
async def test_find_stuck_reserved(session):
    repo = SendLogRepo(session)
    # Manual insert needed to force old timestamp?
    # Or just use repo and mock datetime?
    # SendLogRepo uses datetime.now() inside try_reserve.
    # But find_stuck_reserved compares current time - minutes.
    # Can we just insert manually via session to control reserved_at?
    
    from datetime import datetime, timedelta
    
    # Insert an "old" reserved entry
    old_time = (datetime.now() - timedelta(minutes=60)).isoformat()
    old_entry = SendLog(
        chat_id=1,
        target_date="2000-01-01",
        kind="old",
        reserved_at=old_time,
        status="reserved"
    )
    session.add(old_entry)
    
    # Insert a "fresh" reserved entry
    fresh_time = datetime.now().isoformat()
    fresh_entry = SendLog(
        chat_id=2,
        target_date="2000-01-01",
        kind="fresh",
        reserved_at=fresh_time,
        status="reserved"
    )
    session.add(fresh_entry)
    await session.commit()
    
    # Check
    stuck_list = await repo.find_stuck_reserved(older_than_minutes=30)
    
    # Should find chat_id=1, but not chat_id=2
    ids = [x.chat_id for x in stuck_list]
    assert 1 in ids
    assert 2 not in ids
