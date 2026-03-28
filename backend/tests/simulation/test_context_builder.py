"""
Tests for app.services.simulation.context_builder.

These are pure-function tests — no LLM calls, no database writes.
The ``sample_market`` and ``sample_personas`` fixtures (defined in
tests/simulation/conftest.py) provide realistic ORM objects backed by
an in-memory SQLite database.

Test organisation
-----------------
  TestBuildBaseContext        — market facts are correctly formatted
  TestBuildBaseContextNone    — optional fields handled gracefully when None
  TestBuildSystemPrompt       — persona identity + epistemic framing + schema
  TestBuildSystemPromptGuards — structural safety (enum/dict completeness)
  TestBuildUserPrompt         — market data + task instruction; separation check
"""

import types

import pytest

from app.models.persona import EpistemicStyle
from app.services.simulation.context_builder import (
    _EPISTEMIC_FRAMINGS,
    build_base_context,
    build_system_prompt,
    build_user_prompt,
)


# ===========================================================================
# build_base_context
# ===========================================================================


class TestBuildBaseContext:
    """build_base_context(market) → structured market facts as a plain-text string."""

    def test_returns_string(self, sample_market):
        assert isinstance(build_base_context(sample_market), str)

    def test_contains_external_id(self, sample_market):
        assert sample_market.external_id in build_base_context(sample_market)

    def test_contains_title(self, sample_market):
        assert sample_market.title in build_base_context(sample_market)

    def test_contains_category(self, sample_market):
        assert sample_market.category in build_base_context(sample_market)

    def test_contains_yes_price(self, sample_market):
        # current_yes_price = 0.6200 → formatted as "0.6200"
        assert "0.6200" in build_base_context(sample_market)

    def test_contains_no_price(self, sample_market):
        # current_no_price = 0.3800 → formatted as "0.3800"
        assert "0.3800" in build_base_context(sample_market)

    def test_contains_implied_probability_percentage(self, sample_market):
        # 0.6200 × 100 = 62.0 → "62.0%"
        assert "62.0%" in build_base_context(sample_market)

    def test_contains_volume(self, sample_market):
        # volume_24h = 125000.00 → "$125,000.00"
        assert "125,000" in build_base_context(sample_market)

    def test_contains_open_interest(self, sample_market):
        # open_interest = 890000.00 → "$890,000.00"
        assert "890,000" in build_base_context(sample_market)

    def test_contains_description(self, sample_market):
        # Partial match on a distinctive phrase from the description.
        assert "exceeds $100,000" in build_base_context(sample_market)

    def test_contains_data_freshness_label(self, sample_market):
        # fetched_at is rendered as an ISO 8601 string under this label.
        assert "Data as of:" in build_base_context(sample_market)

    def test_does_not_contain_json(self, sample_market):
        # Context is plain text, not JSON — keeps it readable and token-efficient.
        result = build_base_context(sample_market)
        assert result.strip()[0] != "{"


# ===========================================================================
# build_system_prompt
# ===========================================================================


