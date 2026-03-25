"""
Simulation engine — main orchestrator.

Manages the full lifecycle of a simulation run:
  1. Load simulation + market from DB
  2. Select personas (domain routing or explicit list)
  3. Build context for each agent
  4. Run all agents in parallel (asyncio.gather)
  5. Aggregate estimates (logit-space weighted mean)
  6. Generate ReportAgent synthesis
  7. Persist all results and mark simulation complete

TODO: Implement in Week 4.
"""
import uuid


async def run_simulation(
    simulation_id: uuid.UUID,
    persona_ids: list[uuid.UUID] | None = None,
) -> None:
    """
    Background task entry point.
    Called by POST /simulations via FastAPI BackgroundTasks.

    persona_ids=None means use domain routing (recommended).
    """
    # Step 1: Load simulation + market from DB
    # Step 2: Select personas
    # Step 3: asyncio.gather(*[run_agent(market, persona) for persona in personas])
    # Step 4: aggregate_estimates(results, market.current_yes_price)
    # Step 5: generate_report(simulation, results, aggregation)
    # Step 6: Update simulation.status = "complete"
    raise NotImplementedError("Simulation engine — implement in Week 4")
