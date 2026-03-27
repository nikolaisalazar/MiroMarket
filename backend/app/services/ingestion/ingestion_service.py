"""
Kalshi ingestion service.

Sits between kalshi_client (HTTP layer) and the database.
Responsible for:
- Normalizing raw Kalshi responses into our Market schema
- Upserting markets (insert-or-update keyed on external_id / Kalshi ticker)
- Writing a MarketPriceHistory snapshot on every successful upsert
- Returning a structured IngestionResult so callers can report stats

This module has no knowledge of FastAPI — it accepts an AsyncSession and
returns plain objects. Both the manual route (POST /markets/ingest) and a
future scheduler call the same functions here.
"""
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Market, MarketPriceHistory, MarketStatus
from app.schemas.market import IngestionResult
from app.services.ingestion.kalshi_client import (
    KalshiAPIError,
    KalshiAuthError,
    KalshiRateLimitError,
    kalshi_client,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kalshi → internal status mapping
# ---------------------------------------------------------------------------
_STATUS_MAP: dict[str, MarketStatus] = {
    "open": MarketStatus.open,
    "closed": MarketStatus.closed,
    "settled": MarketStatus.resolved,
    "finalized": MarketStatus.resolved,
}


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _cents_to_decimal(value: int | float | None) -> float | None:
    """
    Convert a Kalshi cent-price (0–100 integer) to a decimal probability
    (0.0000–1.0000).  Returns None if value is None or zero in a way that
    indicates missing data (Kalshi sometimes sends 0 for illiquid markets).
    """
    if value is None:
        return None
    return round(float(value) / 100, 4)


def normalize_market(raw: dict) -> dict:
    """
    Convert a raw Kalshi market dict into a flat dict that maps directly
    onto Market model columns.

    Price convention:
      Kalshi sends yes_ask / yes_bid / no_ask / no_bid as integer cents.
      We store the mid-price as a decimal in [0, 1].

    All original Kalshi fields are preserved in raw_metadata so we can
    re-normalize without re-fetching if the schema ever changes.
    """
    # --- Mid-price calculation -------------------------------------------
    yes_ask = raw.get("yes_ask") or 0
    yes_bid = raw.get("yes_bid") or 0
    no_ask  = raw.get("no_ask")  or 0
    no_bid  = raw.get("no_bid")  or 0

    yes_mid = _cents_to_decimal((yes_ask + yes_bid) / 2) if (yes_ask or yes_bid) else None
    no_mid  = _cents_to_decimal((no_ask  + no_bid)  / 2) if (no_ask  or no_bid)  else None

    # --- Status mapping --------------------------------------------------
    raw_status = (raw.get("status") or "open").lower()
    status = _STATUS_MAP.get(raw_status, MarketStatus.open)

    # --- Resolution date -------------------------------------------------
    resolution_date: datetime | None = None
    for field in ("close_time", "expiration_time"):
        ts = raw.get(field)
        if ts:
            try:
                resolution_date = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                logger.warning("Could not parse date %r from field %r", ts, field)
            break

    now = datetime.now(timezone.utc)

    return {
        "external_id":       raw["ticker"],
        "title":             raw.get("title") or raw.get("subtitle") or raw["ticker"],
        "description":       raw.get("subtitle") or raw.get("description"),
        "category":          raw.get("category"),
        "resolution_date":   resolution_date,
        "current_yes_price": yes_mid,
        "current_no_price":  no_mid,
        "volume_24h":        raw.get("volume_24h"),
        "open_interest":     raw.get("open_interest"),
        "status":            status,
        "raw_metadata":      raw,
        "fetched_at":        now,
        "updated_at":        now,
    }


# ---------------------------------------------------------------------------
# DB upsert
# ---------------------------------------------------------------------------

async def _upsert_market(db: AsyncSession, raw: dict) -> Market:
    """
    Insert or update a single market row, then append a price history snapshot.

    Uses a SELECT-then-write pattern instead of raw SQL ON CONFLICT so we
    stay in the SQLAlchemy ORM layer and keep the code readable. At our
    polling frequency this is fast enough; we can switch to a bulk upsert
    later if needed.
    """
    normalized = normalize_market(raw)
    ticker = normalized["external_id"]

    result = await db.execute(
        select(Market).where(Market.external_id == ticker)
    )
    market = result.scalar_one_or_none()

    if market:
        # Update all mutable fields; leave id and created_at untouched
        for key, value in normalized.items():
            if key != "created_at":
                setattr(market, key, value)
        logger.debug("Updated market %s", ticker)
    else:
        market = Market(**normalized)
        db.add(market)
        logger.debug("Inserted market %s", ticker)

    # flush to ensure market.id is populated before writing history
    await db.flush()

    # Price history snapshot — written on every ingestion pass so we can
    # chart price movement over time (powers the V2 chart feature)
    if normalized["current_yes_price"] is not None:
        snapshot = MarketPriceHistory(
            market_id=market.id,
            yes_price=normalized["current_yes_price"],
            volume=normalized.get("volume_24h"),
            recorded_at=normalized["fetched_at"],
        )
        db.add(snapshot)

    return market


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

async def ingest_markets(
    db: AsyncSession,
    limit: int = 100,
    category: str | None = None,
    status: str = "open",
) -> IngestionResult:
    """
    Fetch markets from Kalshi and upsert them into the database.

    This is the primary entry point for both:
    - Manual trigger via POST /api/v1/markets/ingest
    - Future automated scheduler

    Args:
        db:       AsyncSession injected by FastAPI or passed directly.
        limit:    How many markets to fetch from Kalshi (max 1000).
        category: Optional Kalshi category filter.
        status:   Kalshi market status filter — default "open".

    Returns:
        IngestionResult with counts and timing.

    Raises:
        KalshiAuthError:      On 401/403 — likely a bad API key.
        KalshiRateLimitError: On 429 — caller should retry later.
        KalshiAPIError:       On any other Kalshi-side failure.
    """
    started_at = time.monotonic()

    # Fetch from Kalshi — let auth/rate-limit errors propagate to the caller
    # so the route can convert them into the correct HTTP status codes.
    raw_markets = await kalshi_client.get_markets(
        limit=limit,
        category=category,
        status=status,
    )

    ingested = 0
    errors = 0

    for raw in raw_markets:
        ticker = raw.get("ticker", "<unknown>")
        try:
            await _upsert_market(db, raw)
            ingested += 1
        except Exception as exc:
            # A single bad market should not abort the entire batch
            errors += 1
            logger.error("Failed to upsert market %s: %s", ticker, exc)

    await db.commit()

    duration_ms = int((time.monotonic() - started_at) * 1000)
    logger.info(
        "Ingestion complete — fetched=%d ingested=%d errors=%d duration=%dms",
        len(raw_markets), ingested, errors, duration_ms,
    )

    return IngestionResult(
        fetched=len(raw_markets),
        ingested=ingested,
        errors=errors,
        duration_ms=duration_ms,
        timestamp=datetime.now(timezone.utc),
    )


async def ingest_single_market(db: AsyncSession, ticker: str) -> Market:
    """
    Fetch and upsert a single market by Kalshi ticker.

    Used by the manual "run agents on this market" flow — the dashboard
    can call this to ensure the market is fresh before deploying agents.

    Raises:
        KalshiNotFoundError: If the ticker doesn't exist on Kalshi.
    """
    raw = await kalshi_client.get_market(ticker)
    market = await _upsert_market(db, raw)
    await db.commit()
    return market
