# Design Review — Multi-Item Complaint

Reviewed document: `.agents/tasks/awaaz-phase0-polish-final/design.md`
Reviewer: design-review subagent (fresh read, verified against source)
Verdict: **APPROVED** (0 HIGH, 0 MEDIUM; NITs only)

This design is a revision that already answered a prior review (its §3). I re-read the
actual source rather than trusting those answers, and every claim the design makes about
existing code checked out. Details are in the Verified Assumptions section. The remaining
items are NITs — none block implementation.

---

## Findings

1. **NIT — `_segment_clauses` regex is enumerated but not written out.**
   §2.3.4 lists the split tokens (`.`, `۔`, `!`, `?`, newline, ` bhi `, ` بھی `, ` aur `,
   ` اور `, `،`, `,`) and says "implement as a single `re.split` on the alternation", but
   the exact pattern (and ordering/escaping of multi-char vs single-char alternatives) is
   left to the implementer. The observable result is pinned by the §2.7 tests
   (`_segment_clauses` yields one commodity per clause for the driver), so this is not
   blocking, but spelling out the pattern avoids churn.
   CONCRETE FIX — specify, e.g.:
   ```python
   _CLAUSE_SPLIT = re.compile(r"\s+bhi\s+|\s+بھی\s+|\s+aur\s+|\s+اور\s+|[.۔!?،,\n]")
   def _segment_clauses(self, text: str) -> List[str]:
       return [c.strip() for c in _CLAUSE_SPLIT.split(text or "") if c and c.strip()]
   ```
   Note the connective patterns must precede the single-char class in the alternation and
   carry `\s+` guards so " aur " does not clip inside words like "aurat".

2. **NIT — `find_all_items` substring matcher can over-match very short aliases.**
   §2.3.4's `find_all_items` keeps the `len(alias) >= 3` guard from `resolve_item` tier-3,
   but on a *whole clause* the `alias in norm` test with a 3-char alias (e.g. `"alu"`,
   `"gur"`-type) can match an unrelated substring. For the driver this is harmless (aliases
   present are `aaloo`/`pyaaz`), and the design restricts discovery to per-clause text, but
   a defensive word-boundary check would reduce spurious discovery rows.
   CONCRETE FIX — add a boundary-aware check for the pure-substring branch, keeping exact
   id/alias equality as-is:
   ```python
   if len(alias) >= 3 and (alias == norm or re.search(rf"\b{re.escape(alias)}\b", norm) or norm in alias):
   ```
   Optional; the current form already satisfies every acceptance criterion.

3. **NIT — `exec_driver_sql` / `fetchall()` sync-vs-async left for implementation-time
   confirmation.** §2.4.2's inline comment and §3 both flag that the awaitability of
   `AsyncConnection.exec_driver_sql` and the sync nature of `CursorResult.fetchall()` must be
   confirmed against the installed SQLAlchemy. The migration is additive and fail-fast, so
   risk is low, but the design should name the fallback.
   CONCRETE FIX — if the raw-driver form misbehaves on the pinned SQLAlchemy, use the
   `text()` wrapper form instead:
   ```python
   from sqlalchemy import text
   res = await conn.execute(text('PRAGMA table_info("complaints")'))
   cols = {row[1] for row in res.fetchall()}
   ```
   State this alternative in §2.4.2 so the coder has a decided path either way.

---

## Verified Assumptions

Each was checked by reading the cited source file.

- **`extract_price_and_normalize` returns a tuple `(Optional[float], float)`** — confirmed at
  `services/nlp_rules.py` (`def extract_price_and_normalize(...) -> Tuple[Optional[float], float]`,
  returns `None, 0.0` / `price, conf` / `plausible[0], 0.65`). The design's mandatory tuple
  unpacking (prior finding 1) is correct and necessary.
- **`resolve_item` tier-3 returns the FIRST alias match and tier-4 is fuzzy (`token_set_ratio >= 75`)**
  — confirmed at `services/rates.py` `resolve_item`. The design's decision to add
  `find_all_items` (collect-all, tiers 1–3, no fuzzy) instead of reusing `resolve_item` for
  discovery is justified and correct (prior finding 2).
- **`_alias_map` is `normalized_alias -> canonical_id` and includes the canonical id itself,
  the `name_en`, `name_ur`, and every alias** — confirmed in `RateService.load`. So
  `find_all_items` scanning `_alias_map` covers exact-id / exact-alias / substring as the
  design claims.
