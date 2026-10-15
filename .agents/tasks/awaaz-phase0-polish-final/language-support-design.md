# Design: Full 6-Language Support for Awaaz Pakistan

**Mode:** READ-ONLY investigation + implementation-ready design. No source files were edited.
**Target languages:** English (`en`), Urdu (`ur`), Punjabi (`pa`), Sindhi (`sd`), Balochi (`bal`), Pashto (`ps`).
**Repo:** `c:\Users\muham\OneDrive\Desktop\HacktoberFest\HacktoberFest_Project-Awaaz_Pakistan-` (branch `polish/final`).

---

## 1. Summary answer (read first)

The project has **two independent language layers**, both confirmed by reading the code:

- **Layer 1 — Complaint understanding (backend AI).** `awaaz_backend/services/nlp_rules.py` and `awaaz_backend/ai_pipeline.py` detect the citizen's language, parse the price/item, and reply in-kind. They support **Urdu (script), Roman Urdu, Punjabi, Pashto, English today — Sindhi and Balochi are entirely missing.**
- **Layer 2 — UI interface language (frontend).** `awaaz_pakistan/src/i18n/translations.js` ships **only `en` and `ur`** blocks; `awaaz_pakistan/src/i18n/LanguageContext.jsx` hardcodes RTL and the Urdu font to `language === 'ur'`; the switcher in `awaaz_pakistan/src/components/ui/Navbar.jsx` offers **only two buttons (EN / اردو)**. Punjabi, Sindhi, Balochi, Pashto UI blocks and multi-language RTL handling are all missing.

The two layers are only loosely coupled (both exist to serve the same six languages, but share no code), so they can be implemented largely independently.

**Three facts shape the whole design:**

1. **The UI reads translations by dot-path, not a function.** Every component does `t.nav.report`, `t.verdict.title`, etc. (confirmed across `Navbar.jsx`, `Footer.jsx`, `FaqSection.jsx`, `KeyFeaturesSection.jsx`, `HeroSection.jsx`, `LocationPicker.jsx`, `FinalCtaSection.jsx`, `LiveImpactStatsSection.jsx`). A missing key therefore throws `TypeError: Cannot read properties of undefined` at render — it does **not** silently render blank. So the English-fallback mechanism **cannot be a `t()` wrapper**; it must guarantee that every language object is structurally complete. The chosen mechanism is a **recursive deep-merge of each language block over the full `en` block at module load** (details in §3.4).
2. **Five of six languages are Arabic-script RTL** (Urdu, Punjabi/Shahmukhi, Sindhi, Balochi/Arabic-script, Pashto); only English is LTR. The current `isRtl = language === 'ur'` check and the `font-urdu` body class must become set-membership checks.
3. **Balochi voice is not reliably transcribable.** Balochi orthography is unstandardized (both Arabic-script and Latin are in use) and faster-whisper has weak-to-no Balochi coverage. The design must specify **graceful degradation** for Balochi voice (fall back to text input and an Urdu/English response) and must **not** claim reliable Balochi transcription.

**Concurrency:** two other workflows have uncommitted edits in the tree right now (`git status` shows `ai_pipeline.py`, `main.py`, `requirements.txt`, `routers/complaints.py` modified). One is the **faster-whisper swap** (confirmed in the `ai_pipeline.py` working-tree diff: lazy `_import_whisper_model`, PyAV stub, `_load_wav_mono_float32`), the other is **multi-item parsing** (confirmed by staged edits to `complaints.py`/`main.py`). **This language work must land AFTER both merge** and must be written as *additive* to a multi-item world (see §6 and the ordered checklist in §5).

---

## 2. Layer 1 — Backend complaint understanding (add Sindhi + Balochi)

All Layer-1 changes are in two files. Every change below is grounded in the current code.

### 2.1 `awaaz_backend/services/nlp_rules.py`

#### (a) `detect_language()` — add Sindhi and Balochi branches

Current logic (lines ~246–293): if any Arabic-script char present → check Pashto-unique letters `['ښ','ړ','ږ','ۍ','ڼ']` → else return `"Urdu"`. For Latin script it checks English words, then Punjabi roman patterns, then Pashto roman patterns, else `"Roman Urdu"`.

