import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.models.simulation import Simulation, SimulationStatus
from app.schemas.simulation import SimulationCreate, SimulationResponse

router = APIRouter()


@router.post("", response_model=SimulationResponse, status_code=202)
async def create_simulation(
    body: SimulationCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Kick off a simulation. Returns immediately with status='pending'.
    The frontend polls GET /simulations/{id} until status='complete'.
    """
    sim = Simulation(
        id=uuid.uuid4(),
        market_id=body.market_id,
        simulation_mode=body.mode,
        status=SimulationStatus.pending,
        created_at=datetime.utcnow(),
    )
    db.add(sim)
    await db.commit()
    await db.refresh(sim)

    # TODO (Week 4): Uncomment once engine.py is implemented.
    # from app.services.simulation.engine import run_simulation
    # background_tasks.add_task(run_simulation, sim.id, body.persona_ids)

    return sim


@router.get("/{simulation_id}", response_model=SimulationResponse)
async def get_simulation(simulation_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get a simulation by ID, including all agent estimates.
    The frontend polls this endpoint every 2s to track status.
    """
    result = await db.execute(
        select(Simulation)
        .where(Simulation.id == simulation_id)
        .options(selectinload(Simulation.agent_estimates))
    )
    sim = result.scalar_one_or_none()
    if not sim:
        raise NotFoundError("Simulation", simulation_id)
    return sim


@router.get("", response_model=List[SimulationResponse])
async def list_simulations(
    market_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List all simulations, optionally filtered by market."""
    query = (
        select(Simulation)
        .options(selectinload(Simulation.agent_estimates))
        .order_by(Simulation.created_at.desc())
    )
    if market_id:
        query = query.where(Simulation.market_id == market_id)
    result = await db.execute(query)
    return result.scalars().all()
