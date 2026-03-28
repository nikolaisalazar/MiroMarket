"""
Context builder — the prompt engineering layer.

Every agent's output quality depends on what goes into this module.
It assembles the system and user prompts for a given (market, persona) pair.

Architecture note
-----------------
Prompts are split into two distinct layers that must never be mixed:

  system prompt  →  who the agent *is*
                    (persona identity + epistemic style framing + output schema)

  user prompt    →  what the agent is asked to *analyse*
                    (market facts + task instruction)

Keeping these separate ensures that a persona's reasoning style does not
contaminate the market data it receives, and that swapping personas across
the same market context never requires touching the market prompt.

Uncertainty representation
--------------------------
Each agent reports a point estimate (``probability``) plus a 90% credible
interval (``lower_bound``, ``upper_bound``).  Conceptually these bounds
are the edges of a Beta-distributed belief over the resolution probability:
the agent believes with 90% subjective probability that the true resolution
probability lies within [lower_bound, upper_bound].

In practice the LLM generates these heuristically rather than from an
analytically derived Beta distribution.  The aggregator (aggregator.py)
works in logit space, which implies a logit-normal distribution — consistent
with but not identical to the Beta framing.  The bounds are therefore used
for display and uncertainty measurement only; core aggregation uses only
``probability`` and ``credibility_weight``.

On self-correction and bias naming
-----------------------------------
The ``self_correction`` field (present in the AgentEstimate schema) is
intentionally *not* requested here.  Bias correction is instead achieved
through three structural mechanisms:

  1. Epistemic diversity   — five distinct reasoning styles naturally
                             disagree, covering the bias space collectively.
  2. Inter-agent debate    — deliberative mode lets agents challenge each
                             other's reasoning directly (Phase V2).
  3. Credibility weighting — the aggregator discounts systematically
                             overconfident personas at the population level.

Asking agents to self-report their own biases mid-estimate risks
suppressing the very persona-consistent behaviour the simulation depends
on.  The known-bias list on each persona is preserved for aggregation
weighting and future analysis but is not injected into prompts.
"""

from __future__ import annotations

from app.models.market import Market
from app.models.persona import AgentPersona, EpistemicStyle

# ---------------------------------------------------------------------------
# Epistemic style framing paragraphs
#
# One paragraph per EpistemicStyle, inserted verbatim into the system prompt.
# Each paragraph lets the agent inhabit its reasoning style naturally rather
# than being told to "act like" a type.  Calibration tendencies (e.g.
# contrarian → overconfident, consensus → underconfident) are encoded
# implicitly — naming specific cognitive biases would risk suppressing the
# very behaviour the simulation relies on.
# ---------------------------------------------------------------------------
_EPISTEMIC_FRAMINGS: dict[EpistemicStyle, str] = {
    EpistemicStyle.bayesian: (
        "You reason using Bayesian inference. You begin every analysis by "
        "establishing a prior probability anchored to historical base rates "
        "and reference classes, then update incrementally as new evidence "
        "arrives. You are resistant to narrative reasoning that lacks "
        "probabilistic grounding and rarely shift your estimate dramatically "
        "on a single data point. Your prior is your anchor; evidence is what "
        "moves it — not stories."
    ),
    EpistemicStyle.frequentist: (
        "You ground all estimates in historical frequency data and empirical "
        "base rates. You distrust arguments that lack statistical backing and "
        "anchor strongly to long-run averages. You are skeptical of "
        "regime-change arguments unless they are supported by substantial "
        "quantitative evidence. Before accepting any claim, you ask: "
        "'How often has this happened before, under similar conditions?'"
    ),
    EpistemicStyle.contrarian: (
        "You systematically fade consensus. You believe crowded trades are "
        "the most dangerous and that widely-held views are already priced in. "
        "You are drawn to differentiated, non-consensus positions and take "
        "strong stances when you believe the market is mispriced. You look "
        "for the argument the crowd is ignoring and build your estimate "
        "around it."
    ),
    EpistemicStyle.consensus: (
        "You weight expert consensus and existing prediction-market prices "
        "heavily in your analysis. You defer to the wisdom of crowds and "
        "established forecasters, and you rarely take strong independent "
        "positions. You treat the current market price as a highly "
        "informative signal — fading it requires a compelling reason you "
        "can articulate clearly."
    ),
    EpistemicStyle.heuristic: (
        "You rely on pattern recognition, mental shortcuts, and fast-thinking "
        "heuristics developed through experience. You are decisive and "
        "action-oriented, drawing on vivid recent examples and market "
        "signals. You are sensitive to news flow, momentum, and narrative "
        "shifts. You trust your pattern-matching ability and act on it with "
        "confidence."
    ),
    EpistemicStyle.custom: (
        # Placeholder only — build_system_prompt() bypasses this entry entirely
        # when persona.custom_system_prompt is set, which it always is for custom
        # personas.  This entry exists solely to keep _EPISTEMIC_FRAMINGS in sync
        # with the EpistemicStyle enum so the structural guard tests don't fail.
        "You are an analytical forecasting agent applying your own reasoning methodology."
    ),
}


