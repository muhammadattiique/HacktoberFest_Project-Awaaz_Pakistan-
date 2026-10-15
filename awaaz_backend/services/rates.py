import json
import logging
import re
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from rapidfuzz import fuzz, process
from config import settings

logger = logging.getLogger(__name__)


# Conservative Arabic -> Urdu script-variant folding. Several regional spellings
# (notably Pashto) use the Arabic forms of letters that the rate-list stores in
# their Urdu forms, so an exact/word-boundary match would otherwise miss them
# even though the words are the same. Only the SAFE, non-colliding substitutions
# are folded here; this is additive normalization, NOT a widening to substrings.
_SCRIPT_FOLD_MAP = {
    "\u064A": "\u06CC",  # Arabic yeh ي -> Urdu yeh ی
    "\u0649": "\u06CC",  # Arabic alef maksura ى -> Urdu yeh ی
    "\u0643": "\u06A9",  # Arabic kaf ك -> Urdu kaf ک
}
# NATIVE-REVIEW-REQUIRED: heh variants intentionally not folded (ه/ہ/ۀ/ة carry
# distinct roles across Urdu/Pashto/Sindhi and folding them risks collisions).


def _normalize_script(s: str) -> str:
    """Fold common Arabic letter variants to the Urdu forms the rate-list uses.

    Lets a Pashto spelling like پياز (Arabic yeh U+064A) match the rate-list
    پیاز (Urdu yeh U+06CC) without loosening the word-boundary matching.
    """
    if not s:
        return s
    return "".join(_SCRIPT_FOLD_MAP.get(ch, ch) for ch in s)


