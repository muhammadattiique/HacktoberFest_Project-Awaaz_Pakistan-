# Voice Transcription Fix — Implementation Plan

Goal: Make `/api/complaints/voice` work for BOTH mic recording and audio upload by replacing the OpenAI reference `whisper` engine with `faster-whisper` (CTranslate2 backend), loading audio WITHOUT the PyAV (`av`) native dependency, so transcription works with Windows Smart App Control ON.

Scope is strictly the Whisper/transcription surface of `awaaz_backend/ai_pipeline.py` plus `requirements.txt` and the transcription-specific test mocks. Do NOT touch `parse_complaint_text`, `parse_complaint_items`, `COMPLAINT_SCHEMA`, `FEW_SHOT_SYSTEM_PROMPT`, or any Ollama/LLM parsing logic — another workflow is concurrently editing those.

---

## Verified facts (from investigation — do not re-litigate)

Each decision below was confirmed by reading the real code and running it in `awaaz_backend\venv`:

1. **`import av` is blocked by Application Control** — confirmed: `import faster_whisper` fails at `faster_whisper/__init__.py:1` → `faster_whisper.audio` → `import av` → `ImportError: DLL load failed ... An Application Control policy has blocked this file`. `ctranslate2`, `numpy` (2.5.4), `tokenizers`, `onnxruntime` load fine.
2. **`faster_whisper/transcribe.py` ALSO imports `av` indirectly** — its module top has `from faster_whisper.audio import decode_audio, pad_or_trim`. So `from faster_whisper.transcribe import WhisperModel` does NOT help; it still triggers `faster_whisper/__init__.py` and then transcribe's own `faster_whisper.audio` import. Both paths pull in `av`.
3. **The working bypass (CONFIRMED):** insert a stub module for `faster_whisper.audio` into `sys.modules` BEFORE importing `faster_whisper`, then `from faster_whisper import WhisperModel` succeeds. Verified: `WhisperModel import OK via stub`. We never call `decode_audio`/`pad_or_trim` because we pass a decoded numpy array directly.
4. **End-to-end transcription works under SAC** — confirmed: `WhisperModel('base', device='cpu', compute_type='int8')` loaded (auto-downloaded `Systran/faster-whisper-base` CTranslate2 weights to the HF cache), and `model.transcribe(numpy_float32_array, language=None, condition_on_previous_text=False, temperature=0.0, vad_filter=True)` returned a `segments` generator + `info` object with no `av` involvement.
5. **faster-whisper API shape (CONFIRMED):**
   - `transcribe(...)` returns `(segments, info)`. `segments` is a GENERATOR of `Segment` objects — must be consumed with `list(...)` or iteration.
   - Each `Segment` has `.text`, `.no_speech_prob`, `.avg_logprob`, `.start`, `.end`, `.compression_ratio` (and more).
   - `info` has `.language` (ISO code e.g. `'ur'`, `'en'`, `'ko'`) and `.language_probability`.
   - `transcribe()` accepts the kwargs `language`, `initial_prompt`, `condition_on_previous_text`, `temperature`, `vad_filter` (signature verified).
6. **Audio is always a clean 16 kHz mono 16-bit PCM WAV before transcription** — `services/audio.py:validate_and_convert_audio` runs FFmpeg with `-acodec pcm_s16le -ar 16000 -ac 1` into `processed_16k.wav`, and `routers/complaints.py` passes that WAV path to `transcribe_audio_detailed`. So a stdlib `wave` + numpy loader is always sufficient; no resampling needed in practice.
7. **`import whisper` outside the app runtime:** only `bench/instrumented_server.py` and `Dockerfile` reference `import whisper`/`whisper.load_model`; `torch` is used only by `bench/env_detect.py`. The app runtime (`ai_pipeline.py`) is the ONLY place in the request path. Decision: KEEP `openai-whisper` and `torch` in `requirements.txt` (do not remove) so the bench tooling and Dockerfile do not break — conservative, and the lazy-import keeps them off the serving path. ADD `faster-whisper` and `numpy` (numpy is used directly by the new loader; currently only transitive).
8. **Baseline tests are green:** `pytest tests/test_pipeline.py tests/test_api.py -q` → 23 passed. `test_pipeline.py` never touches transcription. `test_api.py`'s voice tests monkeypatch `ai_pipeline.transcribe_audio_detailed` entirely and only assert the router's 503/400 behavior on the returned dict shape — so preserving the exact return dict shape keeps them passing with NO edits.
9. **No `conftest.py`, no `pytest.ini`.** Tests run from inside `awaaz_backend/` with `TestClient(app)`.

