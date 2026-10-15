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


def test_english_comma_and_chain_each_item_gets_own_price():
    """BUG 1 regression — comma + ` and ` chained English clauses.

    "...potatoes at 150 ..., onions at 200 ..., tomatoes at 250 ... and sugar
    at 180 ..." must attribute EACH item the price in its OWN clause. The final
    " and sugar" pair used to collapse into tomato's clause, so sugar grabbed
    250 instead of its own 180. LLM is stubbed so this is deterministic and the
    rule-only clause attribution is exercised directly.
    """
    text = (
        "Hello sir, in Raja Bazaar the shopkeeper is selling potatoes at 150 "
        "rupees per kilo, onions at 200 rupees per kilo, tomatoes at 250 rupees "
        "per kilo and sugar at 180 rupees per kilo. The official rates are much "
        "lower. Please take action."
    )
    with patch.object(ai_pipeline, "_call_ollama_llm_multi", return_value=None):
        items = ai_pipeline.parse_complaint_items(text)
    by_id = {it["item_canonical_id"]: it for it in items}

    # "sugar" resolves to the canonical "chini" (Sugar) id.
    assert {"aloo", "pyaaz", "tamatar", "chini"}.issubset(by_id.keys()), by_id.keys()

    # Each item carries the price from its OWN clause.
    assert by_id["aloo"]["reported_price"] == 150.0
    assert by_id["pyaaz"]["reported_price"] == 200.0
    assert by_id["tamatar"]["reported_price"] == 250.0
    # The regression: sugar must be 180, NOT tomato's 250.
    assert by_id["chini"]["reported_price"] == 180.0, by_id["chini"]
    assert by_id["chini"]["percentage_overcharge"] == pytest.approx(28.6, abs=0.2)

    # BUG 2 — an English complaint gets an English acknowledgment, not Roman Urdu.
    for it in items:
        assert it["detected_language"] == "English", it
        ack = (it.get("native_response") or "").lower()
        assert "aap ki shikayat" not in ack, it
        assert "shukriya" not in ack, it


def test_aaloo_pyaaz_roman_driver_pyaaz_200_not_regressed():
    """BUG 1 must not regress the aaloo + pyaaz Roman case.

    "Pyaaz bhi 200 rupay kilo" trails its price in the next ` bhi ` clause, so
    pyaaz must still borrow the adjacent 200 and aaloo must keep its own 150.
    LLM stubbed so the clause-borrow logic is exercised directly.
    """
    text = "Aloo 150 rupay kilo bech raha hai. Pyaaz bhi 200 rupay kilo le raha hai."
    with patch.object(ai_pipeline, "_call_ollama_llm_multi", return_value=None):
        items = ai_pipeline.parse_complaint_items(text)
    by_id = {it["item_canonical_id"]: it for it in items}
    assert by_id["pyaaz"]["reported_price"] == 200.0, by_id["pyaaz"]
    assert by_id["aloo"]["reported_price"] == 150.0, by_id["aloo"]


def test_english_acknowledgment_is_english_not_roman_urdu():
    """BUG 2 regression — even if the LLM emits a Roman-Urdu acknowledgment for
    an English complaint, the stored native_response must be English."""
    fake_llm = [{
        "item_name": "Potato",
        "reported_price": 150,
        "category": "PERA - Overpricing",
        "urgency": "High",
        "detected_language": "English",
        # Model drift: Roman-Urdu reply on an English complaint.
        "native_response": "Aap ki shikayat darj kar li gayi hai. Shukriya.",
    }]
    text = "The shopkeeper is selling potatoes at 150 rupees per kilo. The official rate is lower."
    with patch.object(ai_pipeline, "_call_ollama_llm_multi", return_value=fake_llm):
        items = ai_pipeline.parse_complaint_items(text)
    potato = {it["item_canonical_id"]: it for it in items}["aloo"]
    assert potato["detected_language"] == "English"
    ack = potato["native_response"].lower()
    assert "aap ki shikayat" not in ack
    assert "thank you" in ack


def test_pashto_digit_chain_each_item_own_price():
    """BUG 1 regression — the Pashto connective ` او ` must split clauses so a
    later commodity cannot steal an earlier one's price.

    Input: '... ٹماٹر 250 ... او چینی 180 ... خرڅوي'. Before the fix ` او ` was
    not a delimiter, so چینی stayed in ٹماٹر's clause and borrowed 250. چینی
    (chini / Sugar) must read 180 and ٹماٹر (tamatar / Tomato) must read 250.
    LLM stubbed so the rule-only segmentation + attribution is exercised.
    The full 4-item resolution (الو/پياز) also needs FEAT-002 aliases; here we
    assert only the two commodities already in-vocab via their Urdu-script
    aliases, plus the detected language.
    """
    text = (
        "جنابه، دوکاندار الو 150 روپۍ کيلو، پياز 200 روپۍ کيلو، "
        "ٹماٹر 250 روپۍ کيلو او چینی 180 روپۍ کيلو خرڅوي"
    )
    with patch.object(ai_pipeline, "_call_ollama_llm_multi", return_value=None):
        items = ai_pipeline.parse_complaint_items(text)
    by_id = {it["item_canonical_id"]: it for it in items}

    assert "tamatar" in by_id, by_id.keys()
    assert "chini" in by_id, by_id.keys()
    assert by_id["tamatar"]["reported_price"] == 250.0, by_id["tamatar"]
    # The regression: chini must be 180, NOT tomato's 250.
    assert by_id["chini"]["reported_price"] == 180.0, by_id["chini"]

    for it in items:
        assert it["detected_language"] == "Pashto", it


def test_two_items_one_clause_positional():
    """SECONDARY hardening — when a single clause names two commodities with two
    prices, each gets its nearest-following price via the positional helper.

    Exercises _attribute_prices_positionally directly on a forced single clause
    'tamatar 250 aur chini 180' (as it would look before segmentation) so the
    nearest-price attribution is covered without depending on the splitter.
    """
    clause = "tamatar 250 chini 180"
    found = rate_service.find_all_items(clause)
    found_ids = {cid for cid, _ in found}
    assert {"tamatar", "chini"}.issubset(found_ids), found_ids

    mapping = ai_pipeline._attribute_prices_positionally(clause, found)
    assert mapping["tamatar"]["price"] == 250.0, mapping["tamatar"]
    assert mapping["chini"]["price"] == 180.0, mapping["chini"]


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
