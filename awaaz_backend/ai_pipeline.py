import os
import re
import json
import time
import logging
import threading
from typing import Dict, Any, Optional, Tuple, List
import whisper
import ollama

from config import settings
from services.nlp_rules import (
    normalize_digits,
    parse_word_numbers,
    extract_price_and_normalize,
    detect_language,
    classify_category_and_urgency,
    generate_native_acknowledgment
)
from services.rates import rate_service

logger = logging.getLogger(__name__)

# Pakistani domain vocabulary for Whisper prompt bias
WHISPER_INITIAL_PROMPT = (
    "Aloo, pyaaz, tamatar, chini, atta, doodh, roti, naan, chicken, murghi, anday, "
    "cooking oil, ghee, daal chana, daal masoor, chawal, sau, hazaar, rupay, kilo, "
    "seer, pao, darjan, dukandar, mandi, Sunday bazaar, Islamabad, Rawalpindi, "
    "mehnga, sasta, rate list, overcharging, munafa khori, G-9 Markaz, Raja Bazaar."
)

# JSON schema for Ollama structured generation
COMPLAINT_SCHEMA = {
    "type": "object",
    "properties": {
        "item_name": {
            "type": "string",
            "description": "Standard English commodity name (e.g. Potato, Onion, Milk, Flour, Chicken, Bread, or Municipal/Food issue)"
        },
        "reported_price": {
            "type": "integer",
            "description": "Reported price in PKR charged per official unit. 0 if not a price issue."
        },
        "category": {
            "type": "string",
            "enum": ["PERA - Overpricing", "PFA - Food Safety", "Municipal - Infrastructure"],
            "description": "Enforcement agency category"
        },
        "urgency": {
            "type": "string",
            "enum": ["Low", "Medium", "High"],
            "description": "Severity of violation"
        },
        "detected_language": {
            "type": "string",
            "description": "Detected language (Urdu, Roman Urdu, Punjabi, Pashto, English)"
        },
        "native_response": {
            "type": "string",
            "description": "Short, reassuring citizen acknowledgment in the SAME language and SAME script."
        }
    },
    "required": ["item_name", "reported_price", "category", "urgency", "detected_language", "native_response"]
}

FEW_SHOT_SYSTEM_PROMPT = """You are Awaaz Pakistan's governance AI engine.
Your task is to parse citizen complaints submitted in Urdu (Urdu script), Roman Urdu, Punjabi, Pashto, or English.
Classify the grievance into one of three official categories:
1. 'PERA - Overpricing' (overcharging for food items, essentials, sugar, flour, milk, chicken, vegetables, roti)
2. 'PFA - Food Safety' (adulterated food, expired items, insects in food, dirty milk, unhygienic restaurant)
3. 'Municipal - Infrastructure' (garbage, sewage overflowing, leaking water lines, broken streetlights, potholes)

Urgency levels:
- 'High': Severe price gouging (>50% overcharge), rotten food causing illness, open manholes/flooding.
- 'Medium': Moderate overpricing (20-50%), unhygienic conditions, blocked drain.
- 'Low': Minor price discrepancy (<20%), minor litter.

Return output strictly complying with the specified JSON schema.

Examples:
Input: "آلو مارکیٹ میں دو سو روپے کلو بیچ رہے ہیں جبکہ لسٹ میں سو روپے ہے۔"
Output: {
  "item_name": "Potato",
  "reported_price": 200,
  "category": "PERA - Overpricing",
  "urgency": "High",
  "detected_language": "Urdu",
  "native_response": "آپ کی شکایت موصول ہو چکی ہے۔ پرائس کنٹرول مجسٹریٹ کو کارروائی کے لیے مطلع کر دیا گیا ہے۔ شکریہ۔"
}

Input: "Bhai Raja Bazaar mein Madina store wala doodh 280 rupay liter de raha hai, bohat loot machai hai."
Output: {
  "item_name": "Fresh Milk",
  "reported_price": 280,
  "category": "PERA - Overpricing",
  "urgency": "Medium",
  "detected_language": "Roman Urdu",
  "native_response": "Aap ki shikayat darj kar li gayi hai. Price Control team ko karwai ke liye bhaij diya gaya hai. Shukriya."
}

Input: "Tandoor aale ne roti bees rupay di ditti ae, aakhda ae aata mehnga ae."
Output: {
  "item_name": "Tandoori Roti",
  "reported_price": 20,
  "category": "PERA - Overpricing",
  "urgency": "Medium",
  "detected_language": "Punjabi",
  "native_response": "تہاڈی شکایت درج ہو گئی اے۔ متعلقہ مجسٹریٹ نوں کارروائی واسطے بھیج دتا گیا اے۔ مہربانی۔"
}

Input: "Dukaan waale khorak kharab shaway shodi rakrre di, dukaandar da pfa yaftah na de."
Output: {
  "item_name": "Spoiled Food",
  "reported_price": 0,
  "category": "PFA - Food Safety",
  "urgency": "High",
  "detected_language": "Pashto",
  "native_response": "ستاسو شکایت ثبت شو او د خوړو خوندیتوب ادارې ته واستول شو. مننه."
}

Input: "Open sewerage gutter overflowing in front of school in G-9 Markaz Islamabad."
Output: {
  "item_name": "Open Sewerage",
  "reported_price": 0,
  "category": "Municipal - Infrastructure",
  "urgency": "High",
  "detected_language": "English",
  "native_response": "Your complaint regarding open sewerage has been routed to CDA / Municipal services for immediate clearance."
}
"""


