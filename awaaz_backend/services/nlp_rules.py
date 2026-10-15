import re
import unicodedata
from typing import Dict, Any, Optional, Tuple, List
from rapidfuzz import fuzz, process
from config import settings


# 1. Eastern Arabic / Urdu / Arabic-Indic digit mapping
URDU_INDIC_DIGITS = {
    '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
    '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
}

# 2. Number words in Urdu script, Roman Urdu, Punjabi, Pashto, English
BASIC_NUMBER_WORDS = {
    # 1 - 10
    "ek": 1, "aik": 1, "ikk": 1, "ik": 1, "yaw": 1, "one": 1, "ایک": 1, "اک": 1,
    "do": 2, "dō": 2, "dwa": 2, "two": 2, "دو": 2,
    "teen": 3, "tin": 3, "dre": 3, "three": 3, "تین": 3,
    "chaar": 4, "char": 4, "salor": 4, "four": 4, "چار": 4,
    "paanch": 5, "panch": 5, "panj": 5, "pinza": 5, "five": 5, "پانچ": 5, "پنج": 5,
    "chhe": 6, "che": 6, "chhey": 6, "shpag": 6, "six": 6, "چھ": 6,
    "saat": 7, "sat": 7, "uwo": 7, "seven": 7, "سات": 7,
    "aath": 8, "ath": 8, "ata": 8, "eight": 8, "آٹھ": 8, "اٹھ": 8,
    "nau": 9, "no": 9, "naha": 9, "nine": 9, "نو": 9,
    "das": 10, "dass": 10, "las": 10, "ten": 10, "دس": 10,
    # 11 - 20
    "gyarah": 11, "yarahan": 11, "گیارہ": 11,
    "barah": 12, "barahan": 12, "بارہ": 12,
    "terah": 13, "terahan": 13, "تیرہ": 13,
    "chaudah": 14, "chodah": 14, "چودہ": 14,
    "pandrah": 15, "pandra": 15, "پندرہ": 15,
    "solah": 16, "sola": 16, "سولہ": 16,
    "satrah": 17, "satra": 17, "سترہ": 17,
    "atharah": 18, "athara": 18, "اٹھارہ": 18,
    "unnees": 19, "unnis": 19, "انیس": 19,
    "bees": 20, "bis": 20, "wist": 20, "twenty": 20, "بیس": 20,
    # Tens & Multiples
    "pachees": 25, "pachis": 25, "painji": 25, "پچیس": 25,
    "tees": 30, "tis": 30, "dhersh": 30, "thirty": 30, "تیس": 30,
    "pantees": 35, "pantis": 35, "پینتیس": 35,
    "chalees": 40, "chalis": 40, "chalwees": 40, "forty": 40, "چالیس": 40,
    "pantaalees": 45, "pantalis": 45, "پینتالیس": 45,
    "pachaas": 50, "pachas": 50, "panja": 50, "pinzos": 50, "fifty": 50, "پچاس": 50,
    "saath": 60, "sath": 60, "shpeta": 60, "sixty": 60, "ساٹھ": 60,
    "sattar": 70, "owaya": 70, "seventy": 70, "ستر": 70,
    "assi": 80, "atya": 80, "eighty": 80, "اسی": 80,
    "nabbe": 90, "nawey": 90, "ninety": 90, "نوے": 90,
    # Hundreds & Thousands
    "sau": 100, "so": 100, "sauu": 100, "sal": 100, "hundred": 100, "سو": 100,
    "hazaar": 1000, "hazar": 1000, "zar": 1000, "thousand": 1000, "ہزار": 1000,
    "lakh": 100000, "laakh": 100000, "لاکھ": 100000,
    # Sindhi / Balochi romanized number words that differ from the shared forms
    # above (do/teen/char/panch/sau/hazaar are already present and shared).
    # NATIVE-REVIEW-REQUIRED: Roman Sindhi/Balochi numerals are not standardized.
    "yak": 1, "hik": 1,            # Balochi / Sindhi 1
    "du": 2,                       # Balochi 2 (distinct spelling from "do")
    "ba": 2,                       # Sindhi 2
    "sai": 3, "tei": 3,            # Balochi / Sindhi 3
    "shash": 6,                    # Balochi 6
    "hapt": 7,                     # Balochi 7
    "hasht": 8,                    # Balochi 8
    "nuh": 9,                      # Balochi 9
    "dah": 10,                     # Balochi 10
    "sad": 100,                    # Balochi 100
    # Pashto number words (Arabic/Pashto script).
    # NATIVE-REVIEW-REQUIRED: Pashto numeral spellings vary regionally; the
    # forms below are the common standard spellings but should be verified by a
    # native speaker before production use.
    "يو": 1,                       # Pashto 1
    "دوه": 2,                      # Pashto 2
    "درې": 3,                      # Pashto 3
    "څلور": 4,                     # Pashto 4
    "پنځه": 5,                     # Pashto 5
    "شپږ": 6,                      # Pashto 6
    "اووه": 7,                     # Pashto 7
    "اته": 8,                      # Pashto 8
    "نهه": 9,                      # Pashto 9
    "لس": 10,                      # Pashto 10
    "شل": 20,                      # Pashto 20
    "پنځوس": 50,                   # Pashto 50
    "سل": 100,                     # Pashto 100
    "سوه": 100,                    # Pashto 100 (variant)
    "زر": 1000,                    # Pashto 1000 (also shared Roman 'zar' above)
    "زره": 1000,                   # Pashto 1000 (variant)
    # Missing Punjabi (Shahmukhi) number words.
    # NATIVE-REVIEW-REQUIRED: Punjabi Shahmukhi numeral spellings.
    "تن": 3,                       # Punjabi 3
    "پنجاہ": 50                    # Punjabi 50
}

