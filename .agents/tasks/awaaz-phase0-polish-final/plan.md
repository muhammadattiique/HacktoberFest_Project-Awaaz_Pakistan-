# Implementation Plan — Multi-Item Complaint

Source design: `.agents/tasks/awaaz-phase0-polish-final/design.md` (approved). This plan sequences that design against the real file contents on branch `polish/final`. Edit the repo directly; do not commit.

Environment (Windows / PowerShell):
- Backend: `awaaz_backend` with venv at `awaaz_backend\venv`, invoked as `.\venv\Scripts\python.exe` from the backend dir. Deps installed; do NOT recreate the venv.
- Frontend: `awaaz_pakistan` (React 18 + Vite + Tailwind + framer-motion), npm scripts `lint` and `build`.
- `whisper` import must stay lazy (inside `AIPipeline._init_whisper`); tiktoken DLL is blocked. Ollama is live at `http://localhost:11434` with `qwen2.5:1.5b-instruct`.
- Verified rate-list values: `aloo`=Rs 100, `pyaaz`=Rs 120, `doodh`=Rs 210. Thresholds: `OVERCHARGE_ALERT_THRESHOLD_PCT=20.0`, `HIGH_SEVERITY_THRESHOLD_PCT=50.0`. `init_db` is the sole schema authority (called from `main.py` lifespan).

Dependency order: model column → startup migration → rates collect-all helper → pipeline multi-item → schemas → router → backend tests → frontend api → frontend render → i18n → full verification.

---

- [ ] 1. Add the `submission_id` column to the `Complaint` model and `to_dict()`.
      Add `submission_id = Column(String(36), nullable=True, index=True)` immediately after the `id` column, and add `"submission_id": self.submission_id,` to the `to_dict()` return dict. Not a FK, not unique (groups rows; legacy rows may be NULL).
      Files: `awaaz_backend/db/models.py`
      Verify: `cd awaaz_backend; .\venv\Scripts\python.exe -c "from db.models import Complaint; assert 'submission_id' in Complaint.__table__.c; assert 'submission_id' in Complaint(transcript_raw='x', category='c', urgency='Low', native_response='n', routing_agency='a', helpline_reference='1').to_dict()"` — exits 0.

- [ ] 2. Add an idempotent additive SQLite migration in `init_db`.
      Keep the existing `create_all`, then inside the same `engine.begin()` block, when `"sqlite" in settings.DATABASE_URL`, call a new `_ensure_submission_id_column(conn)` that runs `PRAGMA table_info("complaints")` via `await conn.exec_driver_sql(...)`, reads column names from `row[1]`, and only when `submission_id` is absent runs `ALTER TABLE complaints ADD COLUMN submission_id VARCHAR(36)` then `CREATE INDEX IF NOT EXISTS ix_complaints_submission_id ON complaints (submission_id)`. No new imports needed (`settings` already imported; use `exec_driver_sql`, not `text()`). Fully idempotent across fresh DB, migrated DB, and restart.
      Files: `awaaz_backend/db/session.py`
      Verify: `cd awaaz_backend; .\venv\Scripts\python.exe -c "import asyncio; from db.session import init_db; asyncio.run(init_db()); asyncio.run(init_db())"` — runs twice without error (proves idempotency on the existing `awaaz.db`).

- [ ] 3. Add the additive collect-all resolver `find_all_items` to `RateService`.
      New public method `find_all_items(self, text_or_name: str) -> List[Tuple[str, Dict[str, Any]]]` that scans `self._alias_map` under `self._lock`, collecting EVERY distinct `(canonical_id, dict(self.items[canonical_id]))` whose alias (`len(alias) >= 3`) satisfies `alias == norm or alias in norm or norm in norm`'s clause (exact-id / exact-alias / substring — tiers 1-3 only, NO fuzzy tier-4), de-duped by canonical id, preserving alias-map insertion order. Leave `resolve_item` and `compare_price` untouched.
      Files: `awaaz_backend/services/rates.py`
      Verify: `cd awaaz_backend; .\venv\Scripts\python.exe -c "from services.rates import rate_service; ids={i for i,_ in rate_service.find_all_items('aaloo aur pyaaz dono mehnge')}; assert {'aloo','pyaaz'} <= ids, ids"` — exits 0 (collect-all returns both commodities).

