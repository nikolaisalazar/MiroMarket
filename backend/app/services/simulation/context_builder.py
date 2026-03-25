"""
Context builder — the prompt engineering layer.

Every agent's output quality depends on what goes into this module.
Builds the system and user prompts for a given (market, persona) pair.

TODO: Implement in Week 3.
"""


def build_base_context(market) -> dict:
    """
    Extract the relevant market fields into a clean context dict.
    This is shared across all agents in a simulation run.
    """
    raise NotImplementedError


def build_system_prompt(persona) -> str:
    """
    Build the system prompt that establishes the agent's identity,
    epistemic style, domain expertise, and known biases.
    Agents are explicitly shown their own biases so they can self-correct.
    """
    raise NotImplementedError


def build_user_prompt(market, persona, base_context: dict) -> str:
    """
    Build the user prompt containing market details and the JSON
    output schema the agent must follow.

    Expected JSON output from each agent:
    {
        "probability": float,           # 0.0 – 1.0
        "confidence": float,            # 0.0 – 1.0
        "lower_bound": float,           # 90% CI
        "upper_bound": float,
        "reasoning": str,               # 2-4 paragraphs of chain-of-thought
        "key_factors": [str],           # top factors driving the estimate
        "dissenting_notes": str,        # what would cause significant revision
        "self_correction": str          # how known biases might be affecting this
    }
    """
    raise NotImplementedError