# Special Pakistani fractional idioms
FRACTIONAL_PHRASES = {
    # 1.25, 125, 1250
    "sawa sau": 125, "سوا سو": 125,
    "sawa do sau": 225, "سوا دو سو": 225,
    "sawa teen sau": 325, "سوا تین سو": 325,
    "sawa hazaar": 1250, "sawa hazar": 1250, "سوا ہزار": 1250,
    # 1.5 multiplier
    "dedh sau": 150, "dedh so": 150, "deedh sau": 150, "ڈیڑھ سو": 150, "دیڑھ سو": 150,
    "dedh hazaar": 1500, "dedh hazar": 1500, "ڈیڑھ ہزار": 1500,
    "dedh lakh": 150000, "ڈیڑھ لاکھ": 150000,
    # 1.75, 2.75, etc.
    "paune sau": 75, "پونے سو": 75,
    "paune do sau": 175, "پونے دو سو": 175,
    "paune teen sau": 275, "پونے تین سو": 275,
    "paune chaar sau": 375, "paune char sau": 375, "پونے چار سو": 375,
    "paune paanch sau": 475, "paune panch sau": 475, "پونے پانچ سو": 475,
    "paune hazaar": 750, "paune hazar": 750, "پونے ہزار": 750,
    # 2.5 multiplier
    "dhai sau": 250, "dhai so": 250, "dhaye sau": 250, "ڈھائی سو": 250,
    "dhai hazaar": 2500, "dhai hazar": 2500, "ڈھائی ہزار": 2500,
    "dhai lakh": 250000, "ڈھائی لاکھ": 250000,
    # 3.5, 4.5, etc.
    "saadhe teen sau": 350, "sadhe teen sau": 350, "ساڑھے تین سو": 350,
    "saadhe chaar sau": 450, "sadhe char sau": 450, "ساڑھے چار سو": 450,
    "saadhe paanch sau": 550, "sadhe panch sau": 550, "ساڑھے پانچ سو": 550,
    "saadhe chhe sau": 650, "sadhe che sau": 650, "ساڑھے چھ سو": 650,
    "saadhe saat sau": 750, "sadhe sat sau": 750, "ساڑھے سات سو": 750,
    "saadhe aath sau": 850, "sadhe ath sau": 850, "ساڑھے آٹھ سو": 850,
    "saadhe nau sau": 950, "sadhe no sau": 950, "ساڑھے نو سو": 950,
    "saadhe teen hazaar": 3500, "ساڑھے تین ہزار": 3500,
    "saadhe chaar hazaar": 4500, "ساڑھے چار ہزار": 4500
}


def normalize_digits(text: str) -> str:
    """Replaces Eastern Arabic / Urdu digits with ASCII digits."""
    if not text:
        return ""
    result = []
    for ch in text:
        result.append(URDU_INDIC_DIGITS.get(ch, ch))
    return "".join(result)


