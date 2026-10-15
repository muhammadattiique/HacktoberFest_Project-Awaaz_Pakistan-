# Multi-Item Complaint — Requirements & Technical Design

Project: Awaaz Pakistan (`polish/final` branch)
Scope area: backend AI pipeline + complaint persistence/API, frontend verdict rendering
Status: implementation-ready

---

## 1. Requirements

### 1.1 Summary

Today a single citizen complaint that names several commodities is reduced to **one** record for the **first** item only; every other item is silently dropped. The verification driver —

> "Bhai sahab, Raja Bazaar Rawalpindi mein Madina Cash & Carry wala dukandar aaloo 150 rupay kilo bech raha hai, jabke sarkari rate list ke hisab se ye sirf 80 rupay kilo hona chahiye. Pyaaz bhi 200 rupay kilo le raha hai. Ye log zabardasti mehngai kar ke awaam ko loot rahe hain. Please is ke khilaf action lein."

— currently produces one Potato record (reported Rs 150 vs official Rs 100, +50%) and discards the onion (pyaaz, Rs 200). We must capture **every** extractable item as its own fully-formed complaint, grouped under one shared `submission_id`, without breaking any existing single-item consumer.

Note on the "80 rupay" figure: the citizen *claims* the official rate is Rs 80, but the system compares against the authoritative notified rate from `rate-list.json` (`aloo` = Rs 100). The design keeps that behaviour — the official price always comes from `rate_service`, never from the citizen's text. So Potato remains Rs 150 vs Rs 100 (+50%). This is intentional and unchanged.

### 1.2 Functional Requirements

- FR1 — A submission that names N extractable commodities creates N `Complaint` rows, one per item, each with its own `id`, `category`, `urgency`, `status`, routing, and price comparison.
- FR2 — All rows from one submission share a single `submission_id` (one UUID generated per submission).
- FR3 — Shared fields are copied verbatim onto every row of the submission: `transcript_raw`, `detected_language`, `location_area`, `shop_name`, `lat`, `lng`, `audio_filename`, `audio_duration_seconds`.
- FR4 — Non-price items (PFA food-safety, Municipal infrastructure) that co-occur in the same submission also split into their own rows with correct `category`/`routing_agency`/`helpline_reference`.
- FR5 — The aaloo+pyaaz driver produces exactly two rows: `Potato` (Rs 150 vs Rs 100, +50%, High) and `Onion` (reported Rs 200 vs its notified `pyaaz` rate of Rs 120, +66.7%, High), sharing one `submission_id`. Because Onion's overcharge (66.7%) exceeds Potato's (50%), the Onion is the `primary` and sorts to index 0.
- FR6 — A one-item submission behaves exactly as today (one row) plus a `submission_id` that groups just that row.
- FR7 — A submission with no resolvable item produces exactly one row using the existing "Unspecified" fallback, with a `submission_id`.
- FR8 — `POST /api/complaints/text` and `POST /api/complaints/voice` return all created complaints plus a designated `primary` (highest severity / highest overcharge), while remaining backward compatible for callers that read a single object's single-item fields.
- FR9 — `GET /api/complaints`, `GET /api/complaints/{id}`, `PATCH /api/complaints/{id}` stay per-row and unchanged in shape, except `ComplaintResponse` now carries `submission_id`.
- FR10 — The frontend verdict renders one violation card per returned complaint, under a header stating how many violations were detected, preserving existing styling/animation/RTL.

### 1.3 Non-Functional Requirements

- NFR1 — Backward compatibility is mandatory: existing per-row fields (`item_name`, `reported_price`, `official_price`, `percentage_overcharge`, …) remain populated exactly as today on every row. Analytics, admin, list, CSV export, and shop-profile consumers must keep working untouched.
- NFR2 — The only schema change is one additive, nullable, indexed `submission_id` column. No data migration tool (Alembic) exists; the column is added idempotently at startup. Old rows must not break.
- NFR3 — Robustness: an Ollama outage never raises to the caller. Multi-item extraction degrades to best-effort rule extraction producing at least one item, mirroring today's hybrid philosophy.
- NFR4 — All multi-item rows for a submission are persisted in a **single transaction** (all-or-nothing).
- NFR5 — Whisper import stays lazy (inside `AIPipeline._init_whisper`). No module-level `import whisper`.
- NFR6 — No change to auth, CORS, or admin-key behaviour. No reformatting of unrelated files. No commits.

### 1.4 Acceptance Criteria (testable)

1. `POST /api/complaints/text` with the aaloo+pyaaz driver returns HTTP 201, a body with `submission_id`, a `complaints` array of length 2, and a `primary` object.
2. The two complaints have distinct `id`s and an identical `submission_id`; one has `item_canonical_id == "aloo"`, the other `item_canonical_id == "pyaaz"`.
3. The Potato row has `reported_price == 150`, `official_price == 100`, `percentage_overcharge == 50.0`, `category == "PERA - Overpricing"`.
4. The Onion row has `reported_price == 200`, `official_price == 120` (the `pyaaz` notified rate from `rate-list.json`), `price_difference_pkr == 80.0`, `percentage_overcharge == 66.7` (`round((200-120)/120*100, 1)`), and `urgency == "High"`.
5. Every row in the response shares identical `transcript_raw`, `location_area`, `shop_name`, `lat`, `lng`, `detected_language`.
6. `primary` equals the row with the highest `percentage_overcharge` (ties broken by urgency rank High>Medium>Low). For the aaloo+pyaaz driver this means `primary.item_canonical_id == "pyaaz"` (66.7% > 50%), and `complaints[0]` is likewise the Onion row because the list is overcharge-sorted.
7. A single-item submission ("Aloo 180 rupay kilo") returns `complaints` of length 1 and `primary` equal to that element; the row still passes every existing `test_api.py` assertion.
8. A no-item submission returns `complaints` of length 1 with the "Unspecified" fallback and a non-null `submission_id`.
9. `GET /api/complaints`, `GET /api/complaints/{id}`, `PATCH /api/complaints/{id}` return `ComplaintResponse` objects that now include `submission_id` and are otherwise unchanged; all existing `test_api.py` tests pass.
10. With Ollama forced unavailable (patched `_call_ollama_llm` returning `None`), the aaloo+pyaaz driver still yields at least the Potato row via rules, and the endpoint still returns 201.
11. Startup against a pre-existing `awaaz.db` that lacks `submission_id` adds the column without error; previously stored rows load with `submission_id == None`.
12. The frontend renders two violation cards (Potato and Onion) with a "2 violations detected" header for the driver, each card showing its own commodity, prices, overcharge %, routing, helpline, and complaint id.

