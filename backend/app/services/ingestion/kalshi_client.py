"""
Kalshi REST API client.
Docs: https://trading-api.kalshi.com/trade-api/v2/openapi.json

All raw Kalshi responses are stored in Market.raw_metadata so we can
re-normalize without re-fetching if the schema changes.
"""
import httpx

from app.config import settings


class KalshiClient:
    def __init__(self):
        self.base_url = settings.KALSHI_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {settings.KALSHI_API_KEY}",
            "Content-Type": "application/json",
        }

    async def get_markets(
        self,
        limit: int = 100,
        category: str | None = None,
        status: str = "open",
    ) -> list[dict]:
        """
        Fetch markets from Kalshi.
        TODO: Implement in Week 2.
        """
        raise NotImplementedError("Kalshi client not yet implemented")

    async def get_market(self, ticker: str) -> dict:
        """
        Fetch a single market by its Kalshi ticker.
        TODO: Implement in Week 2.
        """
        raise NotImplementedError


kalshi_client = KalshiClient()