def parse_word_numbers(text: str) -> str:
    """
    Finds and replaces Pakistani word numbers (e.g. 'do sau', 'ڈیڑھ سو', 'paanch sau pachas')
    with their corresponding integer digits in the text.
    """
    if not text:
        return ""

    lowered = text.lower()

    # 1. Check pre-defined fractional and compound phrases first
    for phrase, val in FRACTIONAL_PHRASES.items():
        if phrase in lowered:
            # Replace case-insensitively
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            lowered = pattern.sub(f" {val} ", lowered)

    # 2. Check compound hundred/thousand phrases like "do sau", "teen sau pachas", "پانچ سو پچاس", "aik hazaar"
    # Matches patterns like: [multiplier 1-9] sau [optional tens 1-99]
    compound_hundreds = [
        ("aik", 1), ("ek", 1), ("ikk", 1), ("yaw", 1), ("ایک", 1),
        ("do", 2), ("dwa", 2), ("du", 2), ("دو", 2),
        ("teen", 3), ("tin", 3), ("dre", 3), ("تین", 3),
        ("chaar", 4), ("char", 4), ("salor", 4), ("چار", 4),
        ("paanch", 5), ("panch", 5), ("panj", 5), ("pinza", 5), ("پانچ", 5),
        ("chhe", 6), ("che", 6), ("shpag", 6), ("چھ", 6),
        ("saat", 7), ("sat", 7), ("uwo", 7), ("سات", 7),
        ("aath", 8), ("ath", 8), ("ata", 8), ("آٹھ", 8),
        ("nau", 9), ("no", 9), ("naha", 9), ("نو", 9),
        # NATIVE-REVIEW-REQUIRED: Sindhi/Balochi 1-9 prefixes that differ from
        # the shared forms above, mirrored from BASIC_NUMBER_WORDS.
        ("yak", 1), ("hik", 1), ("ba", 2), ("sai", 3), ("tei", 3),
        ("shash", 6), ("hapt", 7), ("hasht", 8), ("nuh", 9),
        # NATIVE-REVIEW-REQUIRED: Pashto 1-9 prefixes (for 'يو سل'=100 etc).
        ("يو", 1), ("دوه", 2), ("درې", 3), ("څلور", 4), ("پنځه", 5),
        ("شپږ", 6), ("اووه", 7), ("اته", 8), ("نهه", 9),
        # NATIVE-REVIEW-REQUIRED: Punjabi Shahmukhi تن=3 (for 'تن سو'=300).
        ("تن", 3)
    ]

    for prefix, mult in compound_hundreds:
        # Match 'prefix sau' / 'so' / 'sal' / 'sad' / 'سو' or the Pashto سل / سوه
        for sau_word in ["sau", "so", "sal", "sad", "سوه", "سو", "سل"]:
            phrase = f"{prefix} {sau_word}"
            if phrase in lowered:
                base_val = mult * 100
                lowered = lowered.replace(phrase, f" {base_val} ")

        # Match 'prefix hazaar' / 'hazar' / 'zar' / 'ہزار' or the Pashto زر / زره
        for hazar_word in ["hazaar", "hazar", "zar", "ہزار", "زره", "زر"]:
            phrase = f"{prefix} {hazar_word}"
            if phrase in lowered:
                base_val = mult * 1000
                lowered = lowered.replace(phrase, f" {base_val} ")

    # 3. Handle standalone basic number words when surrounded by word boundaries
    words = lowered.split()
    converted_tokens = []
    i = 0
    while i < len(words):
        w = words[i].strip('.,!?:;')
        if w in BASIC_NUMBER_WORDS:
            val = BASIC_NUMBER_WORDS[w]
            # Check if followed by tens, e.g. "500 50" -> 550
            if i + 1 < len(words):
                next_w = words[i + 1].strip('.,!?:;')
                if next_w in BASIC_NUMBER_WORDS:
                    next_val = BASIC_NUMBER_WORDS[next_w]
                    # If current is hundreds and next is tens (e.g. 500 and 50)
                    if val in [100, 200, 300, 400, 500, 600, 700, 800, 900] and 1 <= next_val <= 99:
                        converted_tokens.append(str(val + next_val))
                        i += 2
                        continue
            converted_tokens.append(str(val))
        else:
            converted_tokens.append(words[i])
        i += 1

    res_str = " ".join(converted_tokens)
    # Merge patterns like "2 100" -> "200", "5 100" -> "500"
    res_str = re.sub(r'\b([1-9])\s+(100|1000)\b', lambda m: str(int(m.group(1)) * int(m.group(2))), res_str)
    # Merge hundreds followed by tens/ones: "500 50" -> "550", "200 25" -> "225"
    res_str = re.sub(r'\b(\d+00)\s+([1-9]\d?)\b', lambda m: str(int(m.group(1)) + int(m.group(2))), res_str)
    return res_str


