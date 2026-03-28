import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class EpistemicStyle(str, enum.Enum):
    bayesian = "bayesian"
    frequentist = "frequentist"
    heuristic = "heuristic"
    contrarian = "contrarian"
    consensus = "consensus"
    custom = "custom"      # User-authored persona with a fully custom system prompt


class CalibrationProfile(str, enum.Enum):
    overconfident = "overconfident"
    underconfident = "underconfident"
    well_calibrated = "well_calibrated"


class RiskOrientation(str, enum.Enum):
    risk_seeking = "risk_seeking"
    risk_neutral = "risk_neutral"
    risk_averse = "risk_averse"


class AgentPersona(Base):
    __tablename__ = "agent_personas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)

    # Arrays of strings (e.g. ["macroeconomics", "monetary-policy"])
    domain_expertise = Column(ARRAY(String), default=list)
    known_biases = Column(ARRAY(String), default=list)
    information_sources = Column(ARRAY(String), default=list)

    epistemic_style = Column(Enum(EpistemicStyle), nullable=False)
    calibration = Column(Enum(CalibrationProfile), nullable=False)
    risk_orientation = Column(Enum(RiskOrientation), nullable=False)

    # Weight used in logit-space aggregation. Default 1.0 = neutral.
    # Domain-specialist agents get a temporary boost during aggregation.
    credibility_weight = Column(Numeric(4, 3), default=1.0)

    description = Column(Text)

    # User-authored system prompt for custom personas (epistemic_style == custom).
    # When set, build_system_prompt() uses this verbatim (plus the output schema).
    # NULL for all seed personas — their identity is assembled from the fields above.
    custom_system_prompt = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    estimates = relationship("AgentEstimate", back_populates="persona")
