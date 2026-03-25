from decimal import Decimal
from typing import List, Optional
import uuid

from pydantic import BaseModel


class PersonaResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    domain_expertise: List[str]
    epistemic_style: str
    known_biases: List[str]
    calibration: str
    information_sources: List[str]
    risk_orientation: str
    credibility_weight: Decimal
    description: Optional[str] = None

    model_config = {"from_attributes": True}