def extract_quantities_and_units(text: str) -> Tuple[float, str, Optional[float]]:
    """
    Parses unit, quantity multiplier, and any total-to-unit price conversion factor.
    Returns:
        (quantity: float, detected_unit: str, total_bill: Optional[float])
    """
    norm = normalize_digits(text).lower()

    # Special quantities:
    # "pao" / "paao" = 0.25 kg
    if re.search(r'\b(pao|paao|paw|پاؤ|پاو)\b', norm):
        return 0.25, "kg", None

    # "aadha kilo" / "half kg" = 0.5 kg
    if re.search(r'\b(adha kilo|aadha kilo|adha kg|aadha kg|half kg|half kilo|ادھا کلو|آدھا کلو)\b', norm):
        return 0.5, "kg", None

    # "dedh kilo" / "1.5 kg" = 1.5 kg
    if re.search(r'\b(dedh kilo|1\.5\s*(kg|kilo)|ڈیڑھ کلو)\b', norm):
        return 1.5, "kg", None

    # "dhai kilo" / "2.5 kg" = 2.5 kg
    if re.search(r'\b(dhai kilo|2\.5\s*(kg|kilo)|ڈھائی کلو)\b', norm):
        return 2.5, "kg", None

    # "seer" / "ser" = 0.933 kg (1 seer ~ 0.933 kg in Pakistani traditional weight)
    if re.search(r'\b(seer|ser|سیر)\b', norm):
        return 0.933, "kg", None

    # "maund" / "mann" = 40 kg
    if re.search(r'\b(maund|mann|man|من)\b', norm):
        return 40.0, "kg", None

    # "20kg bag" / "atta bag" / "thaila"
    if re.search(r'\b(20\s*k(g|ilo)|thaila|thaile|bag|تھیلا)\b', norm):
        return 1.0, "bag", None

    # "half dozen" / "aadha darjan" = 0.5 dozen
    if re.search(r'\b(adha darjan|aadha darjan|half dozen|ادھا درجن|آدھا درجن)\b', norm):
        return 0.5, "dozen", None

    # "dozen" / "darjan"
    if re.search(r'\b(darjan|dozen|darzan|درجن)\b', norm):
        match_n = re.search(r'(\d+)\s*(darjan|dozen|درجن)', norm)
        q = float(match_n.group(1)) if match_n else 1.0
        return q, "dozen", None

    # "litre" / "liter"
    if re.search(r'\b(litre|liter|ltr|لیٹر)\b', norm):
        match_n = re.search(r'(\d+(?:\.\d+)?)\s*(litre|liter|ltr|لیٹر)', norm)
        q = float(match_n.group(1)) if match_n else 1.0
        return q, "litre", None

    # "kilo" / "kg"
    match_kg = re.search(r'(\d+(?:\.\d+)?)\s*(kilo|kg|kilogram|کلو)', norm)
    if match_kg:
        return float(match_kg.group(1)), "kg", None

    # "piece" / "roti" / "naan" / "adad"
    match_pc = re.search(r'(\d+)\s*(piece|adad|roti|naan|عدد)', norm)
    if match_pc:
        return float(match_pc.group(1)), "piece", None

    # Default 1.0 unit
    return 1.0, "kg", None


