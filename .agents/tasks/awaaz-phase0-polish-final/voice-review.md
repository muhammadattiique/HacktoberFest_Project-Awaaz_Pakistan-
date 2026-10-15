# faster-whisper transcription under Windows Smart App Control

The voice path previously crashed at the native `av` (PyAV) decoder, which is blocked by Windows Smart App Control, so `/api/complaints/voice` returned the 503 "temporarily unavailable" message for both mic recording and audio upload. This change swaps the openai-whisper engine for faster-whisper (CTranslate2), stubs out `faster_whisper.audio` in `sys.modules` before import so PyAV is never loaded, and decodes the already-FFmpeg-normalized 16 kHz mono WAV with a stdlib `wave` + numpy helper that feeds faster-whisper a float32 numpy array instead of a file path. The whole engine import stays lazy inside `_init_whisper`, so a load failure still degrades to a graceful 503 rather than crashing app startup. Watch for: the `pad_or_trim` stub is the one subtle piece — it has to be a real numpy re-implementation (not a no-op) because `transcribe()` calls it during language detection; the coder hit and fixed exactly this (confirmed in the verification note). The live end-to-end evidence for both mic/synthetic (.wav) and upload (.ogg) is present and shows HTTP 201, not 503.

**Verdict**: APPROVED

## High-level view

The engine swap is confined to the transcription surface of `ai_pipeline.py`. The PyAV problem is solved by inserting a stub `faster_whisper.audio` module into `sys.modules` ahead of `from faster_whisper import WhisperModel`; `decode_audio` becomes a raising stub (never reached because audio is passed as an array, not a path) while `pad_or_trim` is re-implemented in pure numpy because `transcribe()` genuinely calls it. Audio decoding moved to a stdlib-`wave` loader that normalizes int16 to float32 in [-1, 1] with defensive mono/sample-rate handling, numpy-only.

The return contract is the stable anchor the router depends on, and it is preserved exactly: the model-None early return, the audio-load and transcribe error dicts, and the success dict `{text, language, confidence, segments}` all keep their old shapes. Every post-processing branch (no_speech_prob > 0.60 discard, ≥5-consecutive-word repetition discard, canned-phrase discard, avg_confidence) is byte-for-byte intact, now reading the materialized segment dicts.

Concurrency boundary held: `parse_complaint_text`, `COMPLAINT_SCHEMA`, `FEW_SHOT_SYSTEM_PROMPT`, and `_call_ollama_llm` are untouched by this diff. The `routers/complaints.py` changes in the working tree are threadpool-offloading edits owned by the concurrent workflow, not transcription-contract changes, and the 503 branch still keys off the same transcription result dict.

The mandatory live evidence is present: MODEL LOADED confirmed under SAC, and two `/api/complaints/voice` POSTs — a SAPI-generated speech WAV and `synthetic_en_10s.ogg` — both returned HTTP 201 with non-empty transcripts and populated categories, not a 503.

<details>
<summary>Issues (0)</summary>

No blocking or non-blocking findings. All requirements verified.

</details>

<details>
<summary>Details</summary>

### PyAV bypass via sys.modules stub

A grep of the final `ai_pipeline.py` finds `import av`, `import whisper`, and `whisper.load_model` only inside docstrings and comments, never as executable imports (confirmed). `WhisperModel` is pulled in only inside `_import_whisper_model()`, which runs solely from `_init_whisper`.

The `pad_or_trim` stub is the trap worth calling out. `decode_audio` is a raiser (only reached for path/bytes inputs this code never passes), but `pad_or_trim` had to be re-implemented in numpy identically to upstream rather than stubbed to a no-op, because `transcribe()` calls it internally during language detection and segment encoding. The verification note records that the first run 503'd precisely because the stub's `pad_or_trim` was initially inadequate, root-caused it, and the passing live POSTs are from the corrected run.

### Concurrency boundary

The `ai_pipeline.py` diff touches only the imports, the two new helpers, `_init_whisper`, and the model-call section of `transcribe_audio_detailed`. `parse_complaint_text`, `COMPLAINT_SCHEMA`, `FEW_SHOT_SYSTEM_PROMPT`, and `_call_ollama_llm` are not in this diff — the concurrency boundary holds. The `routers/complaints.py` working-tree changes are `run_in_threadpool` offloading owned by the concurrent workflow; the 503 branch still consumes the transcription result dict unchanged, so the graceful-503 contract is intact.

### Live evidence check

The required evidence is present in the verification note and sufficient: (1) MODEL LOADED under SAC with `whisper_loaded` asserted true; (2) mic/synthetic .wav POST to `/api/complaints/voice` → HTTP 201 with a real transcript and `category=PERA - Overpricing`, not 503; (3) .ogg upload POST → HTTP 201 with transcript and populated category, not 503. The full suite is reported at 41 passed. Per instructions I did not re-run the server, model load, or pytest; the one narrow spot-check I ran — grepping the final `ai_pipeline.py` for a stray executable `import av` — came back clean.

</details>

<details>
<summary>File map</summary>

- `awaaz_backend/ai_pipeline.py` — engine swapped to faster-whisper via sys.modules stub; new `_import_whisper_model` and `_load_wav_mono_float32` helpers; `_init_whisper` and the model-call half of `transcribe_audio_detailed` rewritten; post-processing and return contract preserved.
- `awaaz_backend/requirements.txt` — added `faster-whisper>=1.2.0` and `numpy>=1.26`; kept `openai-whisper`/`torch` for bench/Dockerfile.
- `awaaz_backend/routers/complaints.py` — threadpool offloading (concurrent workflow, out of this task's scope); transcription-result 503 contract unchanged.

Full diff: `git diff main -- awaaz_backend/ai_pipeline.py awaaz_backend/requirements.txt`

</details>