**Problem:** Sindhi and Balochi in Arabic script will currently be mis-detected as `"Urdu"`, and their Roman forms as `"Roman Urdu"`. We add discriminators **before** the generic Urdu fallthrough, ordered most-specific-first so we do not steal detections from Urdu.

- **Sindhi script markers (add inside the Arabic-script branch, checked before the `return "Urdu"`):** Sindhi uses letters absent from standard Urdu: `ڄ ٺ ٽ ڻ ڱ ڳ ڦ ڀ ٿ` (and implosives `ڏ ڌ`). Detection rule: if any char in `['ڄ','ٺ','ٽ','ڻ','ڱ','ڳ','ڦ','ڀ','ٿ','ڏ']` → return `"Sindhi"`. These are strong signals — none appear in Urdu/Punjabi-Shahmukhi text.
- **Balochi script markers:** Balochi Arabic script largely overlaps Urdu/Persian and has **no reliable unique code points**, so script-based detection is weak. Treat Arabic-script Balochi as **best-effort**: detect only via Roman keyword markers (below); if a citizen writes Balochi in Arabic script it will fall through to `"Urdu"` — document this as an accepted limitation, not a bug. (Flag for native review.)
- **Sindhi Roman markers (add a `sindhi_patterns` list before the Punjabi check, since some tokens could overlap):** whole-word regexes for common Sindhi function words, e.g. `\bmaan\b` (I), `\btawhan\b`/`\btuhan\b` (you), `\baahe\b`/`\baahy\b` (is), `\bkahro\b`, `\bghani\b` (much/expensive), `\bqeemat\b` is shared so avoid it. **Flag the exact marker set for native-speaker review** — Roman Sindhi is not standardized.
- **Balochi Roman markers (add a `balochi_patterns` list):** whole-word regexes for Balochi function words, e.g. `\bmani\b` (my), `\btaw\b`/`\btau\b` (you), `\bint\b`/`\bent\b` (is), `\bgran\b` (expensive), `\bbazar\b` is shared so avoid it. **Flag for native-speaker review.**

Ordering guidance: inside the Arabic-script branch check **Pashto → Sindhi → (Balochi weak/skip) → Urdu**. For Latin check **English → Sindhi → Balochi → Punjabi → Pashto → Roman Urdu**, with the caveat that Roman Sindhi/Balochi/Urdu overlap heavily; keep the marker lists short and high-precision to minimise false positives against the existing `test_language_detection` cases (which must keep passing — see §4).

#### (b) `BASIC_NUMBER_WORDS` / `FRACTIONAL_PHRASES` / `URDU_INDIC_DIGITS`

- `URDU_INDIC_DIGITS`: **no change needed.** Sindhi and Balochi Arabic script reuse the same Eastern-Arabic/Urdu digit glyphs already mapped (۰–۹, ٠–٩).
- `BASIC_NUMBER_WORDS`: add Sindhi and Balochi romanized number words where they differ from the ~Urdu forms already present. Many overlap (`do`, `teen`, `sau`, `hazaar` are shared across the region), so the additions are small. Suggested additions (flag for native review): Balochi `yak`(1), `du`(2), `sai`(3), `char`(4), `panch`(5), `shash`(6), `hapt`(7), `hasht`(8), `nuh`(9), `dah`(10), `sad`(100), `hazar`(1000 — already present). Sindhi: `hik`(1), `ba`(2), `tei`(3), `chaar`(already), `panj`(already), `sau`(already). Where a word already maps to the same value, no edit is required.
- `FRACTIONAL_PHRASES`: the Pakistani fractional idioms (`dedh sau`, `dhai sau`, `sawa`, `paune`, `saadhe`) are shared colloquially across Sindhi/Balochi speakers in these markets; **no new entries are strictly required**, but note in a comment that these idioms are assumed shared. Keep this additive and low-risk.
- **The compound-hundreds table inside `parse_word_numbers()`** (the `compound_hundreds` list, lines ~140–152) should get the same new 1–9 Balochi/Sindhi prefixes added if they differ, so `"<prefix> sau"` compounds resolve. This is the one spot in number parsing that must mirror any `BASIC_NUMBER_WORDS` prefix additions.

#### (c) `generate_native_acknowledgment()` — add Sindhi + Balochi branches

