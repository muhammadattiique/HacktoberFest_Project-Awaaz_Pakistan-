# Implementation Plan

## Overview

Four small, mostly independent changes plus a verification task make the voice feature
language-accurate: upgrade the Whisper model (backend config), confirm language propagation,
add a frontend speech-language helper, wire it into playback, then verify end to end.

## Task Dependency Graph

```
1 (whisper model)  ->  5 (verify)
2 (lang propagation) -> 5
3 (speech helper)  ->  4 (wire playback)  ->  5
```

Tasks 1, 2, and 3 are independent and can be done in any order. Task 4 depends on 3.
Task 5 (verification) depends on all of the above.
```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2", "3"] },
    { "wave": 2, "tasks": ["4"] },
    { "wave": 3, "tasks": ["5"] }
  ]
}
```

## Tasks

- [x] 1. Upgrade Whisper model configuration for multilingual accuracy
  - Change default `WHISPER_MODEL` in `config.py` from `base` to `small` (overridable via env)
  - Add/update `WHISPER_MODEL` note in `.env.example` with download/RAM implication (no secrets)
  - Document the model choice and first-run download in backend README
  - _Requirements: 1.1, 1.2, 5.1, 5.2_

- [x] 2. Confirm detected-language propagation in the pipeline
  - Verify `ai_pipeline.transcribe_audio_detailed` returns detected language and that it
    flows into extraction and native-response generation unchanged
  - Keep the Pakistani `initial_prompt` bias intact
  - _Requirements: 1.3, 2.1_

- [x] 3. Add frontend speech-language mapping helper
  - Create `src/lib/speechLang.js` with `getSpeechLangCode(detectedLanguage)`
  - Implement ordered fallbacks per language (Urdu/Roman Urdu -> ur-PK, Punjabi -> pa-IN,
    Pashto -> ps-AF, English -> en-US) using available `speechSynthesis` voices
  - _Requirements: 2.2, 2.3_

- [x] 4. Wire Replay Voice and auto-speak to the helper
  - Replace both inline `detected_language === 'Urdu' ? 'ur-PK' : 'en-US'` expressions in
    `ReportSection.jsx` with `getSpeechLangCode(...)`
  - _Requirements: 2.2, 2.3_

- [x] 5. Verify no regressions and offline operation
  - Run existing backend tests (or document live verification if pytest unavailable)
  - Run frontend `npm run build` and `npm run lint`
  - Live end-to-end: submit two different-language voice inputs; confirm transcript and
    acknowledgement match the spoken language and differ from each other
  - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 5.3_

## Notes

- The model upgrade triggers a one-time Whisper `small` download (~460 MB) and uses more
  RAM/CPU than `base`; this is the main accuracy lever and is expected.
- Error handling and FFmpeg resolution were fixed in prior work and are only verified here.


