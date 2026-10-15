# Implementation Plan — Awaaz Pakistan: 6-Language Support + Multi-Item Hardening

Branch: `polish/final`. Edit the repo directly (no worktree). Do NOT push. Commit locally.
Backend venv: from `awaaz_backend`, invoke `.\venv\Scripts\python.exe` (faster-whisper installed; keep whisper import LAZY; never import `openai-whisper`, PyAV `av`, or `tiktoken` at module load). Ollama is live at http://localhost:11434 (qwen2.5:1.5b-instruct). A dev backend holds port 8000 — do NOT use it; live tests must start a fresh uvicorn on port 8020 and shut it down after. Do NOT change auth, CORS, or admin-key behavior.

Grounding confirmed by reading: `nlp_rules.py`, `ai_pipeline.py`, `services/rates.py`, `routers/complaints.py`, `rate-list.json`, `tests/test_nlp_rules.py`, `src/i18n/translations.js` (en = lines ~2-244, ur = ~244-471, 13 key groups), `src/i18n/LanguageContext.jsx`, `src/components/ui/Navbar.jsx`, `src/sections/ReportSection.jsx`, `src/lib/utils.js`, `package.json`. Both concurrent workflows (faster-whisper + multi-item) have already merged; `git status` shows the source tree clean. Baseline `pytest tests/test_nlp_rules.py` = 7 passed.

Order below is dependency-ordered. Backend language edits (1-4) are self-contained. Multi-item fixes (5-9) are independent of the language edits except both touch `ai_pipeline.py` string regions. Frontend fallback (10) MUST land before the new partial language blocks (11) so a missing key can never crash render.

---

## GOAL A — Backend (Layer 1): add Sindhi + Balochi

- [ ] 1. Add Sindhi + Balochi detection to `detect_language()`.
      Re-read the function first. Inside the Arabic-script branch, after the Pashto-unique check and BEFORE `return "Urdu"`, add a Sindhi check: if any char in `['ڄ','ٺ','ٽ','ڻ','ڱ','ڳ','ڦ','ڀ','ٿ','ڏ']` return `"Sindhi"` (these letters do not appear in Urdu/Punjabi-Shahmukhi). Balochi Arabic-script has no unique code points → no script rule; it may fall through to `"Urdu"` (accepted, documented in a comment). For Latin script, add short high-precision `sindhi_patterns` (e.g. `\bmaan\b`, `\btawhan\b`/`\btuhan\b`, `\baahe\b`/`\baahy\b`, `\bkahro\b`, `\bghani\b` — avoid shared `qeemat`/`bazar`) and `balochi_patterns` (e.g. `\bmani\b`, `\btaw\b`/`\btau\b`, `\bint\b`/`\bent\b`, `\bgran\b`) checked in order English → Sindhi → Balochi → Punjabi → Pashto → Roman Urdu. Keep lists short so existing `test_language_detection` cases still pass. Mark both marker lists with a `# NATIVE-REVIEW-REQUIRED` comment.
      Files: `awaaz_backend/services/nlp_rules.py`, `awaaz_backend/tests/test_nlp_rules.py` (add Sindhi script + Sindhi/Balochi Roman assertions to `test_language_detection`).
      Verify: from `awaaz_backend`, `.\venv\Scripts\python.exe -m pytest tests/test_nlp_rules.py::test_language_detection -v` — all existing + new assertions pass.

- [ ] 2. Add Sindhi/Balochi romanized number words.
      Add to `BASIC_NUMBER_WORDS` only where they differ from forms already present (many overlap: `do`,`teen`,`sau`,`hazaar`,`char`,`panch` already exist). Suggested Balochi: `yak`(1),`du`(2),`sai`(3),`shash`(6),`hapt`(7),`hasht`(8),`nuh`(9),`dah`(10),`sad`(100). Sindhi: `hik`(1),`ba`(2),`tei`(3). Mirror any new 1-9 prefixes into the `compound_hundreds` list inside `parse_word_numbers()` so `"<prefix> sau"` resolves. Mark additions `# NATIVE-REVIEW-REQUIRED`. Do not duplicate existing keys.
      Files: `awaaz_backend/services/nlp_rules.py`, `awaaz_backend/tests/test_nlp_rules.py` (extend `test_punjabi_and_pashto_numbers` or add a Sindhi/Balochi number test, e.g. `parse_word_numbers("du sau rupay")` contains `"200"`).
      Verify: `.\venv\Scripts\python.exe -m pytest tests/test_nlp_rules.py -q` — all pass including new number assertions.

