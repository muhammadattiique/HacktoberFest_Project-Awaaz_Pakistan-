# Convergence pass — review findings resolution

Branch: `polish/final` (local only; not pushed). Reviewed against
`.agents/tasks/awaaz-phase0-polish-final/review.json` (verdict: CHANGES_REQUESTED, 4 findings).

## Finding 1 — Uncommitted CORS change in `awaaz_backend/main.py` (NFR6)
RESOLVED. The working-tree edit that flipped `allow_credentials` and rewrote the
origin handling (plus an admin-key warning) was reverted with
`git checkout -- awaaz_backend/main.py`. `main.py` now matches its committed
state; CORS/auth/admin are untouched, honoring NFR6.

## Finding 2 — Whisper engine swap (OpenAI `whisper` -> `faster-whisper`)
KEPT as an intentional, required deviation (documented here per the finding's
"at minimum document it" option).

Rationale: the swap is already committed inside FEAT-001 (5a0728c) and is
*required* for the backend to import at all on this machine. Stock
`openai-whisper` pulls in `tiktoken`, whose native DLL is blocked by Windows
Smart App Control, so a module-level/stock-whisper import path cannot even be
collected by the API tests. Reverting it would break backend import and all 47
tests — a behavior regression the task does not want.

The swap preserves the lazy-load constraint (NFR5): `WhisperModel` is imported
only inside `AIPipeline._init_whisper()` via `_import_whisper_model()`, which
stubs `faster_whisper.audio` in `sys.modules` so PyAV (`av`, also blocked) is
never imported. A load failure degrades voice to a 503 instead of crashing
startup. Audio is pre-decoded to 16 kHz mono PCM WAV by `services/audio.py` and
fed to the model as a numpy array.

Companion change: `awaaz_backend/requirements.txt` adds `faster-whisper>=1.2.0`
and `numpy>=1.26` (with an inline comment explaining the stub/PyAV avoidance).
This was still uncommitted in the working tree; it is committed in this pass
because the committed code already imports `faster_whisper`, so the declared
dependencies must match the code. `openai-whisper`/`torch` are left in
requirements for compatibility.

## Finding 3 — Stray `DATABASE_URL` scratch override
RESOLVED. No `DATABASE_URL` override is set in the verification shell; every
backend command in this pass ran with `$env:DATABASE_URL=$null`. The full suite
is 47/47 green without any override.

## Finding 4 — Leftover scratch DB files
RESOLVED. `awaaz_backend/_scratch_verify.db` (0 bytes) and
`awaaz_backend/awaaz_scratch_feat001.db` were deleted. Only the real dev DB
`awaaz_backend/awaaz.db` remains. Live-verification scratch files
(`uvicorn_live.out/.err`, `live_resp.json`) created this pass were also removed.

## Verification re-run (all green)
- `import ai_pipeline, routers.complaints, db.session, schemas, services.rates` -> OK (whisper lazy).
- `init_db()` run twice -> idempotent OK.
- `find_all_items('aaloo aur pyaaz dono mehnge')` -> {aloo, pyaaz}.
- `pytest -q` -> 47 passed.
- Live port 8010, POST aaloo+pyaaz driver to `/api/complaints/text`: 201, 2
  complaints sharing one `submission_id`; Potato/aloo 150/100/+50.0% and
  Onion/pyaaz 200/120/diff 80/+66.7%/High; `primary.item_canonical_id == 'pyaaz'`
  (pyaaz sorted to index 0). Server stopped afterward.
- Frontend `npm run lint` -> 0 warnings / 0 errors; `npm run build` -> success
  (the >1000 kB chunk notice is pre-existing vendor-three, unrelated).
