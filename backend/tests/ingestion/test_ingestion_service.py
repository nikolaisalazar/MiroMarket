"""
Integration tests for ingestion_service.

These tests exercise the full service layer — normalization, DB upsert, and
price history — using a real in-memory SQLite database and mocked HTTP.
This catches bugs that pure unit tests miss, such as wrong column names,
missing flush() calls, or broken relationships.

Fixtures:
  db  — in-memory SQLite AsyncSession (see conftest.py)
  httpx_mock — from pytest-httpx, intercepts all httpx calls
"""
from datetime import timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.market import Market, MarketPriceHistory, MarketStatus
from app.services.ingestion.ingestion_service import ingest_markets, ingest_single_market
from app.services.ingestion.kalshi_client import KalshiAuthError, KalshiRateLimitError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_raw(ticker: str = "FED-RATE-JULY26", **overrides) -> dict:
    base = {
        "ticker":        ticker,
        "title":         "Will the Fed cut rates before July 2026?",
        "subtitle":      "Fed rate decision",
        "category":      "economics",
        "close_time":    "2026-07-01T00:00:00Z",
        "yes_ask":       36,
        "yes_bid":       32,
        "no_ask":        68,
        "no_bid":        64,
        "volume_24h":    15_000,
        "open_interest": 42_000,
        "status":        "open",
    }
    base.update(overrides)
    return base


def mock_client(markets: list[dict]):
    """Return an AsyncMock for kalshi_client.get_markets that yields `markets`."""
    m = AsyncMock(return_value=markets)
    return patch("app.services.ingestion.ingestion_service.kalshi_client.get_markets", m)


def mock_single_client(market: dict):
    """Return an AsyncMock for kalshi_client.get_market."""
    m = AsyncMock(return_value=market)
    return patch("app.services.ingestion.ingestion_service.kalshi_client.get_market", m)


# ---------------------------------------------------------------------------
# ingest_markets — happy path
# ---------------------------------------------------------------------------

async def test_ingest_markets_inserts_new_market(db):
    with mock_client([make_raw()]):
        result = await ingest_markets(db)

    assert result.fetched   == 1
    assert result.ingested  == 1
    assert result.errors    == 0
    assert result.duration_ms >= 0
    assert result.timestamp.tzinfo == timezone.utc

    row = (await db.execute(select(Market))).scalar_one()
    assert row.external_id    == "FED-RATE-JULY26"
    assert row.status         == MarketStatus.open
    assert float(row.current_yes_price) == pytest.approx(0.34)
    assert float(row.current_no_price)  == pytest.approx(0.66)
    assert row.category       == "economics"
    assert row.raw_metadata   is not None


async def test_ingest_markets_writes_price_history(db):
    with mock_client([make_raw()]):
        await ingest_markets(db)

    snapshots = (await db.execute(select(MarketPriceHistory))).scalars().all()
    assert len(snapshots) == 1
    snap = snapshots[0]
    assert float(snap.yes_price) == pytest.approx(0.34)
    assert snap.volume == 15_000
    assert snap.recorded_at is not None


async def test_ingest_markets_upserts_existing_market(db):
    """Running ingestion twice should update the row, not duplicate it."""
    with mock_client([make_raw(yes_ask=36, yes_bid=32)]):
        await ingest_markets(db)

    # Simulate a price move on the second ingestion
    with mock_client([make_raw(yes_ask=46, yes_bid=42)]):
        result = await ingest_markets(db)

    assert result.ingested == 1

    markets = (await db.execute(select(Market))).scalars().all()
    assert len(markets) == 1  # Still only one row

    # Price should reflect the second ingestion
    assert float(markets[0].current_yes_price) == pytest.approx(0.44)


async def test_ingest_markets_writes_snapshot_on_every_pass(db):
    """Each ingestion pass should add a new price history snapshot."""
    with mock_client([make_raw()]):
        await ingest_markets(db)
    with mock_client([make_raw(yes_ask=50, yes_bid=46)]):
        await ingest_markets(db)

    snapshots = (await db.execute(select(MarketPriceHistory))).scalars().all()
    assert len(snapshots) == 2


async def test_ingest_multiple_markets(db):
    markets = [make_raw(f"TICKER-{i}") for i in range(5)]
    with mock_client(markets):
        result = await ingest_markets(db)

    assert result.fetched  == 5
    assert result.ingested == 5
    assert result.errors   == 0

    rows = (await db.execute(select(Market))).scalars().all()
    assert len(rows) == 5


async def test_ingest_skips_bad_market_but_continues(db):
    """A market with a missing ticker should be counted as an error, not abort the batch."""
    markets = [
        make_raw("GOOD-MARKET"),
        {"title": "No ticker here"},   # will fail normalization (KeyError on 'ticker')
        make_raw("ALSO-GOOD"),
    ]
    with mock_client(markets):
        result = await ingest_markets(db)

    assert result.errors   == 1
    assert result.ingested == 2

    tickers = [
        r.external_id
        for r in (await db.execute(select(Market))).scalars().all()
    ]
    assert "GOOD-MARKET" in tickers
    assert "ALSO-GOOD"   in tickers


async def test_ingest_no_price_history_when_prices_missing(db):
    """If a market has no bid/ask, no price history row should be written."""
    with mock_client([make_raw(yes_ask=0, yes_bid=0, no_ask=0, no_bid=0)]):
        await ingest_markets(db)

    snapshots = (await db.execute(select(MarketPriceHistory))).scalars().all()
    assert len(snapshots) == 0


# ---------------------------------------------------------------------------
# ingest_markets — error propagation
# ---------------------------------------------------------------------------

async def test_auth_error_propagates(db):
    m = AsyncMock(side_effect=KalshiAuthError(401, "Unauthorized"))
    with patch("app.services.ingestion.ingestion_service.kalshi_client.get_markets", m):
        with pytest.raises(KalshiAuthError):
            await ingest_markets(db)


async def test_rate_limit_error_propagates(db):
    m = AsyncMock(side_effect=KalshiRateLimitError(429, "Too many requests"))
    with patch("app.services.ingestion.ingestion_service.kalshi_client.get_markets", m):
        with pytest.raises(KalshiRateLimitError):
            await ingest_markets(db)


# ---------------------------------------------------------------------------
# ingest_single_market
# ---------------------------------------------------------------------------

async def test_ingest_single_market_inserts_and_returns_orm(db):
    with mock_single_client(make_raw("SINGLE-TEST")):
        market = await ingest_single_market(db, "SINGLE-TEST")

    assert isinstance(market, Market)
    assert market.external_id == "SINGLE-TEST"
    assert market.id is not None


async def test_ingest_single_market_updates_on_second_call(db):
    with mock_single_client(make_raw("SINGLE-TEST", yes_ask=36, yes_bid=32)):
        await ingest_single_market(db, "SINGLE-TEST")

    with mock_single_client(make_raw("SINGLE-TEST", yes_ask=60, yes_bid=56)):
        market = await ingest_single_market(db, "SINGLE-TEST")

    assert float(market.current_yes_price) == pytest.approx(0.58)

    rows = (await db.execute(select(Market))).scalars().all()
    assert len(rows) == 1