def extract_price_and_normalize(text: str, canonical_unit: str = "kg") -> Tuple[Optional[float], float]:
    """
    Extracts reported price from transcript, converting Pakistani fractional idioms
    and total quantities (e.g. '500 ke 2 kilo' -> 250/kg; '100 ka aadha kilo' -> 200/kg).
    Returns: (normalized_unit_price, confidence)
    """
    if not text:
        return None, 0.0

    # 1. Normalize digits & convert word numbers to digits
    normalized_text = normalize_digits(text)
    converted = parse_word_numbers(normalized_text)

    # 2. Extract quantity and detected unit
    quantity, detected_unit, _ = extract_quantities_and_units(converted)

    # 3. Look for explicit price patterns
    # Patterns:
    # "500 rupay k 2 kilo" / "500 k 2 kilo"
    bill_for_qty_match = re.search(r'(\d+)\s*(?:rupay|rs|rupees|روپے|کا|کے)?\s*(?:k|ke|kay|mein|me)?\s*(\d+(?:\.\d+)?)\s*(?:kilo|kg|seer|pao|darjan|لیٹر|کلو)', converted, re.IGNORECASE)
    if bill_for_qty_match:
        total_pkr = float(bill_for_qty_match.group(1))
        qty = float(bill_for_qty_match.group(2))
        if qty > 0:
            unit_price = round(total_pkr / qty, 2)
            return unit_price, 0.95

    # "100 rupay ka aadha kilo" or "100 ka adha kilo" / "100 ka pao" / "300 ka 1 seer"
    ka_fraction_match = re.search(r'(\d+)\s*(?:rupay|rs|rupees|روپے)?\s*(?:ka|ke|kay|mein|me)?\s*(?:(\d+(?:\.\d+)?)\s*)?(aadha kilo|adha kilo|half kg|pao|paao|seer|ser|سیر)', converted, re.IGNORECASE)
    if ka_fraction_match:
        price_val = float(ka_fraction_match.group(1))
        n_qty = float(ka_fraction_match.group(2)) if ka_fraction_match.group(2) else 1.0
        frac_word = ka_fraction_match.group(3).lower()
        if "pao" in frac_word or "paao" in frac_word:
            # 1 pao = 0.25 kg -> 1 kg = price * 4 / n_qty
            return round((price_val / n_qty) * 4.0, 2), 0.95
        elif "adha" in frac_word or "half" in frac_word:
            # 0.5 kg -> 1 kg = price * 2 / n_qty
            return round((price_val / n_qty) * 2.0, 2), 0.95
        elif "seer" in frac_word or "ser" in frac_word or "سیر" in frac_word:
            # 1 seer ~ 0.933 kg -> 1 kg = price / (n_qty * 0.933)
            return round(price_val / (n_qty * 0.933), 2), 0.92

    # "300 per kg" / "300 rupay kilo" / "300 rupay" / "روپے 300"
    price_patterns = [
        r'(\d+)\s*(?:rupay|rupees|rs|\/-|روپے)\s*(?:kilo|kg|per kg|darjan|litre|فی کلو)',
        r'(\d+)\s*(?:rupay|rupees|rs|\/-|روپے)',
        r'(?:rupay|rupees|rs|روپے)\s*(\d+)',
        r'(\d+)\s*(?:kilo|kg|per kg)',
    ]

    for pat in price_patterns:
        match = re.search(pat, converted, re.IGNORECASE)
        if match:
            raw_price = float(match.group(1))
            # Adjust if quantity was non-1.0 and user mentioned "X rupay ka Y"
            if quantity != 1.0 and quantity > 0:
                # E.g. "100 rupay ka aadha kilo" where quantity = 0.5
                normalized_price = round(raw_price / quantity, 2)
                return normalized_price, 0.90
            return raw_price, 0.90

    # 4. Fallback: find any standalone number that looks like a plausible PKR price (e.g. 10 - 5000)
    numbers = [float(n) for n in re.findall(r'\b\d+\b', converted)]
    plausible = [n for n in numbers if 10 <= n <= 10000 and n not in [2024, 2025, 2026]]
    if plausible:
        # Take the most prominent price number
        return plausible[0], 0.65

    return None, 0.0