- [ ] 4. Rewrite the pipeline for multi-item extraction while keeping `parse_complaint_text` byte-compatible.
      In `ai_pipeline.py`: (a) keep whisper lazy; (b) rename today's single-item `COMPLAINT_SCHEMA` body into `COMPLAINT_ITEM_SCHEMA` and add `COMPLAINT_SCHEMA_MULTI = {"type":"object","properties":{"items":{"type":"array","items":COMPLAINT_ITEM_SCHEMA,"minItems":1}},"required":["items"]}`; (c) extend `FEW_SHOT_SYSTEM_PROMPT` — wrap every existing example output as `{"items":[<existing output>]}`, add ONE new multi-item example built from the aaloo+pyaaz driver showing two items (Potato Rs 150, Onion Rs 200), and add the instruction line "If the complaint mentions multiple commodities or multiple distinct issues, return one object per commodity/issue in `items`."; (d) add `_call_ollama_llm_multi(text) -> Optional[List[dict]]` mirroring `_call_ollama_llm` but with `format=COMPLAINT_SCHEMA_MULTI`, returning `parsed["items"]`, coercing a bare object to a one-element list, reusing the fence-strip + retry logic; (e) add `_segment_clauses(text) -> List[str]` splitting on `.`, `۔`, `!`, `?`, newline and connectives ` bhi `, ` بھی `, ` aur `, ` اور `, `،`, `,` via one `re.split`, stripping and dropping empties; (f) add `_reconcile_item(**kwargs) -> Dict` lifting the second half of today's `parse_complaint_text` verbatim (item resolve, price precedence with `rule_price, _ = extract_price_and_normalize(clause or text)` tuple-unpack and `rule_price and rule_price > 0` short-circuit, category/urgency override, `compare_price`, urgency alignment, routing override, native-response guard, needs_review/confidence); (g) add `_discover_items_by_rules(clauses) -> List[dict]` using `rate_service.find_all_items(clause)` per clause (de-duped by canonical id), each reconciled with `has_llm=False`, falling back to one "Unspecified Commodity" item when no clause yields any id; (h) add `parse_complaint_items(text) -> List[dict]` wrapped in a top-level try/except that NEVER raises and always returns ≥1 item: build LLM list (each via `_reconcile_item(has_llm=True)` with per-item clause attribution), build rule list, union+de-dupe by `item_canonical_id` (merge: price from rule row when `>0` else LLM, recompute comparison fields from chosen price; category/urgency/native from LLM when present; drop unresolved rows only if a resolved row exists), order by `percentage_overcharge` desc, guarantee ≥1; (i) re-express `parse_complaint_text` as `return self.parse_complaint_items(transcript_text)[0]` (empty transcript still returns the existing single fallback dict as a one-element list).
      Files: `awaaz_backend/ai_pipeline.py`
      Verify: `cd awaaz_backend; .\venv\Scripts\python.exe -m pytest tests/test_pipeline.py -q` — all existing tests stay green (proves `parse_complaint_text` compatibility).

- [ ] 5. Add `submission_id` to `ComplaintResponse` and the new `MultiComplaintResponse` schema.
      In `schemas.py`, insert `submission_id: Optional[str] = None` between `id` and `created_at` on `ComplaintResponse`. Add `class MultiComplaintResponse(BaseModel): submission_id: str; complaints: List[ComplaintResponse]; primary: ComplaintResponse`. No other schema changes.
      Files: `awaaz_backend/schemas.py`
      Verify: `cd awaaz_backend; .\venv\Scripts\python.exe -c "from schemas import MultiComplaintResponse, ComplaintResponse; assert 'submission_id' in ComplaintResponse.model_fields; assert set(MultiComplaintResponse.model_fields)=={'submission_id','complaints','primary'}"` — exits 0.

- [ ] 6. Make both POST endpoints persist N rows in one transaction and return `MultiComplaintResponse`.
      In `routers/complaints.py`: add `import uuid`; add `_select_primary(responses) -> ComplaintResponse` (max `percentage_overcharge`, tie-break urgency rank High=3/Medium=2/Low=1, then original order); add `async def _persist_submission(db, *, transcript_text, shared: dict) -> MultiComplaintResponse` that calls `await run_in_threadpool(ai_pipeline.parse_complaint_items, transcript_text)`, generates one `submission_id = str(uuid.uuid4())`, builds one `Complaint(**per-item fields, **shared, submission_id=...)` per item, `db.add_all`, single `await db.commit()`, refresh all, validates to `ComplaintResponse`, returns `MultiComplaintResponse`. Change both `submit_voice_complaint` and `submit_text_complaint` to `response_model=MultiComplaintResponse` (keep 201). Each handler keeps its own `inferred_area = location_area or extract_area_from_text(...)` logic and passes it in `shared["location_area"]`; voice passes `audio_filename`/`audio_duration_seconds`, text passes `None`/`None`. Voice keeps its entire existing audio/Whisper/400/503/finally-cleanup path unchanged. Do NOT touch GET/PATCH list logic, auth, or CORS.
      Files: `awaaz_backend/routers/complaints.py`
      Verify: `cd awaaz_backend; .\venv\Scripts\python.exe -m pytest tests/test_api.py -q` — existing tests still pass after updating them (step 7); the single-item submit assertions remain valid against `MultiComplaintResponse.primary`.