class TestBuildSystemPrompt:
    """build_system_prompt(persona) → system prompt string with identity + schema."""

    def test_returns_string(self, sample_personas):
        assert isinstance(build_system_prompt(sample_personas[0]), str)

    def test_contains_persona_name(self, sample_personas):
        for persona in sample_personas:
            assert persona.name in build_system_prompt(persona)

    def test_contains_all_domain_expertise_items(self, sample_personas):
        bayesian = sample_personas[0]
        result = build_system_prompt(bayesian)
        for domain in bayesian.domain_expertise:
            assert domain in result, f"Domain '{domain}' missing from system prompt"

    def test_contains_persona_description(self, sample_personas):
        bayesian = sample_personas[0]
        # Distinctive phrase from _PERSONA_SEEDS description.
        assert "Bayesian updating" in build_system_prompt(bayesian)

    # --- JSON output schema -------------------------------------------------

    def test_contains_all_schema_fields(self, sample_personas):
        required_fields = (
            "probability",
            "confidence",
            "lower_bound",
            "upper_bound",
            "reasoning",
            "key_factors",
            "dissenting_notes",
        )
        result = build_system_prompt(sample_personas[0])
        for field in required_fields:
            assert field in result, f"Schema field '{field}' missing from system prompt"

    def test_does_not_request_self_correction(self, sample_personas):
        """
        self_correction is omitted from prompts by design.
        Bias correction is handled structurally (epistemic diversity,
        inter-agent debate, credibility weighting) rather than via
        self-reporting mid-estimate.
        """
        for persona in sample_personas:
            assert "self_correction" not in build_system_prompt(persona)

    def test_mentions_credible_interval(self, sample_personas):
        # The 90% CI framing should appear so agents understand the bounds semantics.
        result = build_system_prompt(sample_personas[0])
        assert "90%" in result

    def test_probability_clamp_mentioned(self, sample_personas):
        # Agents must know to avoid 0 and 1 (log(0) guard for logit aggregation).
        result = build_system_prompt(sample_personas[0])
        assert "0.01" in result and "0.99" in result

    # --- Epistemic style framing --------------------------------------------

    def test_bayesian_framing(self, sample_personas):
        # personas[0] = bayesian-updater
        result = build_system_prompt(sample_personas[0])
        assert "Bayesian" in result or "prior" in result

    def test_frequentist_framing(self, sample_personas):
        # personas[1] = frequentist-analyst
        result = build_system_prompt(sample_personas[1])
        assert "base rates" in result or "frequency" in result.lower()

    def test_contrarian_framing(self, sample_personas):
        # personas[2] = contrarian-trader
        result = build_system_prompt(sample_personas[2])
        assert "consensus" in result or "fade" in result

    def test_consensus_framing(self, sample_personas):
        # personas[3] = consensus-tracker
        result = build_system_prompt(sample_personas[3])
        assert "consensus" in result or "wisdom of crowds" in result

    def test_heuristic_framing(self, sample_personas):
        # personas[4] = heuristic-trader
        result = build_system_prompt(sample_personas[4])
        assert "pattern" in result or "heuristic" in result.lower()

    def test_all_epistemic_styles_produce_distinct_prompts(self, sample_personas):
        """Five personas with different epistemic styles must yield five distinct prompts."""
        prompts = [build_system_prompt(p) for p in sample_personas]
        assert len(set(prompts)) == 5

    # --- Separation guarantee -----------------------------------------------

    def test_market_data_absent_from_system_prompt(self, sample_personas, sample_market):
        """
        System prompt must never embed market-specific data.
        Market facts belong in the user prompt only.
        """
        for persona in sample_personas:
            result = build_system_prompt(persona)
            assert sample_market.title not in result
            assert sample_market.external_id not in result


# ===========================================================================
# build_user_prompt
# ===========================================================================


class TestBuildUserPrompt:
    """build_user_prompt(market, persona, base_context) → task prompt with market data."""

    def test_returns_string(self, sample_market, sample_personas):
        ctx = build_base_context(sample_market)
        assert isinstance(build_user_prompt(sample_market, sample_personas[0], ctx), str)

    def test_contains_base_context_verbatim(self, sample_market, sample_personas):
        ctx = build_base_context(sample_market)
        result = build_user_prompt(sample_market, sample_personas[0], ctx)
        assert ctx in result

    def test_contains_task_instruction(self, sample_market, sample_personas):
        ctx = build_base_context(sample_market)
        result = build_user_prompt(sample_market, sample_personas[0], ctx)
        assert "resolves YES" in result

    def test_requests_json_output(self, sample_market, sample_personas):
        ctx = build_base_context(sample_market)
        result = build_user_prompt(sample_market, sample_personas[0], ctx)
        assert "JSON" in result

    def test_persona_identity_absent_from_user_prompt(self, sample_market, sample_personas):
        """
        User prompt must not contain persona identity content.
        The system and user prompts must remain cleanly separated:
        system = who the agent is; user = what it is asked to analyse.
        """
        persona = sample_personas[0]  # bayesian-updater
        ctx = build_base_context(sample_market)
        user_prompt = build_user_prompt(sample_market, persona, ctx)

        # Distinctive phrases from the bayesian system prompt must not appear.
        assert "Bayesian inference" not in user_prompt
        assert "base-rate prior" not in user_prompt

    def test_user_prompts_identical_across_personas(self, sample_market, sample_personas):
        """
        In independent mode all agents receive the same market data.
        The user prompt must not vary by persona (persona variance lives
        entirely in the system prompt).
        """
        ctx = build_base_context(sample_market)
        prompts = [
            build_user_prompt(sample_market, p, ctx) for p in sample_personas
        ]
        assert len(set(prompts)) == 1, (
            "User prompts differ across personas — persona-specific content "
            "must stay in the system prompt, not the user prompt."
        )


