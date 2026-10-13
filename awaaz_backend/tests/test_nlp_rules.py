import pytest
from services.nlp_rules import (
    normalize_digits,
    parse_word_numbers,
    extract_quantities_and_units,
    extract_price_and_normalize,
    detect_language,
    classify_category_and_urgency,
    generate_native_acknowledgment
)


def test_digit_normalization():
    """Verify Eastern Arabic and Urdu script digits normalize to ASCII."""
    urdu_digits = "۰۱۲۳۴۵۶۷۸۹"
    assert normalize_digits(urdu_digits) == "0123456789"

    mixed_text = "آلو ۱۰۰ روپے کلو"
    assert normalize_digits(mixed_text) == "آلو 100 روپے کلو"


def test_word_numbers_pakistani_idioms():
    """Verify Pakistani fractional and compound idioms parse to exact integers."""
    # Sawa sau = 125
    parsed = parse_word_numbers("sawa sau rupay")
    assert "125" in parsed

    # Dedh sau = 150
    parsed = parse_word_numbers("dedh sau rupay")
    assert "150" in parsed

    # Urdu script: ڈیڑھ سو = 150
    parsed = parse_word_numbers("ڈیڑھ سو روپے")
    assert "150" in parsed

    # Dhai sau = 250
    parsed = parse_word_numbers("dhai sau ka kilo")
    assert "250" in parsed

    # Urdu script: ڈھائی سو = 250
    parsed = parse_word_numbers("ڈھائی سو روپے")
    assert "250" in parsed

    # Saadhe teen sau = 350
    parsed = parse_word_numbers("saadhe teen sau")
    assert "350" in parsed

    # Paune do sau = 175
    parsed = parse_word_numbers("paune do sau")
    assert "175" in parsed

    # Compound: do sau = 200
    parsed = parse_word_numbers("do sau rupay")
    assert "200" in parsed

    # Compound: paanch sau pachas = 550
    parsed = parse_word_numbers("paanch sau pachas rupay")
    assert "550" in parsed

    # Aik hazaar = 1000
    parsed = parse_word_numbers("aik hazaar rupay")
    assert "1000" in parsed

    # Urdu script: ایک ہزار = 1000
    parsed = parse_word_numbers("ایک ہزار روپے")
    assert "1000" in parsed

    # Standalone pachaas = 50
    parsed = parse_word_numbers("pachaas rupay")
    assert "50" in parsed


def test_punjabi_and_pashto_numbers():
    """Verify Punjabi and Pashto words convert to numbers."""
    # Punjabi
    parsed_pb = parse_word_numbers("panj sau rupay")
    assert "500" in parsed_pb

    # Pashto
    parsed_ps = parse_word_numbers("dwa sau rupay")
    assert "200" in parsed_ps


def test_sindhi_and_balochi_numbers():
    """Verify Sindhi and Balochi romanized words convert to numbers."""
    # Balochi: du sau = 200
    parsed_bal = parse_word_numbers("du sau rupay")
    assert "200" in parsed_bal

    # Balochi: sai sad = 300 (sad = 100)
    parsed_bal2 = parse_word_numbers("sai sad rupay")
    assert "300" in parsed_bal2

    # Sindhi: ba sau = 200
    parsed_sd = parse_word_numbers("ba sau rupay")
    assert "200" in parsed_sd