def detect_language(text: str) -> str:
    """
    Detects language among Urdu (Urdu script), Roman Urdu, Punjabi, Pashto, English.
    """
    if not text:
        return "Urdu"

    # Check for Urdu / Arabic script
    has_arabic_script = any('\u0600' <= ch <= '\u06FF' or '\u0750' <= ch <= '\u077F' for ch in text)
    if has_arabic_script:
        # Check for Pashto unique characters (ښ, ړ, ږ, ۍ, ڼ)
        if any(ch in text for ch in ['ښ', 'ړ', 'ږ', 'ۍ', 'ڼ']):
            return "Pashto"
        # Check for Sindhi unique letters (not present in Urdu/Punjabi-Shahmukhi).
        # NATIVE-REVIEW-REQUIRED: Sindhi implosive/aspirated letters.
        if any(ch in text for ch in ['ڄ', 'ٺ', 'ٽ', 'ڻ', 'ڱ', 'ڳ', 'ڦ', 'ڀ', 'ٿ', 'ڏ']):
            return "Sindhi"
        # NOTE: Arabic-script Balochi has no unique code points and overlaps
        # Urdu/Persian, so Balochi written in Arabic script may fall through to
        # "Urdu" here. This is an accepted limitation (Roman-marker detection only).
        return "Urdu"

    text_lower = text.lower()

    # 1. English indicators (check English first to avoid false positives from English words)
    english_words = {
        "the", "is", "at", "which", "are", "charging", "overcharging", "complaint",
        "store", "price", "official", "rate", "rupees", "vegetable", "market",
        "for", "potatoes", "onions", "milk", "vendor", "selling", "chicken"
    }
    tokens = set(re.findall(r'\b[a-z]+\b', text_lower))
    if len(tokens.intersection(english_words)) >= 2:
        return "English"

    # 2. Sindhi Roman indicators (whole word checks, high-precision markers).
    # NATIVE-REVIEW-REQUIRED: Roman Sindhi is not standardized; shared tokens
    # (qeemat/bazar) are deliberately excluded to avoid stealing Roman-Urdu detections.
    sindhi_patterns = [
        r'\bmaan\b', r'\btawhan\b', r'\btuhan\b', r'\baahe\b', r'\baahy\b',
        r'\bkahro\b', r'\bghani\b'
    ]
    if any(re.search(pat, text_lower) for pat in sindhi_patterns):
        return "Sindhi"

    # 3. Balochi Roman indicators (whole word checks, high-precision markers).
    # NATIVE-REVIEW-REQUIRED: Roman Balochi is not standardized; shared tokens
    # (bazar) are deliberately excluded. Lowest-confidence detector.
    balochi_patterns = [
        r'\bmani\b', r'\btaw\b', r'\btau\b', r'\bint\b', r'\bent\b', r'\bgran\b'
    ]
    if any(re.search(pat, text_lower) for pat in balochi_patterns):
        return "Balochi"

    # 4. Punjabi Roman indicators (whole word checks)
    punjabi_patterns = [
        r'\bassi\b', r'\btussi\b', r'\bsaanu\b', r'\blabhya\b', r'\bkeeta\b',
        r'\bjanda\b', r'\bmundey\b', r'\btuhadi\b', r'\baakhda\b', r'\baakhdi\b',
        r'\bditta\b', r'\bditti\b', r'\bpainji\b', r'\bpanja\b', r'\bvich\b'
    ]
    if any(re.search(pat, text_lower) for pat in punjabi_patterns):
        return "Punjabi"

    # 5. Pashto Roman indicators (whole word checks)
    pashto_patterns = [
        r'\bdera\b', r'\bmanana\b', r'\bstaso\b', r'\bzama\b', r'\bkhawand\b',
        r'\bkhorak\b', r'\bshoday\b', r'\bshaway\b', r'\brakrre\b', r'\bshodi\b'
    ]
    if any(re.search(pat, text_lower) for pat in pashto_patterns):
        return "Pashto"

    # Default to Roman Urdu for latin script Pakistani code-switching
    return "Roman Urdu"


