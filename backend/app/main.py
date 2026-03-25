from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import engine, Base
from app.api.routes import markets, simulations, reports, personas


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on startup and shutdown.
    Creates all DB tables on startup (safe to run repeatedly — won't overwrite data).
    For production, use Alembic migrations instead of create_all.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="MiroMarket API",
    description="Multi-agent prediction market simulation engine",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the Next.js frontend (localhost:3000) to call this API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(markets.router,     prefix="/api/v1/markets",     tags=["markets"])
app.include_router(simulations.router, prefix="/api/v1/simulations", tags=["simulations"])
app.include_router(reports.router,     prefix="/api/v1/reports",     tags=["reports"])
app.include_router(personas.router,    prefix="/api/v1/personas",    tags=["personas"])


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "version": "0.1.0"}