- [ ] 3. Add Sindhi + Balochi branches to `generate_native_acknowledgment()`.
      Add `elif language == "Sindhi":` and `elif language == "Balochi":` branches BEFORE the Roman-Urdu `else`, returning the DRAFT native strings from the design §2.1c (Sindhi: "توهان جي شڪايت درج ٿي وئي آهي…"; Balochi: "شمے شکایت درج بوت…"). Each branch gets a `# DRAFT — NATIVE-REVIEW-REQUIRED` comment and Roman gloss.
      Files: `awaaz_backend/services/nlp_rules.py`, `awaaz_backend/tests/test_nlp_rules.py` (add assertions that `generate_native_acknowledgment("Sindhi")` and `("Balochi")` return non-empty Arabic-script strings).
      Verify: `.\venv\Scripts\python.exe -m pytest tests/test_nlp_rules.py::test_native_acknowledgment -v` — passes.

- [ ] 4. Widen `detected_language` description + add Sindhi/Balochi few-shot examples in `ai_pipeline.py`.
      Re-read the file first. In `COMPLAINT_ITEM_SCHEMA.detected_language.description`, change the string to include Sindhi + Balochi: `"Detected language (Urdu, Roman Urdu, Punjabi, Sindhi, Balochi, Pashto, English)"`. In `FEW_SHOT_SYSTEM_PROMPT`: add Sindhi + Balochi to the enumerated input-languages sentence, and append two few-shot examples (one Sindhi, one Balochi) in the multi-item `{"items":[...]}` shape per design §2.2b, flagged as drafts. String-only, additive edits — do NOT touch `parse_complaint_items`/`_call_ollama_llm_multi`/`_segment_clauses` logic.
      Files: `awaaz_backend/ai_pipeline.py`.
      Verify: `.\venv\Scripts\python.exe -m pytest tests/ -q` — full backend suite green (no import/JSON-shape regression).

---

## GOAL B — Multi-item correctness (arbitrary counts)

- [ ] 5. Fix BUG 1 (phantom item): tighten rule discovery + LLM-item attribution.
      Re-read `services/rates.py` `find_all_items` and `ai_pipeline.py` `_discover_items_by_rules`/`_attribute_clause`/`parse_complaint_items`. Root cause: (a) `find_all_items` tier-3 uses `alias in norm or norm in alias` with `len>=3` — the `norm in alias` direction and loose substrings let an unrelated token hit a commodity alias; and (b) an LLM-hallucinated item (the prompt is chicken-heavy) survives even when `_attribute_clause` finds no clause, borrowing a stray price. FIX: in `find_all_items`, require a genuine word-boundary token match of the alias against the text (drop the `norm in alias` direction; match aliases as whole tokens, not loose substrings) so a commodity is only discovered when actually mentioned. In `parse_complaint_items`, when merging LLM items, DROP any LLM item whose `item_name` cannot be attributed to a clause (`_attribute_clause` returns None) AND is not present in rule discovery — i.e. an item must be BOTH genuinely present in the text AND carry a price from its own clause. Preserve the existing 1-item and 0-item fallbacks.
      Files: `awaaz_backend/services/rates.py`, `awaaz_backend/ai_pipeline.py`.
      Verify: step 7 regression test (count==7, no Chicken). Also `.\venv\Scripts\python.exe -m pytest tests/test_rates.py -q` stays green.

- [ ] 6. Fix BUG 2 (under-rate items flagged as violations) + primary selection.
      In `_reconcile_item`: when `pct_overcharge <= 0` (reported price at/below official), keep the mentioned item but mark it compliant — do NOT escalate urgency (urgency stays Low, never High for non-overcharge), never drop a mentioned item. Confirm `compare_price` already yields negative `price_difference_pkr`/`percentage_overcharge` for under-rate (it does). In `routers/complaints.py` `_select_primary`: it already picks max by `(percentage_overcharge, urgency_rank)`; add a guard so an under-rate item (pct <= 0) is never chosen as primary when any item has positive overcharge (max over the positive set first; fall back to overall max only if none are violations). Do not change DB schema or shared/auth behavior.
      Files: `awaaz_backend/ai_pipeline.py`, `awaaz_backend/routers/complaints.py`.
      Verify: step 7 regression test asserts the under-rate items (e.g. flour, milk at/below official) have `percentage_overcharge <= 0` and `urgency != "High"`, and `primary` is the highest positive-overcharge item.