### 1.5 Out of Scope

- Grouping/filtering complaints by `submission_id` in list/analytics endpoints or admin UI.
- De-duplicating repeated items within one submission (each extracted item becomes a row).
- Changing official rates, thresholds, routing agencies, or helpline numbers.
- Any Alembic/migration framework adoption.
- Backfilling `submission_id` for historical rows (they stay `NULL`).

---

## 2. Technical Design

### 2.1 Overview

The feature is implemented in four layers that already exist, extended minimally:

1. **AI pipeline** (`ai_pipeline.py`) gains a `parse_complaint_items(text) -> List[dict]` method that returns one per-item dict in the exact shape `parse_complaint_text` returns today. `parse_complaint_text` is kept and re-expressed as "return the primary item from the multi-item result", so all existing callers and tests keep working.
2. **Persistence** (`db/models.py`, `db/session.py`) gains a nullable, indexed `submission_id` column, added idempotently at startup via a `PRAGMA table_info` guard.
3. **API** (`routers/complaints.py`, `schemas.py`) builds one `Complaint` per extracted item inside one transaction sharing a `submission_id`, and returns a new `MultiComplaintResponse`. Read endpoints are unchanged except `ComplaintResponse` gains optional `submission_id`.
4. **Frontend** (`lib/api.js`, `sections/ReportSection.jsx`, `i18n/translations.js`) renders each returned complaint as its own violation card under a count header, with a fallback for the legacy single-object shape.

Technology stack (locked): FastAPI, SQLAlchemy 2.x async + aiosqlite (SQLite at `awaaz_backend/awaaz.db`), Pydantic v2, Ollama `qwen2.5:1.5b-instruct`, lazy OpenAI Whisper; React 18 + Vite + Tailwind + framer-motion + axios.

### 2.2 Data flow

```
request text/voice transcript
        │
        ▼
ai_pipeline.parse_complaint_items(text)  ──► List[item dict]   (>= 1 element, never raises)
        │                                     each dict == today's parse_complaint_text shape
        ▼
router: submission_id = str(uuid4())
        for each item dict:
            Complaint(**item fields, **shared fields, submission_id=submission_id)
            db.add(complaint)
        db.commit()  (single transaction)  →  refresh all
        ▼
pick primary = max overcharge (tie → urgency rank)
        ▼
MultiComplaintResponse{ submission_id, complaints:[...], primary }
```

### 2.3 Pipeline design (the core)

File: `awaaz_backend/ai_pipeline.py`.

#### 2.3.1 New method `parse_complaint_items`

Signature:

```python
def parse_complaint_items(self, transcript_text: str) -> List[Dict[str, Any]]:
    """Return a list of per-item extraction dicts.

    Each element has the identical shape parse_complaint_text returns today
    (item_name, item_canonical_id, unit, reported_price, official_price,
     price_difference_pkr, percentage_overcharge, category, urgency,
     detected_language, native_response, routing_agency, helpline_reference,
     extraction_confidence, needs_review).

    Guarantees:
      * never raises to the caller (LLM failure degrades to rules);
      * always returns at least one element (fallback "Unspecified").
    """
```

#### 2.3.2 LLM path — schema and prompt changes

`COMPLAINT_SCHEMA` becomes an object wrapping an `items` array, so the single-item schema is preserved per element:

```python
COMPLAINT_ITEM_SCHEMA = {   # one item == today's COMPLAINT_SCHEMA properties
    "type": "object",
    "properties": { ... existing item_name/reported_price/category/urgency/
                        detected_language/native_response ... },
    "required": ["item_name", "reported_price", "category", "urgency",
                 "detected_language", "native_response"],
}

COMPLAINT_SCHEMA_MULTI = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": COMPLAINT_ITEM_SCHEMA, "minItems": 1}},
    "required": ["items"],
}
```

`FEW_SHOT_SYSTEM_PROMPT` is extended: all existing single-item examples are kept, each wrapped as `{"items": [ <existing output> ]}`, and **one new multi-item example** is added using the aaloo+pyaaz driver, showing two items (Potato Rs 150, Onion Rs 200). The system instruction gains one line: "If the complaint mentions multiple commodities or multiple distinct issues, return one object per commodity/issue in `items`."

A new private `_call_ollama_llm_multi(text) -> Optional[List[dict]]` mirrors `_call_ollama_llm` but passes `format=COMPLAINT_SCHEMA_MULTI`, parses the wrapper, and returns `parsed["items"]` (a list) or `None`. It reuses the existing markdown-fence stripping and retry logic. If the model returns a bare object instead of the wrapper (small-model drift), it is coerced to a one-element list.

#### 2.3.3 Per-item reconciliation (deterministic layer)

The deterministic rule layer today resolves **one** item from the whole text. For multi-item we drive reconciliation **per LLM item** and additionally run a **rule-only multi-item discovery** so items the LLM misses are still caught.

