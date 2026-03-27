"""
Pytest fixtures for simulation-layer tests.

All fixtures here depend on `simulation_db` — a fresh in-memory SQLite
session that includes every table the simulation engine touches:

    markets, market_price_history,
    agent_personas, simulations, agent_estimates, simulation_reports

The root conftest.py handles all SQLite compatibility patches (JSONB,
ARRAY, UUID) before any models are imported, so simply importing them
here is safe.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Model imports — order matters for SQLAlchemy's metadata registration.
# Market must be imported before Simulation (FK dependency).
from app.models.market import Market, MarketPriceHistory, MarketSource, MarketStatus  # noqa: F401
from app.models.persona import (
    AgentPersona,
    CalibrationProfile,
    EpistemicStyle,
    RiskOrientation,
)
from app.models.report import SimulationReport  # noqa: F401
from app.models.simulation import AgentEstimate, Simulation, SimulationMode, SimulationStatus  # noqa: F401

# ---------------------------------------------------------------------------
# All tables needed for simulation tests, in dependency order.
# SQLAlchemy resolves FK ordering automatically in create_all.
# ---------------------------------------------------------------------------
_ALL_TABLES = [
    Market.__table__,
    MarketPriceHistory.__table__,
    AgentPersona.__table__,
    Simulation.__table__,
    AgentEstimate.__table__,
    SimulationReport.__table__,
]

# ---------------------------------------------------------------------------
# Persona seed data
#
# Five personas — one per EpistemicStyle — with deliberately distinct
# calibration profiles and risk orientations so tests can verify that
# aggregation treats them differently.
# ---------------------------------------------------------------------------
_PERSONA_SEEDS = [
    {
        "name": "The Bayesian Updater",
        "slug": "bayesian-updater",
        "epistemic_style": EpistemicStyle.bayesian,
        "calibration": CalibrationProfile.well_calibrated,
        "risk_orientation": RiskOrientation.risk_neutral,
        "domain_expertise": ["macroeconomics", "monetary-policy", "probability-theory"],
        "known_biases": ["anchoring"],
        "information_sources": ["academic-papers", "central-bank-reports"],
        "credibility_weight": Decimal("1.200"),
        "description": (
            "Applies Bayesian updating rigorously. Starts with a base-rate prior "
            "and adjusts incrementally as evidence arrives. Resistant to narrative "
            "fallacies and slow to update on single data points."
        ),
    },
    {
        "name": "The Frequentist",
        "slug": "frequentist-analyst",
        "epistemic_style": EpistemicStyle.frequentist,
        "calibration": CalibrationProfile.well_calibrated,
        "risk_orientation": RiskOrientation.risk_averse,
        "domain_expertise": ["statistics", "historical-data", "base-rates"],
        "known_biases": ["base-rate-overcorrection"],
        "information_sources": ["historical-databases", "government-statistics"],
        "credibility_weight": Decimal("1.000"),
        "description": (
            "Grounds all estimates firmly in historical base rates and frequency data. "
            "Distrusts narratives without statistical backing. Anchors strongly to "
            "long-run averages and is slow to accept regime-change arguments."
        ),
    },
    {
        "name": "The Contrarian",
        "slug": "contrarian-trader",
        "epistemic_style": EpistemicStyle.contrarian,
        "calibration": CalibrationProfile.overconfident,
        "risk_orientation": RiskOrientation.risk_seeking,
        "domain_expertise": ["market-microstructure", "sentiment-analysis", "options-flow"],
        "known_biases": ["overconfidence", "contrarian-bias"],
        "information_sources": ["social-media-sentiment", "options-flow", "short-interest"],
        "credibility_weight": Decimal("0.800"),
        "description": (
            "Systematically fades consensus. Assumes crowded trades are about to "
            "reverse. Often overconfident in their differentiated view and prone to "
            "doubling down when the market moves against them."
        ),
    },
    {
        "name": "The Consensus Tracker",
        "slug": "consensus-tracker",
        "epistemic_style": EpistemicStyle.consensus,
        "calibration": CalibrationProfile.underconfident,
        "risk_orientation": RiskOrientation.risk_averse,
        "domain_expertise": ["survey-research", "expert-forecasting", "prediction-markets"],
        "known_biases": ["herding", "authority-bias"],
        "information_sources": ["expert-forecasts", "prediction-markets", "polls"],
        "credibility_weight": Decimal("0.900"),
        "description": (
            "Weights expert consensus and existing prediction-market prices heavily. "
            "Defers to the wisdom of crowds. Rarely takes strong independent positions "
            "and tends to anchor to whatever the current market price already implies."
        ),
    },
    {
        "name": "The Heuristic Trader",
        "slug": "heuristic-trader",
        "epistemic_style": EpistemicStyle.heuristic,
        "calibration": CalibrationProfile.overconfident,
        "risk_orientation": RiskOrientation.risk_neutral,
        "domain_expertise": ["technical-analysis", "pattern-recognition", "news-trading"],
        "known_biases": ["recency-bias", "availability-heuristic"],
        "information_sources": ["news-feeds", "price-charts", "social-media"],
        "credibility_weight": Decimal("0.900"),
        "description": (
            "Relies on mental shortcuts and pattern recognition. Fast-thinking and "
            "decisive. Overweights vivid recent examples and underweights slow-moving "
            "structural factors. Prone to anchoring on the most recent headline."
        ),
    },
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def simulation_db() -> AsyncSession:
    """
    Yields an AsyncSession backed by a fresh in-memory SQLite database
    containing all tables needed for simulation tests.

    Isolation is identical to the root `db` fixture — each test gets a
    completely fresh database with no shared state.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            Market.metadata.create_all,
            tables=_ALL_TABLES,
        )

    TestSession = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with TestSession() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def sample_market(simulation_db: AsyncSession) -> Market:
    """
    A single open Kalshi market persisted in `simulation_db`.

    Uses a realistic BTC price market so prompt-engineering tests have
    plausible market data to work with.
    """
    market = Market(
        external_id="KXBTC-25DEC31",
        source=MarketSource.kalshi,
        title="Will Bitcoin exceed $100,000 by December 31, 2025?",
        description=(
            "Resolves YES if the BTC/USD closing price on any major exchange "
            "exceeds $100,000 on December 31, 2025."
        ),
        category="crypto",
        status=MarketStatus.open,
        current_yes_price=Decimal("0.6200"),
        current_no_price=Decimal("0.3800"),
        volume_24h=Decimal("125000.00"),
        open_interest=Decimal("890000.00"),
        fetched_at=datetime.now(timezone.utc),
    )
    simulation_db.add(market)
    await simulation_db.commit()
    await simulation_db.refresh(market)
    return market


