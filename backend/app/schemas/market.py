from datetime import datetime
from decimal import Decimal
from typing import Optional
import uuid

from pydantic import BaseModel


class MarketSummary(BaseModel):
    """Compact market view for list pages."""
    id: uuid.UUID
    external_id: str
    title: str
    category: Optional[str] = None
    resolution_date: Optional[datetime] = None
    current_yes_price: Optional[Decimal] = None
    status: str
    fetched_at: datetime

    model_config = {"from_attributes": True}


class MarketDetail(MarketSummary):
    """Full market view for the detail page."""
    description: Optional[str] = None
    current_no_price: Optional[Decimal] = None
    volume_24h: Optional[Decimal] = None
    open_interest: Optional[Decimal] = None
    created_at: datetime


class IngestionResult(BaseModel):
    """Response shape returned by POST /markets/ingest."""
    fetched: int      # How many markets Kalshi returned
    ingested: int     # How many were successfully upserted
    errors: int       # How many failed (logged server-side)
    duration_ms: int  # Wall-clock time for the full operation
    timestamp: datetime
