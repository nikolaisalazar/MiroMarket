from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import uuid

from pydantic import BaseModel


class SimulationCreate(BaseModel):
    market_id: uuid.UUID
    mode: str = "independent"
    # If None, domain routing selects the most relevant personas automatically.
    persona_ids: Optional[List[uuid.UUID]] = None


class AgentEstimateResponse(BaseModel):
    id: uuid.UUID
    persona_id: uuid.UUID
    round_number: int
    probability: Decimal
    confidence: Optional[Decimal] = None
    reasoning: Optional[str] = None
    lower_bound: Optional[Decimal] = None
    upper_bound: Optional[Decimal] = None
    key_factors: Optional[List[str]] = None
    dissenting_notes: Optional[str] = None
    self_correction: Optional[str] = None
    parse_failed: bool = False

    model_config = {"from_attributes": True}


class SimulationResponse(BaseModel):
    id: uuid.UUID
    market_id: uuid.UUID
    status: str
    simulation_mode: str
    num_agents: Optional[int] = None
    aggregate_probability: Optional[Decimal] = None
    market_price_at_run: Optional[Decimal] = None
    signal_direction: Optional[str] = None
    signal_strength: Optional[Decimal] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    agent_estimates: List[AgentEstimateResponse] = []

    model_config = {"from_attributes": True}
