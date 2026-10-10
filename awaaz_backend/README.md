# 🇵🇰 Awaaz Pakistan (Voice of Pakistan)
### AI-Powered Voice Governance & Anti-Price-Gouging Platform for Pakistani Citizens

A complete, production-quality, demo-ready FastAPI backend designed specifically for citizens in **Islamabad and Rawalpindi (the Twin Cities)** to report price gouging, food safety hazards, and municipal breakdown in their native spoken tongue.

Built for hackathons and public administration governance, **Awaaz Pakistan** eliminates literacy and language barriers by accepting voice notes in **Urdu (Urdu script), Roman Urdu, Punjabi, Pashto, and English**, processing everything **100% locally with zero cloud dependencies**.

---

## 🏛️ Local Context & Twin Cities Reality

In Islamabad and Rawalpindi, citizens frequently suffer from artificial inflation and price gouging on kitchen staples (**Aloo, Pyaaz, Tamatar, Chini, Atta, Doodh, Roti/Naan, Chicken, Anday, Cooking Oil, Daal, Chawal**), especially during Ramzan, market strikes, and floods.

While district administrations (**ICT Islamabad Administration** and **Rawalpindi District Administration / Price Control Committees**) notify official ceiling rates daily, enforcement is hampered because citizens cannot easily navigate bureaucratic portals or type in formal English/Urdu.

### Institutional Governance Routing
Awaaz Pakistan automatically routes grievances to the legally mandated enforcement bodies:
1. **PERA (Punjab Enforcement & Regulatory Authority) / ICT Price Magistrates**
   - Regulates overpricing, hoarding, and missing rate lists under the *Price Control and Prevention of Profiteering and Hoarding Act 1977* and *Punjab Price Control Act 2024*.
   - Helpline placeholder: `1717` / `051-9108194` *(VERIFY BEFORE PRODUCTION)*
2. **PFA (Punjab Food Authority)**
   - Investigates adulterated milk (chemical/water), unhygienic bakeries, stale meat, insect-infested pulses, and food poisoning outbreaks.
   - Helpline placeholder: `1223` *(VERIFY BEFORE PRODUCTION)*
3. **Municipal Bodies (CDA/MCI in Islamabad & RWMC/WASA in Rawalpindi)**
   - Resolves overflowing open gutters, contaminated water supply pipes, dark street lights, and uncollected garbage heaps.
   - Helpline placeholder: `1819` / `1334` *(VERIFY BEFORE PRODUCTION)*

---

## 🧠 System Architecture: Hybrid AI Engine

Small 1.5B language models running on consumer hardware are notoriously brittle when handling Pakistani multilingual code-switching and numerical units (e.g. *"dedh sau"*, *"dhai sau"*, *"100 rupay ka aadha kilo"*, *"seer"*). 

Awaaz Pakistan solves this with an industrial **Hybrid AI Architecture**:

```
                       [ Citizen Audio Voice Note ]
                                    │
                                    ▼
                     [ services/audio.py: FFmpeg ]
             (16kHz mono WAV conversion, silence/duration check)
                                    │
                                    ▼
                  [ ai_pipeline.py: OpenAI Whisper ]
            (Pakistani vocabulary biased initial_prompt)
                                    │
                        [ Transcript Text ]
                                    │
         ┌──────────────────────────┴──────────────────────────┐
         ▼                                                     ▼
[ Local Ollama LLM ]                                 [ Deterministic Rule Engine ]
(qwen2.5:1.5b-instruct)                               (services/nlp_rules.py)
 • Structured JSON Schema                             • Eastern Arabic digits (۰-۹ -> 0-9)
 • Few-shot in Urdu, Roman Urdu,                      • Urdu/Punjabi number words
   Punjabi, Pashto, English                           • Fractional units (pao, seer, mann)
         │                                            • Total bill -> unit price
         └──────────────────────────┬──────────────────────────┘
                                    ▼
                         [ Hybrid Repair Layer ]
                • Rules validate & repair LLM extractions
                • Deterministic override on food safety & infra
                • Reconciles commodity against official rate-list.json
                • Generates reassuring response in citizen's exact dialect
                                    │
                                    ▼
                 [ SQLite Database & Enforcement API ]
                 • Overcharge % & severity tiering
                 • Hotspots & Repeat-Offender Analytics
```

