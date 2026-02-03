import secrets
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SetupToken


class SetupTokenRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_token(self, chat_id: int, created_by: int | None, ttl_minutes: int) -> str:
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=ttl_minutes)

        for _ in range(5):
            token = secrets.token_urlsafe(16)
            exists = await self.get_token(token)
            if exists is None:
                self.session.add(
                    SetupToken(
                        token=token,
                        chat_id=chat_id,
                        created_by=created_by,
                        created_at=now.isoformat(),
                        expires_at=expires_at.isoformat(),
                    )
                )
                return token

        token = secrets.token_urlsafe(16)
        self.session.add(
            SetupToken(
                token=token,
                chat_id=chat_id,
                created_by=created_by,
                created_at=now.isoformat(),
                expires_at=expires_at.isoformat(),
            )
        )
        return token

    async def get_token(self, token: str) -> SetupToken | None:
        stmt = select(SetupToken).where(SetupToken.token == token)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_used(self, token: str, used_by: int | None) -> None:
        stmt = (
            update(SetupToken)
            .where(SetupToken.token == token)
            .values(used_at=datetime.utcnow().isoformat(), used_by=used_by)
        )
        await self.session.execute(stmt)

    async def get_last_used_chat_id(self, user_id: int) -> int | None:
        stmt = (
            select(SetupToken.chat_id)
            .where(SetupToken.used_by == user_id, SetupToken.used_at.is_not(None))
            .order_by(SetupToken.used_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def is_chat_setup_token_creator(self, chat_id: int, user_id: int) -> bool:
        stmt = (
            select(SetupToken.id)
            .where(SetupToken.chat_id == chat_id, SetupToken.created_by == user_id)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