class RateService:
    """
    Manages official district price rates for Islamabad and Rawalpindi.
    Supports dynamic reloading, fuzzy alias matching, and price gouging calculation.
    """
    def __init__(self, rate_list_path: Optional[str] = None):
        self.path = Path(rate_list_path or settings.RATE_LIST_PATH)
        self._lock = threading.Lock()
        self.meta: Dict[str, Any] = {}
        self.items: Dict[str, Dict[str, Any]] = {}
        # Pre-calculated alias lookup map: normalized_alias -> canonical_id
        self._alias_map: Dict[str, str] = {}
        self.load()

    def load(self) -> bool:
        """Loads or reloads the rate list from JSON file thread-safely."""
        with self._lock:
            try:
                if not self.path.exists():
                    logger.error(f"Rate list file not found at {self.path}")
                    return False
                
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                self.meta = data.get("meta", {})
                self.items = data.get("items", {})

                # Build flat alias lookup. Keys are script-normalized (Arabic
                # variants folded to the Urdu forms) so a folded query matches.
                alias_map = {}
                for item_id, item_data in self.items.items():
                    # Item id itself
                    alias_map[_normalize_script(item_id.lower().strip())] = item_id
                    # English name
                    if "name_en" in item_data:
                        alias_map[_normalize_script(item_data["name_en"].lower().strip())] = item_id
                    # Urdu name
                    if "name_ur" in item_data:
                        alias_map[_normalize_script(item_data["name_ur"].strip())] = item_id
                    # Aliases list
                    for alias in item_data.get("aliases", []):
                        alias_map[_normalize_script(alias.lower().strip())] = item_id

                self._alias_map = alias_map
                logger.info(f"Loaded {len(self.items)} rate items and {len(self._alias_map)} aliases from {self.path}")
                return True
            except Exception as e:
                logger.exception(f"Failed to load rate-list.json: {e}")
                return False

    def reload(self) -> bool:
        """Exposed reload method."""
        return self.load()

    def get_meta(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.meta)

    def get_all_items(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self.items.items()}

    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self.items.get(item_id)
            return dict(item) if item else None

    def resolve_item(self, text_or_name: str) -> Optional[Tuple[str, Dict[str, Any], float]]:
        """
        Resolves an item name from user query using direct lookup and fuzzy matching.
        Returns: (canonical_id, item_dict, match_confidence) or None
        """
        if not text_or_name:
            return None

        normalized = _normalize_script(text_or_name.lower().strip())

        with self._lock:
            # 1. Exact canonical ID
            if normalized in self.items:
                return normalized, dict(self.items[normalized]), 1.0

            # 2. Exact alias match
            if normalized in self._alias_map:
                canonical_id = self._alias_map[normalized]
                return canonical_id, dict(self.items[canonical_id]), 0.98

            # 3. Substring / Token matching in aliases
            for alias, canonical_id in self._alias_map.items():
                if len(alias) >= 3 and (alias == normalized or alias in normalized or normalized in alias):
                    return canonical_id, dict(self.items[canonical_id]), 0.92

            # 4. RapidFuzz matching across all aliases
            choices = list(self._alias_map.keys())
            best_match = process.extractOne(normalized, choices, scorer=fuzz.token_set_ratio)
            
            if best_match:
                matched_alias, score, _ = best_match
                if score >= 75:  # Good fuzzy threshold
                    canonical_id = self._alias_map[matched_alias]
                    confidence = round(score / 100.0, 2)
                    return canonical_id, dict(self.items[canonical_id]), confidence

        return None

    def find_all_items(self, text_or_name: str) -> List[Tuple[str, Dict[str, Any]]]:
        """All distinct ``(canonical_id, item_dict)`` whose name/alias (len>=3)
        is genuinely MENTIONED in the text as a whole word/token.

        Mirrors ``resolve_item`` tiers 1-2 (exact id / exact alias) and a
        tightened tier-3: an alias counts as present only on a real
        word-boundary match against the text (``\\b alias \\b``), never on a
        loose substring of an unrelated word. The old ``norm in alias``
        direction is dropped entirely — a fragment of the text being contained
        inside a longer alias is not a mention and used to let unrelated words
        (and LLM-borrowed stray tokens) fabricate commodities. The greedy fuzzy
        tier-4 is still deliberately excluded. De-duplicated by canonical id,
        preserving alias-map insertion order.
        """
        norm = _normalize_script((text_or_name or "").lower().strip())
        out: List[Tuple[str, Dict[str, Any]]] = []
        seen: set = set()
        if not norm:
            return out
        with self._lock:
            for alias, canonical_id in self._alias_map.items():
                if len(alias) < 3:
                    continue
                if canonical_id in seen:
                    continue
                # Whole-word / whole-token match: the alias must appear in the
                # text delimited by non-word boundaries (handles Latin and
                # Urdu-script tokens alike). Equality is covered by the regex.
                pattern = r"(?<!\w)" + re.escape(alias) + r"(?!\w)"
                if re.search(pattern, norm):
                    seen.add(canonical_id)
                    out.append((canonical_id, dict(self.items[canonical_id])))
        return out

    def compare_price(
        self,
        item_id: str,
        reported_price: float,
        unit: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compares reported price with official rate.
        Calculates overcharge, percentage, and severity.
        """
        item = self.get_item(item_id)
        if not item:
            return {
                "item_canonical_id": None,
                "item_name": item_id,
                "unit": unit or "unit",
                "official_price": 0.0,
                "reported_price": float(reported_price),
                "price_difference_pkr": 0.0,
                "percentage_overcharge": 0.0,
                "is_overpriced": False,
                "severity": "Unknown",
                "recommended_action": "Item not found in official notified rate list. Manual verification required.",
                "legal_statute_note": "Unlisted commodity under ICT / Punjab Price Control regulations."
            }

        official_price = float(item.get("price", 0.0))
        item_unit = item.get("unit", "kg")
        rep_price = float(reported_price)

        diff_pkr = round(rep_price - official_price, 2)
        pct_overcharge = round(((rep_price - official_price) / official_price) * 100.0, 1) if official_price > 0 else 0.0
        is_overpriced = rep_price > official_price

        # Determine severity and recommended actions
        if pct_overcharge >= settings.HIGH_SEVERITY_THRESHOLD_PCT:
            severity = "Critical"
            action = "Immediate inspection by Special Price Magistrate / Assistant Commissioner. Substantial overcharging (>50%)."
        elif pct_overcharge >= settings.OVERCHARGE_ALERT_THRESHOLD_PCT:
            severity = "High"
            action = "Schedule price monitoring inspection under Punjab Enforcement & Regulatory Authority (PERA) / ICT Administration."
        elif pct_overcharge > 0:
            severity = "Moderate"
            action = "Notice of violation. Vendor cautioned to display official rate board."
        else:
            severity = "Normal"
            action = "Fair pricing within official notified ceiling rate."

        statute = "Price Control and Prevention of Profiteering and Hoarding Act 1977 (ICT) / Punjab Price Control of Essential Commodities Act 2024"

        return {
            "item_canonical_id": item_id,
            "item_name": item.get("name_en", item_id.capitalize()),
            "unit": item_unit,
            "official_price": official_price,
            "reported_price": rep_price,
            "price_difference_pkr": diff_pkr,
            "percentage_overcharge": pct_overcharge,
            "is_overpriced": is_overpriced,
            "severity": severity,
            "recommended_action": action,
            "legal_statute_note": statute
        }


# Singleton instance
rate_service = RateService()

