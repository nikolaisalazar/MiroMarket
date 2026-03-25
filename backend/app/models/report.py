import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class ReportSignal(str, enum.Enum):
    strong_buy = "strong_buy"
    buy = "buy"
    hold = "hold"
    sell = "sell"
    strong_sell = "strong_sell"


class ConsensusLevel(str, enum.Enum):
    high = "high"           # std_dev < 0.08
    medium = "medium"       # std_dev < 0.15
    low = "low"             # std_dev < 0.22
    contested = "contested" # std_dev >= 0.22


class SimulationReport(Base):
    __tablename__ = "simulation_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    simulation_id = Column(
        UUID(as_uuid=True), ForeignKey("simulations.id"), unique=True, nullable=False
    )

    aggregate_method = Column(String(50))       # e.g. "logit_weighted_mean"
    final_probability = Column(Numeric(5, 4))
    market_price = Column(Numeric(5, 4))
    edge = Column(Numeric(5, 4))                # final_probability - market_price
    signal = Column(Enum(ReportSignal))
    consensus_level = Column(Enum(ConsensusLevel))

    bull_case = Column(Text)
    bear_case = Column(Text)
    key_uncertainties = Column(JSONB)           # List of strings
    recommended_action = Column(Text)
    report_markdown = Column(Text)              # Full ReportAgent output as Markdown
    minority_views = Column(JSONB)              # Notable dissenting agent summaries

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    simulation = relationship("Simulation", back_populates="report")