# ===========================================================================
# build_base_context — None-value paths
# ===========================================================================


def _market_stub(**overrides):
    """
    Return a minimal market-like namespace for testing None-value paths.

    build_base_context only reads attributes — it never calls SQLAlchemy
    methods — so a SimpleNamespace is sufficient and avoids the overhead
    of a database fixture for these edge-case tests.
    """
    defaults = dict(
        external_id="KXTEST-001",
        title="Test market",
        category="test",
        description="Resolves YES if the test condition is met.",
        current_yes_price=0.60,
        current_no_price=0.40,
        volume_24h=None,
        open_interest=None,
        fetched_at=None,
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


class TestBuildBaseContextNone:
    """
    Regression guards for the None-value paths in build_base_context.

    These tests exist to prevent a future refactor from accidentally
    removing the None guards and turning a graceful fallback into a crash.
    If a market is ingested without volume data, the context must still
    be well-formed rather than raising a TypeError.
    """

    def test_none_volume_renders_na(self):
        market = _market_stub(volume_24h=None)
        result = build_base_context(market)
        assert "N/A" in result

    def test_none_open_interest_renders_na(self):
        market = _market_stub(open_interest=None)
        result = build_base_context(market)
        assert "N/A" in result

    def test_none_fetched_at_renders_unknown(self):
        market = _market_stub(fetched_at=None)
        result = build_base_context(market)
        assert "unknown" in result

    def test_all_none_optional_fields_still_returns_string(self):
        """All three optional fields None simultaneously — function must not crash."""
        market = _market_stub(volume_24h=None, open_interest=None, fetched_at=None)
        result = build_base_context(market)
        assert isinstance(result, str)
        assert market.title in result


# ===========================================================================
# build_system_prompt — structural safety guards
# ===========================================================================


class TestBuildSystemPromptGuards:
    """
    Structural safety tests that are independent of any specific persona.

    These guard against the _EPISTEMIC_FRAMINGS dict falling out of sync
    with the EpistemicStyle enum.  If a new epistemic style is added to
    the enum without a corresponding entry in the framings dict,
    build_system_prompt will raise a KeyError at runtime.  This test
    catches that at commit time instead.
    """

    def test_all_epistemic_styles_have_framings(self):
        """
        Every value in EpistemicStyle must have a matching entry in
        _EPISTEMIC_FRAMINGS.  Failure here means a new style was added
        to the enum without updating the prompt framing dict.
        """
        missing = set(EpistemicStyle) - set(_EPISTEMIC_FRAMINGS.keys())
        assert not missing, (
            f"EpistemicStyle values missing from _EPISTEMIC_FRAMINGS: {missing}. "
            "Add a framing paragraph for each new style in context_builder.py."
        )

    def test_no_extra_framings_without_enum_value(self):
        """
        Every entry in _EPISTEMIC_FRAMINGS must correspond to a real
        EpistemicStyle value.  Orphaned entries indicate a stale framing
        whose enum value was removed.
        """
        orphaned = set(_EPISTEMIC_FRAMINGS.keys()) - set(EpistemicStyle)
        assert not orphaned, (
            f"_EPISTEMIC_FRAMINGS contains keys with no matching EpistemicStyle: "
            f"{orphaned}. Remove or rename the stale entry."
        )