- **`aloo` price = 100, `pyaaz` price = 120** — confirmed in `rate-list.json`. AC4/FR5 values
  (Onion 200 vs 120, diff 80.0, +66.7%, High) are arithmetically correct:
  `round((200-120)/120*100,1) == 66.7`, and 66.7% ≥ `HIGH_SEVERITY_THRESHOLD_PCT` drives High.
  Potato 150 vs 100 = +50.0%. Since 66.7 > 50, Onion is primary / `complaints[0]`
  (prior findings 3 & 4) — correct.
- **`compare_price("")` returns the "item not found" dict with zeros** — confirmed in
  `rates.py` (`if not item: return {... official_price: 0.0, percentage_overcharge: 0.0 ...}`).
  The design's unresolved-item path matches.
- **`parse_complaint_text` ignores the LLM `detected_language` and always serialises the
  rule `det_lang`** — confirmed (`if llm_lang: final_detected_lang = det_lang`). The design's
  requirement that `_reconcile_item` preserve this (so all rows share one language) is
  faithful (FR3/AC5).
- **Current price precedence is "rule price wins when `> 0`, else LLM price"** — confirmed in
  `parse_complaint_text`. The merge/de-dupe rule (prior finding 5) correctly mirrors it, so a
  hallucinated LLM price cannot win.
- **`db/session.py` `init_db` currently only runs `Base.metadata.create_all`; there is NO
  `PRAGMA table_info` check today** — confirmed. The design correctly contradicts the task
  prompt's premise and specifies adding the guarded `ALTER TABLE`, establishing the pattern.
  `settings` is already imported at module top; no new import needed for `settings.DATABASE_URL`.
- **Whisper import is lazy inside `_init_whisper`; no module-level `import whisper`** —
  confirmed in `ai_pipeline.py`. The design preserves this (NFR5) and touches none of the
  Whisper/transcription path except to reuse it.
- **`ComplaintResponse` field order is `id` then `created_at`** — confirmed in `schemas.py`.
  Inserting `submission_id` between them (prior finding 6) matches, and `model_config =
  ConfigDict(from_attributes=True)` is present, so serialising a model with a new attribute
  is safe (prior finding 7).
- **`to_dict()` consumers** iterate expected keys; adding a `submission_id` key is inert
  (NFR1) — confirmed by the `to_dict` shape and that `ComplaintResponse` uses
  `from_attributes`, not `to_dict`.
- **Router handlers compute `inferred_area = location_area or extract_area_from_text(...)`
  before persistence and pass `run_in_threadpool(ai_pipeline.parse_complaint_text, ...)`** —
  confirmed in both `/voice` and `/text`. The design's `_persist_submission` refactor keeps
  area inference in the handler and offloads the (now multi-item) parse to a threadpool,
  consistent with today.
- **Voice handler's temp-dir / FFmpeg / Whisper / 400 / 503 / `finally: rmtree` flow** —
  confirmed; the design leaves it unchanged and only swaps the single-row persistence for
  `_persist_submission`.
- **Auth / CORS / admin:** PATCH uses `Depends(verify_admin_api_key)`; the design touches no
  auth, CORS, or admin code (NFR6) — confirmed by the untouched read/PATCH endpoints.
- **Frontend:** `translations.js` has two `verdict:` blocks (en and ur), each ending near
  `viewOnMap` — confirmed. `copiedId` is currently a boolean (`useState(false)`) toggled
  `setCopiedId(true)/setCopiedId(false)` — confirmed, so the per-card id-string change
  (prior finding 8) is needed. `is_violation` is never returned by the backend and is used
  only as a defensive `|| data.is_violation` — confirmed, so dropping it per-card is a no-op.
  The `/api/process-complaint` voice fallback on a 404 returning a legacy single object —
  confirmed in `lib/api.js`; the `normalizeComplaintResult` wrapper handles it.

## Unverified / Wrong Assumptions

- **Wrong premise in the task prompt (not the design):** the prompt states `db/session.py`
  "mirrors" an existing `PRAGMA table_info` check. It does not — `init_db` only calls
  `create_all` today. The design correctly identifies and corrects this; no design defect.
- **Unverified (left to implementation, see NIT 3):** the exact awaitable/sync behavior of
  `AsyncConnection.exec_driver_sql` + `CursorResult.fetchall()` on the pinned SQLAlchemy
  version was not executed here. Low risk (additive, fail-fast), with a documented `text()`
  fallback.
- **Not independently executed:** the LLM multi-item prompt behavior of
  `qwen2.5:1.5b-instruct` (whether it reliably emits the `{"items":[...]}` wrapper) is not
  verifiable statically. The design's rule-only discovery path makes this non-blocking — the
  onion is rescued by `find_all_items` even if the model emits only potato (AC10), which is
  the correct robustness posture.
