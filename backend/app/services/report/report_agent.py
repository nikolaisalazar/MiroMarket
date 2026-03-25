"""
ReportAgent — meta-agent that synthesizes all agent estimates.

The ReportAgent receives the full panel of estimates + reasoning and produces
a structured signal report: bull/bear case, consensus analysis, recommended action.

This uses REPORT_MODEL (defaults to a more capable model than AGENT_MODEL)
because quality matters more here — this is what the user actually reads.

TODO: Implement in Week 5.
"""
import litellm
from app.config import settings
from app.services.simulation.aggregator import AggregationResult


REPORT_SYSTEM_PROMPT = """
You are the Chief Analysis Officer at a quantitative prediction research firm.
Your role is to synthesize estimates from a panel of domain experts into a
structured signal report for prediction market trading.

You do NOT generate new estimates. You analyze the expert panel's outputs,
identify convergence and divergence, extract the strongest reasoning threads,
and produce a clear, actionable report.

Be intellectually honest. Note limitations, data gaps, and cases where the
panel is genuinely uncertain. Avoid false confidence.

Output format: structured JSON (schema provided in user message).
"""


async def generate_report(
    simulation,
    estimates: list,
    aggregation: AggregationResult,
) -> dict:
    """
    Call the ReportAgent and return structured report data.

    Returns dict matching SimulationReport fields:
    {
        "executive_summary": str,
        "signal": str,
        "final_probability": float,
        "bull_case": str,
        "bear_case": str,
        "key_uncertainties": list[str],
        "consensus_analysis": str,
        "recommended_action": str,
        "report_markdown": str,
        ...
    }

    TODO: Implement in Week 5.
    """
    raise NotImplementedError("Report agent — implement in Week 5")