---

## 📂 Project Structure

```
awaaz_backend/
├── main.py                   # FastAPI app factory, CORS (*), routers, exception handlers
├── config.py                 # Pydantic BaseSettings, helplines, model parameters
├── auth.py                   # Administrative X-API-Key verification (401/403)
├── timeutils.py              # Timezone-safe naive-UTC timestamp helpers
├── ai_pipeline.py            # Whisper singleton + Ollama 1.5B client + hybrid repair
├── rate-list.json            # Official notified rate database (32 items with rich aliases)
├── schemas.py                # Pydantic v2 schemas for requests, responses, and KPIs
├── requirements.txt          # Python dependency specifications
├── Dockerfile                # Production container with system FFmpeg
├── .dockerignore             # Keeps venv/pycache/db out of the build context
├── docker-compose.yml        # Multi-service stack (Ollama + Backend)
├── db/
│   ├── models.py             # SQLAlchemy 2.x Complaint model
│   └── session.py            # Async SQLite session engine
├── services/
│   ├── rates.py              # Rate list loader, alias resolution, fuzzy matching
│   ├── nlp_rules.py          # Urdu digits, number idioms, unit conversions, language detection
│   ├── audio.py              # FFmpeg conversion, duration validation, silence detection
│   └── analytics.py          # Hotspots, repeat offenders, trends, KPIs
├── routers/
│   ├── complaints.py         # Voice/text submission, filters (bbox/date/shop/authority), status
│   ├── rates.py              # Rate list view, dynamic reload, instant price check
│   ├── analytics.py          # Governance analytics, hotspots, public obfuscated map points
│   └── admin.py              # Health, safe config, shop dossier, CSV export, demo reseed
├── scripts/
│   └── seed_demo_data.py     # 45+ realistic Twin Cities demo grievances spanning 14 days
└── tests/
    ├── test_rates.py         # Rate list loading, aliases, and price comparison tests
    ├── test_nlp_rules.py     # Digits, Pakistani fractional idioms, languages, units
    ├── test_audio.py         # Audio duration, conversion, silence rejection
    ├── test_pipeline.py      # Whisper/Ollama hybrid pipeline and fallback tests
    └── test_api.py           # End-to-end FastAPI integration tests
```

---

