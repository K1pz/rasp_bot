from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.db.models import SendLog
from datetime import datetime, timedelta

STATUS_RESERVED = "reserved"
STATUS_OK = "ok"
STATUS_ERROR = "error"
# Legacy compatibility: older versions used "sent" for successful delivery.
STATUS_SENT_LEGACY = "sent"
SUCCESS_STATUSES = (STATUS_OK, STATUS_SENT_LEGACY)


def is_send_success(status: str | None) -> bool:
    return status in SUCCESS_STATUSES


class SendLogRepo:
    def __init__(self, session: AsyncSession):
        self.session = session
        
    async def try_reserve(
        self,
        chat_id: int,
        target_date: str,
        kind: str,
        older_than_minutes: int = 15,
    ) -> bool:
        """
        Attempts to reserve a sending task.
        Allows re-reservation if status is "error" or "reserved" is stale.
        """
        now = datetime.now().isoformat()
        stuck_before = (datetime.now() - timedelta(minutes=older_than_minutes)).isoformat()

        stmt = sqlite_insert(SendLog).values(
            chat_id=chat_id,
            target_date=target_date,
            kind=kind,
            reserved_at=now,
            status=STATUS_RESERVED,
        ).on_conflict_do_update(
            index_elements=["chat_id", "target_date", "kind"],
            set_={
                "reserved_at": now,
                "status": STATUS_RESERVED,
                "error": None,
                "sent_at": None,
            },
            where=(
                (SendLog.status == STATUS_ERROR)
                | ((SendLog.status == STATUS_RESERVED) & (SendLog.reserved_at < stuck_before))
            )
        )

        result = await self.session.execute(stmt)
        return result.rowcount > 0
    
    async def mark_sent(self, chat_id: int, target_date: str, kind: str, sent_at: str):
        stmt = update(SendLog).where(
            SendLog.chat_id == chat_id,
            SendLog.target_date == target_date,
            SendLog.kind == kind
        ).values(status=STATUS_OK, sent_at=sent_at)
        await self.session.execute(stmt)

    async def mark_error(self, chat_id: int, target_date: str, kind: str, error: str):
        stmt = update(SendLog).where(
            SendLog.chat_id == chat_id,
            SendLog.target_date == target_date,
            SendLog.kind == kind
        ).values(status=STATUS_ERROR, error=error, sent_at=None)
        await self.session.execute(stmt)
        
    async def get_last_sent(self, kind: str) -> SendLog | None:
        """Get the most recent successfully delivered log entry for a given kind."""
        stmt = select(SendLog).where(
            SendLog.kind == kind, 
            SendLog.status.in_(SUCCESS_STATUSES),
        ).order_by(desc(SendLog.target_date)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_log(self, chat_id: int, target_date: str, kind: str) -> SendLog | None:
        stmt = select(SendLog).where(
            SendLog.chat_id == chat_id,
            SendLog.target_date == target_date,
            SendLog.kind == kind,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_stuck_reserved(self, older_than_minutes: int) -> list[SendLog]:
        """Find logs that are stuck in 'reserved' state for longer than N minutes."""
        limit_time = (datetime.now() - timedelta(minutes=older_than_minutes)).isoformat()
        
        stmt = select(SendLog).where(
            SendLog.status == STATUS_RESERVED,
            SendLog.reserved_at < limit_time
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