Current function (lines ~384–412) switches on the language string and returns a native-script acknowledgment for Urdu / Punjabi / Pashto / English, else Roman Urdu. Add two branches **before** the Roman-Urdu `else`:

```python
    elif language == "Sindhi":
        # DRAFT — REQUIRES NATIVE SINDHI REVIEW before production.
        return "توهان جي شڪايت درج ٿي وئي آهي. لاڳاپيل اٿارٽيءَ ڏانهن ڪارروائيءَ لاءِ موڪلي وئي آهي. مهرباني."
        # Roman gloss: "Tawhan ji shikayat daraj thi vai aahe. Laagaapil authority
        # ddaanhan karrvaai laai mokli vai aahe. Mehrbani."

    elif language == "Balochi":
        # DRAFT — REQUIRES NATIVE BALOCHI REVIEW. Arabic-script Balochi is not
        # standardized; this string is best-effort and may need Latin-script form.
        return "شمے شکایت درج بوت. مزنیں ادارہ ءَ کارروائی ئِے واستہ دیم دات بوت. منتوار."
        # Roman gloss: "Shumay shikayat daraj boot. Maznen idaara-a karrvaai-e
        # waasta deem daat boot. Mintawaar."
```

**Both acknowledgment strings above are drafts and MUST be verified by native Sindhi and Balochi speakers before any production use.** They are structurally correct (polite "your complaint has been registered and forwarded for action; thank you") but orthographic/idiomatic fidelity is not guaranteed by this design.

### 2.2 `awaaz_backend/ai_pipeline.py`

> **Concurrency caution:** this file is being rewritten by the faster-whisper workflow right now (working-tree diff confirmed) and the multi-item workflow touches it too. The two edits below are **small, string-only, and additive** — they do not depend on single- vs multi-item shape. Apply them *after* those workflows merge, re-reading the file first.

#### (a) `COMPLAINT_SCHEMA` — widen `detected_language` description

Current (lines ~61–64): the `detected_language` property has
`"description": "Detected language (Urdu, Roman Urdu, Punjabi, Pashto, English)"`.
Change the description string to include Sindhi and Balochi:
`"Detected language (Urdu, Roman Urdu, Punjabi, Sindhi, Balochi, Pashto, English)"`.
This is a free-text `"type": "string"` field (no `enum`), so widening it is a pure description edit with zero structural risk — safe regardless of multi-item schema changes. **If** the multi-item workflow converts the schema to an array of item objects, this `detected_language` field stays at the top level either way; just re-locate it after merge.

#### (b) `FEW_SHOT_SYSTEM_PROMPT` — add one Sindhi and one Balochi example

Current prompt (lines ~84–145) lists the supported input languages in its first paragraph and gives five few-shot examples (Urdu, Roman Urdu, Punjabi, Pashto, English). Two additive edits:

1. In the opening sentence, add Sindhi and Balochi to the enumerated input languages.
2. Append two new few-shot examples (draft, flag for native review):

```
Input: "هي دڪاندار اڱڻ 200 رپيا ڪلو ۾ وڪڻي رهيو آهي، سرڪاري ريٽ 100 رپيا آهي."
Output: {
  "item_name": "Potato",
  "reported_price": 200,
  "category": "PERA - Overpricing",
  "urgency": "High",
  "detected_language": "Sindhi",
  "native_response": "توهان جي شڪايت درج ٿي وئي آهي. پرائس ڪنٽرول مئجسٽريٽ ڏانهن موڪلي وئي آهي. مهرباني."
}

Input: "اے دکاندار آلو ۲۰۰ روپیہ کیلو ءَ پہ دیگ انت، سرکاری ریٹ ۱۰۰ روپیہ انت."
Output: {
  "item_name": "Potato",
  "reported_price": 200,
  "category": "PERA - Overpricing",
  "urgency": "High",
  "detected_language": "Balochi",
  "native_response": "شمے شکایت درج بوت. پرائس کنٹرول مجسٹریٹ ءَ دیم دات بوت. منتوار."
}
```

