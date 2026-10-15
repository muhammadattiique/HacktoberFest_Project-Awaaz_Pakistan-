# Implementation Plan — Awaaz Backend Multi-Item / Regional-Script Fixes

Branch: `polish/final`. Backend dir: `awaaz_backend`. Edit repo directly, commit locally, DO NOT push.

Run everything from `awaaz_backend` with the existing venv and `DATABASE_URL` unset:
`$env:DATABASE_URL=$null; .\venv\Scripts\python.exe -m pytest ...`
Ollama (qwen2.5:1.5b-instruct) is live at http://localhost:11434. For any live HTTP check, start a throwaway uvicorn on port 8040 and shut it down + delete any scratch DB afterward.

## Investigation summary (grounded in code that was read and run)

- `ai_pipeline._segment_clauses` splits on `. ۔ ! ? \n bhi بھی aur اور and tay o ، ,` — it does **NOT** split on Pashto ` او `, Punjabi Shahmukhi ` تے `, or Sindhi ` ۽ `. Confirmed live: the Pashto example keeps "ٹماٹر 250 ... او چینی 180 ..." in ONE clause, so چینی borrows 250.
- `_discover_items_by_rules`: when `len(found)==1` it calls `_price_clause_for` (own-clause price, else borrow next clause if next has a price and no commodity — the ` bhi ` case). When a clause resolves to **2+** commodities it passes the whole clause to each, and `_reconcile_item` calls `extract_price_and_normalize(clause)` which returns the FIRST plausible number — so the 2nd commodity steals the 1st's price.
- `rate_service.find_all_items` matches aliases on a Unicode word boundary `(?<!\w)alias(?!\w)`. Confirmed `\w` matches Arabic-script letters, so boundaries work; the greedy fuzzy tier is deliberately excluded (keeps the 7-item test free of a phantom Chicken). The fix must stay inside this word-boundary discipline.
- `rate-list.json` aliases lack Pashto/Sindhi spellings. Confirmed live: `find_all_items('الو')`→[], `find_all_items('پياز')`→[]. Note `پياز` (Pashto, Arabic yeh U+064A) ≠ `پیاز` (rate-list, Urdu yeh U+06CC) — a **character-variant** mismatch, not only a missing word. `چینی` already matches (chini alias present).
- `nlp_rules`: Punjabi `تن`(3) and `پنجاہ`(50) are missing (so `تن سو پنجاہ`=350 fails). ALL Pashto number words are missing (يو دوه درې څلور پنځه شپږ اووه اته نهه لس شل پنځوس سل سوه زر). `نو چار پنج سو ہزار اک` already parse.
- TEA ALREADY EXISTS as `chai_patti` (price 1600, SAMPLE) with aliases `چائے / چائے کی پتی` — but NOT the Punjabi `چاہ پتی`. So the tea decision is: do NOT add a new item; ADD the `چاہ پتی` + Pashto/Sindhi aliases to the existing `chai_patti`, and keep its rate flagged SAMPLE.
- Under-rate filtering in `routers/complaints.py` (`_is_registrable`, `_select_primary`) and `MultiComplaintResponse.primary: Optional` MUST be preserved untouched.
- Baseline: `pytest tests/test_pipeline.py tests/test_nlp_rules.py tests/test_rates.py tests/test_multi_item.py` = 37 passed (with Ollama live).

---

- [ ] 1. Add the missing regional "and"/list connectives to clause segmentation.
      In `ai_pipeline._segment_clauses`, extend the `re.split` alternation to also split on ` او ` (Pashto and), ` تے ` (Punjabi Shahmukhi and), and ` ۽ ` (Sindhi and, U+06FD). Keep every existing delimiter and the existing strip/empty-drop. Order the new tokens so ` اور ` (already present) still matches before the shorter ` او ` is reached only on a true space-delimited ` او ` (they cannot overlap because each token is space-padded). Update the docstring to list the added connectives.
      Files: `awaaz_backend/ai_pipeline.py`
      Verify: `.\venv\Scripts\python.exe -c "from ai_pipeline import ai_pipeline; print(ai_pipeline._segment_clauses('ٹماٹر 250 روپۍ کيلو او چینی 180 روپۍ کيلو'))"` — tomato and sugar land in SEPARATE clauses (two list elements, neither containing both numbers).

