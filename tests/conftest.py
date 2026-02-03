import os
import pytest
import pytest_asyncio
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from app.db.models import Base

# Make sure importing app.config doesn't fail during test collection.
os.environ.setdefault("BOT_TOKEN", "TEST_TOKEN")

# Use in-memory SQLite for tests
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# Redefine event_loop is often not needed in newer pytest-asyncio, 
# but if we want session scope for engine, we need loop_scope="session" via configuration or arguments.
# Since pytest-asyncio 0.23+, loop handling changed. 

# Let's try simple per-function fixtures first if session scope is tricky without config, 
# or use loop_scope='session' in the fixture decorator if supported.
# However, to be safe and simple:

@pytest_asyncio.fixture(loop_scope="session")
async def engine():
    # Use StaticPool to persist state in memory across connections
    engine = create_async_engine(
        TEST_DB_URL, 
        connect_args={"check_same_thread": False}, 
        poolclass=StaticPool
    )
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    yield engine
    
    await engine.dispose()

@pytest_asyncio.fixture(loop_scope="function")
async def session(engine):
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()
