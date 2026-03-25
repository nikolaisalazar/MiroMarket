import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, Text
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class SimulationStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    aggregating = "aggregating"
    reporting = "reporting"
    complete = "complete"
    failed = "failed"


class SimulationMode(str, enum.Enum):
    independent = "independent"     # MVP: agents estimate independently
    deliberative = "deliberative"   # V2: agents see peer estimates and can revise


class SignalDirection(str, enum.Enum):
    strong_buy = "strong_buy"
    buy = "buy"
    hold = "hold"
    sell = "sell"
    strong_sell = "strong_sell"


class Simulation(Base):
    __tablename__ = "simulations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_id = Column(UUID(as_uuid=True), ForeignKey("markets.id"), nullable=False)
    status = Column(Enum(SimulationStatus), default=SimulationStatus.pending)
    simulation_mode = Column(Enum(SimulationMode), default=SimulationMode.independent)
    num_agents = Column(Integer)
    aggregate_probability = Column(Numeric(5, 4))
    market_price_at_run = Column(Numeric(5, 4))  # Snapshot of price when sim started
    signal_direction = Column(Enum(SignalDirection))
    signal_strength = Column(Numeric(3, 2))       # 0.0 – 1.0, magnitude of the edge
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    market = relationship("Market", back_populates="simulations")
    agent_estimates = relationship("AgentEstimate", back_populates="simulation")
    report = relationship("SimulationReport", back_populates="simulation", uselist=False)


class AgentEstimate(Base):
    __tablename__ = "agent_estimates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    simulation_id = Column(UUID(as_uuid=True), ForeignKey("simulations.id"), nullable=False)
    persona_id = Column(UUID(as_uuid=True), ForeignKey("agent_personas.id"), nullable=False)
    round_number = Column(Integer, default=1)       # 1 = MVP; 1–3 = V2 deliberation

    probability = Column(Numeric(5, 4), nullable=False)
    confidence = Column(Numeric(3, 2))              # Agent's stated confidence 0–1
    lower_bound = Column(Numeric(5, 4))             # 90% CI low
    upper_bound = Column(Numeric(5, 4))             # 90% CI high

    reasoning = Column(Text)                        # Full chain-of-thought
    key_factors = Column(JSONB)                     # List of key factors (stored as JSON)
    dissenting_notes = Column(Text)                 # What would change their estimate
    self_correction = Column(Text)                  # How their biases might be affecting them

    raw_llm_response = Column(JSONB)                # Full LiteLLM response object
    tokens_used = Column(Integer)
    latency_ms = Column(Integer)
    parse_failed = Column(Boolean, default=False)   # True if JSON parsing failed

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    simulation = relationship("Simulation", back_populates="agent_estimates")
    persona = relationship("AgentPersona", back_populates="estimates")
