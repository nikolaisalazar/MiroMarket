"""
Route-level tests for /api/v1/markets.

These tests verify HTTP status codes, response shapes, and error translation.
The service layer is mocked so these tests never touch the DB or Kalshi —
they only check that the route correctly:
  - Passes query params to the service
  - Serializes IngestionResult to JSON
  - Converts KalshiAPIError subtypes to appropriate HTTP error codes

We use FastAPI's TestClient (sync wrapper around the async app) which is
the simplest approach for route testing.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.market import IngestionResult
from app.services.ingestion.kalshi_client import (
    KalshiAuthError,
    KalshiRateLimitError,
    KalshiServerError,
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """
    TestClient wraps the async FastAPI app in a sync interface.
    The context manager handles lifespan (DB create_all on startup).
    """
    with TestClient(app) as c:
        yield c


def make_result(**overrides) -> IngestionResult:
    base = dict(
        fetched=10,
        ingested=10,
        errors=0,
        duration_ms=250,
        timestamp=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return IngestionResult(**base)


# ---------------------------------------------------------------------------
# POST /ingest — happy path
# ---------------------------------------------------------------------------

def test_ingest_returns_200_with_result(client):
    mock = AsyncMock(return_value=make_result())
    with patch("app.api.routes.markets.ingest_markets", mock):
        resp = client.post("/api/v1/markets/ingest")

    assert resp.status_code == 200
    body = resp.json()
    assert body["fetched"]   == 10
    assert body["ingested"]  == 10
    assert body["errors"]    == 0
    assert "duration_ms" in body
    assert "timestamp"   in body


def test_ingest_passes_limit_param(client):
    mock = AsyncMock(return_value=make_result(fetched=50, ingested=50))
    with patch("app.api.routes.markets.ingest_markets", mock) as m:
        client.post("/api/v1/markets/ingest?limit=50")

    _, kwargs = m.call_args
    assert kwargs["limit"] == 50


def test_ingest_passes_category_param(client):
    mock = AsyncMock(return_value=make_result())
    with patch("app.api.routes.markets.ingest_markets", mock) as m:
        client.post("/api/v1/markets/ingest?category=economics")

    _, kwargs = m.call_args
    assert kwargs["category"] == "economics"


def test_ingest_passes_status_param(client):
    mock = AsyncMock(return_value=make_result())
    with patch("app.api.routes.markets.ingest_markets", mock) as m:
        client.post("/api/v1/markets/ingest?status=closed")

    _, kwargs = m.call_args
    assert kwargs["status"] == "closed"


def test_ingest_limit_exceeding_max_is_rejected(client):
    # limit le=500, so 501 should be a 422 Unprocessable Entity
    resp = client.post("/api/v1/markets/ingest?limit=501")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /ingest — error translation
# ---------------------------------------------------------------------------

def test_auth_error_returns_502(client):
    mock = AsyncMock(side_effect=KalshiAuthError(401, "bad key"))
    with patch("app.api.routes.markets.ingest_markets", mock):
        resp = client.post("/api/v1/markets/ingest")

    assert resp.status_code == 502
    assert "KALSHI_API_KEY" in resp.json()["detail"]


def test_rate_limit_error_returns_502(client):
    mock = AsyncMock(side_effect=KalshiRateLimitError(429, "slow down"))
    with patch("app.api.routes.markets.ingest_markets", mock):
        resp = client.post("/api/v1/markets/ingest")

    assert resp.status_code == 502
    assert "rate limit" in resp.json()["detail"].lower()


def test_generic_kalshi_error_returns_502(client):
    mock = AsyncMock(side_effect=KalshiServerError(503, "service unavailable"))
    with patch("app.api.routes.markets.ingest_markets", mock):
        resp = client.post("/api/v1/markets/ingest")

    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# POST /{ticker}/ingest — single market
# ---------------------------------------------------------------------------

def test_single_ingest_returns_market_detail(client):
    from app.models.market import Market, MarketStatus, MarketSource
    import uuid
    from decimal import Decimal

    fake_market = Market(
        id=uuid.uuid4(),
        external_id="FED-RATE-JULY26",
        source=MarketSource.kalshi,
        title="Will the Fed cut rates before July 2026?",
        status=MarketStatus.open,
        current_yes_price=Decimal("0.34"),
        current_no_price=Decimal("0.66"),
        fetched_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    mock = AsyncMock(return_value=fake_market)
    with patch("app.api.routes.markets.ingest_single_market", mock):
        resp = client.post("/api/v1/markets/FED-RATE-JULY26/ingest")

    assert resp.status_code == 200
    body = resp.json()
    assert body["external_id"] == "FED-RATE-JULY26"


def test_single_ingest_404_for_unknown_ticker(client):
    from app.services.ingestion.kalshi_client import KalshiNotFoundError
    mock = AsyncMock(side_effect=KalshiNotFoundError(404, "not found"))
    with patch("app.api.routes.markets.ingest_single_market", mock):
        resp = client.post("/api/v1/markets/DOES-NOT-EXIST/ingest")

    assert resp.status_code == 404
