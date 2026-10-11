# Design Document

## Overview

Make the voice complaint path language-aware and accurate for all five supported
languages (Urdu, Roman Urdu, Punjabi, Pashto, English) while staying fully offline.
Investigation of the current code identified three concrete root causes:

1. Backend uses the Whisper `base` model (`config.py: WHISPER_MODEL = "base"`), which is
   English-biased and transcribes Urdu/Punjabi/Pashto poorly or empty.
2. The frontend "Replay Voice" / acknowledgement playback maps only `Urdu -> ur-PK` and
   routes every other detected language to `en-US`
   (`ReportSection.jsx`), so Roman Urdu/Punjabi/Pashto are spoken in English.
3. There is no explicit language -> speech-synthesis mapping helper, so playback cannot
   degrade gracefully to the closest voice.

Error handling and audio conversion were already fixed in prior work (actionable 503 on
transcription failure, 400 on silence, FFmpeg resolution with imageio-ffmpeg fallback) and
are preserved here.

## Architecture

Unchanged pipeline, with model/config and language-mapping improvements:

Citizen audio -> FFmpeg (16 kHz mono WAV) -> Whisper (multilingual) -> transcript + detected
language -> Ollama/rule hybrid extraction -> native acknowledgement -> API response ->
frontend verdict + language-correct Replay Voice.

## Components and Interfaces

### 1. Whisper model configuration (backend)
- File: `config.py`
- Change the default `WHISPER_MODEL` from `base` to a multilingual model (`small` as the
  default balance of accuracy vs. resources), overridable via the `WHISPER_MODEL`
  environment variable (already supported by pydantic settings).
- Document the download/RAM implication in `.env.example` and README (no secrets).
- Rationale: `small`/`medium` dramatically improve Urdu/Punjabi/Pashto over `base`; `small`
  is the safe default for consumer hardware while remaining much better than `base`.

### 2. Transcription language retention (backend)
- File: `ai_pipeline.py`
- Already returns `language` and `text`; verify the detected language flows into the
  extraction and native-response generation. Keep the Pakistani `initial_prompt` bias.
- No structural change required beyond confirming `detected_language` propagation.

### 3. Speech-synthesis language mapping (frontend)
- New helper: `src/lib/speechLang.js` exporting `getSpeechLangCode(detectedLanguage)`.
  Mapping:
  - Urdu -> `ur-PK`
  - Roman Urdu -> `ur-PK` (closest native voice; falls back to `hi-IN` then `en-US` if ur-PK
    voice is unavailable in the browser)
  - Punjabi -> `pa-IN` (fallback `ur-PK` -> `en-US`)
  - Pashto -> `ps-AF` (fallback `fa-IR` -> `en-US`)
  - English -> `en-US`
- The helper inspects `window.speechSynthesis.getVoices()` and returns the first available
  code from the ordered fallback list, so playback never silently becomes English when a
  closer voice exists.

### 4. Replay Voice wiring (frontend)
- File: `ReportSection.jsx`
- Replace both inline `data.detected_language === 'Urdu' ? 'ur-PK' : 'en-US'` expressions
  (the auto-speak on verdict and the "Replay Voice" button) with `getSpeechLangCode(...)`.

## Data Models

No schema changes. `detected_language` already exists on the complaint response and is used
for RTL rendering and now for voice selection.

## Error Handling

Preserved from current implementation:
- Transcription failure -> HTTP 503 with actionable message; no fabricated result.
- Silent/no-speech audio -> HTTP 400 "no audible speech".
- Frontend maps 400/413/415/422/503/500 and network errors to specific messages and offers
  the text fallback.

## Testing Strategy

- Backend: run existing `tests/` (test_pipeline, test_api, test_audio) to confirm no
  regression from the model-config change. Where pytest is unavailable in the environment,
  document the live verification steps.
- Model behaviour: perform a live end-to-end check once the backend is running with the new
  model, submitting at least two different-language inputs and confirming the transcript and
  acknowledgement match the spoken language (and differ from each other).
- Frontend: `npm run build` and `npm run lint`; unit-free manual check that
  `getSpeechLangCode` returns expected codes and falls back correctly.
- Confirm offline operation (no cloud transcription dependency introduced).