def classify_category_and_urgency(text: str, overcharge_pct: float = 0.0) -> Tuple[str, str, str, str]:
    """
    Classifies governance category, urgency level, routing agency, and helpline reference.
    Returns: (category, urgency, routing_agency, helpline)
    """
    norm = text.lower()

    # 1. PFA - Food Safety
    food_safety_kw = [
        "kharab", "baasi", "expired", "keere", "keera", "ganda", "milawat", "badboo",
        "fungus", "stale", "vomit", "bimar", "pfa", "unhygienic", "rotten", "pet kharab",
        "chemical", "سڑا", "خراب", "ملاوٹ", "بدبو", "بیمار", "فوڈ اتھارٹی"
    ]
    if any(kw in norm for kw in food_safety_kw):
        category = "PFA - Food Safety"
        agency = "Punjab Food Authority (PFA)"
        helpline = settings.PFA_FOOD_SAFETY_HELPLINE
        # Escalate to High when the report describes actual harm to people or
        # deliberate adulteration, not merely an untidy kitchen. "pet kharab"
        # (stomach upset / food poisoning) is the most common way citizens
        # describe illness caused by unsafe food.
        illness_kw = [
            "bimar", "bimari", "pet kharab", "keere", "keera", "chemical",
            "vomit", "ulti", "hospital", "zeher", "poison", "death", "mar gaya",
            "بیمار", "زہر", "الٹی", "قے",
        ]
        urgency = "High" if any(kw in norm for kw in illness_kw) else "Medium"
        return category, urgency, agency, helpline

    # 2. Municipal - Infrastructure
    infra_kw = [
        "kachra", "kooda", "gutter", "naali", "nali", "sewer", "sewerage", "paani nahi",
        "cda", "wasa", "road", "street light", "leakage", "gatter", "dhuan", "manhole",
        "سیوریج", "کچرا", "کوڑا", "گٹر", "نالی", "پانی", "واسا"
    ]
    if any(kw in norm for kw in infra_kw):
        category = "Municipal - Infrastructure"
        agency = "Capital Development Authority (CDA / MCI) / WASA Rawalpindi"
        helpline = settings.CDA_MUNICIPAL_HELPLINE
        urgency = "High" if ("gatter" in norm or "open manhole" in norm or "leakage" in norm) else "Medium"
        return category, urgency, agency, helpline

    # 3. Default: PERA - Overpricing
    category = "PERA - Overpricing"
    agency = "Punjab Enforcement & Regulatory Authority (PERA) / ICT Administration"
    helpline = settings.PERA_ENFORCEMENT_HELPLINE

    if overcharge_pct >= settings.HIGH_SEVERITY_THRESHOLD_PCT:
        urgency = "High"
    elif overcharge_pct >= settings.OVERCHARGE_ALERT_THRESHOLD_PCT:
        urgency = "Medium"
    else:
        urgency = "Low"

    return category, urgency, agency, helpline


def generate_native_acknowledgment(language: str, item_name: Optional[str] = None, price_diff: float = 0.0) -> str:
    """
    Generates reassuring citizen acknowledgment in the exact same language and script.
    """
    if language == "Urdu":
        if price_diff > 0:
            return "آپ کی شکایت موصول ہو گئی ہے۔ مجاز پرائس کنٹرول مجسٹریٹ کو کارروائی کے لیے مطلع کر دیا گیا ہے۔ شکریہ۔"
        return "آپ کی شکایت موصول ہو چکی ہے۔ متعلقہ اتھارٹی کو کارروائی کے لیے بھیج دیا گیا ہے۔ آپ کا شکریہ۔"

    elif language == "Punjabi":
        return "تہاڈی شکایت درج ہو گئی اے۔ پرائس کنٹرول مجسٹریٹ نوں فوری کارروائی واسطے بھیج دتا گیا اے۔ مہربانی۔"

    elif language == "Pashto":
        return "ستاسو شکایت په بریالیتوب سره ثبت شو او اړوندې ادارې ته واستول شو. ستاسو له همکارۍ مننه."

    elif language == "Sindhi":
        # DRAFT — NATIVE-REVIEW-REQUIRED before production use.
        # Roman gloss: "Tawhan ji shikayat daraj thi vai aahe. Laagaapil authority
        # ddaanhan karrvaai laai mokli vai aahe. Mehrbani."
        return "توهان جي شڪايت درج ٿي وئي آهي. لاڳاپيل اٿارٽيءَ ڏانهن ڪارروائيءَ لاءِ موڪلي وئي آهي. مهرباني."

    elif language == "Balochi":
        # DRAFT — NATIVE-REVIEW-REQUIRED. Arabic-script Balochi is not standardized;
        # this string is best-effort and may need a Latin-script form.
        # Roman gloss: "Shumay shikayat daraj boot. Maznen idaara-a karrvaai-e
        # waasta deem daat boot. Mintawaar."
        return "شمے شکایت درج بوت. مزنیں ادارہ ءَ کارروائی ئِے واستہ دیم دات بوت. منتوار."

    elif language == "English":
        return "Your complaint has been successfully registered and forwarded to the district price enforcement authorities. Thank you."

    else:  # Roman Urdu
        if price_diff > 0:
            return "Aap ki shikayat darj kar li gayi hai. Price Control Magistrate ko karwai ke liye bhaij diya gaya hai. Shukriya."
        return "Aap ki shikayat darj kar li gayi hai. Mutalliqa authority ko karwai ke liye bhaij diya gaya hai. Shukriya."
