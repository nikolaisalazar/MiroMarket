from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.models.persona import AgentPersona
from app.schemas.persona import PersonaResponse

router = APIRouter()


@router.get("", response_model=List[PersonaResponse])
async def list_personas(db: AsyncSession = Depends(get_db)):
    """List all active agent personas."""
    result = await db.execute(
        select(AgentPersona).where(AgentPersona.is_active == True)
    )
    return result.scalars().all()


@router.get("/{slug}", response_model=PersonaResponse)
async def get_persona(slug: str, db: AsyncSession = Depends(get_db)):
    """Get a specific persona by its slug (e.g. 'quantitative-economist')."""
    result = await db.execute(
        select(AgentPersona).where(AgentPersona.slug == slug)
    )
    persona = result.scalar_one_or_none()
    if not persona:
        raise NotFoundError("Persona", slug)
    return persona