- [ ] 7. Add the 7-item regression test (new backend test file).
      Create `tests/test_multi_item.py`. Test the exact 7-item input from the task ("…aaloo 150…pyaaz 200…tamatar 250…chini 180…atta 120…chawal 400…doodh 280…"). Call `ai_pipeline.parse_complaint_items(text)` directly (rule+LLM path; Ollama is live). Assert: `len(items) == 7`; the set of resolved `item_canonical_id`s equals {aloo, pyaaz, tamatar, chini, atta_kg, chawal_basmati, doodh}; NO item whose canonical id is `chicken_meat`/`chicken_live` or `item_name` contains "Chicken". Add cases: 1-item input → exactly 1; empty/0-identifiable input → exactly 1 "Unspecified" record. Mark the LLM-dependent assertions tolerant of Ollama variance where needed but keep the no-Chicken + count assertions strict.
      Files: `awaaz_backend/tests/test_multi_item.py`.
      Verify: `.\venv\Scripts\python.exe -m pytest tests/test_multi_item.py -v` — passes.

- [ ] 8. Fix `formatVariance` for negative/zero variance in `utils.js`.
      Re-read `src/lib/utils.js`. Current `formatVariance` prefixes `+` only for positive but still calls `toFixed` on the raw negative, producing `+-14.3%` only if a `+` is prepended elsewhere; fix so: positive → `+14.3%`, negative → `-14.3%` (native minus, never `+-`), zero → `0.0%`. Keep return `null` for null/undefined.
      Files: `awaaz_pakistan/src/lib/utils.js`.
      Verify: `cd awaaz_pakistan; npm run build` succeeds; `npm run lint` clean. Manual: `formatVariance(-14.3)` → `-14.3%`, `formatVariance(76.9)` → `+76.9%`.

- [ ] 9. Fix the VerdictCard variance color/label + the "N violations detected" header wording.
      Re-read `src/sections/ReportSection.jsx`. The VerdictCard already switches rose vs emerald on `percentage_overcharge > 0` and uses `formatVariance` — confirm it renders `-14.3%` (not `+-`) now that step 8 is fixed, and that compliant items show emerald with the normal badge. The multi-item header uses `t.verdict.violationsCount.replaceAll('{count}', complaints.length)` — change the count to the number of ACTUAL violations (items with `percentage_overcharge > 0`), OR reword the key to "N items analysed" (see step 12 for the i18n copy change in all language blocks). Keep the header shown only when `complaints.length > 1`.
      Files: `awaaz_pakistan/src/sections/ReportSection.jsx`.
      Verify: `cd awaaz_pakistan; npm run build && npm run lint` clean. Manual: a mix of over- and under-charged items shows a truthful count and no `+-`.

---

## GOAL A — Frontend (Layer 2): 6-language UI

- [ ] 10. Add English-fallback deep-merge + multi-language RTL/font; export LANGUAGES + RTL_LANGS.
      Re-read `src/i18n/LanguageContext.jsx` and `src/i18n/translations.js`. In the i18n module export `LANGUAGES = [{code,label,native}]` for en/ur/pa/sd/bal/ps and `RTL_LANGS = new Set(['ur','pa','sd','bal','ps'])` (single source of truth — add to `translations.js` or a new `languages.js`). In `LanguageContext.jsx`: replace `const t = translations[language] || translations.en` with a memoized recursive `deepMergeFallback(translations.en, translations[language] || {})` (per design §3.4; en is the complete base so every dot-path resolves — no component changes needed). Replace the three `language === 'ur'` checks with `RTL_LANGS.has(language)` for `dir`, the `font-urdu` body class, and the context `isRtl` value. Validate persisted `awaaz_lang` against known codes on init, default `en`. Do this FIRST so later partial blocks never crash.
      Files: `awaaz_pakistan/src/i18n/LanguageContext.jsx`, `awaaz_pakistan/src/i18n/translations.js` (+ optional `languages.js`).
      Verify: `cd awaaz_pakistan; npm run build && npm run lint` clean. Manual: force `setLanguage('pa')` before the pa block exists → UI renders English, no crash/blank.

- [ ] 11. Author full `pa`, `sd`, `bal`, `ps` blocks in `translations.js`.
      Mirror the en/ur structure (all 13 key groups) with best-effort translations; the deep-merge backstops any gaps but author complete. Prefix each new block with a greppable `// NATIVE-REVIEW-REQUIRED (<lang>): best-effort draft, not native-verified.` comment (Balochi lowest-confidence). en stays the complete superset — add any brand-new key to en first.
      Files: `awaaz_pakistan/src/i18n/translations.js`.
      Verify: `cd awaaz_pakistan; npm run build && npm run lint` clean. `grep -c NATIVE-REVIEW-REQUIRED` in translations.js returns 4.