**CONCURRENCY WARNING for the coder:** `ai_pipeline.py` is being edited concurrently by another workflow (multi-item parsing). RE-READ `ai_pipeline.py` immediately before editing. Make minimal, surgical edits confined to: the module-level stub helper, `_init_whisper`, `transcribe_audio_detailed`, `transcribe_audio`, and the new WAV loader helper. Do NOT reformat or touch `parse_complaint_text`/`parse_complaint_items`/`COMPLAINT_SCHEMA`/`FEW_SHOT_SYSTEM_PROMPT`/`_call_ollama_llm`.

---

## Plan

- [ ] 1. Add `faster-whisper` and `numpy` to `awaaz_backend/requirements.txt`; leave `openai-whisper` and `torch` in place.
      Add two lines (e.g. `faster-whisper>=1.2.0` and `numpy>=1.26`) near the existing `openai-whisper`/`torch` lines. Do NOT remove `openai-whisper>=20231117` or `torch>=2.0.0` — `bench/instrumented_server.py`, `bench/env_detect.py`, and `Dockerfile` still import them; the app runtime no longer does, but the lazy import keeps that harmless.
      Files: `awaaz_backend/requirements.txt`
      Verify: `.\venv\Scripts\python.exe -c "import faster_whisper, numpy"` is NOT a valid check (top-level `import faster_whisper` fails under SAC by design). Instead confirm the file parses by running `.\venv\Scripts\python.exe -m pip install -r requirements.txt` and seeing it resolve without error (both packages already installed: faster-whisper 1.2.1, numpy 2.5.4).

- [ ] 2. Add a module-level helper in `ai_pipeline.py` that imports `WhisperModel` while stubbing out `faster_whisper.audio` so `av` is never loaded.
      Add a private function (e.g. `_import_whisper_model()`) that: builds a dummy `types.ModuleType("faster_whisper.audio")` exposing `decode_audio` and `pad_or_trim` as no-op/raise stubs, inserts it into `sys.modules["faster_whisper.audio"]` only if that key is not already present, then does `from faster_whisper import WhisperModel` and returns the class. Add `import sys` and `import types` to the existing imports if not present (keep them with the stdlib imports at the top). Keep this helper tiny and self-contained — it must NOT run at module import time (call it only from inside `_init_whisper`), preserving the "import failure degrades to 503, never crashes app startup" guarantee (design NFR5: no module-level whisper import).
      Files: `awaaz_backend/ai_pipeline.py`
      Verify: `.\venv\Scripts\python.exe -c "from ai_pipeline import _import_whisper_model; print(_import_whisper_model().__name__)"` prints `WhisperModel`.

- [ ] 3. Rewrite `_init_whisper()` to load the faster-whisper model via the stub helper, keeping the lazy-import-inside-try pattern.
      Replace the `import whisper` / `whisper.load_model(...)` body with: `WhisperModel = _import_whisper_model()` then `self._whisper_model = WhisperModel(settings.WHISPER_MODEL, device=settings.WHISPER_DEVICE, compute_type="int8")`. Keep the surrounding `try/except Exception`, the timing log, and `self.whisper_loaded = True/False` exactly as today so any load failure (e.g. first-run download offline) still degrades to a 503 instead of crashing. Keep the existing explanatory comment but update it to reference `faster-whisper`/`av` instead of `tiktoken`/`whisper`.
      Files: `awaaz_backend/ai_pipeline.py`
      Verify: `.\venv\Scripts\python.exe -c "from ai_pipeline import ai_pipeline; ai_pipeline._init_whisper(); print('loaded=', ai_pipeline.whisper_loaded)"` prints `loaded= True` (first run downloads `Systran/faster-whisper-base`; a benign HF symlink UserWarning on stderr is expected and must be ignored).

