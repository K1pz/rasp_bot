from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.db.models import Upload

class UploadsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert_upload(self, **kwargs) -> int:
        upload = Upload(**kwargs)
        self.session.add(upload)
        await self.session.flush() # flush to generate ID
        return upload.id

    async def get_last_upload(self, chat_id: int) -> Upload | None:
        stmt = (
            select(Upload)
            .where(Upload.chat_id == chat_id)
            .order_by(desc(Upload.id))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