**These few-shot examples are drafts for native review.** With a 1.5B model, few-shot examples strongly steer output, so getting the native text right matters for Sindhi/Balochi reply quality. Note the hybrid repair layer in `parse_complaint_text()` already respects the deterministic `detect_language()` result over the LLM's (`final_detected_lang = det_lang`), so even if the LLM mislabels, the rule engine's new Sindhi/Balochi detection governs the acknowledgment path.

---

## 3. Layer 2 — Frontend UI interface language (add pa, sd, bal, ps)

### 3.1 Shape of a `translations.js` language block

Read from the `en` block in `awaaz_pakistan/src/i18n/translations.js`. A complete language block is an object with these **13 top-level key groups**, each a flat object of string values:

| Group | Keys (count) | Notes |
|---|---|---|
| `nav` | 9 | brand, tagline, report, howItWorks, liveDashboard, officialRates, faq, reportNow, adminPortal |
| `hero` | 10 | includes `titleAwaaz`, `titleSub`, `subtitle` (lists spoken languages — update copy to mention all 6) |
| `ticker` | 2 | liveAlerts, vsOfficial |
| `howItWorks` | 8 | badge/title/subtitle + step1–3 title/desc |
| `features` | 12 | badge/title/subtitle + feat1–5 title/desc (feat1Desc lists dialects — update) |
| `report` | ~40 | tabs, record prompts, upload, location block, error strings |
| `verdict` | 19 | the price-violation result card labels |
| `stats` | 10 | includes `languagesSupported` label |
| `recent` | 11 | complaint table column headers |
| `rates` | 13 | official rate directory + category names |
| `faq` | 15 | badge/title/subtitle + q1–q6/a1–a6 (q1/a1 enumerate supported languages — update copy) |
| `footer` | 7 | CTA + footer links |
| `privacy` | 5 | privacy modal |
| `admin` | ~35 | admin portal (gate, map, filters, statuses, notes) |

(Count the exact `en` keys at implementation time; the structure above is the authoritative set of groups. The `ur` block already mirrors all of them, so `ur` is the template to copy for each new language.)

**Each new block (`pa`, `sd`, `bal`, `ps`) must contain every key** — otherwise, with the dot-path access pattern, any missing key throws at render (see §1 fact 1). The deep-merge fallback (§3.4) backstops this at runtime, but blocks should still be authored complete.

### 3.2 Per-language authoring + native-review policy (product-owner decision)

- Author full `pa`, `sd`, `bal`, `ps` blocks with **best-effort** translations.
- Mark every non-`en`/`ur` block with a clear native-review TODO at the top of the block, e.g.:
  ```js
  // ⚠️ NATIVE-REVIEW-REQUIRED (Punjabi/Shahmukhi): machine/best-effort draft.
  // Not verified by a native speaker. Review before production.
  pa: { /* ... */ },
  ```
  Use a greppable marker string `NATIVE-REVIEW-REQUIRED` so reviewers can find all four blocks.
- Do **not** overstate fidelity: Shahmukhi Punjabi, Sindhi, and Balochi (Arabic script) renderings are drafts. Balochi copy especially is lowest-confidence.

### 3.3 The switcher wiring (`awaaz_pakistan/src/components/ui/Navbar.jsx`)

Today the switcher is **two hardcoded buttons** (desktop, lines ~86–119) plus a **binary toggle** on mobile (lines ~121–126):
- Desktop: one `<button onClick={() => setLanguage('en')}>EN` and one `setLanguage('ur')>اردو`.
- Mobile: `onClick={() => setLanguage(language === 'en' ? 'ur' : 'en')}` showing the opposite label — a pure 2-way toggle.

**Required change:** replace both with a data-driven list of all six languages. Define a `LANGUAGES` array (ideally exported from the i18n module so it is the single source of truth):

```js
export const LANGUAGES = [
  { code: 'en',  label: 'EN',    native: 'English'  },
  { code: 'ur',  label: 'اردو',  native: 'اردو'     },
  { code: 'pa',  label: 'پنجابی', native: 'پنجابی'   },
  { code: 'sd',  label: 'سنڌي',  native: 'سنڌي'     },
  { code: 'bal', label: 'بلۏچی', native: 'بلۏچی'    }, // review glyphs
  { code: 'ps',  label: 'پښتو',  native: 'پښتو'     },
];
```
- Desktop switcher: map `LANGUAGES` to buttons (the existing pill styling applies per-item; six pills may need to collapse into a dropdown on narrow desktop widths — a `<select>` or a small popover is acceptable and simpler to keep accessible).
- Mobile switcher: the binary toggle must become a real selector (a native `<select>` is the lowest-risk, most accessible option on mobile).
- Keep `aria-label`s and the `cursor-pointer`/focus-ring treatment for accessibility.