- [ ] 4. Add a stdlib-`wave` + numpy audio loader helper that reads the 16 kHz mono 16-bit PCM WAV into a normalized float32 numpy array.
      Add a function (module-level or static method, e.g. `_load_wav_mono_float32(path) -> np.ndarray`) that: opens the file with `wave.open(path, "rb")`, reads all frames, asserts/uses `getsampwidth()==2` and `getnchannels()==1`, converts bytes via `numpy.frombuffer(frames, dtype=numpy.int16)`, and returns `(arr.astype(numpy.float32) / 32768.0)`. If `getnchannels()>1` (defensive), reshape and average channels to mono. If `getframerate()!=16000` (defensive), do NOT pull in a resampling lib — log a warning and proceed (the FFmpeg step guarantees 16 kHz; document this). `import numpy as np` and `import wave` at the top (wave is stdlib). Dependency-light: numpy only — NO librosa, NO soundfile, NO av.
      Files: `awaaz_backend/ai_pipeline.py`
      Verify: covered by step 7's end-to-end run (a real decoded WAV is loaded and transcribed). For a quick isolated check, generate a 1 s 16 kHz mono PCM WAV with the stdlib `wave` module and confirm the helper returns a `float32` array of length 16000 in `[-1, 1]`.

- [ ] 5. Rewrite `transcribe_audio_detailed(audio_file_path)` for the faster-whisper API while PRESERVING the exact return contract and all post-processing.
      Keep the existing guards verbatim: the lazy re-init under `self._whisper_lock` when `self._whisper_model` is falsy, and the early return `{"text":"", "language":"ur", "confidence":0.0, "segments":[], "error":"Whisper model not initialized"}` when the model is still None. Then: load the WAV via the step-4 helper (wrap in try/except → on failure return the same error dict shape with `error=str(e)`); call `segments_gen, info = self._whisper_model.transcribe(audio_array, language=None, initial_prompt=WHISPER_INITIAL_PROMPT, condition_on_previous_text=False, temperature=0.0, vad_filter=True)` under `self._whisper_lock` inside try/except (on exception return the error dict exactly as today). Materialize `segments = [{"text": s.text, "no_speech_prob": s.no_speech_prob, "avg_logprob": s.avg_logprob, "start": s.start, "end": s.end} for s in segments_gen]` so later code reading `s.get("no_speech_prob", 0.0)` keeps working, and build `raw_text = "".join(s["text"] for s in segments).strip()`. Set `detected_lang = info.language or "ur"`.
      PRESERVE every existing post-processing branch byte-for-byte in behavior: (a) the `all(no_speech_prob > 0.60)` hallucination discard; (b) the ">=5 consecutive identical words" repetition-loop discard; (c) the canned-phrase discard against `["thank you for watching","subtitles by","amara.org","shukriya","subscribe"]`; (d) the `avg_confidence = max(0.2, min(1.0, 1.0 - mean(no_speech_prob)))` computation defaulting to 0.85 when no segments. Return the SAME success dict shape: `{"text","language","confidence","segments"}`.
      Files: `awaaz_backend/ai_pipeline.py`
      Verify: step 7's end-to-end run exercises this; dict shape is additionally guarded by `tests/test_api.py` voice tests in step 8.

- [ ] 6. Confirm `transcribe_audio(audio_file_path)` is unchanged.
      It delegates to `transcribe_audio_detailed` and returns `res.get("text","")`. No edit needed — it works unchanged with the new implementation. Only touch it if a concurrent merge moved it.
      Files: `awaaz_backend/ai_pipeline.py` (no change expected)
      Verify: `.\venv\Scripts\python.exe -c "from ai_pipeline import ai_pipeline; print(type(ai_pipeline.transcribe_audio).__name__)"` resolves without error.

