"""
Kalshi REST API client.
Docs: https://trading-api.kalshi.com/trade-api/v2/openapi.json

Responsibilities:
- HTTP communication with Kalshi only (no DB, no business logic)
- Cursor-based pagination handled transparently
- All prices returned as raw Kalshi integers (cents, 0–100)
- Full raw response preserved so ingestion_service can normalize

Error hierarchy:
  KalshiAPIError            — base for all Kalshi-sourced errors
  ├── KalshiAuthError       — 401/403
  ├── KalshiNotFoundError   — 404
  ├── KalshiRateLimitError  — 429 (caller should back off)
  └── KalshiServerError     — 5xx
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class KalshiAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Kalshi API {status_code}: {message}")


class KalshiAuthError(KalshiAPIError):
    pass


class KalshiNotFoundError(KalshiAPIError):
    pass


class KalshiRateLimitError(KalshiAPIError):
    pass


class KalshiServerError(KalshiAPIError):
    pass


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class KalshiClient:
    """
    Thin async wrapper around the Kalshi v2 REST API.

    A fresh httpx.AsyncClient is created per call group so this class
    is safe to instantiate once at module level and share across requests.
    """

    def __init__(self) -> None:
        self.base_url = settings.KALSHI_BASE_URL.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {settings.KALSHI_API_KEY}",
            "Content-Type": "application/json",
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
        )

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def get_markets(
        self,
        limit: int = 100,
        category: str | None = None,
        status: str = "open",
    ) -> list[dict]:
        """
        Fetch up to `limit` markets from Kalshi.

        Handles cursor-based pagination automatically — callers just request
        how many markets they want and receive a flat list.

        Args:
            limit:    Maximum number of markets to return (capped at 1000).
            category: Optional Kalshi category slug to filter by.
            status:   "open" | "closed" | "settled" — defaults to open markets.

        Returns:
            List of raw Kalshi market dicts (prices in cents, 0–100).
        """
        limit = min(limit, 1000)
        results: list[dict] = []
        cursor: str | None = None
        page_size = min(limit, 200)  # Kalshi max per page is 200

        async with self._client() as client:
            while len(results) < limit:
                params: dict[str, str | int] = {
                    "limit": min(page_size, limit - len(results)),
                    "status": status,
                }
                if category:
                    params["category"] = category
                if cursor:
                    params["cursor"] = cursor

                logger.debug(
                    "Fetching Kalshi markets page (fetched=%d, limit=%d)",
                    len(results),
                    limit,
                )
                response = await client.get("/markets", params=params)
                self._check_response(response)

                data = response.json()
                page: list[dict] = data.get("markets", [])
                results.extend(page)

                cursor = data.get("cursor")
                if not cursor or not page:
                    break  # Exhausted all available markets

        logger.info("Fetched %d markets from Kalshi", len(results))
        return results

    async def get_market(self, ticker: str) -> dict:
        """
        Fetch a single market by its Kalshi ticker.

        Args:
            ticker: Kalshi market ticker, e.g. "HIGHNY-23NOV31-B75".

        Returns:
            Raw Kalshi market dict.

        Raises:
            KalshiNotFoundError: If the ticker does not exist.
        """
        async with self._client() as client:
            response = await client.get(f"/markets/{ticker}")
            self._check_response(response)
            data = response.json()

        # Kalshi wraps single-market responses under a "market" key
        return data.get("market", data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_response(response: httpx.Response) -> None:
        """Raise a typed KalshiAPIError for any non-2xx response."""
        if response.is_success:
            return

        try:
            body = response.json()
            message = body.get("message") or body.get("error") or response.text
        except Exception:
            message = response.text or "no response body"

        code = response.status_code
        if code in (401, 403):
            raise KalshiAuthError(code, message)
        if code == 404:
            raise KalshiNotFoundError(code, message)
        if code == 429:
            raise KalshiRateLimitError(code, "Rate limit exceeded — back off before retrying")
        if code >= 500:
            raise KalshiServerError(code, message)

        # Catch-all for unexpected 4xx
        raise KalshiAPIError(code, message)


# Module-level singleton — import this everywhere
kalshi_client = KalshiClient()