Shared, text-level signals computed once (unchanged helpers), passed to every per-item call:
- `det_lang = detect_language(text)` — the whole-text language, reused on every item. The current `parse_complaint_text` already **ignores** the LLM's `detected_language` and always serialises `det_lang` (see the `if llm_lang: final_detected_lang = det_lang` line); `_reconcile_item` must preserve that exactly, so every row of a submission carries the same `detected_language` (satisfies FR3/AC5).
- `rule_cat, rule_urg, _, _ = classify_category_and_urgency(text)` — computed once; used as the category/urgency fallback and for the PFA/Municipal deterministic override, identical to today. (Category classification is text-level, not item-level, in the current rules; we keep that — a mixed submission's category override is driven by keyword presence in the shared text, which is acceptable because the dominant non-price grievance keywords, e.g. "gutter", surface the Municipal/PFA category for the item that carries no price. See the mixed-category edge case in 2.8.)

**Signature (exact contract):**

```python
def _reconcile_item(
    self,
    *,
    item_name_hint: Optional[str],      # LLM item_name for this item, or rule-discovered name
    reported_price_hint: Optional[float],  # LLM reported_price for this item (may be None)
    category_hint: Optional[str],       # LLM category for this item (may be None/invalid)
    urgency_hint: Optional[str],        # LLM urgency for this item (may be None/invalid)
    native_hint: Optional[str],         # LLM native_response (may be None)
    clause: Optional[str],              # the clause attributed to this item (2.3.4), or None
    text: str,                          # full transcript (for category/routing/lang)
    det_lang: str,
    rule_cat: str,
    rule_urg: str,
    has_llm: bool,                      # True when this item came from the LLM path
) -> Dict[str, Any]:
```

`_reconcile_item` reuses the **exact** current single-item logic from `parse_complaint_text`, parameterised by one item instead of the whole text:

1. Resolve canonical id from `item_name_hint`: `rate_service.resolve_item(item_name_hint)`. If it resolves, take `name_en`/`unit` from the item dict; if unresolved, keep the raw `item_name_hint` and `item_canonical_id = None` (same as today's `else: final_item_name = str(llm_item)` branch).
2. Price precedence (identical to today's `rule_price > 0 ? rule_price : llm_price_val : 0.0`). `extract_price_and_normalize` returns a **tuple** `(Optional[float], float)` = `(normalized_unit_price, confidence)`, so it must be unpacked — never used as a scalar:

   ```python
   rule_price, _rule_price_conf = extract_price_and_normalize(clause or text)   # tuple unpack
   if rule_price and rule_price > 0:        # None short-circuits (None and ... is falsy)
       price = rule_price
   else:
       try:
           llm_price_val = float(reported_price_hint) if reported_price_hint is not None else 0.0
       except (ValueError, TypeError):
           llm_price_val = 0.0
       price = llm_price_val if llm_price_val > 0 else 0.0
   ```

   Keep the `rule_price and rule_price > 0` ordering so a `None` price short-circuits before the comparison. This mirrors today's `rule_price, price_confidence = extract_price_and_normalize(text)` unpack in `parse_complaint_text`.
3. Category: `rule_cat` wins when it is `PFA - Food Safety` or `Municipal - Infrastructure`; else `category_hint` if in the valid-enum list; else `rule_cat` — identical to today. Urgency: `urgency_hint` if in `{Low,Medium,High}`, else left `None` for the post-step to fill.
4. `comparison = rate_service.compare_price(item_id=canonical_id or "", reported_price=price, unit=unit)` → `official_price`, `price_difference_pkr`, `percentage_overcharge`. (When `canonical_id` is None, `compare_price("")` returns the "item not found" dict with zeros, exactly as today's unresolved path.)
5. Urgency alignment for `PERA - Overpricing` against `HIGH_SEVERITY_THRESHOLD_PCT` / `OVERCHARGE_ALERT_THRESHOLD_PCT`, else `Low` — identical to today.
6. Routing agency + helpline via `classify_category_and_urgency(text, pct_overcharge)` with the same hard PFA/Municipal overrides as today.
7. `native_response`: keep `native_hint` when it is non-empty, `len > 10`, and not an English template leaking into a Roman-Urdu complaint (the exact `any(w in llm_ack.lower() for w in [...])` guard today); otherwise `generate_native_acknowledgment(det_lang, item_name, price_diff)`. Acknowledgment is per item, but the frontend speaks only the **primary's** acknowledgment and renders the shared transcript once (see 2.6).
8. `needs_review`/`extraction_confidence`: same rules as today — for `PERA - Overpricing`, `needs_review=True` and confidence capped at 0.55 when `reported_price <= 0 or not canonical_id`; otherwise `needs_review=True` when confidence `< 0.60`. Base confidence starts at 0.50, `+0.35` when `has_llm` is True (mirrors today), clamped to `[0.20, 0.99]`.

This is a direct refactor: the body of `_reconcile_item` is the second half of today's `parse_complaint_text` (from "Compute price comparison" onward, plus the item/price/category reconciliation above it) lifted verbatim into a helper. For the **single-item** path, `parse_complaint_items` calls `_reconcile_item` once with the whole text as the clause and the single LLM object's fields as hints, so `parse_complaint_text`'s observable output is byte-for-byte unchanged (verified by keeping every existing `test_pipeline.py` assertion green).

#### 2.3.4 Per-item price mapping and clause segmentation

`extract_price_and_normalize` returns the **first** plausible price it finds (`plausible[0]` in the fallback branch), and `extract_quantities_and_units` reads the first unit — both operate on free text. Running either on the whole aaloo+pyaaz transcript yields only `150` (first match), which is exactly why the onion is lost today. To map prices to the right item without rewriting those functions, segment the text into clauses and run the extractor **per clause**.

Clause segmentation — new private helper `_segment_clauses(text) -> List[str]`:

- Split on sentence punctuation (`.`, `۔`, `!`, `?`, newline) **and** the enumerating connectives that separate commodities in Pakistani code-switching: ` bhi `, ` بھی `, ` aur `, ` اور `, and the comma `،`/`,`. Implement as a single `re.split` on the alternation, then strip and drop empty fragments. The driver "… aaloo 150 rupay kilo bech raha hai, jabke … 80 rupay kilo hona chahiye. Pyaaz bhi 200 rupay kilo le raha hai. …" splits so that `aaloo … 150 … hona chahiye` and `Pyaaz … 200 …` land in separate clauses.
- Note the "80 rupay" trap: the aaloo clause also contains "80 rupay" (the citizen's *claimed* official rate). This is harmless because the official price is **always** taken from `rate_service.compare_price` (`aloo` = Rs 100), never from the clause; the clause price only supplies the **reported** price. `extract_price_and_normalize` returns a `(price, confidence)` tuple whose price is `150` (the first price in the clause, "150 rupay kilo"), so reported=150 vs official=100 (+50%) is preserved. This matches §1.1's note.

Price attribution for an item (used in `_reconcile_item` step 2):

- Given the item's resolved canonical id/aliases, pick the clause whose text contains that item's name or any alias via a **constrained** match (see rule-discovery below for the exact matcher) — not fuzzy. Run `reported_price, _conf = extract_price_and_normalize(clause)` on that clause (unpacking the tuple — see finding 1). This yields 150→aloo and 200→pyaaz.
- Fallback when no clause can be attributed to the item (name absent from every clause): use `reported_price_hint` (the LLM price) for that item; if that is also `0`, the item keeps `0.0` and `needs_review=True`. For the single-item case the whole text is one clause, so this reduces to today's exact behaviour.

Rule-only discovery (LLM-down path) — new private helper `_discover_items_by_rules(clauses) -> List[dict]`:

- Why `resolve_item` cannot be used directly for discovery (two independent problems):
  1. It is **greedy**: its tier-4 RapidFuzz branch (`token_set_ratio >= 75`) matches almost any non-trivial clause to *some* commodity, so it would fabricate spurious items. We must reject tier-4.
  2. It **returns the first match only**: tier-3 iterates `self._alias_map` (a dict of `normalized_alias -> canonical_id`) and `return`s the first alias (in dict-insertion order) with `len(alias) >= 3` that is a substring of the clause. A clause that still contains **two** commodity names (a run-on with no splitting connective, so segmentation did not separate them) would resolve to only the first commodity and silently drop the second — re-introducing the exact bug being fixed.

- Discovery therefore does **not** call `resolve_item`. Instead a new thin public method on `RateService` scans the alias map to collect **every distinct canonical id** present in a clause, applying the same tier-1-to-3 matching rule (and only that rule, so fuzzy tier-4 is excluded by construction):

  ```python
  # services/rates.py — new method, additive, owned by RateService
  def find_all_items(self, text_or_name: str) -> List[Tuple[str, Dict[str, Any]]]:
      """All distinct (canonical_id, item_dict) whose name/alias (len>=3) appears
      in the text. Mirrors resolve_item tiers 1-3 (exact id / exact alias /
      >=3-char substring) but collects ALL matches instead of returning the first.
      Fuzzy tier-4 is deliberately excluded. Preserves alias-map insertion order."""
      norm = (text_or_name or "").lower().strip()
      out: List[Tuple[str, Dict[str, Any]]] = []
      seen: set[str] = set()
      for alias, canonical_id in self._alias_map.items():
          if len(alias) >= 3 and (alias == norm or alias in norm or norm in alias):
              if canonical_id not in seen:
                  seen.add(canonical_id)
                  out.append((canonical_id, dict(self.items[canonical_id])))
      return out
  ```

  (`_alias_map` already contains every alias plus the canonical ids themselves as keys, so exact-id and exact-alias matches are covered by the same substring test at confidence-equivalent ≥0.92. `find_all_items` intentionally bypasses `resolve_item`'s single-return and its fuzzy tier, and keeps the private `_alias_map` encapsulated inside `RateService`.)

- For each clause, call `rate_service.find_all_items(clause)`. Each distinct canonical id found (across all clauses, de-duplicated so the same commodity named in two clauses yields one discovery row) becomes an item: `name_en`/`unit` from the returned item dict, `reported_price, _conf = extract_price_and_normalize(clause)` for the clause the id was found in (tuple unpack — finding 1), and `category/urgency/routing` from `classify_category_and_urgency(text)`, all reconciled through `_reconcile_item` with `has_llm=False` and `clause=` the matching clause.
- If a clause contains two commodity ids, each becomes its own discovery row attributed to that same clause; the per-clause `extract_price_and_normalize` returns the clause's first price for both, which `_reconcile_item` then keeps or overrides per the price-precedence rule. (This is the degenerate run-on case; the driver does not hit it because its connectives split cleanly, but the collect-all behaviour means a two-commodity clause no longer silently drops the second commodity.)
- If **no** clause yields any canonical id, emit exactly one "Unspecified Commodity" item via the existing rule-only fallback branch (same dict today's `else:` path produces). This guarantees ≥1 item.
- The driver works offline because both `aloo` and `pyaaz` are canonical ids / aliases in `rate-list.json`, so `find_all_items` on the aaloo clause yields `[("aloo", …)]` and on the pyaaz clause yields `[("pyaaz", …)]` → two rule items with 150 and 200.

Invariant ownership: commodity resolution (which canonical ids a clause names) is owned by `RateService` via the additive, public `find_all_items`; the pipeline never touches the private `_alias_map`. `resolve_item` is left untouched for all existing single-item callers. `find_all_items` is used only by the new discovery path.

#### 2.3.5 Merge, de-dupe, ordering

`parse_complaint_items` assembles the final list as follows:

1. Build the **LLM item list**: if `_call_ollama_llm_multi` returned a non-empty list, run each element through `_reconcile_item(has_llm=True)` using per-item clause attribution (2.3.4). If it returned `None`/empty, the LLM list is empty.
2. Build the **rule item list** via `_discover_items_by_rules(clauses)` (always run, so LLM-missed items are still caught — this is what rescues the onion if the small model emits only potato).
3. **Union + de-dupe by `item_canonical_id`:** when both the LLM list and the rule list contain the same canonical id, collapse them into **one** merged row. The merge rule mirrors the project's existing price precedence (rule price wins when `> 0`) so a hallucinated LLM price can never override a deterministically extracted clause price:
   - **Price** — take the **rule-discovered row's `reported_price` if it is `> 0`, else the LLM row's `reported_price`.** The rule row's price comes from `extract_price_and_normalize` on the attributed clause and is the single source of price truth, exactly as `parse_complaint_text` does today (`if rule_price and rule_price > 0: use it`). Because `official_price`/`price_difference_pkr`/`percentage_overcharge` are derived from the chosen reported price via `rate_service.compare_price`, recompute them (or carry them from the row whose price was chosen) so the merged row's comparison is internally consistent with its final price.
   - **Category / urgency / native_response** — take the **LLM row's** values when present (it carries the model's richer classification and native-language acknowledgment); fall back to the rule row's values when the LLM row lacks them.
   - **Canonical identity fields** (`item_name`, `item_canonical_id`, `unit`) — identical in both rows by construction (same canonical id), so either is fine; use the rule row's resolved `name_en`/`unit`.

   This makes the deterministic rule the authority on price while preserving the LLM's classification/wording. Rows with `item_canonical_id is None` (unresolved) are kept **only if** the union contains no resolved row, preventing a spurious "Unspecified" row from sitting beside real items.
4. **Order** the surviving rows by `percentage_overcharge` descending (ties keep insertion order) so index 0 is a natural primary; the router still computes `primary` explicitly (2.5.2).
5. Guarantee ≥1 element: if after de-dupe the list is empty (should not happen, since discovery always yields ≥1), fall back to the single "Unspecified" dict.

#### 2.3.6 `parse_complaint_text` compatibility

```python
def parse_complaint_text(self, transcript_text: str) -> Dict[str, Any]:
    items = self.parse_complaint_items(transcript_text)
    return items[0]   # highest-overcharge / fallback item
```

Because `parse_complaint_items` orders by overcharge and always returns ≥1 element, every existing `test_pipeline.py` assertion (single Urdu/Roman item, food-safety, infrastructure, empty transcript, LLM-failure fallback) continues to hold. The empty-transcript branch returns the existing single fallback dict wrapped in a one-element list.

#### 2.3.7 Pipeline error handling (concrete)

| Operation | Failure | Recoverable? | Caller receives | Logging |
|---|---|---|---|---|
| `_call_ollama_llm_multi` network/timeout/parse error | yes | falls back to rule-only discovery | `logger.warning` (as today) |
| LLM returns non-list / empty | yes | coerce to list or fall back to rules | `logger.info` |
| `rate_service.resolve_item` returns None for an item | yes (expected) | item kept with `canonical_id=None`, `official_price=0`, `needs_review=True` | none (normal path) |
| `extract_price_and_normalize` finds no price | yes | price `0.0`, `needs_review=True` for overpricing | none |
| empty/whitespace transcript | n/a | one-element list with existing "Unspecified" fallback | none |
| any unexpected exception inside `parse_complaint_items` | yes | caught at method top-level `try/except`, returns one-element fallback list | `logger.exception` |

`parse_complaint_items` **never** raises; the whole body is wrapped so an unforeseen error still yields the one-element safe fallback.

### 2.4 Persistence design

#### 2.4.1 Model change — `db/models.py`

Add after `id`:

```python
submission_id = Column(String(36), nullable=True, index=True)
```

Add to `to_dict()`:

```python
"submission_id": self.submission_id,
```

`submission_id` is intentionally **not** a foreign key and **not** unique — it groups rows, and old rows may be `NULL`.

Adding this key to `to_dict()` is safe for NFR1: `ComplaintResponse` serialises via `from_attributes` (it reads model attributes directly, not `to_dict()`), and the `to_dict()` consumers (analytics/CSV/admin) iterate over the keys they expect rather than failing on an unexpected one, so an additional key is ignored by every current consumer. No consumer breaks on the extra key.

#### 2.4.2 Idempotent column creation — `db/session.py`

The prompt states `db/session.py` already does a `PRAGMA table_info("complaints")` check at startup; it does **not** today (`init_db` only runs `Base.metadata.create_all`). `create_all` creates missing *tables* but never alters an existing table, so a pre-existing `awaaz.db` would keep the old schema. We therefore add the guarded `ALTER TABLE` here, which also establishes the pattern the prompt references.

No new imports are needed: `session.py` already imports `settings` at module top (`from config import settings`) to build the engine, so `settings.DATABASE_URL` is in scope. A `from sqlalchemy import text` import is **not** required either, because we use `conn.exec_driver_sql` (the raw-string driver API) rather than the `text()` wrapper.

```python
async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Additive, idempotent migration for SQLite (no Alembic in this project).
        if "sqlite" in settings.DATABASE_URL:
            await _ensure_submission_id_column(conn)

async def _ensure_submission_id_column(conn) -> None:
    # conn is an AsyncConnection; exec_driver_sql is awaitable and returns a
    # CursorResult whose fetchall() is synchronous.
    result = await conn.exec_driver_sql('PRAGMA table_info("complaints")')
    cols = {row[1] for row in result.fetchall()}   # row[1] == column name
    if "submission_id" not in cols:
        await conn.exec_driver_sql(
            'ALTER TABLE complaints ADD COLUMN submission_id VARCHAR(36)'
        )
        # Index creation is idempotent via IF NOT EXISTS; name matches the one
        # SQLAlchemy would generate for index=True (ix_complaints_submission_id).
        await conn.exec_driver_sql(
            'CREATE INDEX IF NOT EXISTS ix_complaints_submission_id '
            'ON complaints (submission_id)'
        )
```

Notes:
- Both statements run **inside the same `engine.begin()` transaction** as `create_all`, so startup migration is atomic; a failure rolls back and surfaces at startup (fail-fast), which is the desired behaviour for a schema problem.
- `ALTER TABLE … ADD COLUMN` on SQLite only supports a nullable column without a non-constant default, which is exactly what we need. New rows written by the app always set `submission_id`; historical rows stay `NULL`.
- On a brand-new DB, `create_all` already includes the column (and its index from `index=True` on the model), so the `PRAGMA` check finds it present and the `ALTER`/`CREATE INDEX` are skipped — no error. On a pre-existing DB that already ran this once, the column is present and the block is likewise skipped — fully idempotent across restarts.
- The `VARCHAR(36)` in the raw DDL matches `String(36)` in the model, keeping a fresh-DB schema and a migrated-DB schema byte-identical.
- Invariant ownership: the *application layer* (router) owns populating `submission_id` on every new row; the DB only guarantees the column exists and is indexed. This matches the project's create-all-at-startup convention (there is no Alembic; `init_db` is the sole schema authority).

#### 2.4.3 Old-row semantics

Historical rows load with `submission_id == None`. `ComplaintResponse.submission_id` is `Optional[str] = None`, so serialising them is safe. We do **not** backfill (`submission_id = id`) to avoid a write migration; `None` is an acceptable "ungrouped legacy" marker and no consumer groups by it (out of scope).

### 2.5 API design

File: `awaaz_backend/schemas.py` and `awaaz_backend/routers/complaints.py`.

#### 2.5.1 Schemas

`ComplaintResponse` gains one optional field, inserted **between `id` and `created_at`** (today `created_at` immediately follows `id`; keep that order with `submission_id` slotted in between — field order is cosmetic in Pydantic, this is purely for readability):

```python
class ComplaintResponse(BaseModel):
    id: str
    submission_id: Optional[str] = None
    created_at: datetime
    ...   # everything else unchanged
    model_config = ConfigDict(from_attributes=True)
```

New response schema (preferred shape):

```python
class MultiComplaintResponse(BaseModel):
    submission_id: str
    complaints: List[ComplaintResponse]
    primary: ComplaintResponse
```

`primary` is included as a full object (not just an id) so a backward-compatible client can read `response.primary.item_name` etc. without a second lookup, and so the response is self-describing.

#### 2.5.2 Endpoint changes

Both `POST /api/complaints/text` and `POST /api/complaints/voice` change `response_model` from `ComplaintResponse` to `MultiComplaintResponse` (still `status_code=201`). The shared extraction/persistence logic is factored into one helper to avoid duplicating it across the two handlers:

```python
async def _persist_submission(
    db: AsyncSession,
    *,
    transcript_text: str,
    shared: dict,     # audio_filename, audio_duration_seconds, location_area,
                      # shop_name, lat, lng
) -> MultiComplaintResponse:
    items = await run_in_threadpool(ai_pipeline.parse_complaint_items, transcript_text)
    submission_id = str(uuid.uuid4())
    complaints: list[Complaint] = []
    for ex in items:
        complaints.append(Complaint(
            submission_id=submission_id,
            transcript_raw=transcript_text,
            detected_language=ex["detected_language"],
            category=ex["category"],
            urgency=ex["urgency"],
            status="Pending",
            extraction_confidence=ex["extraction_confidence"],
            needs_review=ex["needs_review"],
            item_name=ex.get("item_name"),
            item_canonical_id=ex.get("item_canonical_id"),
            unit=ex.get("unit"),
            reported_price=ex.get("reported_price"),
            official_price=ex.get("official_price"),
            price_difference_pkr=ex.get("price_difference_pkr"),
            percentage_overcharge=ex.get("percentage_overcharge"),
            native_response=ex["native_response"],
            routing_agency=ex["routing_agency"],
            helpline_reference=ex["helpline_reference"],
            **shared,   # audio + location/shop/lat/lng
        ))
    db.add_all(complaints)
    await db.commit()
    for c in complaints:
        await db.refresh(c)
    responses = [ComplaintResponse.model_validate(c) for c in complaints]
    primary = _select_primary(responses)
    return MultiComplaintResponse(
        submission_id=submission_id, complaints=responses, primary=primary
    )
```

`detected_language` on every row comes from the per-item dicts; since `detect_language` is computed on the whole text, all items share the same value, satisfying FR3.

`_select_primary(responses)` chooses the max `percentage_overcharge`; ties broken by urgency rank `{High:3, Medium:2, Low:1}`, then by original order. Since `parse_complaint_items` already orders by overcharge, this is typically `responses[0]`, but the explicit selector keeps the contract clear.

Each handler computes `inferred_area = location_area or extract_area_from_text(transcript_text)` **before** calling the helper (unchanged logic) and passes it in `shared["location_area"]`, so area inference stays in the handler exactly as today and `_persist_submission` stays transport-agnostic. The `shared` dict therefore contains: `audio_filename`, `audio_duration_seconds`, `location_area` (the inferred value), `shop_name`, `lat`, `lng`. These keys are applied to each `Complaint` via `**shared`, so every row of a submission shares identical audio/location/shop metadata (FR3/AC5).

The voice handler keeps its existing audio pipeline (temp dir, FFmpeg conversion via `validate_and_convert_audio`, Whisper transcription via `transcribe_audio_detailed`, the 400 "no audible speech"/503 "transcription unavailable" branches, and the `finally: shutil.rmtree(temp_dir)`) **unchanged**, then calls `_persist_submission` with the transcript and a `shared` dict carrying `audio_filename=audio.filename` and `audio_duration_seconds=duration_sec`. The text handler calls it with `audio_filename=None, audio_duration_seconds=None`. The `parse_complaint_items` call runs via `run_in_threadpool` (as `parse_complaint_text` does today) because it performs blocking Ollama/rule work.

#### 2.5.3 Input validation (unchanged + explicit)

- `transcript_text`: required, `min_length=2` (Pydantic), trimmed; empty-after-trim → 400 (existing behaviour in the text handler is retained).
- `location_area`, `shop_name`: optional strings, passed through.
- `lat`, `lng`: optional floats, passed through (no range check today; unchanged).
- Voice `audio`: required `UploadFile`; validity/size/format handled by the existing `validate_and_convert_audio` path returning 400/413/415/503 as today.

#### 2.5.4 API error handling (concrete)

| Operation | Failure | Status | Body | Logging |
|---|---|---|---|---|
| empty text after trim | fatal for request | 400 | `detail` "Complaint text cannot be empty" (unchanged) | none |
| audio invalid | fatal | 400 | existing message | none |
| whisper unavailable | fatal | 503 | existing message | `logger.error` (unchanged) |
| `parse_complaint_items` | never raises | — | always returns ≥1 item | handled in pipeline |
| `db.commit()` DB error | fatal | 500 (global handler) | generic 500 body | `logger.exception` via global handler |

The single `commit` guarantees all-or-nothing (NFR4); a failure rolls back the whole submission and the global exception handler returns 500.

#### 2.5.5 Read endpoints

`GET /api/complaints`, `GET /api/complaints/{id}`, `PATCH /api/complaints/{id}` are unchanged except they now serialise `submission_id` (because `ComplaintResponse` includes it). The list query, filters, pagination, and PATCH auth are untouched.

### 2.6 Frontend design

Files: `awaaz_pakistan/src/lib/api.js`, `awaaz_pakistan/src/sections/ReportSection.jsx`, `awaaz_pakistan/src/i18n/translations.js`.

#### 2.6.1 `api.js` — shape normalisation

`submitTextComplaint` / `submitVoiceComplaint` return `result.data` as today. To keep `ReportSection` simple and resilient to both shapes, add a small normaliser used by the section (or inline in the section):

```js
// Returns { submissionId, complaints: [...], primary } for any backend shape.
export const normalizeComplaintResult = (data) => {
  if (data && Array.isArray(data.complaints)) {
    return {
      submissionId: data.submission_id ?? null,
      complaints: data.complaints,
      primary: data.primary ?? data.complaints[0] ?? null,
    };
  }
  // Legacy single-object shape (also covers /api/process-complaint fallback).
  return { submissionId: data?.submission_id ?? null, complaints: data ? [data] : [], primary: data ?? null };
};
```

`submitTextComplaint`/`submitVoiceComplaint` are unchanged — they still return `{ success, data, isDemo }` where `data === res.data`. `ReportSection` keeps reading `result.data` and then calls `normalizeComplaintResult(result.data)` to get `{ submissionId, complaints, primary }`. This satisfies the "if backend returns new `{complaints:[...]}` shape render the list, with a fallback that still works for a single object" requirement, including the existing `/api/process-complaint` voice fallback (invoked on a 404 from `/api/complaints/voice`) which returns a single legacy object — the normaliser wraps it to a one-element `complaints` array so the multi-card renderer handles it with no special-casing. `onComplaintSubmitted(data)` is still passed the raw `result.data` (the recent-complaints ticker consumes the list endpoint, not this shape, so no change is needed there).

#### 2.6.2 `ReportSection.jsx` — multi-card verdict

- Replace `verdictData` usage with the normalised result: store `{ submissionId, complaints, primary }`.
- Add a header above the cards: `t.verdict.violationsCount` formatted with the count (e.g. "2 violations detected from your report"). Show the header only when `complaints.length > 1`; for a single item keep today's layout (no behavioural regression).
- Extract the existing verdict `CardTilt` block into an inner `VerdictCard` component (defined in the same file, above `ReportSection`) rendered via `complaints.map((c) => <VerdictCard key={c.id} complaint={c} ... />)`. Each card reads the per-complaint fields the current markup already uses: `id`, `item_name`, `reported_price`, `official_price`, `percentage_overcharge`, `routing_agency`, `helpline_reference`, `native_response`, `detected_language`, `needs_review`. The markup moves **verbatim** — the rose/emerald theming driven by `complaint.percentage_overcharge > 0`, the three `Badge` variants (red/green/neutral) keyed off `percentage_overcharge > 0` / `item_name` presence, the `formatPrice`/`formatVariance` calls, the `font-urdu` RTL branch when `detected_language === 'Urdu'`, the per-card Copy-ID button, the per-card Replay-Voice `speakText` call, and the `needs_review` amber notice. Note the backend does **not** return `is_violation`; the existing `|| verdictData.is_violation` term is a defensive no-op and is dropped in the per-card version, relying solely on `percentage_overcharge > 0` (unchanged observable behaviour, since `is_violation` was always `undefined`).
- Copy-ID state must be per-card: replace the single `copiedId` boolean with a `copiedId` holding the **id string** that was last copied (or null). Today's handler is `setCopiedId(true); setTimeout(() => setCopiedId(false), 2000)`; it becomes `setCopiedId(id); setTimeout(() => setCopiedId(null), 2000)` where `id` is `complaint.id`, and each card renders its checkmark when `copiedId === complaint.id`. This keeps the checkmark on the correct card when there are multiple.
- Transcript is shared, so render it **once** (from `primary.transcript_raw`) in a panel above the card list rather than inside every card, matching FR3's "shown once" intent. The `MiniLocationMap` (shared `lat`/`lng`, read from `primary`) likewise renders once, after the card list, exactly where today's single map renders.
- Count header: above the card list render `t.verdict.violationsCount.replaceAll('{count}', String(complaints.length))` **only when** `complaints.length > 1`; for a single item, render nothing new so the single-item layout is byte-identical to today. (`replaceAll` instead of `replace` is deliberate: `String.prototype.replace` with a string argument substitutes only the first `{count}`, which is fragile if a translator later adds a second token; `replaceAll` is safe for any number of tokens.)
- `avatarController.setVerdict`: compute `isViolation = complaints.some(c => (c.percentage_overcharge ?? 0) > 0)`. Build chips by mapping each complaint to one `{text: item_name}` neutral chip plus, when `percentage_overcharge` is truthy, one variance chip (`alert` when that item is a violation, else `success`); cap the total chip count at 6 so the avatar summary stays readable. For a single item this reproduces today's three-chip layout.
- Speech: speak `primary.native_response` with the existing `primary.detected_language === 'Urdu' ? 'ur-PK' : 'en-US'` selection (one utterance, not one per card).
- State shape: `verdictData` is replaced by the normalised `{ submissionId, complaints, primary }` object (or `null`). The `useEffect` and submit handlers that reset `setVerdictData(null)` are unchanged; the render guard becomes `verdictData && verdictData.complaints.length > 0`.

#### 2.6.3 i18n

`translations.js` has **two** `verdict:` blocks — one in the English (`en`) object and one in the Urdu (`ur`) object — with identical key sets (`title`, `violationBadge`, …, `viewOnMap`). Add the same new key to **both**, next to `viewOnMap`, consistent with existing keys:

```js
// English verdict block
violationsCount: "{count} violations detected from your report",
// Urdu verdict block
violationsCount: "آپ کی اطلاع سے {count} خلاف ورزیاں سامنے آئیں",
```

The codebase has **no** interpolation helper (keys are plain strings used directly), so render with `t.verdict.violationsCount.replaceAll('{count}', String(complaints.length))` — `replaceAll` substitutes every `{count}` token (future-proof against a second token) and `String(...)` coerces the count explicitly. No existing `t.verdict.*` or `t.report.*` keys are renamed or removed, so every current consumer keeps working.

#### 2.6.4 Frontend edge cases

- `complaints.length === 1`: identical to today (header hidden, one card).
- `complaints.length === 0` (defensive, shouldn't happen): keep the current "no verdict" state; do not crash the map.
- Legacy single-object backend (or `/api/process-complaint`): normaliser wraps it to a one-element list; renders exactly as today.
- Non-violation items (overcharge 0 / unverified): card uses the emerald/neutral theming per the existing conditional, per card.

### 2.7 Testability

Unit-testable (deterministic, LLM patched off as in `test_pipeline.py`):
- `parse_complaint_items("<aaloo+pyaaz driver>")` returns 2 items with correct canonical ids/prices/overcharge: `aloo` (150 vs 100, +50.0%) and `pyaaz` (200 vs 120, +66.7%), covering clause segmentation + per-item reconciliation.
- `_segment_clauses("<aaloo+pyaaz driver>")` yields clauses such that the aaloo clause resolves (via `rate_service.find_all_items`) to exactly `["aloo"]` and the pyaaz clause to exactly `["pyaaz"]` — i.e. one commodity per clause for the driver (proves finding 2's segmentation assumption for the targeted input).
- `rate_service.find_all_items("aaloo aur pyaaz dono mehnge")` returns **both** `aloo` and `pyaaz` (proves the collect-all resolver does not drop the second commodity in a run-on clause).
- Single-item and food-safety/infra/empty cases keep `parse_complaint_text` output identical (regression).
- LLM-down path still yields ≥1 item for the driver (rule-only discovery via `find_all_items`).
- De-dupe merge: when an LLM row and a rule row share a canonical id but carry different reported prices, the merged row keeps the **rule** price when `> 0` (proves finding 5's precedence — a hallucinated LLM price does not win).
- `_select_primary` ordering/tie-break, including that for the driver `_select_primary` returns the `pyaaz` row (66.7% > 50%).

Integration-testable (FastAPI `TestClient`, as in `test_api.py`):
- `POST /api/complaints/text` with the driver → 201, `len(complaints)==2`, shared `submission_id`, distinct ids, Potato/Onion fields per AC 1–6, and `primary.item_canonical_id == "pyaaz"`.
- Single-item submission → `len==1`, `primary == complaints[0]`; existing assertions still pass.
- `GET`/`PATCH` responses include `submission_id` and otherwise unchanged.
- Startup migration: against a DB missing the column (simulated by creating a table without it, or asserting idempotency on a fresh DB), `init_db` adds it without error.

Hard-to-test / manual:
- Voice path end-to-end (Whisper blocked on this machine) — covered indirectly by reusing the unchanged transcription path and testing `_persist_submission` through the text endpoint; the existing 503/400 voice tests still apply.

### 2.8 Edge cases summary

- Same item mentioned twice → two rows (no de-dupe by design, within scope note); canonical-id de-dupe in `parse_complaint_items` collapses obvious duplicates to avoid noise — documented behaviour, keep the higher-overcharge one.
- Mixed categories in one submission (e.g. "aloo mehnga + gutter overflow") → one PERA row + one Municipal row, shared `submission_id`.
- Item resolvable but no price → row with `official_price` from rates (if canonical) or 0, `needs_review=True`.
- Price present but item unresolvable → row with raw LLM name, `canonical_id=None`, `official_price=0`, `needs_review=True`.
- No item at all → single "Unspecified" fallback row (today's behaviour) with a `submission_id`.

### 2.9 Files touched (implementation checklist)

- `awaaz_backend/db/models.py` — add `submission_id` column + `to_dict` entry.
- `awaaz_backend/db/session.py` — add idempotent `ALTER TABLE` guarded by `PRAGMA table_info` in `init_db`.
- `awaaz_backend/ai_pipeline.py` — add `parse_complaint_items`, `_call_ollama_llm_multi`, `_reconcile_item`, `_segment_clauses`, `_discover_items_by_rules`; multi-item schema + prompt example; re-express `parse_complaint_text`. Keep whisper lazy.
- `awaaz_backend/services/rates.py` — add additive public `find_all_items(text) -> List[Tuple[str, dict]]` (collect-all, tiers 1-3, no fuzzy). `resolve_item` unchanged.
- `awaaz_backend/schemas.py` — `ComplaintResponse.submission_id`; new `MultiComplaintResponse`.
- `awaaz_backend/routers/complaints.py` — `_persist_submission`, `_select_primary`; both POST handlers return `MultiComplaintResponse`.
- `awaaz_pakistan/src/lib/api.js` — `normalizeComplaintResult`.
- `awaaz_pakistan/src/sections/ReportSection.jsx` — multi-card rendering, count header, shared transcript/map, avatar chips.
- `awaaz_pakistan/src/i18n/translations.js` — `verdict.violationsCount` (EN + UR).
- `awaaz_backend/tests/test_pipeline.py`, `tests/test_api.py` — add multi-item cases; keep existing tests green.

### 2.10 Verification plan

Backend (from `awaaz_backend`, using the existing venv — do **not** recreate it):

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

- All existing tests must stay green (backward compatibility).
- New tests: multi-item pipeline extraction, multi-item POST, `submission_id` presence on read endpoints, startup idempotent column add.

Manual smoke (optional, Ollama up):

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

POST the aaloo+pyaaz driver to `/api/complaints/text`; confirm 2 complaints with a shared `submission_id`, Potato (Rs 150 vs Rs 100, +50%) and Onion (Rs 200 vs Rs 120, +66.7%), and `primary.item_canonical_id == "pyaaz"` (the Onion, 66.7% > 50%) rendered as the first card.

Frontend (from `awaaz_pakistan`):

```powershell
npm run build
```

- Confirm build passes; manually verify the verdict renders two cards + "2 violations detected" header for the driver, and one card for a single-item submission.

Clean up any scratch DB/files created during verification. Do not commit.

---

## 3. Responses to design review (`design-review.json` / `design-review.md`)

All HIGH and MEDIUM findings are resolved directly in the sections above; the NITs are addressed too. Verified against source (`services/rates.py`, `services/nlp_rules.py`, `rate-list.json`) during this revision.

- **Finding 1 (HIGH) — `extract_price_and_normalize` returns a tuple, not a scalar. ADDRESSED.** §2.3.3 step 2 now shows the explicit `rule_price, _rule_price_conf = extract_price_and_normalize(clause or text)` unpack with the `rule_price and rule_price > 0` short-circuit on `None`. §2.3.4 price attribution and rule-discovery both unpack as `reported_price, _conf = extract_price_and_normalize(clause)`. Confirmed signature `-> Tuple[Optional[float], float]` in `nlp_rules.py:246`.

- **Finding 2 (HIGH) — `resolve_item` tier-3 returns only the first alias match, dropping a second commodity in a multi-commodity clause. ADDRESSED.** Discovery no longer calls `resolve_item`. §2.3.4 adds an additive public `RateService.find_all_items(text)` that scans `_alias_map` and collects **every distinct** canonical id (tiers 1-3 only; fuzzy tier-4 excluded by construction), de-duplicated. A unit test proves `find_all_items("aaloo aur pyaaz dono mehnge")` returns both ids, and a `_segment_clauses` test proves the driver segments to one commodity per clause (both in §2.7). Verified tier-3 `len(alias) >= 3 and (... substring ...)` early-return at `rates.py:102`.

- **Finding 3 (MEDIUM) — AC4 Onion values were placeholders. ADDRESSED.** AC4 and FR5 now pin `official_price == 120`, `price_difference_pkr == 80.0`, `percentage_overcharge == 66.7`, `urgency == "High"`. Verified `pyaaz` = Rs 120 in `rate-list.json`.

- **Finding 4 (MEDIUM) — primary for the driver is the Onion, not the Potato; narrative was ambiguous. ADDRESSED.** AC6 now states `primary.item_canonical_id == "pyaaz"` (66.7% > 50%) and that `complaints[0]` is the Onion. FR5, the §2.10 manual-smoke step, the §2.7 integration/unit tests, and the frontend first-card expectation are all aligned to primary = Onion.

- **Finding 5 (MEDIUM) — de-dupe tie-break let a hallucinated LLM price win. ADDRESSED.** §2.3.5 step 3 now specifies the merge takes **price from the rule row when `> 0`, else the LLM price** (rule is the single source of price truth, matching `parse_complaint_text`), while keeping the LLM's category/urgency/native text; derived comparison fields are recomputed from the chosen price for consistency. A unit test asserts the rule price wins on conflict.

- **Finding 6 (NIT) — field position. ADDRESSED.** §2.5.1 now says insert `submission_id` between `id` and `created_at`.

- **Finding 7 (NIT) — `to_dict()` extra-key safety. ADDRESSED.** §2.4.1 adds a sentence confirming `ComplaintResponse` uses `from_attributes` (not `to_dict`) and `to_dict` consumers ignore extra keys, so the addition is safe (NFR1).

- **Finding 8 (NIT) — per-card `copiedId` reset body. ADDRESSED.** §2.6.2 now states the handler is `setCopiedId(id); setTimeout(() => setCopiedId(null), 2000)` with each card checking `copiedId === complaint.id`.

- **Finding 9 (NIT) — `.replace` only hits the first token. ADDRESSED.** §2.6.2 and §2.6.3 switch to `.replaceAll('{count}', String(complaints.length))`.

- **Review's unverified item on `exec_driver_sql`/`fetchall` (sync).** Left as an implementation-time confirmation note (already flagged in §2.4.2's inline comment); the migration is additive and fail-fast, so the risk is low. Not blocking; a coder confirms against the installed SQLAlchemy version. No design change required.
