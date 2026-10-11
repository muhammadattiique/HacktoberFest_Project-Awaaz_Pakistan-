import os
import re
import sys
import json
import time
import types
import wave
import logging
import threading
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import ollama

# NOTE: the faster-whisper `WhisperModel` is imported lazily inside
# `_init_whisper()` (via `_import_whisper_model()`) rather than at module load.
# This keeps the backend able to start and serve text complaints even on
# machines where a native extension cannot load (e.g. blocked by a Windows
# Smart App Control / Application Control policy). Voice transcription then
# fails gracefully with a 503 instead of crashing the whole app at import time.
#
# faster-whisper's default audio decoder is PyAV (`av`), whose native DLL is
# blocked by Smart App Control on the target machine. We never need PyAV: the
# audio is already decoded to a 16 kHz mono PCM WAV by services/audio.py and we
# feed faster-whisper a decoded numpy array directly. `_import_whisper_model()`
# stubs out `faster_whisper.audio` in sys.modules before importing so `import av`
# is never triggered.

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

# JSON schema for Ollama structured generation (one commodity/issue == one item)
COMPLAINT_ITEM_SCHEMA = {
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

# Multi-item wrapper schema: a submission may name several commodities/issues.
COMPLAINT_SCHEMA_MULTI = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": COMPLAINT_ITEM_SCHEMA,
            "minItems": 1
        }
    },
    "required": ["items"]
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
If the complaint mentions multiple commodities or multiple distinct issues, return one object per commodity/issue in items.

Examples:
Input: "آلو مارکیٹ میں دو سو روپے کلو بیچ رہے ہیں جبکہ لسٹ میں سو روپے ہے۔"
Output: {"items": [{
  "item_name": "Potato",
  "reported_price": 200,
  "category": "PERA - Overpricing",
  "urgency": "High",
  "detected_language": "Urdu",
  "native_response": "آپ کی شکایت موصول ہو چکی ہے۔ پرائس کنٹرول مجسٹریٹ کو کارروائی کے لیے مطلع کر دیا گیا ہے۔ شکریہ۔"
}]}

Input: "Bhai Raja Bazaar mein Madina store wala doodh 280 rupay liter de raha hai, bohat loot machai hai."
Output: {"items": [{
  "item_name": "Fresh Milk",
  "reported_price": 280,
  "category": "PERA - Overpricing",
  "urgency": "Medium",
  "detected_language": "Roman Urdu",
  "native_response": "Aap ki shikayat darj kar li gayi hai. Price Control team ko karwai ke liye bhaij diya gaya hai. Shukriya."
}]}

Input: "Tandoor aale ne roti bees rupay di ditti ae, aakhda ae aata mehnga ae."
Output: {"items": [{
  "item_name": "Tandoori Roti",
  "reported_price": 20,
  "category": "PERA - Overpricing",
  "urgency": "Medium",
  "detected_language": "Punjabi",
  "native_response": "تہاڈی شکایت درج ہو گئی اے۔ متعلقہ مجسٹریٹ نوں کارروائی واسطے بھیج دتا گیا اے۔ مہربانی۔"
}]}

Input: "Dukaan waale khorak kharab shaway shodi rakrre di, dukaandar da pfa yaftah na de."
Output: {"items": [{
  "item_name": "Spoiled Food",
  "reported_price": 0,
  "category": "PFA - Food Safety",
  "urgency": "High",
  "detected_language": "Pashto",
  "native_response": "ستاسو شکایت ثبت شو او د خوړو خوندیتوب ادارې ته واستول شو. مننه."
}]}

Input: "Open sewerage gutter overflowing in front of school in G-9 Markaz Islamabad."
Output: {"items": [{
  "item_name": "Open Sewerage",
  "reported_price": 0,
  "category": "Municipal - Infrastructure",
  "urgency": "High",
  "detected_language": "English",
  "native_response": "Your complaint regarding open sewerage has been routed to CDA / Municipal services for immediate clearance."
}]}

