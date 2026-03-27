"""
Shared pytest fixtures for the MiroMarket test suite.

DB strategy: each test that touches the database gets a fresh in-memory
SQLite instance so tests are fully isolated and never require a running
Postgres.

SQLite compatibility notes:
  PostgreSQL-specific types (JSONB, ARRAY, UUID) cannot be compiled by
  SQLite directly. This module patches the SQLite DDL compiler once at
  import time to handle all three:

    JSONB  → plain JSON storage (value semantics identical for tests)
    ARRAY  → JSON storage (bind/result processors also patched to
              serialize/deserialize Python lists as JSON strings)
    UUID   → VARCHAR(36) storage (PostgreSQL UUID bind/result processors
              already handle str conversion correctly for non-PG dialects)

  These patches only affect the test process — production continues to
  use native PostgreSQL types via asyncpg.

  The `db` fixture creates only the Market and MarketPriceHistory tables.
  Tests that need additional tables (e.g. simulation tests) use the
  fixtures defined in their own conftest.py.
"""
import json

import pytest
from sqlalchemy.dialects.postgresql import ARRAY as PGARRAY
from sqlalchemy.dialects.sqlite import base as _sqlite_base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# SQLite DDL patches
# ---------------------------------------------------------------------------

# JSONB → JSON
if not hasattr(_sqlite_base.SQLiteTypeCompiler, "visit_JSONB"):
    _sqlite_base.SQLiteTypeCompiler.visit_JSONB = (  # type: ignore[attr-defined]
        _sqlite_base.SQLiteTypeCompiler.visit_JSON
    )

# ARRAY → JSON  (DDL only; value processors patched below)
if not hasattr(_sqlite_base.SQLiteTypeCompiler, "visit_ARRAY"):
    def _visit_array(self, type_, **kw):  # type: ignore[misc]
        return "JSON"
    _sqlite_base.SQLiteTypeCompiler.visit_ARRAY = _visit_array  # type: ignore[attr-defined]

# UUID → VARCHAR(36)
if not hasattr(_sqlite_base.SQLiteTypeCompiler, "visit_UUID"):
    def _visit_uuid(self, type_, **kw):  # type: ignore[misc]
        return "VARCHAR(36)"
    _sqlite_base.SQLiteTypeCompiler.visit_UUID = _visit_uuid  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# PostgreSQL ARRAY value processors for non-PostgreSQL dialects
#
# PostgreSQL's ARRAY type delegates serialization to the psycopg2 driver,
# so its bind/result processors return None for the PG dialect. aiosqlite
# cannot handle raw Python lists, so we intercept for SQLite and route
# through JSON instead.
# ---------------------------------------------------------------------------

_orig_array_bind = PGARRAY.bind_processor
_orig_array_result = PGARRAY.result_processor


def _array_bind_processor(self, dialect):  # type: ignore[misc]
    if dialect.name == "postgresql":
        return _orig_array_bind(self, dialect)

    def process(value):
        if value is None:
            return None
        return json.dumps(value)

    return process


def _array_result_processor(self, dialect, coltype):  # type: ignore[misc]
    if dialect.name == "postgresql":
        return _orig_array_result(self, dialect, coltype)

    def process(value):
        if value is None:
            return None
        if isinstance(value, list):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value

    return process


PGARRAY.bind_processor = _array_bind_processor  # type: ignore[method-assign]
PGARRAY.result_processor = _array_result_processor  # type: ignore[method-assign]

# ---------------------------------------------------------------------------
# Model imports
# ---------------------------------------------------------------------------

# Import the models we need so SQLAlchemy registers their tables on Base.metadata.
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