### 3.4 RTL, font, and the English-fallback mechanism (`awaaz_pakistan/src/i18n/LanguageContext.jsx`)

Current provider:
```js
const isRtl = language === 'ur';
document.documentElement.setAttribute('dir', isRtl ? 'rtl' : 'ltr');
if (isRtl) document.body.classList.add('font-urdu'); else remove;
const t = translations[language] || translations.en;   // whole-block fallback only
// value: isRtl: language === 'ur'
```

Three changes:

1. **Multi-language RTL.** Replace the three `language === 'ur'` checks with set membership:
   ```js
   const RTL_LANGS = new Set(['ur', 'pa', 'sd', 'bal', 'ps']); // all Arabic-script
   const isRtl = RTL_LANGS.has(language);
   ```
   Apply `isRtl` to `dir`, to the `font-urdu` body class (the Nastaliq/Arabic-script font should apply to all five RTL languages, not just Urdu — see §3.5), and to the context `value`'s `isRtl` field (so every consumer of `useLanguage().isRtl` gets correct behaviour across all six).

2. **English-fallback (deep-merge), the critical fix.** The current `translations[language] || translations.en` only falls back when an *entire* block is absent; it does **not** fill a single missing key, so a partially-translated block would throw on access of the missing key. Implement a recursive deep-merge so the active `t` is always structurally complete:
   ```js
   function deepMergeFallback(base, override) {
     // base = translations.en (complete); override = translations[language]
     const out = Array.isArray(base) ? [...base] : { ...base };
     for (const k of Object.keys(base)) {
       const b = base[k], o = override?.[k];
       if (b && typeof b === 'object' && !Array.isArray(b)) {
         out[k] = deepMergeFallback(b, o ?? {});
       } else {
         out[k] = (o === undefined || o === null || o === '') ? b : o;
       }
     }
     return out;
   }
   // then:
   const t = useMemo(
     () => deepMergeFallback(translations.en, translations[language] || {}),
     [language]
   );
   ```
   Key-resolution order per leaf: **language block → English → (English always exists, so never blank)**. Because `en` is the complete base, every dot-path a component uses (`t.nav.report`, `t.verdict.title`, …) resolves to a string for all six languages, eliminating the `TypeError` risk entirely. This preserves the existing dot-access API, so **no component changes are required** for the fallback.

   Guard: `translations.en` must remain the complete superset of all keys. Any new key added anywhere must be added to `en` first.

3. **Persisted language validation.** `localStorage.getItem('awaaz_lang')` could hold a stale/invalid code; on init, validate against the known codes and default to `'en'` if unknown.

### 3.5 Font / CSS (`awaaz_pakistan/src/index.css`)

- `.font-urdu` (lines ~157–160) uses `'Noto Nastaliq Urdu', 'Gulzar', serif`. Nastaliq is appropriate for Urdu and Punjabi/Shahmukhi; Sindhi, Balochi, and Pashto are more commonly set in **Naskh**. Options (pick one, documented decision): **(chosen)** keep a single Arabic-script font stack applied to all five RTL languages for v1 simplicity, since Noto Nastaliq renders all these scripts legibly, and add a TODO to split Pashto/Sindhi into a Naskh stack (`'Noto Naskh Arabic'`) in a later pass. Rationale: a per-language font class is extra surface area and the product-owner policy is "full infrastructure now, polish later"; a single legible stack avoids missing-glyph boxes while native review is pending. If splitting later, gate it on `document.documentElement.lang` with `[lang="sd"], [lang="ps"], [lang="bal"] { font-family: 'Noto Naskh Arabic', ... }`.
- Verify the chosen web font(s) are actually loaded (check `index.css`/`index.html` for the font `@import`/`<link>`); if Noto Nastaliq is only pulled for Urdu today it already loads globally via the CSS var, so no new network dependency is required for v1.