# ---------------------------------------------------------------------------
# Output schema instructions
#
# Embedded verbatim in the system prompt so the model sees the contract
# once, clearly.  The user prompt adds a brief JSON-only reminder.
#
# Probability values are clamped to [0.01, 0.99] to avoid log(0) during
# the logit-space aggregation that follows.
#
# lower_bound / upper_bound define a 90% credible interval: the agent
# asserts a 90% subjective probability that the market's true resolution
# probability falls within this range.
# ---------------------------------------------------------------------------
_OUTPUT_SCHEMA = """\
Respond with a single JSON object — no markdown fences, no prose outside \
the object.  Use this exact schema:

{
  "probability":      <float, 0.01–0.99>,   // point estimate: P(market resolves YES)
  "confidence":       <float, 0.0–1.0>,     // your certainty in the probability estimate itself
  "lower_bound":      <float, 0.01–0.99>,   // lower edge of your 90% credible interval
  "upper_bound":      <float, 0.01–0.99>,   // upper edge of your 90% credible interval
  "reasoning":        <string>,             // 2–4 paragraphs of analytical chain-of-thought
  "key_factors":      [<string>, ...],      // 3–5 strings: top drivers of your estimate
  "dissenting_notes": <string>              // what evidence or events would cause significant revision
}

Constraints:
  • lower_bound < probability < upper_bound
  • A tighter credible interval implies higher confidence; be honest about uncertainty.
  • Do not output any text outside the JSON object.\
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_base_context(market: Market) -> str:
    """
    Format the relevant market fields into a structured text block.

    This string is shared across all agents in a simulation run and is
    placed in the *user* prompt — never the system prompt — so that
    swapping personas never requires touching the market data.

    Returns a plain-text block that is human-readable and LLM-friendly.
    """
    yes_price = float(market.current_yes_price)
    no_price = float(market.current_no_price)
    implied_pct = yes_price * 100

    volume_str = (
        f"${float(market.volume_24h):,.2f}"
        if market.volume_24h is not None
        else "N/A"
    )
    oi_str = (
        f"${float(market.open_interest):,.2f}"
        if market.open_interest is not None
        else "N/A"
    )
    fetched_str = (
        market.fetched_at.isoformat()
        if market.fetched_at is not None
        else "unknown"
    )

    lines = [
        f"Market ID:  {market.external_id}",
        f"Title:      {market.title}",
        f"Category:   {market.category}",
        "",
        "Resolution criteria:",
        f"  {market.description}",
        "",
        "Current market prices:",
        f"  YES: {yes_price:.4f}   NO: {no_price:.4f}",
        f"  Implied probability (YES): {implied_pct:.1f}%",
        "",
        "Market activity:",
        f"  24h Volume:    {volume_str}",
        f"  Open Interest: {oi_str}",
        "",
        f"Data as of: {fetched_str}",
    ]
    return "\n".join(lines)


def build_system_prompt(persona: AgentPersona) -> str:
    """
    Build the system prompt that establishes the agent's identity.

    Structure:
        1. Role declaration     — name and purpose
        2. Epistemic framing    — style-specific paragraph that the agent
                                  inhabits naturally; calibration tendencies
                                  are encoded implicitly (no bias naming)
        3. Domain expertise     — areas of specialist knowledge
        4. Character narrative  — the persona's longer description
        5. Output schema        — exact JSON contract the agent must follow

    The system prompt intentionally contains no market data.  Market facts
    live in the user prompt so that persona identity and market analysis
    remain cleanly separated.

    Custom personas (epistemic_style == EpistemicStyle.custom) supply their
    own identity via custom_system_prompt.  The output schema is always
    appended — the aggregator's JSON contract is non-negotiable regardless
    of who authored the prompt.
    """
    # --- Custom persona path ------------------------------------------------
    # The user has authored the full identity section.  We only append the
    # output schema so the aggregator's JSON contract is always enforced.
    if persona.custom_system_prompt:
        return "\n".join([
            persona.custom_system_prompt,
            "",
            "---",
            "",
            _OUTPUT_SCHEMA,
        ])

    # --- Seed persona path --------------------------------------------------
    framing = _EPISTEMIC_FRAMINGS[persona.epistemic_style]
    expertise = (
        ", ".join(persona.domain_expertise)
        if persona.domain_expertise
        else "general markets"
    )

    sections = [
        f"You are {persona.name}, a specialized forecasting agent.",
        "",
        framing,
        "",
        f"Your domain expertise spans: {expertise}.",
        "",
        persona.description or "",
        "",
        "---",
        "",
        _OUTPUT_SCHEMA,
    ]
    return "\n".join(sections)


def build_user_prompt(market: Market, persona: AgentPersona, base_context: str) -> str:
    """
    Build the user prompt containing market facts and the task instruction.

    ``base_context`` must be the string returned by ``build_base_context(market)``.
    It is embedded verbatim so callers can compute it once and reuse it
    across all agents in a simulation run.

    ``persona`` is accepted here for future use — deliberative mode (Phase V2)
    will inject peer estimates in a persona-aware way — but is intentionally
    unused in the MVP independent mode.  All agents in an independent
    simulation receive an identical user prompt.
    """
    lines = [
        "## Market data",
        "",
        base_context,
        "",
        "---",
        "",
        "## Your task",
        "",
        (
            "Based on the market data above, produce your probability estimate "
            "that this market resolves YES."
        ),
        "",
        (
            "Apply your analytical approach rigorously. Consider the current "
            "market price as one signal among many — do not simply anchor to it. "
            "Work through the resolution criteria carefully before committing "
            "to a number."
        ),
        "",
        "Respond with valid JSON only, following the schema in your instructions.",
    ]
    return "\n".join(lines)
