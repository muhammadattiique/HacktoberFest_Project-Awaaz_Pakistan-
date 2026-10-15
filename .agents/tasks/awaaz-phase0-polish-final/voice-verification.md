# Voice Transcription Fix — Verification Note

Branch: `polish/final`. Changes left in the working tree (NOT committed), per instructions.
Verified on Windows with Smart App Control ON, using `awaaz_backend\venv\Scripts\python.exe`
(faster-whisper 1.2.1 + ctranslate2 4.8.2, Python 3.12).

## Files changed

1. `awaaz_backend/requirements.txt` — ADDED `faster-whisper>=1.2.0` and `numpy>=1.26`
   (with an explanatory comment). Left `openai-whisper>=20231117` and `torch>=2.0.0` in
   place (still used by `bench/` tooling and the Dockerfile; the app request path no longer
   imports them).
2. `awaaz_backend/ai_pipeline.py` — surgical edits confined to the transcription surface:
   - Added stdlib/numpy imports (`sys`, `types`, `wave`, `numpy as np`) and rewrote the
     module header comment to describe the faster-whisper + PyAV-stub approach.
   - Added module-level helper `_import_whisper_model()` — stubs `faster_whisper.audio` in
     `sys.modules` before `from faster_whisper import WhisperModel`, so PyAV (`av`) is never
     imported. `decode_audio` is a raising stub (only reached for path/bytes inputs we never
     pass); `pad_or_trim` is re-implemented identically to upstream (pure numpy) because
     `transcribe()` genuinely calls it during language detection and segment encoding.
   - Added module-level helper `_load_wav_mono_float32(path)` — stdlib `wave` + numpy only:
     reads 16-bit PCM, `np.frombuffer(int16)/32768.0 -> float32` in [-1,1]; defensive mono
     averaging and a 16 kHz sanity warning. No librosa / soundfile / av.
   - Rewrote `_init_whisper()` to load
     `WhisperModel(settings.WHISPER_MODEL, device=settings.WHISPER_DEVICE, compute_type="int8")`
     via the stub helper, keeping the lazy-import-inside-try + graceful `whisper_loaded=False`.
   - Rewrote the model-call section of `transcribe_audio_detailed()` for the faster-whisper
     API: loads the WAV to a numpy array, calls
     `transcribe(audio_array, language=None, initial_prompt=WHISPER_INITIAL_PROMPT,
     condition_on_previous_text=False, temperature=0.0, vad_filter=True)`, materializes the
     `segments` generator into dicts (`text`, `no_speech_prob`, `avg_logprob`, `start`,
     `end`), sets `detected_lang = info.language or "ur"`.
   - PRESERVED exactly: the model-None early return, the WAV-load/transcribe error dicts
     (same `{"text","language","confidence","segments","error"}` shape), the
     `no_speech_prob > 0.60` discard, the ≥5-consecutive-identical-words discard, the
     canned-phrase discard, the `avg_confidence` computation, and the success dict shape
     `{"text","language","confidence","segments"}`.
   - `transcribe_audio()` unchanged (still `return res.get("text","")`).

NOT touched: `parse_complaint_text`, `COMPLAINT_SCHEMA`, `FEW_SHOT_SYSTEM_PROMPT`,
`_call_ollama_llm`, `config.py` (WHISPER_MODEL=`base`, WHISPER_DEVICE=`cpu` kept),
`services/audio.py` (FFmpeg 16 kHz mono PCM unchanged), `routers/complaints.py`
(graceful-503 flow unchanged), and all tests (no edits needed — see below).

## New `transcribe_audio_detailed` summary

Input WAV path -> `_load_wav_mono_float32` (stdlib wave + numpy) -> float32 array ->
`WhisperModel.transcribe(array, ...)` (no PyAV) -> consume segment generator into dicts ->
same hallucination/silence/canned-phrase filtering -> same return dict shape. All failure
modes return the pre-existing error-dict shape so `routers/complaints.py` keeps its 503/400
contract untouched.

## Commands run and results

1. Import check:
   `python -c "import main; print('IMPORT OK')"` -> `IMPORT OK`.
2. Engine import under SAC (no av/tiktoken):
   `python -c "from ai_pipeline import _import_whisper_model; print(_import_whisper_model().__name__)"`
   -> `WhisperModel`.
3. Model load under SAC:
   `python -c "from ai_pipeline import ai_pipeline; ai_pipeline._init_whisper(); assert ai_pipeline.whisper_loaded; print('MODEL LOADED')"`
   -> `MODEL LOADED` (auto-downloaded `Systran/faster-whisper-base`).
4. Live end-to-end on `uvicorn ... --port 8011`:
   - Mic/WAV path — POST a real speech WAV (generated via Windows SAPI TTS) to
     `/api/complaints/voice` ->
     **HTTP 201**, `transcript_raw`="baisahab, Raja Bazaar main dukandar, ala 150, rupay,
     kilo, bechra, hai ...", `category`="PERA - Overpricing", `item_name`="Fresh Milk",
     `reported_price`=150. NOT a 503.
   - Upload path (.ogg) — POST `bench/fixtures/synthetic_en_10s.ogg`
     (ogg -> FFmpeg -> 16 kHz WAV -> transcribe) ->
     **HTTP 201**, `transcript_raw`="The potato vendor in G-9 Markaz is charging 200 rupees
     per kilo. Please take action quickly.", `category`="PERA - Overpricing",
     `item_name`="Potato", `reported_price`=200. NOT a 503.
   - First run of this exact change produced a 503 whose server log showed
     `pad_or_trim` being called on the stub; root-caused and fixed by giving the stub a real
     numpy `pad_or_trim` (only `decode_audio` needs PyAV, and it is never reached). Both POSTs
     above are from the corrected run. Server shut down afterward (port 8011 closed).
5. Test suite: `python -m pytest tests/ -q` -> **41 passed in 24.90s**. The two voice router
   tests monkeypatch `transcribe_audio_detailed` and assert on the preserved dict shape, so
   they pass with no edits; `test_pipeline.py` does not touch transcription.

## Mic + upload coverage

Both the microphone recording and the "upload audio" feature POST to the same
`POST /api/complaints/voice` endpoint (frontend sends a recorded blob or a chosen file as the
`audio` multipart field). The endpoint runs `validate_and_convert_audio` (FFmpeg ->
16 kHz mono WAV) then `ai_pipeline.transcribe_audio_detailed`. Because both features route
through this single transcription path and it is now verified end-to-end (201, no 503) for a
.wav and a .ogg, **both mic and upload are fixed**.