class AIPipeline:
    def __init__(self):
        self._whisper_model = None
        self._whisper_lock = threading.Lock()
        self._ollama_client = None
        self.whisper_loaded = False
        self.ollama_available = False

    def initialize(self):
        """Loads Whisper once at startup and verifies Ollama connectivity."""
        self._init_whisper()
        self._init_ollama()

    def _init_whisper(self):
        """Load Whisper model with timing log."""
        start_t = time.time()
        try:
            logger.info(f"Loading Whisper model '{settings.WHISPER_MODEL}' on {settings.WHISPER_DEVICE}...")
            self._whisper_model = whisper.load_model(
                settings.WHISPER_MODEL,
                device=settings.WHISPER_DEVICE
            )
            elapsed = time.time() - start_t
            self.whisper_loaded = True
            logger.info(f"Whisper model '{settings.WHISPER_MODEL}' successfully loaded in {elapsed:.2f}s")
        except Exception as e:
            logger.exception(f"Failed to load Whisper model: {e}")
            self.whisper_loaded = False

    def _init_ollama(self):
        """Verify local Ollama client connectivity."""
        try:
            self._ollama_client = ollama.Client(host=settings.OLLAMA_BASE_URL)
            # Test ping / list models
            res = self._ollama_client.list()
            self.ollama_available = True
            logger.info(f"Ollama connected at {settings.OLLAMA_BASE_URL}")
        except Exception as e:
            logger.warning(f"Ollama not reachable at {settings.OLLAMA_BASE_URL}: {e}")
            self.ollama_available = False

    def transcribe_audio_detailed(self, audio_file_path: str) -> Dict[str, Any]:
        """
        Transcribes audio using Whisper with automatic language detection,
        Pakistani prompt biasing, and silence/hallucination filtering.
        """
        if not self._whisper_model:
            with self._whisper_lock:
                if not self._whisper_model:
                    self._init_whisper()

        if not self._whisper_model:
            return {
                "text": "",
                "language": "ur",
                "confidence": 0.0,
                "segments": [],
                "error": "Whisper model not initialized"
            }

        with self._whisper_lock:
            try:
                result = self._whisper_model.transcribe(
                    audio_file_path,
                    initial_prompt=WHISPER_INITIAL_PROMPT,
                    verbose=False,
                    condition_on_previous_text=False,
                    temperature=0.0
                )
            except Exception as e:
                logger.exception(f"Whisper transcription failed: {e}")
                return {
                    "text": "",
                    "language": "ur",
                    "confidence": 0.0,
                    "segments": [],
                    "error": str(e)
                }

        raw_text = result.get("text", "").strip()
        detected_lang = result.get("language", "ur")
        segments = result.get("segments", [])

        # Hallucination and silence checks:
        # Check no_speech_prob on segments
        if segments:
            high_no_speech = all(s.get("no_speech_prob", 0.0) > 0.60 for s in segments)
            if high_no_speech:
                logger.info("Discarded Whisper hallucination due to high no_speech_prob")
                return {"text": "", "language": detected_lang, "confidence": 0.0, "segments": []}

        # Check for repetition loops (common Whisper artifact on silence)
        words = raw_text.split()
        if len(words) >= 6:
            # If same word repeated >= 5 times consecutively
            for i in range(len(words) - 4):
                if words[i] == words[i+1] == words[i+2] == words[i+3] == words[i+4]:
                    logger.info("Discarded Whisper repetition loop artifact")
                    return {"text": "", "language": detected_lang, "confidence": 0.0, "segments": []}

        # Check for standard canned subtitle hallucinations
        canned_phrases = [
            "thank you for watching", "subtitles by", "amara.org",
            "shukriya", "subscribe"
        ]
        if raw_text.lower() in canned_phrases:
            return {"text": "", "language": detected_lang, "confidence": 0.0, "segments": []}

        avg_confidence = 0.85
        if segments:
            # Average compression ratio or confidence proxy
            avg_confidence = max(0.2, min(1.0, 1.0 - sum(s.get("no_speech_prob", 0.0) for s in segments) / len(segments)))

        return {
            "text": raw_text,
            "language": detected_lang,
            "confidence": round(avg_confidence, 2),
            "segments": segments
        }

    def transcribe_audio(self, audio_file_path: str) -> str:
        """Simple transcribe method returning plain string text."""
        res = self.transcribe_audio_detailed(audio_file_path)
        return res.get("text", "")

    def _call_ollama_llm(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Calls local Ollama qwen2.5:1.5b-instruct with JSON schema formatting.
        Includes retry logic and robust markdown JSON block extraction.
        """
        if not self._ollama_client:
            self._init_ollama()

        if not self._ollama_client:
            return None

        prompt = f"Citizen Complaint Text:\n\"{text}\""

        for attempt in range(2):  # Try once, retry once on error
            try:
                response = self._ollama_client.chat(
                    model=settings.OLLAMA_MODEL,
                    messages=[
                        {"role": "system", "content": FEW_SHOT_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    options={"temperature": 0.1},
                    format=COMPLAINT_SCHEMA
                )
                msg_content = response.get("message", {}).get("content", "").strip()
                if not msg_content:
                    continue

                # Strip markdown code fences if present
                clean_json = msg_content
                if "```" in clean_json:
                    clean_json = re.sub(r"^```(?:json)?\s*", "", clean_json, flags=re.MULTILINE)
                    clean_json = re.sub(r"```$", "", clean_json, flags=re.MULTILINE).strip()

                # Extract first {...} block
                match = re.search(r'(\{.*\})', clean_json, re.DOTALL)
                if match:
                    parsed = json.loads(match.group(1))
                    return parsed
                else:
                    parsed = json.loads(clean_json)
                    return parsed

            except Exception as e:
                logger.warning(f"Ollama attempt {attempt + 1} failed: {e}")
                time.sleep(0.3)

        return None

    def parse_complaint_text(self, transcript_text: str) -> Dict[str, Any]:
        """
        Hybrid AI pipeline:
        1. Calls Ollama 1.5B with structured JSON schema.
        2. Validates and repairs LLM extraction using deterministic NLP rules & official rate database.
        3. Falls back gracefully to rule engine if LLM fails, unreachable, or returns invalid data.
        4. Never raises an exception to the caller.
        """
        if not transcript_text or not transcript_text.strip():
            return {
                "item_name": "Unspecified",
                "item_canonical_id": None,
                "unit": "unit",
                "reported_price": 0.0,
                "official_price": 0.0,
                "price_difference_pkr": 0.0,
                "percentage_overcharge": 0.0,
                "category": "PERA - Overpricing",
                "urgency": "Low",
                "detected_language": "Urdu",
                "native_response": "آپ کی آواز ریکارڈ نہیں ہو سکی۔ برائے مہربانی دوبارہ بولیں۔",
                "routing_agency": "Punjab Enforcement & Regulatory Authority (PERA) / ICT Administration",
                "helpline_reference": settings.PERA_ENFORCEMENT_HELPLINE,
                "extraction_confidence": 0.0,
                "needs_review": True
            }

        text = transcript_text.strip()

        # Step 1: Run deterministic NLP extraction as baseline
        det_lang = detect_language(text)
        rule_price, price_confidence = extract_price_and_normalize(text)
        resolved = rate_service.resolve_item(text)
        item_id, item_info, item_confidence = resolved if resolved else (None, {}, 0.0)

        # Step 2: Try LLM extraction
        # Never let an LLM outage break a citizen's complaint: any failure here
        # degrades to the deterministic rule engine instead of raising.
        llm_output = None
        try:
            llm_output = self._call_ollama_llm(text)
        except Exception as exc:
            logger.warning(f"Ollama LLM call raised, falling back to rules: {exc}")
            llm_output = None

        # Step 3: Hybrid validation and repair
        final_item_name = None
        final_canonical_id = item_id
        final_unit = item_info.get("unit", "kg") if item_info else "kg"
        final_reported_price = None
        final_category = None
        final_urgency = None
        final_detected_lang = det_lang
        final_native_response = None
        extraction_confidence = 0.50

        if llm_output and isinstance(llm_output, dict):
            # Extract fields from LLM
            llm_item = llm_output.get("item_name")
            llm_price = llm_output.get("reported_price")
            llm_cat = llm_output.get("category")
            llm_urg = llm_output.get("urgency")
            llm_lang = llm_output.get("detected_language")
            llm_ack = llm_output.get("native_response")

            # Validate / reconcile item
            if not final_canonical_id and llm_item:
                res = rate_service.resolve_item(llm_item)
                if res:
                    final_canonical_id, item_info, _ = res
                    final_item_name = item_info.get("name_en", llm_item)
                    final_unit = item_info.get("unit", "kg")
                else:
                    final_item_name = str(llm_item)
            elif item_info:
                final_item_name = item_info.get("name_en", item_id.capitalize())

            # Validate / reconcile price
            try:
                llm_price_val = float(llm_price) if llm_price is not None else 0.0
            except (ValueError, TypeError):
                llm_price_val = 0.0

            # Prefer rule price if rule extracted a non-zero normalized price from Pakistani idioms
            if rule_price and rule_price > 0:
                final_reported_price = rule_price
            elif llm_price_val > 0:
                final_reported_price = llm_price_val
            else:
                final_reported_price = 0.0

            # Validate Category: Deterministic rules override LLM for Food Safety and Infrastructure
            rule_cat, rule_urg, _, _ = classify_category_and_urgency(text)
            valid_categories = ["PERA - Overpricing", "PFA - Food Safety", "Municipal - Infrastructure"]
            if rule_cat in ["PFA - Food Safety", "Municipal - Infrastructure"]:
                final_category = rule_cat
            elif llm_cat in valid_categories:
                final_category = llm_cat
            else:
                final_category = rule_cat

            # Validate Urgency
            if llm_urg in ["Low", "Medium", "High"]:
                final_urgency = llm_urg

            if llm_lang:
                final_detected_lang = det_lang  # Respect deterministic detector for local nuances

            # Ensure native response matches citizen language
            if final_detected_lang == "Roman Urdu" and llm_ack and any(w in llm_ack.lower() for w in ["your complaint", "please be assured", "dear citizen"]):
                final_native_response = generate_native_acknowledgment("Roman Urdu", final_item_name, price_diff=0.0)
            elif llm_ack and len(llm_ack) > 10:
                final_native_response = llm_ack

            extraction_confidence += 0.35
        else:
            # Fallback path if LLM failed
            logger.info("Using purely rule-based extraction fallback for complaint text")
            if item_info:
                final_item_name = item_info.get("name_en", item_id.capitalize())
            else:
                final_item_name = "Unspecified Commodity"

            final_reported_price = rule_price or 0.0
            extraction_confidence = max(price_confidence, item_confidence)

        # Post-repair validations
        if not final_category:
            final_category, rule_urgency, _, _ = classify_category_and_urgency(text)
            if not final_urgency:
                final_urgency = rule_urgency

        # Compute price comparison against official notified rates
        comparison = rate_service.compare_price(
            item_id=final_canonical_id or "",
            reported_price=final_reported_price,
            unit=final_unit
        )

        official_price = comparison.get("official_price", 0.0)
        diff_pkr = comparison.get("price_difference_pkr", 0.0)
        pct_overcharge = comparison.get("percentage_overcharge", 0.0)

        # Align urgency with price overcharge severity if category is Overpricing
        if final_category == "PERA - Overpricing":
            if pct_overcharge >= settings.HIGH_SEVERITY_THRESHOLD_PCT:
                final_urgency = "High"
            elif pct_overcharge >= settings.OVERCHARGE_ALERT_THRESHOLD_PCT:
                final_urgency = "Medium"
            elif not final_urgency:
                final_urgency = "Low"

        # Determine routing agency & helpline
        _, _, agency, helpline = classify_category_and_urgency(text, pct_overcharge)
        if final_category == "PFA - Food Safety":
            agency = "Punjab Food Authority (PFA)"
            helpline = settings.PFA_FOOD_SAFETY_HELPLINE
        elif final_category == "Municipal - Infrastructure":
            agency = "Capital Development Authority (CDA / MCI) / WASA Rawalpindi"
            helpline = settings.CDA_MUNICIPAL_HELPLINE

        # Native reassurance acknowledgment fallback if needed
        if not final_native_response or (final_detected_lang == "Roman Urdu" and any(w in final_native_response.lower() for w in ["your complaint", "please be assured"])):
            final_native_response = generate_native_acknowledgment(
                language=final_detected_lang,
                item_name=final_item_name,
                price_diff=diff_pkr
            )

        # Flag for human review if confidence is low or crucial details missing
        needs_review = False
        if final_category == "PERA - Overpricing":
            if final_reported_price <= 0 or not final_canonical_id:
                needs_review = True
                extraction_confidence = min(extraction_confidence, 0.55)
        elif extraction_confidence < 0.60:
            needs_review = True

        extraction_confidence = min(0.99, max(0.20, extraction_confidence))

        return {
            "item_name": final_item_name or "Commodity",
            "item_canonical_id": final_canonical_id,
            "unit": final_unit,
            "reported_price": float(final_reported_price),
            "official_price": float(official_price),
            "price_difference_pkr": float(diff_pkr),
            "percentage_overcharge": float(pct_overcharge),
            "category": final_category,
            "urgency": final_urgency or "Medium",
            "detected_language": final_detected_lang,
            "native_response": final_native_response,
            "routing_agency": agency,
            "helpline_reference": helpline,
            "extraction_confidence": round(extraction_confidence, 2),
            "needs_review": needs_review
        }


# Singleton pipeline instance
ai_pipeline = AIPipeline()
