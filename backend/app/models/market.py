import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class MarketSource(str, enum.Enum):
    kalshi = "kalshi"


class MarketStatus(str, enum.Enum):
    open = "open"
    closed = "closed"
    resolved = "resolved"


class Market(Base):
    __tablename__ = "markets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id = Column(String(255), unique=True, nullable=False)  # Kalshi ticker
    source = Column(Enum(MarketSource), nullable=False, default=MarketSource.kalshi)
    title = Column(Text, nullable=False)
    description = Column(Text)
    category = Column(String(100))
    resolution_date = Column(DateTime(timezone=True))
    current_yes_price = Column(Numeric(5, 4))   # 0.0000 – 1.0000
    current_no_price = Column(Numeric(5, 4))
    volume_24h = Column(Numeric(20, 2))
    open_interest = Column(Numeric(20, 2))
    status = Column(Enum(MarketStatus), default=MarketStatus.open)
    raw_metadata = Column(JSONB)  # Full Kalshi API response stored for reference
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    simulations = relationship("Simulation", back_populates="market")
    price_history = relationship("MarketPriceHistory", back_populates="market")


class MarketPriceHistory(Base):
    """Snapshots of market price over time — used for charts in V2."""
    __tablename__ = "market_price_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_id = Column(UUID(as_uuid=True), ForeignKey("markets.id"), nullable=False)
    yes_price = Column(Numeric(5, 4))
    volume = Column(Numeric(20, 2))
    recorded_at = Column(DateTime(timezone=True), nullable=False)

    market = relationship("Market", back_populates="price_history")
