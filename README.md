# MiroMarket

Multi-agent prediction market simulation engine.
Backend: FastAPI + async SQLAlchemy + Supabase (PostgreSQL)
Frontend: Next.js

---

Mostly notes for me right now, relating to start-up and planning

## Prerequisites

- Python 3.12+
- Node.js 18+ *(frontend, not needed yet)*
- A [Supabase](https://supabase.com) project with a PostgreSQL connection string
- A [Kalshi](https://kalshi.com/settings/api) API key

---

## First-time setup

```bash
# 1. Clone and enter the repo
git clone <your-repo-url>
cd MiroMarket

# 2. Create and activate the Python virtual environment
cd backend
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the example env file and fill in your values
cp .env.example .env
```

Open `backend/.env` and set the following — everything else has safe defaults:

```
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>/<db>
KALSHI_API_KEY=<your kalshi api key>
KALSHI_BASE_URL=https://trading-api.kalshi.com/trade-api/v2

# LLM — only needed for simulation (Week 3+)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
```

> `.env` is gitignored — it will never be committed.

---

## Starting the backend

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

The API is now running at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

---

## Running the tests

```bash
# Tests must be run from inside backend
cd backend
source .venv/bin/activate

# Run all ingestion tests (no API key or DB required)
pytest tests/ingestion/ -v

# Run a specific test file
pytest tests/ingestion/test_normalize.py -v
pytest tests/ingestion/test_kalshi_client.py -v
pytest tests/ingestion/test_ingestion_service.py -v
pytest tests/ingestion/test_markets_route.py -v
```

Tests use an in-memory SQLite database and mocked HTTP — no live credentials needed.

---

## Manually triggering a Kalshi ingestion

With the server running and `KALSHI_API_KEY` set:

```bash
# Ingest 10 open markets
curl -X POST "http://localhost:8000/api/v1/markets/ingest?limit=10" | python -m json.tool

# Ingest markets filtered by category
curl -X POST "http://localhost:8000/api/v1/markets/ingest?limit=20&category=economics" | python -m json.tool

# Refresh a single market by ticker
curl -X POST "http://localhost:8000/api/v1/markets/FED-RATE-JULY26/ingest" | python -m json.tool

# List markets stored in the database
curl "http://localhost:8000/api/v1/markets?limit=20" | python -m json.tool
```

---

## Project structure

```
MiroMarket/
├── backend/
│   ├── app/
│   │   ├── api/routes/         # FastAPI route handlers
│   │   │   ├── markets.py      # GET /markets, POST /markets/ingest
│   │   │   ├── simulations.py  # (Week 3)
│   │   │   ├── reports.py      # (Week 3)
│   │   │   └── personas.py     # (Week 3)
│   │   ├── core/
│   │   │   ├── database.py     # Async SQLAlchemy engine + session
│   │   │   └── exceptions.py   # Typed HTTP exceptions
│   │   ├── models/             # SQLAlchemy ORM models
│   │   │   ├── market.py       # Market + MarketPriceHistory
│   │   │   ├── persona.py      # AgentPersona
│   │   │   ├── simulation.py   # Simulation + AgentEstimate
│   │   │   └── report.py       # SimulationReport
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── ingestion/
│   │   │   │   ├── kalshi_client.py      # HTTP client — Kalshi REST API
│   │   │   │   └── ingestion_service.py  # Normalize + upsert to DB
│   │   │   ├── simulation/     # Multi-agent engine (Week 3)
│   │   │   └── report/         # Report generation (Week 3)
│   │   ├── config.py           # Pydantic settings (reads from .env)
│   │   └── main.py             # FastAPI app + lifespan
│   ├── tests/
│   │   ├── conftest.py                            # Shared DB fixture
│   │   └── ingestion/
│   │       ├── test_normalize.py                  # normalize_market() unit tests
│   │       ├── test_kalshi_client.py              # HTTP client tests (mocked)
│   │       ├── test_ingestion_service.py          # DB upsert integration tests
│   │       └── test_markets_route.py              # Route/HTTP tests
│   ├── migrations/             # Alembic (not yet initialized)
│   ├── requirements.txt
│   └── pytest.ini
└── README.md
```

---

## Pipeline (current state — Week 2)

```
POST /api/v1/markets/ingest
        │
        ▼
kalshi_client.get_markets()     ← fetches from Kalshi REST API
        │
        ▼
ingestion_service               ← normalizes prices/status/dates
        │                          upserts Market rows
        │                          writes MarketPriceHistory snapshots
        ▼
Database (Supabase / PostgreSQL)
        │
        ▼
GET /api/v1/markets             ← browse ingested markets
```

---

## Roadmap

| Task | Focus |
|------|-------|
| ✅ 1 | Scaffold — FastAPI, SQLAlchemy, models, routes stubs |
| ✅ 2 | Kalshi ingestion — client, service, upsert, tests |
| 3 | Agent simulation engine — personas, debate, aggregation |
| 4 | Research agent — web search, context injection |
| 5 | Heuristic screener — automated market selection |
| 6 | Frontend dashboard — market browser, manual deploy, results |