- [ ] 7. Mandatory end-to-end verification sequence (the coder MUST run all of these and paste results into the FEAT findings / commit notes).
      Files: none (verification only)
      Verify, in order:
      1. **Import-under-SAC:** `.\venv\Scripts\python.exe -c "from ai_pipeline import _import_whisper_model; print(_import_whisper_model().__name__)"` → prints `WhisperModel` (proves no `av`/`tiktoken` import).
      2. **Model-load-under-SAC:** `.\venv\Scripts\python.exe -c "from ai_pipeline import ai_pipeline; ai_pipeline._init_whisper(); assert ai_pipeline.whisper_loaded; print('OK')"` → prints `OK`.
      3. **Live `/voice` end-to-end (mic path, .wav):** start the server on port 8011 (`.\venv\Scripts\python.exe -m uvicorn main:app --port 8011`), generate a short real speech WAV (or a known-good sample), `POST /api/complaints/voice` with the file, and confirm HTTP 201 with a non-empty `transcript_raw` and a populated `category` — NOT the 503 "temporarily unavailable" message. Do NOT reuse any port already serving; 8011 is reserved for this check.
      4. **Upload path (.ogg):** `POST /api/complaints/voice` with a `.ogg` file to the same running server; confirm 201 (FFmpeg converts `.ogg` → 16 kHz WAV, then faster-whisper transcribes). Confirms the upload-audio feature the user asked for.
      5. **Silent/empty audio still 400:** post a silent clip and confirm the existing 400 "No audible speech detected" path still triggers (post-processing + silence guard intact).
      6. **Test suite:** `.\venv\Scripts\python.exe -m pytest tests/ -q` → all pass (baseline was 23 passed for pipeline+api; full suite must stay green).

- [ ] 8. Update ONLY transcription-specific test mocks if (and only if) any assert on the old whisper internals; do not weaken coverage or touch unrelated tests.
      The current `tests/test_api.py` voice tests (`test_voice_transcription_failure_returns_503`, `test_voice_no_speech_returns_400`) monkeypatch `ai_pipeline.transcribe_audio_detailed` to return a dict and assert on router status codes — they do NOT reference the whisper engine and should keep passing UNCHANGED because the return dict shape is preserved. `tests/test_pipeline.py` does not touch transcription. Therefore the expected outcome is: NO test edits needed. Only if a test is found asserting on `whisper.load_model`, `result["segments"]` internal keys, or openai-whisper's `result` dict directly, update that specific assertion to the faster-whisper Segment-dict shape (`no_speech_prob`, `avg_logprob`, `start`, `end`, `text`) without reducing what it covers. Grep first: `whisper.load_model`, `transcribe(` assertions, `no_speech_prob`.
      Files: `awaaz_backend/tests/test_api.py`, `awaaz_backend/tests/test_pipeline.py` (edit only if the grep finds old-API assertions)
      Verify: `.\venv\Scripts\python.exe -m pytest tests/ -q` → all pass.

---

## Notes / assumptions

- **Model identity:** `WHISPER_MODEL="base"` now resolves to `Systran/faster-whisper-base` (CTranslate2) instead of openai-whisper `base`. Same config value, different artifact; auto-downloaded to the HF cache on first load (needs network once, cached after). No config change required.
- **`compute_type="int8"`** is the sane CPU default for CTranslate2 (fast, low memory). Hardcode it as specified; do not add a new setting.
- **No OS changes.** The fix works with Smart App Control ON; nothing imports `av`, `tiktoken`, or `openai-whisper` on the request path.
- **Benign warning:** a `huggingface_hub` symlink `UserWarning` prints on stderr on this machine (Developer Mode off). It is harmless and must not be treated as a failure.
- If the concurrent multi-item edit has renamed or relocated `transcribe_audio_detailed` by merge time, apply the same surgical rewrite to its new location; the contract (inputs, guards, return dict shape) is the stable anchor.
