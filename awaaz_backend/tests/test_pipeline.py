"""Deterministic tests for the hybrid AI pipeline.

These tests exercise the *rule engine and repair logic*, which is the part that
must behave identically on every machine. The local Ollama LLM is deliberately
disabled for the whole module: when Ollama happens to be running (as it is on a
developer machine or in the demo environment) a 1.5B model will happily answer a
Roman-Urdu prompt in English, which makes assertions on `native_response`
flaky. The LLM path itself is covered by the explicit fallback test below.
"""

import pytest
from unittest.mock import patch

from ai_pipeline import ai_pipeline

# Force the pipeline down its rule-based path for every test in this module.
# Autouse keeps the intent obvious and prevents accidental live-network calls.
@pytest.fixture(autouse=True)
def _disable_live_llm():
    with patch.object(ai_pipeline, "_call_ollama_llm", return_value=None):
        yield


def test_empty_transcript_handling():
    """Verify empty or whitespace transcript returns safe fallback with needs_review=True."""
    res = ai_pipeline.parse_complaint_text("")
    assert res is not None
    assert res["needs_review"] is True
    assert res["extraction_confidence"] == 0.0
    assert "دوبارہ" in res["native_response"]


def test_pipeline_overpricing_extraction_urdu():
    """Verify pipeline extracts commodity, price, and native response for Urdu complaint."""
    text = "آلو دو سو روپے کلو بیچ رہے ہیں جبکہ سرکاری لسٹ میں سو روپے ہے۔"
    res = ai_pipeline.parse_complaint_text(text)

    assert res["item_canonical_id"] == "aloo"
    assert res["reported_price"] == 200.0
    assert res["official_price"] == 100.0
    assert res["price_difference_pkr"] == 100.0
    assert res["percentage_overcharge"] == 100.0
    assert res["category"] == "PERA - Overpricing"
    assert res["urgency"] == "High"
    assert res["detected_language"] == "Urdu"
    assert "شکایت" in res["native_response"]


def test_pipeline_overpricing_extraction_roman_urdu():
    """Verify pipeline parses Roman Urdu code-switching with shop name & area."""
    text = "Bhai Raja Bazaar mein doodh 280 rupay liter de raha hai bohat loot machai hai."
    res = ai_pipeline.parse_complaint_text(text)

    assert res["item_canonical_id"] == "doodh"
    assert res["reported_price"] == 280.0
    assert res["official_price"] == 210.0
    assert res["category"] == "PERA - Overpricing"
    assert res["percentage_overcharge"] > 0
    assert "shikayat" in res["native_response"].lower()


def test_pipeline_food_safety_routing():
    """Verify complaints mentioning rotten food or illness route to PFA."""
    text = "Kharab aur baasi chicken ka salan khila rahe hain jis se pet kharab ho gaya hai."
    res = ai_pipeline.parse_complaint_text(text)

    assert res["category"] == "PFA - Food Safety"
    assert "Punjab Food Authority" in res["routing_agency"]
    assert res["urgency"] == "High"


def test_pipeline_food_safety_illness_is_high_urgency():
    """Illness caused by unsafe food must escalate to High urgency.

    Regression test: "pet kharab" (stomach upset) was previously classified as
    Medium even though it indicates real harm to citizens.
    """
    for text in (
        "Bachon ka pet kharab ho gaya hai is doodh se.",
        "Chemical mila hua ata bik raha hai.",
        "Keere lagay hain is daal mein.",
    ):
        res = ai_pipeline.parse_complaint_text(text)
        assert res["category"] == "PFA - Food Safety", text
        assert res["urgency"] == "High", text


def test_pipeline_food_safety_hygiene_stays_medium():
    """Untidy-but-harmless hygiene reports stay Medium (no false alarms)."""
    res = ai_pipeline.parse_complaint_text("Hotel ka kitchen bohat ganda aur unhygienic hai.")
    assert res["category"] == "PFA - Food Safety"
    assert res["urgency"] == "Medium"


def test_pipeline_municipal_infrastructure_routing():
    """Verify infrastructure issues route to CDA/WASA."""
    text = "G-9 Markaz school ke samne gutter ubal raha hai aur pani jama hai."
    res = ai_pipeline.parse_complaint_text(text)

    assert res["category"] == "Municipal - Infrastructure"
    assert "Capital Development Authority" in res["routing_agency"] or "WASA" in res["routing_agency"]


def test_pipeline_llm_failure_graceful_fallback():
    """Verify that when LLM returns invalid JSON or raises, the pipeline recovers seamlessly.

    The module-level fixture already stubs the LLM out; this test additionally
    proves the pipeline survives an exception (not just a None return).
    """
    with patch.object(ai_pipeline, "_call_ollama_llm", side_effect=RuntimeError("ollama down")):
        text = "Aloo 180 rupay kilo de raha hai dukandar."
        res = ai_pipeline.parse_complaint_text(text)

        assert res is not None
        assert res["item_canonical_id"] == "aloo"
        assert res["reported_price"] == 180.0
        assert res["category"] == "PERA - Overpricing"
        assert res["native_response"] is not None
        assert res["extraction_confidence"] > 0.0