## ⚡ Quickstart Guide

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.14)
- [Ollama](https://ollama.com/) running locally with `qwen2.5:1.5b-instruct`:
  ```bash
  ollama run qwen2.5:1.5b-instruct
  ```
- FFmpeg (automatically detected in environment or venv).

### 2. Virtual Environment & Dependencies
```bash
cd awaaz_backend
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Seed Realistic Demo Data
Populate 45+ realistic complaints across Raja Bazaar, G-9 Markaz, Commercial Market, Aabpara, and Saddar:
```bash
python scripts/seed_demo_data.py
```

### 4. Run the Backend Server
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive Swagger API docs available at: **http://localhost:8000/docs**

### 5. Run the Comprehensive Test Suite
```bash
pytest tests/ -v
```

### 6. Administrative API Key (Important)
Citizen-facing endpoints (`/api/complaints/*`, `/api/rates/*`, `/api/analytics/*`) are
public. Everything that reads enforcement data or mutates a case requires the
shared administrative secret, sent by the React portal in the **`X-API-Key`** header:

```bash
# Missing key   -> 401 Unauthorized
# Wrong key     -> 403 Forbidden
curl -H "X-API-Key: awaaz-admin-2024" http://localhost:8000/api/admin/config
```

Configure it via the environment (a hidden URL is **not** access control):

| Variable | Purpose |
| --- | --- |
| `AWAAZ_ADMIN_API_KEY` | Preferred name for the admin shared secret |
| `ADMIN_API_KEY` | Accepted alias |

Set it to an empty string only if you deliberately want to disable admin auth
(e.g. an isolated local demo). `GET /api/admin/health` is intentionally public so
Docker `HEALTHCHECK` and the citizen status badge keep working without credentials.

**Protected routes:** `PATCH /api/complaints/{id}`, `GET /api/admin/config`,
`GET /api/admin/export`, `POST /api/admin/reseed`, `GET /api/admin/shops/{shop_name}`.

---

## 🐳 Docker Deployment

Run the complete local stack (Backend + Ollama) in Docker:
```bash
docker compose up -d --build
```
The backend will automatically connect to Ollama over the internal Docker network.

---

## 📡 API Reference & Demo Examples

### 1. Voice Complaint Submission
`POST /api/complaints/voice` (multipart/form-data)
- **audio**: Audio file (`.wav`, `.m4a`, `.mp3`, `.ogg`, `.webm`)
- **location_area**: *"Raja Bazaar, Rawalpindi"* (optional)
- **shop_name**: *"Madina Cash & Carry"* (optional)

### 2. Instant Text Complaint Submission
`POST /api/complaints/text`
```json
{
  "transcript_text": "آلو مارکیٹ میں دو سو روپے کلو بیچ رہے ہیں جبکہ سرکاری لسٹ میں سو روپے ہے۔",
  "location_area": "Raja Bazaar, Rawalpindi",
  "shop_name": "Madina Cash & Carry"
}
```
**Response (201 Created):**
```json
{
  "id": "7b82f0c1-321a-4de1-9f20-6d4b29381c19",
  "created_at": "2026-10-09T19:40:00",
  "transcript_raw": "آلو مارکیٹ میں دو سو روپے کلو بیچ رہے ہیں جبکہ سرکاری لسٹ میں سو روپے ہے۔",
  "detected_language": "Urdu",
  "category": "PERA - Overpricing",
  "urgency": "High",
  "status": "Pending",
  "item_name": "Potato",
  "item_canonical_id": "aloo",
  "unit": "kg",
  "reported_price": 200.0,
  "official_price": 100.0,
  "price_difference_pkr": 100.0,
  "percentage_overcharge": 100.0,
  "native_response": "آپ کی شکایت موصول ہو چکی ہے۔ پرائس کنٹرول مجسٹریٹ کو کارروائی کے لیے مطلع کر دیا گیا ہے۔ شکریہ۔",
  "routing_agency": "Punjab Enforcement & Regulatory Authority (PERA) / ICT Administration",
  "helpline_reference": "1717",
  "location_area": "Raja Bazaar, Rawalpindi",
  "shop_name": "Madina Cash & Carry"
}
```

### 3. Check Price Without Filing Complaint
`POST /api/rates/check`
```json
{
  "query": "Aloo 180 rupay"
}
```
**Response:**
```json
{
  "item_canonical_id": "aloo",
  "item_name": "Potato",
  "unit": "kg",
  "official_price": 100.0,
  "reported_price": 180.0,
  "price_difference_pkr": 80.0,
  "percentage_overcharge": 80.0,
  "is_overpriced": true,
  "severity": "High",
  "recommended_action": "Schedule price monitoring inspection under Punjab Enforcement & Regulatory Authority (PERA) / ICT Administration.",
  "legal_statute_note": "Price Control and Prevention of Profiteering and Hoarding Act 1977 (ICT) / Punjab Price Control of Essential Commodities Act 2024"
}
```

### 4. Governance Analytics KPIs
`GET /api/analytics/overview`
Returns:
- Total citizen complaints
- Category distribution (Overpricing vs Food Safety vs Infrastructure)
- Average overcharge percentage across all markets
- Top 5 price-gouged commodities with price ceilings

### 5. Geographic Violation Hotspots
`GET /api/analytics/hotspots`
Returns Twin Cities hotspots (Raja Bazaar, G-9 Markaz, Commercial Market, Aabpara, Saddar) with latitude/longitude coordinates and dominant violation types for map rendering.

### 6. Repeat Offender Tracking
`GET /api/analytics/repeat-offenders`
Identifies persistent violators with 2+ complaints across multiple visits for target magistrate raids.

### 7. System Health Check
`GET /api/admin/health`
Checks Whisper model status, Ollama LLM availability, official rate items count, and database connectivity.
Public by design so container health probes work without credentials.

### 8. Filtered Incident Queries *(admin)*
`GET /api/complaints`
Accepts `category`, `urgency`, `status`, `needs_review`, `location_area`, `search`,
plus `shop`, `authority`, `date_from`, `date_to`, and a spatial `bbox`
(`min_lat,min_lng,max_lat,max_lng`). Invalid dates or bounding boxes return `422`
with an explanatory message rather than a generic server error.

```bash
curl "http://localhost:8000/api/complaints?bbox=33.6,73.0,33.7,73.1&date_from=2024-01-01"
```

### 9. Vendor Enforcement Dossier *(admin)*
`GET /api/admin/shops/{shop_name}`
Returns total/open/resolved citations, historical average and peak overcharge,
estimated excess charged, gouged commodities, a repeat-offender flag, and a
recommended enforcement action. Requires the `X-API-Key` header.

### 10. Server-Side CSV Export *(admin)*
`GET /api/admin/export?category=&status=`
Streams a UTF-8 CSV (with BOM so Excel renders Urdu correctly) and sets an
`X-Record-Count` header. Requires the `X-API-Key` header.

### 11. Public Obfuscated Map Points
`GET /api/analytics/map/points`
Returns coarse spatial points for public macro heatmaps. Coordinates are rounded
to 3 decimal places (~110 m grid) and vendor names/transcripts are never included,
so citizen and vendor privacy is preserved while still showing violation density.

---

## 🛡️ Hackathon Demo Walkthrough

1. **Start the API**: Run `uvicorn main:app --reload`.
2. **Verify System Health**: Open `http://localhost:8000/api/admin/health` to confirm Whisper and Ollama are green.
3. **Show Official Rates**: Navigate to `GET /api/rates` to display 32 notified essentials with Urdu script, units, and categories.
4. **Demonstrate Dialect Ingestion**:
   - Send Urdu script: *"آلو دو سو روپے کلو"* -> Returns 100% price gouging alert in Urdu.
   - Send Roman Urdu: *"Raja Bazaar Madina store doodh 280 rupay de raha hai"* -> Resolves fresh milk at 280 PKR (official 210 PKR).
   - Send Punjabi: *"تہاڈے ریٹ لسٹ وچ دہی دا ریٹ دو سو تریہہ اے، اے کمرشل مارکیٹ آلا تن سو روپے منگ رہیا اے۔"* -> Correctly extracts yogurt at 300 PKR and responds in Punjabi.
   - Send Food Safety: *"Kharab chicken ka salan khila rahe hain bache bimar hain"* -> Instantly routes to **Punjab Food Authority (1223)** with High Urgency.
5. **Show Live Executive Dashboard**:
   - `GET /api/analytics/overview`
   - `GET /api/analytics/hotspots`
   - `GET /api/analytics/repeat-offenders`
   - `GET /api/analytics/trends`

---

## ⚖️ Legal & Production Notice
Official helpline numbers and legal fine brackets contained in `config.py` are demonstrative placeholders for hackathon evaluation. Prior to official deployment with the Government of Pakistan or Provincial Administrations, all statutory references must be formally validated with the competent authorities.

