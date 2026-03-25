from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.models.market import Market
from app.schemas.market import MarketDetail, MarketSummary

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


@router.post("/ingest")
async def trigger_ingestion(
    limit: int = Query(100, le=500),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger a Kalshi market ingestion.
    Fetches fresh market data and upserts into the database.
    TODO: Implement in Week 2 (kalshi_client.py).
    """
    return {"message": "Ingestion not yet implemented", "status": "todo"}