### 3.6 `languagesCount` stat (`awaaz_pakistan/src/sections/LiveImpactStatsSection.jsx`)

Line ~50: `const languagesCount = 4; // Urdu, Punjabi, Pashto, English`. Update to `6` and fix the comment to list all six. The label `t.stats.languagesSupported` and the ` Dialects` suffix stay. Low-risk one-line edit.

---

## 4. faster-whisper language-hint consideration (reference only — another workflow owns transcription)

> This design only *specifies the contract*; it does not implement the transcription layer. The faster-whisper swap is mid-flight (confirmed in the working-tree `ai_pipeline.py` diff: `_import_whisper_model`, PyAV stub, `_load_wav_mono_float32`).

- **Language hint.** faster-whisper's `transcribe(..., language=<code>)` accepts an ISO-639-1 hint. When the citizen has chosen a UI language, passing a hint can improve accuracy for the weaker languages. Map UI codes → Whisper codes: `ur→ur`, `pa→pa`, `ps→ps`, `sd→sd`, `en→en`, **`bal→` (no reliable Whisper code — see below)**. Recommendation: pass the hint only when confidence in the mapping is high, and **otherwise keep Whisper's auto-detect** (the current path auto-detects and returns `result["language"]`). The UI language is a *hint*, not ground truth — a citizen may set UI to English but speak Urdu.
- **Balochi degradation path (must be specified, not implemented here):**
  1. Do **not** send a Balochi language hint (faster-whisper has no dependable Balochi model); let auto-detect run.
  2. If a citizen's UI language is Balochi, the **voice** path should surface a gentle notice that Balochi voice recognition is experimental and **recommend the text-input tab** (which already exists: `report.tabText`).
  3. For the **response**, if detected/selected language is Balochi but transcription confidence is low or empty, fall back to an **Urdu or English** acknowledgment rather than fabricating Balochi — consistent with the existing low-confidence `needs_review` handling in `parse_complaint_text()`.
  4. Never claim reliable Balochi transcription in UI copy. The `report.emptyAudio` / notice strings for `bal` should set this expectation.
- **Coordination note for the implementer:** these are requirements to hand to the transcription workflow (or to add as a thin mapping layer at the call site after it merges), not edits this language task makes to the transcription internals.

---

## 5. Ordered implementation checklist (coder-executable)

> **Sequencing gate:** Steps L1-* and L2-* must run **after** both the multi-item workflow and the faster-whisper workflow have merged to `polish/final`. Before starting, run `git status` and confirm `ai_pipeline.py`, `main.py`, `complaints.py`, `requirements.txt` are clean (committed), then re-read `ai_pipeline.py` and `nlp_rules.py` because line numbers in this doc will have shifted.

Backend (Layer 1):

- [ ] **L1-1. Add Sindhi + Balochi detection to `detect_language()`** in `awaaz_backend/services/nlp_rules.py` (Sindhi script markers + Sindhi/Balochi Roman marker lists, ordered per §2.1a). Self-contained, low collision with concurrent work.
      Files: `awaaz_backend/services/nlp_rules.py`
      Verify: `cd awaaz_backend && python -m pytest tests/test_nlp_rules.py -v` — existing `test_language_detection` still passes AND new Sindhi/Balochi assertions pass.

- [ ] **L1-2. Add Sindhi/Balochi number words** to `BASIC_NUMBER_WORDS` and the `compound_hundreds` list where they differ (§2.1b).
      Files: `awaaz_backend/services/nlp_rules.py`
      Verify: `python -m pytest tests/test_nlp_rules.py::test_punjabi_and_pashto_numbers -v` passes AND new Sindhi/Balochi number assertions pass.

- [ ] **L1-3. Add Sindhi + Balochi branches to `generate_native_acknowledgment()`** with the draft native strings from §2.1c, each marked for native review.
      Files: `awaaz_backend/services/nlp_rules.py`
      Verify: `python -m pytest tests/test_nlp_rules.py::test_native_acknowledgment -v` passes AND new assertions for `generate_native_acknowledgment("Sindhi")`/`("Balochi")` returning non-empty native-script strings pass.

