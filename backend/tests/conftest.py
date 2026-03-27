"""
Shared pytest fixtures for the MiroMarket test suite.

DB strategy: each test that touches the database gets a fresh in-memory
SQLite instance so tests are fully isolated and never require a running
Postgres.

SQLite compatibility notes:
  Other models in this project use PostgreSQL-specific types (JSONB, ARRAY)
  that SQLite cannot compile. Rather than patching every type, the `db`
  fixture creates only the tables needed for the tests in question. Tests
  that need additional tables should extend the fixture locally.

  JSONB on Market.raw_metadata is handled by patching the SQLite DDL
  compiler once at import time — it falls back to plain JSON storage which
  is correct for tests.
"""
import pytest
from sqlalchemy.dialects.sqlite import base as _sqlite_base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Teach SQLite's DDL compiler to treat PostgreSQL JSONB as plain JSON.
# This only affects the test process — production continues to use native JSONB.
if not hasattr(_sqlite_base.SQLiteTypeCompiler, "visit_JSONB"):
    _sqlite_base.SQLiteTypeCompiler.visit_JSONB = (  # type: ignore[attr-defined]
        _sqlite_base.SQLiteTypeCompiler.visit_JSON
    )

# Import the models we need so SQLAlchemy registers their tables on Base.metadata.
# Other models (persona, simulation, report) use ARRAY which SQLite can't compile,
# so we deliberately do NOT import them here — the `db` fixture only creates the
# subset of tables needed for each test module.
from app.models.market import Market, MarketPriceHistory  # noqa: E402


_INGESTION_TABLES = [Market.__table__, MarketPriceHistory.__table__]


@pytest.fixture
async def db() -> AsyncSession:
    """
    Yields an AsyncSession backed by a fresh in-memory SQLite database
    containing only the Market and MarketPriceHistory tables.

    Each test gets a completely isolated database — no shared state.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Market.metadata.create_all,
            tables=_INGESTION_TABLES,
        )

    TestSession = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with TestSession() as session:
        yield session

    await engine.dispose()