Input: "Bhai sahab, Raja Bazaar mein dukandar aaloo 150 rupay kilo bech raha hai jabke sarkari rate kam hai. Pyaaz bhi 200 rupay kilo le raha hai."
Output: {"items": [
  {
    "item_name": "Potato",
    "reported_price": 150,
    "category": "PERA - Overpricing",
    "urgency": "High",
    "detected_language": "Roman Urdu",
    "native_response": "Aap ki shikayat darj kar li gayi hai. Price Control Magistrate ko karwai ke liye bhaij diya gaya hai. Shukriya."
  },
  {
    "item_name": "Onion",
    "reported_price": 200,
    "category": "PERA - Overpricing",
    "urgency": "High",
    "detected_language": "Roman Urdu",
    "native_response": "Aap ki shikayat darj kar li gayi hai. Price Control Magistrate ko karwai ke liye bhaij diya gaya hai. Shukriya."
  }
]}
"""


def _import_whisper_model():
    """Import faster-whisper's ``WhisperModel`` without pulling in PyAV (`av`).

    faster-whisper's package import (`faster_whisper/__init__.py`) and its
    `transcribe` module both import `faster_whisper.audio`, which does
    `import av`. The native `av` DLL is blocked by Windows Smart App Control on
    the target machine, so that import raises an ImportError at load time.

    We never use PyAV: audio is pre-decoded to a 16 kHz mono PCM WAV and fed to
    the model as a numpy array. So we insert a lightweight stub module for
    `faster_whisper.audio` into ``sys.modules`` before importing faster-whisper,
    which short-circuits the real module (and its `import av`).

    Only ``decode_audio`` (the PyAV-backed function) is replaced with a raising
    stub — it is reached solely when a file path or raw bytes is passed to
    ``transcribe``, which we never do. ``pad_or_trim`` is a pure-numpy helper
    that ``transcribe`` DOES call internally (e.g. during language detection and
    per-segment encoding), so it is re-implemented here identically to the
    upstream version. PyAV is never imported.

    Called only from ``_init_whisper`` (never at module import time) so a load
    failure degrades voice to a 503 instead of crashing app startup.
    """
    if "faster_whisper.audio" not in sys.modules:
        stub = types.ModuleType("faster_whisper.audio")

        def _decode_audio_unavailable(*_args, **_kwargs):  # pragma: no cover
            raise RuntimeError(
                "faster_whisper.audio.decode_audio (PyAV) is stubbed out; audio "
                "is decoded with the stdlib wave module and passed as a numpy "
                "array instead."
            )

        def pad_or_trim(array, length: int = 3000, *, axis: int = -1):
            """Pad/trim the array along ``axis`` to ``length`` (numpy-only).

            Mirrors faster_whisper.audio.pad_or_trim so language detection and
            segment encoding work without importing PyAV.
            """
            if array.shape[axis] > length:
                array = array.take(indices=range(length), axis=axis)
            if array.shape[axis] < length:
                pad_widths = [(0, 0)] * array.ndim
                pad_widths[axis] = (0, length - array.shape[axis])
                array = np.pad(array, pad_widths)
            return array

        stub.decode_audio = _decode_audio_unavailable
        stub.pad_or_trim = pad_or_trim
        sys.modules["faster_whisper.audio"] = stub

    from faster_whisper import WhisperModel

    return WhisperModel


def _load_wav_mono_float32(path: str) -> np.ndarray:
    """Load a 16 kHz mono 16-bit PCM WAV into a float32 array in [-1, 1].

    Uses only the stdlib ``wave`` module and numpy — no librosa, soundfile, or
    PyAV. services/audio.py guarantees the input is 16 kHz mono 16-bit PCM, so
    the common path is a straight int16 -> float32 conversion. The channel and
    sample-rate handling below is defensive only.
    """
    with wave.open(path, "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frame_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    if sample_width != 2:
        raise ValueError(
            f"Expected 16-bit PCM WAV (sample width 2), got {sample_width}."
        )

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

    # Defensive: average channels to mono if a multi-channel WAV slips through.
    if n_channels > 1:
        audio = audio.reshape(-1, n_channels).mean(axis=1)

    # Defensive: FFmpeg guarantees 16 kHz, so we never resample here (that would
    # require an extra native dependency). Just warn if the guarantee is broken.
    if frame_rate != 16000:
        logger.warning(
            "WAV sample rate is %d Hz, expected 16000 Hz; transcribing as-is.",
            frame_rate,
        )

    return np.ascontiguousarray(audio, dtype=np.float32)


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
        """Load the faster-whisper model with timing log."""
        start_t = time.time()
        try:
            # Imported lazily (with faster_whisper.audio / PyAV stubbed out) so a
            # blocked/unavailable native extension degrades voice transcription
            # to a 503 instead of preventing the whole backend from importing.
            WhisperModel = _import_whisper_model()
            logger.info(f"Loading Whisper model '{settings.WHISPER_MODEL}' on {settings.WHISPER_DEVICE}...")
            self._whisper_model = WhisperModel(
                settings.WHISPER_MODEL,
                device=settings.WHISPER_DEVICE,
                compute_type="int8"
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

        try:
            audio_array = _load_wav_mono_float32(audio_file_path)
        except Exception as e:
            logger.exception(f"Failed to load audio for transcription: {e}")
            return {
                "text": "",
                "language": "ur",
                "confidence": 0.0,
                "segments": [],
                "error": str(e)
            }

        with self._whisper_lock:
            try:
                segments_gen, info = self._whisper_model.transcribe(
                    audio_array,
                    language=None,
                    initial_prompt=WHISPER_INITIAL_PROMPT,
                    condition_on_previous_text=False,
                    temperature=0.0,
                    vad_filter=True
                )
                # `segments_gen` is a generator; materialize it (and surface any
                # lazy decode error) inside the lock/try as plain dicts shaped
                # like the downstream post-processing expects.
                segments = [
                    {
                        "text": s.text,
                        "no_speech_prob": s.no_speech_prob,
                        "avg_logprob": s.avg_logprob,
                        "start": s.start,
                        "end": s.end,
                    }
                    for s in segments_gen
                ]
            except Exception as e:
                logger.exception(f"Whisper transcription failed: {e}")
                return {
                    "text": "",
                    "language": "ur",
                    "confidence": 0.0,
                    "segments": [],
                    "error": str(e)
                }

        raw_text = "".join(s["text"] for s in segments).strip()
        detected_lang = info.language or "ur"

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

    def _call_ollama_llm_multi(self, text: str) -> Optional[List[dict]]:
        """Call Ollama with the multi-item wrapper schema.

        Mirrors ``_call_ollama_llm`` but passes ``format=COMPLAINT_SCHEMA_MULTI``,
        parses the ``{"items": [...]}`` wrapper, and returns the item list.
        A bare object (small-model drift) is coerced to a one-element list.
        Returns None on failure so the caller degrades to rule-only discovery.
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
                    format=COMPLAINT_SCHEMA_MULTI
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
                parsed = json.loads(match.group(1)) if match else json.loads(clean_json)

                if isinstance(parsed, dict) and "items" in parsed:
                    items = parsed["items"]
                    if isinstance(items, list):
                        return items
                    if isinstance(items, dict):
                        return [items]
                    return None
                # Bare object drift: coerce to a one-element list.
                if isinstance(parsed, dict):
                    return [parsed]
                if isinstance(parsed, list):
                    return parsed
                return None

            except Exception as e:
                logger.warning(f"Ollama multi attempt {attempt + 1} failed: {e}")
                time.sleep(0.3)

        return None

    def _segment_clauses(self, text: str) -> List[str]:
        """Split a transcript into per-commodity clauses.

        Splits on sentence punctuation (``.`` ``۔`` ``!`` ``?`` newline) AND the
        enumerating connectives that separate commodities in Pakistani
        code-switching (` bhi `, ` بھی `, ` aur `, ` اور `, and commas ``،``/``,``).
        Fragments are stripped and empties dropped.
        """
        if not text:
            return []
        parts = re.split(
            r"\.|۔|!|\?|\n| bhi | بھی | aur | اور |،|,",
            text,
        )
        return [p.strip() for p in parts if p and p.strip()]

    def _reconcile_item(
        self,
        *,
        item_name_hint: Optional[str],
        reported_price_hint: Optional[float],
        category_hint: Optional[str],
        urgency_hint: Optional[str],
        native_hint: Optional[str],
        clause: Optional[str],
        text: str,
        det_lang: str,
        rule_cat: str,
        rule_urg: str,
        has_llm: bool,
    ) -> Dict[str, Any]:
        """Reconcile a single extracted item into the canonical 15-key dict.

        This is the second half of the historical single-item
        ``parse_complaint_text`` lifted verbatim and parameterised per item.
        """
        # 1. Resolve canonical id from the item name hint.
        final_canonical_id = None
        final_item_name = None
        final_unit = "kg"
        if item_name_hint:
            res = rate_service.resolve_item(item_name_hint)
            if res:
                final_canonical_id, item_info, _ = res
                final_item_name = item_info.get("name_en", item_name_hint)
                final_unit = item_info.get("unit", "kg")
            else:
                final_item_name = str(item_name_hint)

        # 2. Price precedence: rule-extracted clause price wins over LLM hint.
        rule_price, _rule_price_conf = extract_price_and_normalize(clause or text)
        if rule_price and rule_price > 0:
            price = rule_price
        else:
            try:
                llm_price_val = float(reported_price_hint) if reported_price_hint is not None else 0.0
            except (ValueError, TypeError):
                llm_price_val = 0.0
            price = llm_price_val if llm_price_val > 0 else 0.0

        # 3. Category: deterministic rules override LLM for Food Safety / Infra.
        valid_categories = ["PERA - Overpricing", "PFA - Food Safety", "Municipal - Infrastructure"]
        if rule_cat in ["PFA - Food Safety", "Municipal - Infrastructure"]:
            final_category = rule_cat
        elif category_hint in valid_categories:
            final_category = category_hint
        else:
            final_category = rule_cat

        # Urgency hint only when valid; otherwise filled by threshold logic below.
        final_urgency = urgency_hint if urgency_hint in ["Low", "Medium", "High"] else None

        # 4. Compare reported price against official notified rate.
        comparison = rate_service.compare_price(
            item_id=final_canonical_id or "",
            reported_price=price,
            unit=final_unit
        )
        official_price = comparison.get("official_price", 0.0)
        diff_pkr = comparison.get("price_difference_pkr", 0.0)
        pct_overcharge = comparison.get("percentage_overcharge", 0.0)

        # 5. Align urgency with overcharge severity for Overpricing; for the
        # deterministic PFA/Municipal categories defer to the rule-derived
        # urgency (which carries the illness/hazard escalation) when there is no
        # valid LLM hint.
        if final_category == "PERA - Overpricing":
            if pct_overcharge >= settings.HIGH_SEVERITY_THRESHOLD_PCT:
                final_urgency = "High"
            elif pct_overcharge >= settings.OVERCHARGE_ALERT_THRESHOLD_PCT:
                final_urgency = "Medium"
            elif not final_urgency:
                final_urgency = "Low"
        elif final_category in ("PFA - Food Safety", "Municipal - Infrastructure"):
            if not final_urgency:
                final_urgency = rule_urg

        # 6. Routing agency + helpline, with hard PFA/Municipal overrides.
        _, _, agency, helpline = classify_category_and_urgency(text, pct_overcharge)
        if final_category == "PFA - Food Safety":
            agency = "Punjab Food Authority (PFA)"
            helpline = settings.PFA_FOOD_SAFETY_HELPLINE
        elif final_category == "Municipal - Infrastructure":
            agency = "Capital Development Authority (CDA / MCI) / WASA Rawalpindi"
            helpline = settings.CDA_MUNICIPAL_HELPLINE

        # 7. Native acknowledgment: keep usable LLM hint, else generate it.
        final_native_response = None
        if native_hint and len(native_hint) > 10 and not (
            det_lang == "Roman Urdu"
            and any(w in native_hint.lower() for w in ["your complaint", "please be assured", "dear citizen"])
        ):
            final_native_response = native_hint
        if not final_native_response:
            final_native_response = generate_native_acknowledgment(
                language=det_lang,
                item_name=final_item_name,
                price_diff=diff_pkr
            )

        # 8. Confidence + review flag.
        extraction_confidence = 0.50
        if has_llm:
            extraction_confidence += 0.35
        needs_review = False
        if final_category == "PERA - Overpricing":
            if price <= 0 or not final_canonical_id:
                needs_review = True
                extraction_confidence = min(extraction_confidence, 0.55)
        elif extraction_confidence < 0.60:
            needs_review = True
        extraction_confidence = min(0.99, max(0.20, extraction_confidence))

        return {
            "item_name": final_item_name or "Commodity",
            "item_canonical_id": final_canonical_id,
            "unit": final_unit,
            "reported_price": float(price),
            "official_price": float(official_price),
            "price_difference_pkr": float(diff_pkr),
            "percentage_overcharge": float(pct_overcharge),
            "category": final_category,
            "urgency": final_urgency or "Medium",
            "detected_language": det_lang,
            "native_response": final_native_response,
            "routing_agency": agency,
            "helpline_reference": helpline,
            "extraction_confidence": round(extraction_confidence, 2),
            "needs_review": needs_review
        }

    def _unspecified_item(self, *, det_lang: str, text: str, rule_cat: str, rule_urg: str) -> Dict[str, Any]:
        """The rule-only 'Unspecified Commodity' fallback item (no resolvable id)."""
        return self._reconcile_item(
            item_name_hint="Unspecified Commodity",
            reported_price_hint=None,
            category_hint=None,
            urgency_hint=None,
            native_hint=None,
            clause=text,
            text=text,
            det_lang=det_lang,
            rule_cat=rule_cat,
            rule_urg=rule_urg,
            has_llm=False,
        )

    def _price_clause_for(self, index: int, clauses: List[str]) -> str:
        """Return the clause used for price extraction for the commodity found at
        ``clauses[index]``.

        A splitting connective (e.g. ` bhi `) can separate the commodity word
        from its price (``"Pyaaz"`` | ``"200 rupay kilo"``). When the commodity's
        own clause carries no price, borrow the immediately following clause if
        that one has a price but names no (other) commodity.
        """
        own = clauses[index]
        own_price, _ = extract_price_and_normalize(own)
        if own_price and own_price > 0:
            return own
        nxt_i = index + 1
        if nxt_i < len(clauses):
            nxt = clauses[nxt_i]
            nxt_price, _ = extract_price_and_normalize(nxt)
            if nxt_price and nxt_price > 0 and not rate_service.find_all_items(nxt):
                return nxt
        return own

    def _discover_items_by_rules(
        self,
        clauses: List[str],
        *,
        text: str,
        det_lang: str,
        rule_cat: str,
        rule_urg: str,
    ) -> List[Dict[str, Any]]:
        """Rule-only multi-item discovery across clauses. Always returns >=1 item."""
        out: List[Dict[str, Any]] = []
        seen: set = set()
        for idx, clause in enumerate(clauses):
            found = rate_service.find_all_items(clause)
            for canonical_id, item_info in found:
                if canonical_id in seen:
                    continue
                seen.add(canonical_id)
                price_clause = self._price_clause_for(idx, clauses) if len(found) == 1 else clause
                out.append(
                    self._reconcile_item(
                        item_name_hint=item_info.get("name_en", canonical_id),
                        reported_price_hint=None,
                        category_hint=None,
                        urgency_hint=None,
                        native_hint=None,
                        clause=price_clause,
                        text=text,
                        det_lang=det_lang,
                        rule_cat=rule_cat,
                        rule_urg=rule_urg,
                        has_llm=False,
                    )
                )
        if not out:
            # No clause yielded a resolvable commodity -> single Unspecified item.
            out.append(self._unspecified_item(det_lang=det_lang, text=text, rule_cat=rule_cat, rule_urg=rule_urg))
        return out

    def _attribute_clause(self, item_name_hint: Optional[str], clauses: List[str]) -> Optional[str]:
        """Pick the clause that names this item (via rate_service aliases)."""
        if not item_name_hint:
            return None
        res = rate_service.resolve_item(item_name_hint)
        target_id = res[0] if res else None
        for clause in clauses:
            ids = {cid for cid, _ in rate_service.find_all_items(clause)}
            if target_id and target_id in ids:
                return clause
            if item_name_hint.lower().strip() in clause.lower():
                return clause
        return None

    def parse_complaint_items(self, transcript_text: str) -> List[Dict[str, Any]]:
        """Return a list of per-item extraction dicts (each in the historical
        single-item shape). Never raises; always returns >=1 element.
        """
        try:
            if not transcript_text or not transcript_text.strip():
                return [{
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
                }]

            text = transcript_text.strip()
            det_lang = detect_language(text)
            rule_cat, rule_urg, _, _ = classify_category_and_urgency(text)
            clauses = self._segment_clauses(text) or [text]

            # LLM list (never let an outage break the complaint).
            llm_items: List[Dict[str, Any]] = []
            llm_output = None
            try:
                llm_output = self._call_ollama_llm_multi(text)
            except Exception as exc:
                logger.warning(f"Ollama multi LLM call raised, falling back to rules: {exc}")
                llm_output = None

            if llm_output and isinstance(llm_output, list):
                for raw in llm_output:
                    if not isinstance(raw, dict):
                        continue
                    item_name_hint = raw.get("item_name")
                    clause = self._attribute_clause(item_name_hint, clauses)
                    llm_items.append(
                        self._reconcile_item(
                            item_name_hint=item_name_hint,
                            reported_price_hint=raw.get("reported_price"),
                            category_hint=raw.get("category"),
                            urgency_hint=raw.get("urgency"),
                            native_hint=raw.get("native_response"),
                            clause=clause,
                            text=text,
                            det_lang=det_lang,
                            rule_cat=rule_cat,
                            rule_urg=rule_urg,
                            has_llm=True,
                        )
                    )

            # Rule-only discovery (always run so LLM-missed items are caught).
            rule_items = self._discover_items_by_rules(
                clauses, text=text, det_lang=det_lang, rule_cat=rule_cat, rule_urg=rule_urg
            )

            # Union + de-dupe by canonical id.
            merged: Dict[str, Dict[str, Any]] = {}
            order: List[str] = []
            unresolved: List[Dict[str, Any]] = []

            def _key(item: Dict[str, Any]) -> Optional[str]:
                return item.get("item_canonical_id")

            def _add(item: Dict[str, Any], from_llm: bool) -> None:
                cid = _key(item)
                if cid is None:
                    unresolved.append(item)
                    return
                if cid not in merged:
                    merged[cid] = dict(item)
                    order.append(cid)
                    return
                existing = merged[cid]
                if from_llm:
                    # Keep rule price when it is > 0; else take this LLM price.
                    if not (existing.get("reported_price") or 0) > 0 and (item.get("reported_price") or 0) > 0:
                        for k in ("reported_price", "official_price", "price_difference_pkr", "percentage_overcharge"):
                            existing[k] = item[k]
                    # LLM carries richer classification + wording.
                    for k in ("category", "urgency", "native_response"):
                        if item.get(k):
                            existing[k] = item[k]
                else:
                    # Rule row price is authoritative when > 0.
                    if (item.get("reported_price") or 0) > 0:
                        for k in ("reported_price", "official_price", "price_difference_pkr", "percentage_overcharge"):
                            existing[k] = item[k]
                    for k in ("item_name", "unit"):
                        if item.get(k):
                            existing[k] = item[k]

            # Rule rows first so they are the identity/price authority.
            for it in rule_items:
                _add(it, from_llm=False)
            for it in llm_items:
                _add(it, from_llm=True)

            final_items = [merged[cid] for cid in order]
            # Keep unresolved rows only when no resolved row exists.
            if not final_items and unresolved:
                final_items = unresolved

            if not final_items:
                final_items = [self._unspecified_item(det_lang=det_lang, text=text, rule_cat=rule_cat, rule_urg=rule_urg)]

            # Order by overcharge desc, ties keep insertion order.
            final_items.sort(key=lambda i: i.get("percentage_overcharge", 0.0), reverse=True)
            return final_items

        except Exception as exc:  # pragma: no cover - defensive guardrail
            logger.exception(f"parse_complaint_items failed, returning safe fallback: {exc}")
            return [{
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
            }]

    def parse_complaint_text(self, transcript_text: str) -> Dict[str, Any]:
        """
        Hybrid AI pipeline (single-item facade).

        Returns the primary (highest-overcharge) item from the multi-item
        extraction so every existing single-item caller/test is unchanged.
        """
        items = self.parse_complaint_items(transcript_text)
        return items[0]


# Singleton pipeline instance
ai_pipeline = AIPipeline()
