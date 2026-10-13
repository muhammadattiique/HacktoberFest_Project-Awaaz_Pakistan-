"""FEAT-002 regression tests for multi-item complaint parsing.

Covers:
  * BUG 1 — the phantom/fabricated "Chicken" item. A 7-commodity Roman-Urdu
    complaint must yield EXACTLY those 7 commodities and never a Chicken row,
    even though the few-shot prompt is chicken-heavy and the loose alias match
    used to let a stray token fabricate one.
  * BUG 2 — under-rate (compliant) items must be kept but never flagged High,
    and the highest-overcharge item must sort first.
  * Count invariants — a 1-item complaint yields exactly 1 record; a complaint
    with no identifiable commodity yields exactly 1 "Unspecified" record.

The 7-item assertions exercise the LIVE rule+LLM path (local Ollama at
http://localhost:11434). The count/under-rate invariants stub the LLM so they
are deterministic on any machine.
"""

import pytest
from unittest.mock import patch

from ai_pipeline import ai_pipeline
from services.rates import rate_service


# Exact 7-item regression input from the task.
SEVEN_ITEM_TEXT = (
    "Bhai sahab, Raja Bazaar Rawalpindi mein Madina Cash & Carry wala dukandar "
    "aaloo 150 rupay kilo, pyaaz 200 rupay kilo, tamatar 250 rupay kilo, "
    "chini 180 rupay kilo, atta 120 rupay kilo, chawal 400 rupay kilo aur "
    "doodh 280 rupay liter bech raha hai. Ye log zabardasti mehngai kar ke "
    "awaam ko loot rahe hain. Please is ke khilaf action lein."
)

EXPECTED_IDS = {
    "aloo",
    "pyaaz",
    "tamatar",
    "chini",
    "atta_kg",
    "chawal_basmati",
    "doodh",
}


def test_seven_item_input_yields_exactly_seven_no_chicken():
    """The 7-commodity input resolves to exactly those 7 ids and NO Chicken row.

    Live rule+LLM path (Ollama at :11434). The merge de-dupes by canonical id,
    so even if the LLM emits duplicates or a hallucinated chicken item it must
    not survive into the final list.
    """
    items = ai_pipeline.parse_complaint_items(SEVEN_ITEM_TEXT)
    ids = {it.get("item_canonical_id") for it in items}

    assert ids == EXPECTED_IDS, f"Expected {EXPECTED_IDS}, got {ids}"
    assert len(items) == 7, f"Expected exactly 7 items, got {len(items)}"

    # No chicken row, by canonical id or by (mis)named item.
    assert "chicken_meat" not in ids
    assert "chicken_live" not in ids
    for it in items:
        assert "chicken" not in (it.get("item_name") or "").lower(), it


def test_find_all_items_does_not_fabricate_chicken():
    """Word-boundary alias matching never fabricates a commodity from a
    substring of an unrelated word."""
    # None of these words contain a genuine commodity token.
    ids = {cid for cid, _ in rate_service.find_all_items("mehngai zabardasti dukandar")}
    assert "chicken_meat" not in ids
    assert "chicken_live" not in ids
    assert ids == set()


def test_single_item_complaint_yields_exactly_one():
    """A 1-commodity complaint returns exactly one record (LLM stubbed)."""
    with patch.object(ai_pipeline, "_call_ollama_llm_multi", return_value=None):
        items = ai_pipeline.parse_complaint_items("Aloo 180 rupay kilo bech raha hai dukandar.")
    assert len(items) == 1
    assert items[0]["item_canonical_id"] == "aloo"


def test_zero_identifiable_item_yields_one_unspecified():
    """A complaint with no resolvable commodity returns one 'Unspecified' row."""
    with patch.object(ai_pipeline, "_call_ollama_llm_multi", return_value=None):
        items = ai_pipeline.parse_complaint_items("Yahan bohat buri loot machi hui hai.")
    assert len(items) == 1
    assert items[0]["item_canonical_id"] is None
    assert "Unspecified" in (items[0]["item_name"] or "")


def test_under_rate_item_kept_compliant_not_high():
    """An item priced at/below the official rate is kept, compliant, never High."""
    with patch.object(ai_pipeline, "_call_ollama_llm_multi", return_value=None):
        # Potato official is 100; reporting 80 is UNDER the rate (compliant).
        items = ai_pipeline.parse_complaint_items("Aloo 80 rupay kilo bik raha hai.")
    by_id = {it["item_canonical_id"]: it for it in items}
    assert "aloo" in by_id
    potato = by_id["aloo"]
    assert potato["percentage_overcharge"] <= 0
    assert potato["urgency"] != "High"


def test_under_rate_llm_high_hint_is_overridden():
    """Even if the LLM insists an under-rate item is High, it is forced down."""
    fake_llm = [{
        "item_name": "Potato",
        "reported_price": 80,
        "category": "PERA - Overpricing",
        "urgency": "High",  # wrong — item is under the official rate
        "detected_language": "Roman Urdu",
        "native_response": "Aap ki shikayat darj kar li gayi hai.",
    }]
    with patch.object(ai_pipeline, "_call_ollama_llm_multi", return_value=fake_llm):
        items = ai_pipeline.parse_complaint_items("Aloo 80 rupay kilo bik raha hai.")
    by_id = {it["item_canonical_id"]: it for it in items}
    assert "aloo" in by_id
    assert by_id["aloo"]["percentage_overcharge"] <= 0
    assert by_id["aloo"]["urgency"] != "High"


def test_highest_overcharge_sorts_first():
    """After the existing overcharge-desc sort the biggest violation is first,
    and an under-rate item never leads."""
    with patch.object(ai_pipeline, "_call_ollama_llm_multi", return_value=None):
        # Aloo 80 is under-rate (compliant); pyaaz 200 is +66.7% (violation).
        items = ai_pipeline.parse_complaint_items(
            "Aloo 80 rupay kilo bik raha hai. Pyaaz bhi 200 rupay kilo le raha hai."
        )
    assert items[0]["item_canonical_id"] == "pyaaz"
    assert items[0]["percentage_overcharge"] > 0
