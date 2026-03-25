"""
Aggregator — combines N agent probability estimates into a single signal.

Uses logit-space weighted mean to avoid the boundary compression problem
of raw probability averaging (e.g., averaging 0.9 and 0.95 in raw space
gives 0.925, but in logit space it correctly accounts for the asymmetry
near the boundaries).

Also derives the trading signal by comparing the aggregate to the current
market price.

TODO: Implement in Week 4.
"""
from dataclasses import dataclass


@dataclass
class AggregationResult:
    aggregate_probability: float
    std_dev: float
    consensus_level: str        # "high" | "medium" | "low" | "contested"
    min_estimate: float
    max_estimate: float
    signal: str                 # "strong_buy" | "buy" | "hold" | "sell" | "strong_sell"
    edge: float                 # aggregate_probability - market_price
    signal_strength: float      # 0.0 – 1.0, normalized magnitude of the edge


def aggregate_estimates(
    estimates: list,            # list of AgentEstimate ORM objects
    market_price: float,
) -> AggregationResult:
    """
    Main aggregation function.

    Algorithm:
    1. Clip probabilities to [0.02, 0.98] to avoid logit(0/1) = ±inf
    2. Convert to logit space: logit(p) = log(p / (1-p))
    3. Compute weighted mean in logit space using persona.credibility_weight
    4. Apply domain-specialist boost if applicable
    5. Convert back: expit(logit_mean)
    6. Compute std_dev, consensus_level, signal

    TODO: Implement in Week 4.
    """
    raise NotImplementedError("Aggregator — implement in Week 4")


# Signal thresholds
# Edge = aggregate_probability - market_price
# > +0.10  → strong_buy
# > +0.04  → buy
# > -0.04  → hold
# > -0.10  → sell
# <= -0.10 → strong_sell
SIGNAL_THRESHOLDS = {
    "strong_buy":  0.10,
    "buy":         0.04,
    "hold":       -0.04,
    "sell":       -0.10,
}

# Consensus thresholds (standard deviation of raw estimates)
CONSENSUS_THRESHOLDS = {
    "high":      0.08,
    "medium":    0.15,
    "low":       0.22,
    # > 0.22 → "contested"
}
