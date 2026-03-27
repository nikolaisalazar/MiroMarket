"""
Unit tests for normalize_market().

These tests are pure — no DB, no HTTP, no async. They verify that the
normalization layer correctly converts Kalshi's raw API response format
into the field shapes our Market model expects.

Edge cases covered:
- Standard open market with full bid/ask data
- Missing bid/ask (illiquid market — prices should be None, not 0)
- Status mapping for all three Kalshi states
- Resolution date parsing (Z suffix, +00:00 suffix, missing)
- Title fallback chain (title → subtitle → ticker)
- raw_metadata is the full original dict, unmodified
"""
from decimal import Decimal

from app.models.market import MarketStatus
from app.services.ingestion.ingestion_service import normalize_market


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_raw(**overrides) -> dict:
    """Return a minimal valid Kalshi market dict, with optional field overrides."""
    base = {
        "ticker":       "FED-RATE-JULY26",
        "title":        "Will the Fed cut rates before July 2026?",
        "subtitle":     "Federal Reserve interest rate decision",
        "category":     "economics",
        "close_time":   "2026-07-01T00:00:00Z",
        "yes_ask":      36,
        "yes_bid":      32,
        "no_ask":       68,
        "no_bid":       64,
        "volume_24h":   15_000,
        "open_interest":42_000,
        "status":       "open",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_external_id_is_ticker():
    result = normalize_market(make_raw())
    assert result["external_id"] == "FED-RATE-JULY26"


def test_mid_price_calculation():
    # yes_mid = (36 + 32) / 2 / 100 = 0.34
    # no_mid  = (68 + 64) / 2 / 100 = 0.66
    result = normalize_market(make_raw())
    assert result["current_yes_price"] == 0.34
    assert result["current_no_price"]  == 0.66


def test_prices_sum_to_one_for_binary_market():
    # For a fair binary market yes_mid + no_mid should equal 1.0
    # (ignoring the spread). Here ask/bid are symmetric so it holds exactly.
    raw = make_raw(yes_ask=51, yes_bid=49, no_ask=51, no_bid=49)
    result = normalize_market(raw)
    assert result["current_yes_price"] == 0.50
    assert result["current_no_price"]  == 0.50


def test_title_and_description():
    result = normalize_market(make_raw())
    assert result["title"]       == "Will the Fed cut rates before July 2026?"
    assert result["description"] == "Federal Reserve interest rate decision"


def test_category_preserved():
    result = normalize_market(make_raw())
    assert result["category"] == "economics"


def test_volume_and_open_interest():
    result = normalize_market(make_raw())
    assert result["volume_24h"]    == 15_000
    assert result["open_interest"] == 42_000


def test_raw_metadata_is_original_dict():
    raw = make_raw()
    result = normalize_market(raw)
    assert result["raw_metadata"] is raw


def test_fetched_at_is_set():
    from datetime import timezone
    result = normalize_market(make_raw())
    assert result["fetched_at"] is not None
    assert result["fetched_at"].tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# Status mapping
# ---------------------------------------------------------------------------

def test_status_open():
    assert normalize_market(make_raw(status="open"))["status"] == MarketStatus.open


def test_status_closed():
    assert normalize_market(make_raw(status="closed"))["status"] == MarketStatus.closed


def test_status_settled_maps_to_resolved():
    assert normalize_market(make_raw(status="settled"))["status"] == MarketStatus.resolved


def test_status_finalized_maps_to_resolved():
    assert normalize_market(make_raw(status="finalized"))["status"] == MarketStatus.resolved


def test_unknown_status_defaults_to_open():
    assert normalize_market(make_raw(status="weird_future_status"))["status"] == MarketStatus.open


# ---------------------------------------------------------------------------
# Resolution date parsing
# ---------------------------------------------------------------------------

def test_resolution_date_parses_z_suffix():
    result = normalize_market(make_raw(close_time="2026-07-01T00:00:00Z"))
    rd = result["resolution_date"]
    assert rd is not None
    assert rd.year == 2026
    assert rd.month == 7
    assert rd.day == 1


def test_resolution_date_parses_offset():
    result = normalize_market(make_raw(close_time="2026-07-01T00:00:00+00:00"))
    assert result["resolution_date"] is not None


def test_resolution_date_missing_is_none():
    raw = make_raw()
    del raw["close_time"]
    assert normalize_market(raw)["resolution_date"] is None


def test_resolution_date_null_is_none():
    assert normalize_market(make_raw(close_time=None))["resolution_date"] is None


def test_resolution_date_falls_back_to_expiration_time():
    raw = make_raw()
    del raw["close_time"]
    raw["expiration_time"] = "2026-08-01T00:00:00Z"
    result = normalize_market(raw)
    assert result["resolution_date"].month == 8


# ---------------------------------------------------------------------------
# Price edge cases
# ---------------------------------------------------------------------------

def test_missing_bid_ask_yields_none_prices():
    raw = make_raw(yes_ask=0, yes_bid=0, no_ask=0, no_bid=0)
    result = normalize_market(raw)
    assert result["current_yes_price"] is None
    assert result["current_no_price"]  is None


def test_missing_bid_ask_keys_yields_none_prices():
    raw = make_raw()
    for key in ("yes_ask", "yes_bid", "no_ask", "no_bid"):
        raw.pop(key, None)
    result = normalize_market(raw)
    assert result["current_yes_price"] is None
    assert result["current_no_price"]  is None


def test_one_sided_market_still_computes_mid():
    # Only ask side available (no bids yet)
    raw = make_raw(yes_ask=40, yes_bid=0, no_ask=60, no_bid=0)
    result = normalize_market(raw)
    assert result["current_yes_price"] == 0.20  # (40 + 0) / 2 / 100


# ---------------------------------------------------------------------------
# Title fallback chain
# ---------------------------------------------------------------------------

def test_title_falls_back_to_subtitle_when_title_missing():
    raw = make_raw()
    del raw["title"]
    result = normalize_market(raw)
    assert result["title"] == "Federal Reserve interest rate decision"


def test_title_falls_back_to_ticker_when_both_missing():
    raw = make_raw()
    del raw["title"]
    del raw["subtitle"]
    result = normalize_market(raw)
    assert result["title"] == "FED-RATE-JULY26"