def test_quantity_unit_derivations():
    """Verify derivation of unit prices from quantities like pao, aadha kilo, seer, total bill."""
    # "100 rupay ka aadha kilo" -> 0.5kg for 100 -> 200/kg
    price, conf = extract_price_and_normalize("100 rupay ka aadha kilo")
    assert price == 200.0

    # "100 ka adha kilo"
    price2, conf2 = extract_price_and_normalize("100 ka adha kilo")
    assert price2 == 200.0

    # "500 rupay k 2 kilo aloo diye" -> 500 / 2 = 250/kg
    price3, conf3 = extract_price_and_normalize("500 rupay k 2 kilo aloo diye")
    assert price3 == 250.0

    # "300 ka 1 seer" -> 300 / 0.933 ~= 321.54/kg
    price4, conf4 = extract_price_and_normalize("300 ka 1 seer")
    assert price4 is not None
    assert 320 <= price4 <= 323

    # "80 rupay ka pao tamatar" -> 80 * 4 = 320/kg
    price5, conf5 = extract_price_and_normalize("80 rupay ka pao")
    assert price5 == 320.0

    # "200 rupay kilo" -> 200/kg
    price6, conf6 = extract_price_and_normalize("200 rupay kilo")
    assert price6 == 200.0


def test_language_detection():
    """Verify detection of Urdu script, Roman Urdu, Punjabi, Pashto, English."""
    assert detect_language("آلو دو سو روپے کلو بیچ رہے ہیں") == "Urdu"
    assert detect_language("Aloo do sau rupay kilo bech rahe hain") == "Roman Urdu"
    assert detect_language("The shopkeeper is overcharging for potatoes at 200 rupees per kg") == "English"
    assert detect_language("Tuhadi intizamiya nu aakho dahi teen sau da ditta ae") == "Punjabi"
    assert detect_language("Dukaandar da pfa yaftah na de staso khorak kharab de") == "Pashto"
    # Sindhi script (contains unique Sindhi letters ڻ, ڪ, ٿ)
    assert detect_language("هي دڪاندار اڱڻ ٻه سؤ رپيا ۾ وڪڻي رهيو آهي") == "Sindhi"
    # Sindhi Roman markers (maan, tawhan, aahe)
    assert detect_language("maan chavan tho tawhan ji dukan ghani aahe") == "Sindhi"
    # Balochi Roman markers (mani, taw, gran)
    assert detect_language("mani gal taw sunk e dukandar gran int") == "Balochi"


def test_category_and_urgency_classification():
    """Verify classification into PERA, PFA, and Municipal bodies with proper urgency."""
    # Food Safety (PFA)
    cat_pfa, urg_pfa, agency_pfa, help_pfa = classify_category_and_urgency("Doodh mein chemical aur milawat hai bache bimar ho gaye")
    assert cat_pfa == "PFA - Food Safety"
    assert urg_pfa == "High"
    assert "Food Authority" in agency_pfa

    # Infrastructure (CDA/WASA)
    cat_mun, urg_mun, agency_mun, help_mun = classify_category_and_urgency("G-9 Markaz mein gutter ubal raha hai aur kachra para hai")
    assert cat_mun == "Municipal - Infrastructure"
    assert "Capital Development Authority" in agency_mun

    # Overpricing (PERA)
    cat_pera, urg_pera, agency_pera, help_pera = classify_category_and_urgency("Aloo mehnga bech raha hai", overcharge_pct=60.0)
    assert cat_pera == "PERA - Overpricing"
    assert urg_pera == "High"  # >= 50%
    assert "PERA" in agency_pera


def test_native_acknowledgment():
    """Verify citizen acknowledgments preserve script and language."""
    ack_ur = generate_native_acknowledgment("Urdu", price_diff=50.0)
    assert "شکایت موصول" in ack_ur

    ack_roman = generate_native_acknowledgment("Roman Urdu", price_diff=50.0)
    assert "shikayat darj" in ack_roman.lower()

    ack_en = generate_native_acknowledgment("English")
    assert "registered" in ack_en.lower()

    # Sindhi + Balochi draft acknowledgments must return non-empty Arabic-script strings
    ack_sd = generate_native_acknowledgment("Sindhi")
    assert ack_sd.strip()
    assert any('\u0600' <= ch <= '\u06FF' for ch in ack_sd)

    ack_bal = generate_native_acknowledgment("Balochi")
    assert ack_bal.strip()
    assert any('\u0600' <= ch <= '\u06FF' for ch in ack_bal)

