"""
Tests for KalshiClient (HTTP layer).

pytest-httpx intercepts all httpx calls so these tests never touch the
real Kalshi API — they verify that the client correctly:
  - Constructs request parameters
  - Handles cursor-based pagination
  - Returns raw market dicts untouched
  - Raises the right typed exception for each HTTP error code
"""
import pytest

from app.services.ingestion.kalshi_client import (
    KalshiAPIError,
    KalshiAuthError,
    KalshiNotFoundError,
    KalshiRateLimitError,
    KalshiServerError,
    KalshiClient,
)


KALSHI_BASE = "https://trading-api.kalshi.com/trade-api/v2"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_market(ticker: str = "TEST-MARKET") -> dict:
    return {
        "ticker":       ticker,
        "title":        f"Test market {ticker}",
        "status":       "open",
        "yes_ask":      55,
        "yes_bid":      45,
        "no_ask":       55,
        "no_bid":       45,
        "volume_24h":   1000,
        "open_interest":5000,
        "close_time":   "2026-12-31T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# get_markets — happy path
# ---------------------------------------------------------------------------

async def test_get_markets_returns_list(httpx_mock):
    httpx_mock.add_response(
        url=f"{KALSHI_BASE}/markets?limit=5&status=open",
        json={"markets": [make_market("A"), make_market("B")], "cursor": ""},
    )

    client = KalshiClient()
    markets = await client.get_markets(limit=5)

    assert len(markets) == 2
    assert markets[0]["ticker"] == "A"
    assert markets[1]["ticker"] == "B"


async def test_get_markets_paginates_using_cursor(httpx_mock):
    """Client should follow cursor until it gets enough markets or cursor is empty.

    We don't assert on specific URLs here because query-param ordering in URL
    strings is not guaranteed. The behaviour under test is: the client makes
    two HTTP requests (first page returns a cursor, second exhausts it) and
    the results are concatenated in order.
    """
    # First page — returns two markets + a cursor pointing to page 2
    httpx_mock.add_response(
        json={"markets": [make_market("A"), make_market("B")], "cursor": "page2token"},
    )
    # Second page — returns the final market with an empty cursor
    httpx_mock.add_response(
        json={"markets": [make_market("C")], "cursor": ""},
    )

    client = KalshiClient()
    markets = await client.get_markets(limit=3)

    assert len(markets) == 3
    assert [m["ticker"] for m in markets] == ["A", "B", "C"]


async def test_get_markets_stops_when_cursor_empty(httpx_mock):
    """If first page has fewer markets than limit but cursor is empty, stop."""
    httpx_mock.add_response(
        url=f"{KALSHI_BASE}/markets?limit=100&status=open",
        json={"markets": [make_market("ONLY")], "cursor": ""},
    )

    client = KalshiClient()
    markets = await client.get_markets(limit=100)
    assert len(markets) == 1


async def test_get_markets_respects_limit_cap(httpx_mock):
    """Limit should be silently capped at 1000."""
    httpx_mock.add_response(
        url=f"{KALSHI_BASE}/markets?limit=200&status=open",
        json={"markets": [], "cursor": ""},
    )
    client = KalshiClient()
    # Requesting 9999 should not crash — page_size caps at 200, total at 1000
    markets = await client.get_markets(limit=9999)
    assert markets == []


async def test_get_markets_passes_category_filter(httpx_mock):
    httpx_mock.add_response(
        url=f"{KALSHI_BASE}/markets?limit=10&status=open&category=economics",
        json={"markets": [make_market("ECON-1")], "cursor": ""},
    )
    client = KalshiClient()
    markets = await client.get_markets(limit=10, category="economics")
    assert markets[0]["ticker"] == "ECON-1"


# ---------------------------------------------------------------------------
# get_market — single market
# ---------------------------------------------------------------------------

async def test_get_market_returns_dict(httpx_mock):
    raw = make_market("FED-RATE-JULY26")
    httpx_mock.add_response(
        url=f"{KALSHI_BASE}/markets/FED-RATE-JULY26",
        json={"market": raw},
    )
    client = KalshiClient()
    result = await client.get_market("FED-RATE-JULY26")
    assert result["ticker"] == "FED-RATE-JULY26"


async def test_get_market_handles_unwrapped_response(httpx_mock):
    """Some Kalshi endpoints return the market dict directly, not nested."""
    raw = make_market("DIRECT-RESP")
    httpx_mock.add_response(
        url=f"{KALSHI_BASE}/markets/DIRECT-RESP",
        json=raw,
    )
    client = KalshiClient()
    result = await client.get_market("DIRECT-RESP")
    assert result["ticker"] == "DIRECT-RESP"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

async def test_401_raises_auth_error(httpx_mock):
    httpx_mock.add_response(
        url=f"{KALSHI_BASE}/markets?limit=100&status=open",
        status_code=401,
        json={"message": "Unauthorized"},
    )
    client = KalshiClient()
    with pytest.raises(KalshiAuthError) as exc_info:
        await client.get_markets()
    assert exc_info.value.status_code == 401


async def test_403_raises_auth_error(httpx_mock):
    httpx_mock.add_response(
        url=f"{KALSHI_BASE}/markets?limit=100&status=open",
        status_code=403,
        json={"message": "Forbidden"},
    )
    client = KalshiClient()
    with pytest.raises(KalshiAuthError):
        await client.get_markets()


async def test_404_raises_not_found_error(httpx_mock):
    httpx_mock.add_response(
        url=f"{KALSHI_BASE}/markets/FAKE-TICKER",
        status_code=404,
        json={"message": "Market not found"},
    )
    client = KalshiClient()
    with pytest.raises(KalshiNotFoundError):
        await client.get_market("FAKE-TICKER")


async def test_429_raises_rate_limit_error(httpx_mock):
    httpx_mock.add_response(
        url=f"{KALSHI_BASE}/markets?limit=100&status=open",
        status_code=429,
        json={"message": "Too many requests"},
    )
    client = KalshiClient()
    with pytest.raises(KalshiRateLimitError):
        await client.get_markets()


async def test_500_raises_server_error(httpx_mock):
    httpx_mock.add_response(
        url=f"{KALSHI_BASE}/markets?limit=100&status=open",
        status_code=500,
        text="Internal Server Error",
    )
    client = KalshiClient()
    with pytest.raises(KalshiServerError):
        await client.get_markets()


async def test_error_message_extracted_from_json(httpx_mock):
    httpx_mock.add_response(
        url=f"{KALSHI_BASE}/markets?limit=100&status=open",
        status_code=401,
        json={"message": "invalid api key"},
    )
    client = KalshiClient()
    with pytest.raises(KalshiAuthError, match="invalid api key"):
        await client.get_markets()
