from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# The engine manages the connection pool to your database.
# pool_pre_ping=True checks that connections are alive before using them —
# important for Supabase which may close idle connections.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,         # Set to True to log all SQL queries (useful for debugging)
    pool_pre_ping=True,
)

# Session factory — call AsyncSessionLocal() to get a database session.
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models. Import this in each model file."""
    pass


async def get_db():
    """
    FastAPI dependency that yields a database session per request.
    Usage in a route: db: AsyncSession = Depends(get_db)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
