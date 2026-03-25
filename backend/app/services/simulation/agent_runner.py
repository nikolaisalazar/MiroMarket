"""
Agent runner — invokes a single agent via LiteLLM.

Handles:
- Prompt construction (via context_builder)
- LiteLLM API call (provider-agnostic)
- JSON response parsing with retry logic
- Graceful fallback on parse failure

Model is set via AGENT_MODEL in config.py. Swap freely:
  "openai/gpt-4o-mini"
  "anthropic/claude-haiku-3-5"
  "together_ai/Qwen/Qwen2.5-72B-Instruct"
  "groq/llama-3.1-70b-versatile"
  "ollama/llama3.2"  (local, free)

TODO: Implement in Week 3.
"""
import time
import litellm

from app.config import settings
from app.services.simulation.context_builder import build_system_prompt, build_user_prompt


async def run_agent(market, persona, base_context: dict) -> dict:
    """
    Run a single agent and return its probability estimate as a dict.

    Returns:
        {
            "probability": float,
            "confidence": float,
            "lower_bound": float,
            "upper_bound": float,
            "reasoning": str,
            "key_factors": list[str],
            "dissenting_notes": str,
            "self_correction": str,
            "tokens_used": int,
            "latency_ms": int,
            "parse_failed": bool,
        }
    """
    raise NotImplementedError("Agent runner — implement in Week 3")


def _parse_response(raw: str) -> dict:
    """
    Parse the JSON response from the agent.
    Retries once with stricter instructions on failure.
    Falls back to regex probability extraction as last resort.
    """
    raise NotImplementedError