@pytest.fixture
async def sample_personas(simulation_db: AsyncSession) -> list[AgentPersona]:
    """
    All five seed personas persisted in `simulation_db`.

    Returns them in the same order as `_PERSONA_SEEDS` so tests can
    index by position when they need a specific epistemic style:

        personas[0]  →  bayesian-updater     (well_calibrated, risk_neutral)
        personas[1]  →  frequentist-analyst  (well_calibrated, risk_averse)
        personas[2]  →  contrarian-trader    (overconfident,   risk_seeking)
        personas[3]  →  consensus-tracker    (underconfident,  risk_averse)
        personas[4]  →  heuristic-trader     (overconfident,   risk_neutral)
    """
    personas = [AgentPersona(**seed) for seed in _PERSONA_SEEDS]
    simulation_db.add_all(personas)
    await simulation_db.commit()
    for p in personas:
        await simulation_db.refresh(p)
    return personas


@pytest.fixture
async def sample_simulation(
    simulation_db: AsyncSession,
    sample_market: Market,
) -> Simulation:
    """
    A pending Simulation linked to `sample_market`.

    Starts in `pending` status with no estimates — the same state the
    engine will find it in when it picks it up as a background task.
    """
    sim = Simulation(
        market_id=sample_market.id,
        status=SimulationStatus.pending,
        simulation_mode=SimulationMode.independent,
        num_agents=5,
        market_price_at_run=sample_market.current_yes_price,
    )
    simulation_db.add(sim)
    await simulation_db.commit()
    await simulation_db.refresh(sim)
    return sim
