from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import uuid

from pydantic import BaseModel


class ReportResponse(BaseModel):
    id: uuid.UUID
    simulation_id: uuid.UUID
    final_probability: Optional[Decimal] = None
    market_price: Optional[Decimal] = None
    edge: Optional[Decimal] = None              # positive = aggregate > market (buy signal)
    signal: Optional[str] = None
    consensus_level: Optional[str] = None
    bull_case: Optional[str] = None
    bear_case: Optional[str] = None
    key_uncertainties: Optional[List[str]] = None
    recommended_action: Optional[str] = None
    report_markdown: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