- [ ] **L1-4. Widen `COMPLAINT_SCHEMA` `detected_language` description + add two few-shot examples** to `FEW_SHOT_SYSTEM_PROMPT` in `awaaz_backend/ai_pipeline.py` (§2.2). Re-read the file first; apply additively to whatever single/multi-item shape exists post-merge.
      Files: `awaaz_backend/ai_pipeline.py`
      Verify: `cd awaaz_backend && python -m pytest tests/ -v` — full backend suite green (confirms no import/JSON-shape regressions after the merge).

Frontend (Layer 2):

- [ ] **L2-1. Add the English-fallback deep-merge + multi-language RTL/font** in `awaaz_pakistan/src/i18n/LanguageContext.jsx` (§3.4) and export a `LANGUAGES` list + `RTL_LANGS` set from the i18n module. Do this FIRST so later partial blocks never crash the app.
      Files: `awaaz_pakistan/src/i18n/LanguageContext.jsx` (+ small export, e.g. `awaaz_pakistan/src/i18n/translations.js` or a new `languages.js`)
      Verify: `cd awaaz_pakistan && npm run build` succeeds; `npm run lint` (oxlint) clean. Manual: switch to a language with an empty block and confirm UI renders English, not a blank/crash.

- [ ] **L2-2. Author `pa`, `sd`, `bal`, `ps` blocks** in `awaaz_pakistan/src/i18n/translations.js`, each a full copy of the `en`/`ur` structure with best-effort translations and a `NATIVE-REVIEW-REQUIRED` marker comment (§3.1–3.2).
      Files: `awaaz_pakistan/src/i18n/translations.js`
      Verify: `npm run build` succeeds; `npm run lint` clean. `grep -c "NATIVE-REVIEW-REQUIRED"` returns 4.

- [ ] **L2-3. Rebuild the switcher** in `awaaz_pakistan/src/components/ui/Navbar.jsx` to render all six languages (desktop list/dropdown + mobile `<select>`), driven by the exported `LANGUAGES` list (§3.3).
      Files: `awaaz_pakistan/src/components/ui/Navbar.jsx`
      Verify: `npm run build` + `npm run lint` clean. Manual: all six options appear and `setLanguage` fires for each.

- [ ] **L2-4. Update `languagesCount` 4→6** in `awaaz_pakistan/src/sections/LiveImpactStatsSection.jsx` (§3.6); update hero/features/faq copy that enumerates languages (`hero.subtitle`, `features.feat1Desc`, `faq.q1/a1`) in the `en` and `ur` blocks to mention all six.
      Files: `awaaz_pakistan/src/sections/LiveImpactStatsSection.jsx`, `awaaz_pakistan/src/i18n/translations.js`
      Verify: `npm run build` + `npm run lint` clean. Manual: stat shows "6 Dialects".

- [ ] **L2-5. (Optional, coordinate) Balochi voice notice + Whisper language-hint mapping** at the transcription call site, per §4 — only after the faster-whisper workflow has merged and exposed a hint parameter.
      Files: TBD at the transcription call site (owned by the voice workflow)
      Verify: manual — selecting Balochi UI + voice tab shows the experimental notice and recommends text input; no false claim of Balochi transcription.

Final:

- [ ] **F-1. Full verification pass.** Backend: `cd awaaz_backend && python -m pytest tests/ -v`. Frontend: `cd awaaz_pakistan && npm run build && npm run lint`. Manual: switch through all 6 languages, confirming (a) UI text changes, (b) RTL layout flips for ur/pa/sd/bal/ps and stays LTR for en, (c) no blank keys, (d) no console `TypeError`.

---

## 6. Risks & caveats