- [ ] 7. Update/extend backend tests for the multi-item contract and keep all existing assertions green.
      In `tests/test_api.py`: existing `/text` and `/voice` responses now return `{submission_id, complaints, primary}` — update those assertions to read the single row via `primary` (or `complaints[0]`) so prior field checks still hold; add a test POSTing the aaloo+pyaaz driver asserting `len(complaints)==2`, shared `submission_id`, distinct ids, Potato (150/100/+50.0) and Onion (200/120/+66.7, High), `primary.item_canonical_id=="pyaaz"`; assert GET/PATCH responses include `submission_id`. In `tests/test_pipeline.py`: add `parse_complaint_items` driver test (2 items, correct canonical ids/prices/overcharge), a `_segment_clauses` test (one commodity per clause for the driver), a `find_all_items` run-on test, a de-dupe merge test (rule price wins on conflict), and a `_select_primary` test (returns pyaaz for the driver); keep all existing `_call_ollama_llm`-patched tests unchanged and green.
      Files: `awaaz_backend/tests/test_api.py`, `awaaz_backend/tests/test_pipeline.py`
      Verify: `cd awaaz_backend; .\venv\Scripts\python.exe -m pytest -q` — entire suite green.

- [ ] 8. Add the frontend result normaliser.
      In `lib/api.js` add `export const normalizeComplaintResult = (data) => ...` returning `{ submissionId, complaints, primary }` for the new `{complaints:[...]}` shape and wrapping a legacy single object (and the `/api/process-complaint` fallback) into a one-element `complaints` array. Leave `submitTextComplaint`/`submitVoiceComplaint` returning `{success,data,isDemo}` unchanged.
      Files: `awaaz_pakistan/src/lib/api.js`
      Verify: `cd awaaz_pakistan; npm run lint` — no new lint errors in `api.js`.

- [ ] 9. Render one violation card per complaint in `ReportSection.jsx`.
      Store the normalised `{ submissionId, complaints, primary }` in `verdictData` (reset points unchanged; render guard becomes `verdictData && verdictData.complaints.length > 0`). Extract today's `CardTilt` verdict block verbatim into an inner `VerdictCard` component (same file, above `ReportSection`) and render via `complaints.map((c) => <VerdictCard key={c.id} complaint={c} .../>)`, preserving CardTilt/Badge/rose-emerald theming, `font-urdu` RTL branch, `formatPrice`/`formatVariance`, per-card Replay-Voice and Copy-ID. Change `copiedId` to hold the copied id string (`setCopiedId(id)` / reset to `null`), each card checks `copiedId === complaint.id`. Render the shared transcript once from `primary.transcript_raw` above the cards and `MiniLocationMap` once from `primary` after the cards. Show a count header `t.verdict.violationsCount.replaceAll('{count}', String(complaints.length))` ONLY when `complaints.length > 1`. Compute `isViolation = complaints.some(c => (c.percentage_overcharge ?? 0) > 0)`, build chips across items capped at 6, and speak `primary.native_response` once with the existing lang selection. Drop the dead `|| ...is_violation` term. Use `normalizeComplaintResult(result.data)`; keep `onComplaintSubmitted(result.data)` passing the raw data.
      Files: `awaaz_pakistan/src/sections/ReportSection.jsx`
      Verify: `cd awaaz_pakistan; npm run build` — Vite build succeeds.

- [ ] 10. Add the `violationsCount` i18n key to both verdict blocks.
      In `src/i18n/translations.js`, add next to `viewOnMap` in BOTH the English and Urdu `verdict` blocks: EN `violationsCount: "{count} violations detected from your report"`, UR `violationsCount: "آپ کی اطلاع سے {count} خلاف ورزیاں سامنے آئیں"`. Rename/remove nothing else.
      Files: `awaaz_pakistan/src/i18n/translations.js`
      Verify: `cd awaaz_pakistan; npm run build` — build succeeds and `ReportSection` resolves `t.verdict.violationsCount` in both locales.

- [ ] 11. Full verification sequence.
      (a) Backend import check: `cd awaaz_backend; .\venv\Scripts\python.exe -c "import ai_pipeline, routers.complaints, db.session, schemas, services.rates"` — no error, whisper still lazy. (b) `cd awaaz_backend; .\venv\Scripts\python.exe -m pytest -q` — entire suite green. (c) Live end-to-end: start `.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8010` in background, POST the aaloo+pyaaz driver to `http://localhost:8010/api/complaints/text`, confirm 201 with two complaints sharing one `submission_id`, Potato (150 vs 100, +50%) and Onion (200 vs 120, +66.7%), `primary.item_canonical_id=="pyaaz"`; stop the server afterward. (d) Frontend: `cd awaaz_pakistan; npm run lint` then `npm run build` — both pass. Clean up any scratch DB/files; do not commit.
      Files: (verification only)
      Verify: all four sub-steps succeed with the expected outputs above.
