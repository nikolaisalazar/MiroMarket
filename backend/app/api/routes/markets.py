from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import IngestionError, NotFoundError
from app.models.market import Market
from app.schemas.market import IngestionResult, MarketDetail, MarketSummary
from app.services.ingestion.kalshi_client import (
    KalshiAPIError,
    KalshiAuthError,
    KalshiNotFoundError,
    KalshiRateLimitError,
)
from app.services.ingestion.ingestion_service import ingest_markets, ingest_single_market

router = APIRouter()


@router.get("", response_model=List[MarketSummary])
async def list_markets(
    category: Optional[str] = Query(None, description="Filter by category"),
    status: Optional[str] = Query(None, enum=["open", "closed", "resolved"]),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    query = select(Market)
    if category:
        query = query.where(Market.category == category)
    if status:
        query = query.where(Market.status == status)
    query = query.order_by(Market.fetched_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{market_id}", response_model=MarketDetail)
async def get_market(market_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Market).where(Market.id == market_id))
    market = result.scalar_one_or_none()
    if not market:
        raise NotFoundError("Market", market_id)
    return market


@router.post("/ingest", response_model=IngestionResult)
async def trigger_ingestion(
    limit: int = Query(100, le=500, description="Number of markets to fetch from Kalshi"),
    category: Optional[str] = Query(None, description="Kalshi category slug to filter by"),
    status: str = Query("open", enum=["open", "closed", "settled"], description="Kalshi market status"),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger a Kalshi market ingestion.

    Fetches fresh market data from Kalshi and upserts it into the database.
    Also writes a MarketPriceHistory snapshot for each market so price
    movement can be charted over time.

    This is the manual entry point into the ingestion pipeline — the same
    service function will be invoked by the automated scheduler in a later
    iteration, keeping both paths on identical code.
    """
    try:
        return await ingest_markets(db, limit=limit, category=category, status=status)
    except KalshiAuthError as exc:
        raise IngestionError(f"Authentication failed — check KALSHI_API_KEY ({exc})")
    except KalshiRateLimitError:
        raise IngestionError("Kalshi rate limit hit — wait a moment and try again")
    except KalshiAPIError as exc:
        raise IngestionError(str(exc))


@router.post("/{ticker}/ingest", response_model=MarketDetail)
async def ingest_single(ticker: str, db: AsyncSession = Depends(get_db)):
    """
    Fetch and upsert a single market by Kalshi ticker.

    Used by the dashboard "deploy agents on this market" flow to ensure
    the market row is fresh before kicking off the simulation pipeline.
    """
    try:
        return await ingest_single_market(db, ticker)
    except KalshiNotFoundError:
        raise NotFoundError("Market", ticker)
    except KalshiAuthError as exc:
        raise IngestionError(f"Authentication failed — check KALSHI_API_KEY ({exc})")
    except KalshiAPIError as exc:
        raise IngestionError(str(exc))