- **Translation quality (high).** `pa`, `sd`, `bal`, `ps` UI blocks and the backend Sindhi/Balochi acknowledgment + few-shot strings are **best-effort drafts, not native-verified.** Every one is marked `NATIVE-REVIEW-REQUIRED` / "DRAFT — REQUIRES NATIVE REVIEW." The design deliberately does not claim fidelity. Balochi copy is the lowest confidence.
- **Balochi orthography + ASR (high).** Balochi has no single standard script (Arabic and Latin both used) and faster-whisper has weak/no Balochi coverage. The design mandates graceful degradation (text input + Urdu/English response) and no language hint for Balochi voice. Arabic-script Balochi also has no reliable unique code points, so Layer-1 script detection for Balochi is intentionally weak (Roman-marker only) and may misclassify as Urdu — accepted limitation.
- **RTL layout regressions (medium).** Flipping `dir=rtl` for four *new* languages exercises layout paths previously only hit by Urdu. The Navbar switcher, LocationPicker map controls, the verdict card, and the admin portal filters should be eyeballed in RTL. The deep-merge fallback does not affect layout, only text. Mitigate with the manual switch-through-all-6 check (F-1).
- **Merge-conflict risk with the two concurrent `ai_pipeline.py` edits (medium).** Both this task and the faster-whisper + multi-item tasks edit `ai_pipeline.py`. This task's edits are confined to **two string regions** (`COMPLAINT_SCHEMA.detected_language.description` and `FEW_SHOT_SYSTEM_PROMPT`) that neither concurrent task structurally owns, so textual conflicts are likely only on nearby lines, not semantic. **Mitigation:** sequence this task strictly *after* both merge (per §5 gate), re-read the file, and re-apply by locating the two symbols rather than by line number. The multi-item schema change could relocate `detected_language` into an array element — if so, keep it top-level or replicate the widened description wherever the language field lands. `nlp_rules.py` additions are self-contained (new dict entries, new detector branches, new ack branches) and collide with nothing in the concurrent work.
- **Switcher UX (low).** Six pills may overflow the current pill-bar on small desktops; a dropdown/`<select>` is recommended to keep it accessible and avoid layout breakage.
- **Font coverage (low).** A single Nastaliq stack for all five RTL languages may render Pashto/Sindhi less idiomatically than Naskh would; flagged as a later polish (§3.5), not a blocker.

---

## 7. Evidence index (files read)

- `README.md`, `awaaz_backend/README.md`, `awaaz_pakistan/README.md` — build/test commands, documented language scope (`npm run dev`/`build`/`lint` via oxlint; `python -m uvicorn main:app`; `python -m pytest`). No `AGENTS.md`/`CONTRIBUTING.md`/`.kiro/steering` present.
- `awaaz_backend/services/nlp_rules.py` — `detect_language`, `BASIC_NUMBER_WORDS`, `FRACTIONAL_PHRASES`, `URDU_INDIC_DIGITS`, `parse_word_numbers` compound-hundreds table, `generate_native_acknowledgment`.
- `awaaz_backend/ai_pipeline.py` — `COMPLAINT_SCHEMA.detected_language`, `FEW_SHOT_SYSTEM_PROMPT`, `parse_complaint_text` hybrid repair (confirms `final_detected_lang = det_lang`). Working-tree diff confirms the faster-whisper swap in progress.
- `awaaz_backend/tests/test_nlp_rules.py` — `test_language_detection`, `test_punjabi_and_pashto_numbers`, `test_native_acknowledgment` (the tests to extend).
- `awaaz_pakistan/src/i18n/translations.js` — only `en` + `ur`; 13 top-level key groups enumerated.
- `awaaz_pakistan/src/i18n/LanguageContext.jsx` — hardcoded `language === 'ur'` RTL/font; whole-block-only fallback.
- `awaaz_pakistan/src/components/ui/Navbar.jsx` — two-button desktop switcher + binary mobile toggle.
- Consumers confirming dot-path access: `Navbar.jsx`, `Footer.jsx`, `FaqSection.jsx`, `KeyFeaturesSection.jsx`, `HeroSection.jsx`, `LocationPicker.jsx`, `FinalCtaSection.jsx`, `LiveImpactStatsSection.jsx` (`languagesCount = 4`).
- `awaaz_pakistan/src/index.css` — `.font-urdu` stack and `--font-urdu` var.
- `awaaz_pakistan/package.json` — scripts: `dev`/`build`/`lint` (oxlint)/`preview`.
- `git status` — concurrent uncommitted edits on `ai_pipeline.py`, `main.py`, `requirements.txt`, `routers/complaints.py` (faster-whisper + multi-item workflows).

*Draft native-language strings (Sindhi/Balochi acknowledgments, few-shot examples, switcher glyphs, UI blocks) require native-speaker verification before production. This document specifies infrastructure and best-effort content; it does not certify translation fidelity.*
