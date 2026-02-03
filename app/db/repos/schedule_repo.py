from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, tuple_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.db.models import ScheduleItem

class ScheduleRepo:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def replace_range(self, chat_id: int, date_from: str, date_to: str, items: list[ScheduleItem], upload_id: int):
        """
        Transactional replacement: delete items in range, then insert new items.
        Assumes session transaction is managed by caller or auto-commit behavior if not nested.
        For safety, this should be called within a transaction block.
        """
        # Delete existing items in the date range
        stmt = delete(ScheduleItem).where(
            ScheduleItem.chat_id == chat_id,
            ScheduleItem.date >= date_from, 
            ScheduleItem.date <= date_to
        )
        await self.session.execute(stmt)
        
        # Insert new items
        for item in items:
            item.chat_id = chat_id
            item.source_upload_id = upload_id
            self.session.add(item)

    async def upsert_ical_range(self, chat_id: int, date_from: str, date_to: str, items: list[ScheduleItem], upload_id: int):
        """
        Upserts iCal items by (ical_uid, ical_dtstart) and removes missing items in the date range.
        Cleans the entire interval regardless of import source so stale manual rows are cleared.
        """
        key_pairs = [
            (item.ical_uid, item.ical_dtstart)
            for item in items
            if item.ical_uid and item.ical_dtstart
        ]

        delete_stmt = delete(ScheduleItem).where(
            ScheduleItem.chat_id == chat_id,
            ScheduleItem.date >= date_from,
            ScheduleItem.date <= date_to,
        )
        if key_pairs:
            # NOTE: NULL semantics matter here.
            # Rows imported from Excel/manual sources typically have NULL ical_uid/ical_dtstart.
            # In SQL, `NOT (NULL, NULL) IN (...)` is NULL (unknown), so such rows would NOT be deleted
            # without an explicit NULL check. That leaves stale legacy rows mixed with iCal data.
            delete_stmt = delete_stmt.where(
                (ScheduleItem.ical_uid.is_(None))
                | (ScheduleItem.ical_dtstart.is_(None))
                | (~tuple_(ScheduleItem.ical_uid, ScheduleItem.ical_dtstart).in_(key_pairs))
            )
        await self.session.execute(delete_stmt)

        if not key_pairs:
            return

        rows = []
        for item in items:
            if not item.ical_uid or not item.ical_dtstart:
                continue
            rows.append(
                {
                    "chat_id": chat_id,
                    "date": item.date,
                    "start_time": item.start_time,
                    "end_time": item.end_time,
                    "room": item.room,
                    "subject": item.subject,
                    "teacher": item.teacher,
                    "ical_uid": item.ical_uid,
                    "ical_dtstart": item.ical_dtstart,
                    "source_upload_id": upload_id,
                }
            )

        if not rows:
            return

        stmt = sqlite_insert(ScheduleItem).values(rows).on_conflict_do_update(
            index_elements=["chat_id", "ical_uid", "ical_dtstart"],
            set_={
                "date": sqlite_insert(ScheduleItem).excluded.date,
                "start_time": sqlite_insert(ScheduleItem).excluded.start_time,
                "end_time": sqlite_insert(ScheduleItem).excluded.end_time,
                "room": sqlite_insert(ScheduleItem).excluded.room,
                "subject": sqlite_insert(ScheduleItem).excluded.subject,
                "teacher": sqlite_insert(ScheduleItem).excluded.teacher,
                "source_upload_id": sqlite_insert(ScheduleItem).excluded.source_upload_id,
            },
        )
        await self.session.execute(stmt)
            
    async def get_by_date(self, chat_id: int, date: str) -> list[ScheduleItem]:
        stmt = (
            select(ScheduleItem)
            .where(ScheduleItem.chat_id == chat_id, ScheduleItem.date == date)
            .order_by(ScheduleItem.start_time)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_date_range(self, chat_id: int, date_from: str, date_to: str) -> list[ScheduleItem]:
        stmt = (
            select(ScheduleItem)
            .where(
                ScheduleItem.chat_id == chat_id,
                ScheduleItem.date >= date_from,
                ScheduleItem.date <= date_to,
            )
            .order_by(ScheduleItem.date, ScheduleItem.start_time)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_coverage_minmax(self, chat_id: int):
        """Returns tuple (min_date, max_date) or (None, None)"""
        stmt = select(func.min(ScheduleItem.date), func.max(ScheduleItem.date)).where(
            ScheduleItem.chat_id == chat_id
        )
        result = await self.session.execute(stmt)
        return result.one_or_none()