- [ ] 2. Add a positional (nearest-price) attribution helper and use it when a single clause still holds multiple commodities.
      In `ai_pipeline.py` add `_attribute_prices_positionally(clause, found_items)`: given a clause and the ordered `(canonical_id, item_info)` list from `find_all_items`, locate each commodity's alias match position (reuse the same `(?<!\w)alias(?!\w)` match used by `find_all_items`; match on the resolved alias text) and each price-number position (digits after `normalize_digits` + `parse_word_numbers`, filtered to plausible PKR like `extract_price_and_normalize`'s 10–10000 rule), then assign each commodity the nearest price token that FOLLOWS it (fallback: nearest price BEFORE it). Return a dict `canonical_id -> price` (and build a per-commodity sub-clause string so `_reconcile_item`'s own `extract_price_and_normalize` re-derives unit idioms consistently). In `_discover_items_by_rules`, when `len(found) >= 2` for a clause, call this helper and pass each commodity its OWN nearest-price sub-clause instead of the whole merged clause. Keep the existing `len(found)==1` path (`_price_clause_for`, own-clause / borrow-next / ` bhi ` trailing case) exactly as-is.
      Files: `awaaz_backend/ai_pipeline.py`
      Verify: `.\venv\Scripts\python.exe -m pytest tests/test_multi_item.py tests/test_pipeline.py -q` — all existing tests still pass (aaloo+pyaaz driver, English 4-item, 7-item no-Chicken).

- [ ] 3. In `_attribute_clause` (LLM-item path), confirm each LLM item maps to the clause that actually names it after step 1's finer segmentation, so `_reconcile_item` reads that clause's price. No logic change expected beyond benefiting from the new splits; verify it still returns the naming clause.
      Files: `awaaz_backend/ai_pipeline.py` (likely no edit; confirm by test)
      Verify: covered by step 2's pytest run plus the new Pashto end-to-end test in step 7.

- [ ] 4. Add a conservative Arabic→Urdu script-variant normalization for alias matching, and add Pashto/Sindhi aliases to `rate-list.json`.
      (a) In `services/rates.py` add a private `_normalize_script(s)` that folds the common Arabic variants to the Urdu forms the rate-list uses: Arabic yeh `ي`(U+064A)→`ی`(U+06CC), alef-maksura `ى`(U+0649)→`ی`, Arabic kaf `ك`(U+0643)→Urdu `ک`(U+06A9), Arabic heh `ه`(U+0647) left as-is (do NOT fold heh — Urdu uses both ہ/ه and folding risks collisions; flag NATIVE-REVIEW-REQUIRED). Apply `_normalize_script` to BOTH sides when building `_alias_map` keys and inside `find_all_items`/`resolve_item` normalization, so `پياز`(Arabic yeh) matches `پیاز`(Urdu yeh). This is additive and must not widen matching to substrings — keep the word-boundary regex.
      (b) In `rate-list.json` extend `aliases` arrays (keep JSON valid, UTF-8):
      - `aloo`: add `الو`, `آلو` (Sindhi same) — [confirmed needed: الو was unmatched]
      - `pyaaz`: add `پياز` (Arabic-yeh Pashto), `بصر` (Sindhi) — NATIVE-REVIEW-REQUIRED: بصر
      - `tamatar`: add `رومي` (Pashto), `ٽماٽا`, `ٽماٽو` (Sindhi) — NATIVE-REVIEW-REQUIRED: Sindhi forms
      - `chini`: add `بوره` (Pashto), `کنڊ`, `چيني` (Sindhi) — NATIVE-REVIEW-REQUIRED: کنڊ/چيني
      - `chicken_meat`: add `چرګ`, `مرغ` (Pashto), `ڪڪڙ` (Sindhi) — NATIVE-REVIEW-REQUIRED: ڪڪڙ. Guard: these must stay whole-word so the 7-item no-Chicken test still passes.
      - `anday`: add `هګۍ` (Pashto), `آنا`, `بيضا` (Sindhi) — NATIVE-REVIEW-REQUIRED: all
      - `banaspati_ghee`: add `غوړي` (Pashto), `گيهه` (Sindhi) — NATIVE-REVIEW-REQUIRED
      - `atta_kg`: add `اٽو` (Sindhi) — NATIVE-REVIEW-REQUIRED
      - `chai_patti`: add `چاہ پتی` (Punjabi Shahmukhi), `چاې` (Pashto) — NATIVE-REVIEW-REQUIRED: Pashto form. Do NOT change its SAMPLE price (1600).
      Files: `awaaz_backend/services/rates.py`, `awaaz_backend/rate-list.json`
      Verify: `.\venv\Scripts\python.exe -c "from services.rates import rate_service; print([c for c,_ in rate_service.find_all_items('الو')], [c for c,_ in rate_service.find_all_items('پياز')], [c for c,_ in rate_service.find_all_items('چاہ پتی')])"` — prints `['aloo'] ['pyaaz'] ['chai_patti']`. Then `pytest tests/test_rates.py tests/test_multi_item.py -q` passes (no phantom Chicken).

- [ ] 5. Add Pashto (and missing Punjabi) number words to `services/nlp_rules.py`.
      In `BASIC_NUMBER_WORDS` add: Pashto `يو`:1, `دوه`:2, `درې`:3, `څلور`:4, `پنځه`:5, `شپږ`:6, `اووه`:7, `اته`:8, `نهه`:9, `لس`:10, `شل`:20, `پنځوس`:50, `سل`:100, `سوه`:100, `زر`:1000, `زره`:1000; and the missing Punjabi `تن`:3, `پنجاہ`:50. In the `parse_word_numbers` `compound_hundreds` prefix list add the Pashto 1-9 prefixes (`يو`,`دوه`,`درې`,`څلور`,`پنځه`,`شپږ`,`اووه`,`اته`,`نهه`) and add `سل`/`سوه` to the hundred-word list and `زر`/`زره` to the thousand-word list so `يو سل پنځوس`=150 and `دوه سوه`=200 parse. Keep all additions high-precision (no 1-2 char ambiguous tokens that could collide with commodity words — review `سل`, `زر`). Mark Sindhi numeral spellings NATIVE-REVIEW-REQUIRED and add only ones you can verify differ from existing shared forms.
      Files: `awaaz_backend/services/nlp_rules.py`
      Verify: `.\venv\Scripts\python.exe -c "from services.nlp_rules import parse_word_numbers as p; print(p('يو سل پنځوس'), '|', p('دوه سوه'), '|', p('تن سو پنجاہ'))"` — prints `150 | 200 | 350` (allowing surrounding spaces). Then `pytest tests/test_nlp_rules.py -q` passes (no regression in existing digit/number tests).

- [ ] 6. Add BUG-1 regression tests to `tests/test_multi_item.py`.
      Add (LLM stubbed via `patch.object(ai_pipeline, "_call_ollama_llm_multi", return_value=None)` for determinism):
      - `test_pashto_digit_chain_each_item_own_price`: input `'جنابه، دوکاندار الو 150 روپۍ کيلو، پياز 200 روپۍ کيلو، ٹماٹر 250 روپۍ کيلو او چینی 180 روپۍ کيلو خرڅوي'` → asserts 4 ids `{aloo,pyaaz,tamatar,chini}` present with reported_price 150/200/250/180 respectively, and `detected_language=='Pashto'`.
      - `test_punjabi_shahmukhi_rice_keeps_own_price`: the Punjabi 5-item input → `chawal_basmati` reported_price == 350 (its own `تن سو پنجاہ`), NOT the tea price; `chai_patti` present with its own 1000.
      - Keep the existing English 4-item sugar=180 and aaloo+pyaaz pyaaz=200 tests passing unchanged.
      Files: `awaaz_backend/tests/test_multi_item.py`
      Verify: `.\venv\Scripts\python.exe -m pytest tests/test_multi_item.py -q` — all pass.

- [ ] 7. Add BUG-2 regression tests for aliases + number words.
      In `tests/test_rates.py` add `test_find_all_items_resolves_pashto_sindhi_staples`: `find_all_items('الو')`→contains `aloo`; `find_all_items('پياز')`→`pyaaz`; `find_all_items('چاہ پتی')`→`chai_patti`; and `find_all_items('mehngai zabardasti dukandar')` still == set() (no fabrication). In `tests/test_nlp_rules.py` add `test_pashto_number_words`: `parse_word_numbers('يو سل پنځوس')` contains `150`, `parse_word_numbers('دوه سوه')` contains `200`, and the Punjabi `parse_word_numbers('تن سو پنجاہ')` contains `350`.
      Files: `awaaz_backend/tests/test_rates.py`, `awaaz_backend/tests/test_nlp_rules.py`
      Verify: `.\venv\Scripts\python.exe -m pytest tests/test_rates.py tests/test_nlp_rules.py -q` — all pass.

- [ ] 8. Full regression + live-path integration run.
      Run the whole deterministic + live suite and confirm the three task examples end-to-end.
      Files: none (verification only)
      Verify: `.\venv\Scripts\python.exe -m pytest tests/ -q` — all pass (37 prior + new). Then an optional live check: start `uvicorn main:app --port 8040`, POST the English/Pashto/Punjabi examples to `/api/complaints/text`, confirm English sugar=180 (+28.6%), Pashto → 4 rows potato150/onion200/tomato250/sugar180, Punjabi rice=350; shut uvicorn down and delete any scratch `.db` created. DATABASE_URL stays unset.

## Decisions recorded
- Positional attribution is a SECONDARY hardening; the PRIMARY fix is segmentation (step 1). Both ship together because the Pashto example needs the split and the Punjabi/English examples benefit from the positional fallback when a clause still holds 2+ items.
- Tea: reuse existing `chai_patti` (SAMPLE 1600), only add aliases — chosen over creating a new item because a tea item already exists; creating a second would duplicate and risk the 7-item count tests. Rate stays flagged SAMPLE.
- Script-variant normalization (yeh/kaf fold) chosen in addition to explicit aliases because the Pashto `پياز` vs rate-list `پیاز` mismatch is a code-point difference, not a vocabulary gap; normalization fixes a whole class of such mismatches while explicit aliases cover genuinely different words.
- All non-English native spellings are flagged NATIVE-REVIEW-REQUIRED in the plan and must carry a code comment to that effect.

## Known gaps / assumptions
- Arabic-script Balochi has no unique code points (documented limitation in `detect_language`); Balochi item extraction is out of scope here beyond what shared Urdu aliases already cover.
- Sindhi spellings are best-effort (NATIVE-REVIEW-REQUIRED); if any proves to collide with an existing alias during step 4 verification, drop that single alias rather than widen matching.
