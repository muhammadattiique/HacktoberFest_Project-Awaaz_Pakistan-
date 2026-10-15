import pytest
from services.rates import rate_service


def test_rate_list_loaded():
    """Verify rate list loads at least 25 official items with metadata."""
    items = rate_service.get_all_items()
    meta = rate_service.get_meta()

    assert len(items) >= 25, f"Expected at least 25 items, got {len(items)}"
    assert meta.get("currency") == "PKR"
    assert "Islamabad" in meta.get("region", "")
    assert "Rawalpindi" in meta.get("region", "")


def test_required_pakistani_staples_present():
    """Verify essential items required by citizens are included with official rates."""
    required_keys = [
        "aloo", "pyaaz", "tamatar", "chini", "atta_kg", "atta_20kg",
        "chawal_basmati", "doodh", "dahi", "roti", "naan", "chicken_meat",
        "chicken_live", "beef", "mutton", "anday", "cooking_oil",
        "daal_chana", "daal_masoor", "daal_moong", "kela", "seb", "double_roti"
    ]
    items = rate_service.get_all_items()
    for key in required_keys:
        assert key in items, f"Missing required staple: {key}"
        item = items[key]
        assert "price" in item and item["price"] > 0
        assert "unit" in item
        assert "name_ur" in item
        assert "aliases" in item and len(item["aliases"]) > 0


def test_exact_and_alias_resolution():
    """Verify exact and Roman Urdu / English alias resolution."""
    # Aloo aliases
    res1 = rate_service.resolve_item("aloo")
    assert res1 is not None
    assert res1[0] == "aloo"

    res2 = rate_service.resolve_item("potato")
    assert res2 is not None
    assert res2[0] == "aloo"

    res3 = rate_service.resolve_item("آلو")
    assert res3 is not None
    assert res3[0] == "aloo"

    # Doodh
    res_milk = rate_service.resolve_item("milk")
    assert res_milk is not None
    assert res_milk[0] == "doodh"

    # Chini
    res_sugar = rate_service.resolve_item("sugar")
    assert res_sugar is not None
    assert res_sugar[0] == "chini"


def test_fuzzy_matching_aliases():
    """Verify rapidfuzz handles spelling variants."""
    res_pyaz = rate_service.resolve_item("piaaz")
    assert res_pyaz is not None
    assert res_pyaz[0] == "pyaaz"

    res_tamator = rate_service.resolve_item("tamator")
    assert res_tamator is not None
    assert res_tamator[0] == "tamatar"


def test_price_comparison_calculation():
    """Verify overcharge, price diff, and severity calculation."""
    # Aloo official price = 100
    # Fair price (100)
    comp_fair = rate_service.compare_price("aloo", 100.0)
    assert comp_fair["is_overpriced"] is False
    assert comp_fair["price_difference_pkr"] == 0.0
    assert comp_fair["percentage_overcharge"] == 0.0
    assert comp_fair["severity"] == "Normal"

    # Moderate overcharge (130 -> 30% over official rate)
    comp_mod = rate_service.compare_price("aloo", 130.0)
    assert comp_mod["is_overpriced"] is True
    assert comp_mod["price_difference_pkr"] == 30.0
    assert comp_mod["percentage_overcharge"] == 30.0
    assert comp_mod["severity"] == "High"  # >= 20% alert threshold

    # Critical overcharge (200 -> 100% over official rate)
    comp_crit = rate_service.compare_price("aloo", 200.0)
    assert comp_crit["is_overpriced"] is True
    assert comp_crit["price_difference_pkr"] == 100.0
    assert comp_crit["percentage_overcharge"] == 100.0
    assert comp_crit["severity"] == "Critical"  # >= 50% threshold


def test_find_all_items_resolves_pashto_sindhi_staples():
    """BUG 2 — Pashto/Sindhi regional spellings and the Punjabi tea alias resolve
    via script-variant folding + the new aliases, without fabricating commodities.
    """
    # الو (Pashto/common Arabic-script potato) -> aloo
    aloo_ids = {c for c, _ in rate_service.find_all_items("الو")}
    assert "aloo" in aloo_ids

    # پياز (Pashto, Arabic yeh U+064A) must fold to rate-list پیاز (Urdu yeh) -> pyaaz
    pyaaz_ids = {c for c, _ in rate_service.find_all_items("پياز")}
    assert "pyaaz" in pyaaz_ids

    # چاہ پتی (Punjabi Shahmukhi tea) -> the EXISTING chai_patti item
    chai_ids = {c for c, _ in rate_service.find_all_items("چاہ پتی")}
    assert "chai_patti" in chai_ids

    # No fabrication: a sentence with no commodity token resolves to nothing.
    assert set(rate_service.find_all_items("mehngai zabardasti dukandar")) == set()


def test_reload_rate_list():
    """Verify dynamic reloading works without errors."""
    success = rate_service.reload()
    assert success is True
    assert len(rate_service.get_all_items()) >= 25

