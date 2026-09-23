import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://nashr:nashr@localhost:5432/nashr")
engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an asynchronous database session."""
    async with SessionFactory() as session:
        yield session
