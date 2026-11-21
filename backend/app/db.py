from contextlib import asynccontextmanager

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import settings

engine = create_async_engine(
    settings.database_url, pool_pre_ping=True, connect_args={"timeout": 4}
)
sessions = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def transaction():
    async with sessions.begin() as session:
        yield session


async def database_time(session):
    return await session.scalar(select(func.clock_timestamp()))