- [ ] 12. Update language-enumerating copy + `violationsCount` wording across ALL language blocks.
      In en + ur (and the new pa/sd/bal/ps) blocks, update `hero.subtitle`, `features.feat1Desc`, `faq.q1`/`faq.a1` to mention all six languages (English, Urdu, Punjabi, Sindhi, Balochi, Pashto). Reword `verdict.violationsCount` in ALL blocks to a truthful phrasing consistent with step 9 (e.g. "{count} items analysed from your report" — or keep "violations" only if step 9 feeds it the true violation count).
      Files: `awaaz_pakistan/src/i18n/translations.js`.
      Verify: `cd awaaz_pakistan; npm run build && npm run lint` clean.

- [ ] 13. Rebuild the Navbar switcher to a data-driven 6-language selector.
      Re-read `src/components/ui/Navbar.jsx`. Replace the hardcoded 2-button desktop switcher (EN/اردو) and the binary mobile toggle with a selector driven by the exported `LANGUAGES`. A native `<select>` is preferred for accessibility, especially on mobile; a dropdown/popover is acceptable on desktop. Keep `aria-label`s and the focus-ring/`cursor-pointer` treatment. Fire `setLanguage(code)` for each option.
      Files: `awaaz_pakistan/src/components/ui/Navbar.jsx`.
      Verify: `cd awaaz_pakistan; npm run build && npm run lint` clean. Manual: all six options appear and switch language.

- [ ] 14. Update `languagesCount` 4→6 and the comment.
      Re-read `src/sections/LiveImpactStatsSection.jsx`. Change `const languagesCount = 4` to `6` and update the comment to list all six languages. Low-risk one-liner.
      Files: `awaaz_pakistan/src/sections/LiveImpactStatsSection.jsx`.
      Verify: `cd awaaz_pakistan; npm run build && npm run lint` clean. Manual: stat shows "6".

- [ ] 15. Balochi voice degradation notice + font coverage check.
      Re-read `src/sections/ReportSection.jsx` voice tab. When UI language is Balochi (`language === 'bal'`), show a gentle notice (new i18n key, add to en first then all blocks) that Balochi voice recognition is experimental and recommend the text tab; do NOT claim reliable Balochi transcription. The existing low-confidence/`needs_review` backend path already yields an Urdu/English acknowledgment when transcription is empty — reuse it, no new transcription logic. Confirm the Nastaliq/Arabic-script font (`.font-urdu` in `index.css`, `--font-urdu` var) loads globally (it does for Urdu today) so the five RTL languages render without a new network dependency; add a `// TODO: split Naskh for sd/ps/bal` comment. The VerdictCard `native_response` RTL/font check currently keys on `detected_language === 'Urdu'` — widen it to apply the RTL font for Sindhi/Balochi/Punjabi/Pashto script responses too.
      Files: `awaaz_pakistan/src/sections/ReportSection.jsx`, `awaaz_pakistan/src/i18n/translations.js`, (verify only) `awaaz_pakistan/src/index.css`.
      Verify: `cd awaaz_pakistan; npm run build && npm run lint` clean. Manual: select Balochi + voice tab → experimental notice shown.

---

## Final verification

- [ ] 16. Full pass.
      Backend: from `awaaz_backend`, `.\venv\Scripts\python.exe -m pytest tests/ -v` (all green, incl. new language + multi-item tests). Live integration: start a fresh uvicorn on port 8020 (`.\venv\Scripts\python.exe -m uvicorn main:app --port 8020`), POST the 7-item text complaint to `/complaints/text`, confirm exactly 7 complaints, no Chicken row, under-rate items compliant (pct <= 0, not High), `primary` = highest positive overcharge; then shut the server down. Frontend: `cd awaaz_pakistan; npm run build && npm run lint`. Manual: switch through all 6 languages — UI text changes, RTL flips for ur/pa/sd/bal/ps and stays LTR for en, no blank keys, no console `TypeError`.
      Files: none (verification only).
      Verify: all commands above succeed; the 7-item live test yields exactly 7 complaints with no Chicken and correct compliant/violation classification.

---

## Notes & honesty

- pa/sd/bal UI text and Sindhi/Balochi backend strings are best-effort drafts, NOT native-verified. Every one must carry a `NATIVE-REVIEW-REQUIRED` marker. Balochi is lowest-confidence; Balochi voice is experimental and must degrade to text + Urdu/English response, never claiming reliable transcription.
- Do not change auth, CORS, admin-key, or DB schema. Keep the whisper/faster-whisper import lazy; never import `openai-whisper`, PyAV `av`, or `tiktoken` at module load.
- Re-read each file immediately before editing it.
