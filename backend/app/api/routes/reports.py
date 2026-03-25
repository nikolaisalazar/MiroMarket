from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.models.report import SimulationReport
from app.schemas.report import ReportResponse

router = APIRouter()


@router.get("/{simulation_id}", response_model=ReportResponse)
async def get_report(simulation_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve the ReportAgent synthesis for a completed simulation."""
    result = await db.execute(
        select(SimulationReport).where(
            SimulationReport.simulation_id == simulation_id
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise NotFoundError("Report for simulation", simulation_id)
    return report
