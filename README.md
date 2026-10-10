# Awaaz Pakistan 🇵🇰 — آواز پاکستان

**A voice-first civic-tech platform that connects Pakistani citizens with public governance.**

Citizens record a civic issue in Urdu, English, or a regional language. Awaaz transcribes the audio, understands the intent, attaches a location, and shows governance insights on an interactive 3D dashboard.

> *آپ کی آواز، آپ کا حق* — Your voice, your right.

---

## Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Running the Project](#running-the-project)
- [API Overview](#api-overview)
- [AI Pipeline Details](#ai-pipeline-details)
- [GPS & Geolocation](#gps--geolocation)
- [Design System](#design-system)
- [Testing & Evaluation](#testing--evaluation)
- [Security & Privacy](#security--privacy)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Voice-first complaint submission** — record directly in the browser, no typing needed.
- **Multilingual speech-to-text** — Urdu, English, and code-mixed / Roman Urdu speech via Whisper.
- **Intent extraction** — category, urgency, location mentions, and a bilingual summary via a local LLM (Qwen 2.5 through Ollama), backed by a custom rule engine.
- **Hybrid NLP** — high-precision rules for emergencies and keywords, LLM for ambiguous cases, with a safe fallback if the LLM is unavailable.
- **GPS tagging** — browser geolocation with accuracy reporting, plus manual pin and region-selection fallbacks.
- **3D governance dashboard** — interactive globe and civic nodes showing complaint clusters by region and category.
- **Admin controls** — status updates, filtering, review of low-confidence results, and analytics.
- **JWT authentication** with citizen and admin roles.
- **Glassmorphism UI** — emerald-accented, responsive, accessible, with RTL support for Urdu.

---

## How It Works

```
Browser (MediaRecorder + Geolocation)
        │  multipart upload: audio + coordinates
        ▼
FastAPI backend
        │
        ├─► Audio preprocessing (ffmpeg: 16 kHz mono, normalize, trim silence)
        ├─► Whisper speech-to-text (language detection + confidence signals)
        ├─► Rule engine (nlp_rules.py) ─┐
        ├─► Qwen 2.5 via Ollama ────────┤ reconcile → structured JSON
        ├─► Location validation / reverse geocoding
        ▼
SQLite / SQLAlchemy (awaaz.db)
        │
        ▼
React dashboard (3D globe, charts, admin panel)
```

1. The citizen records audio and allows location access.
2. The backend transcribes the speech and detects the language.
3. The NLP pipeline extracts category, urgency, location text, and a summary.
4. Low-confidence results are flagged for human review instead of being trusted blindly.
5. The complaint is stored and appears on the dashboard.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, Tailwind CSS |
| 3D / Visuals | Three.js, React Three Fiber |
| Audio capture | Browser MediaRecorder API |
| Backend | Python, FastAPI, Pydantic |
| Database | SQLite via SQLAlchemy (PostgreSQL migration path planned) |
| Speech-to-text | OpenAI Whisper |
| NLP / LLM | Qwen 2.5 1.5B via local Ollama + custom rules |
| Auth | JWT |

---

## Project Structure

```
HacktoberFest_Project-Awaaz_Pakistan/
├── awaaz_backend/            # All backend code, venv, and database
│   ├── main.py               # FastAPI entry point
│   ├── auth.py               # JWT authentication
│   ├── admin.py              # Admin / governance controls
│   ├── ai_pipeline.py        # Whisper → NLP orchestration
│   ├── nlp_rules.py          # Rule-based intent engine
│   ├── scripts/              # e.g. seed_demo_data.py
│   ├── bench/                # Benchmarks and audio fixtures
│   ├── eval/                 # Evaluation harness (accuracy metrics)
│   ├── requirements.txt
│   └── awaaz.db              # SQLite database (not committed)
│
├── awaaz_pakistan/           # All frontend code
│   ├── src/                  # Components, pages, hooks, 3D scenes
│   ├── ui-baseline/          # UI screenshots used to detect visual regressions
│   ├── package.json
│   └── vite.config.js
│
└── README.md
```

Backend and frontend code stay strictly inside their own folders.

---

## Getting Started

### Prerequisites

- **Python** 3.10+
- **Node.js** 18+ and npm
- **ffmpeg** available on your PATH
- **Ollama** with the Qwen model: `ollama pull qwen2.5:1.5b`
- A browser with microphone and location support (Chrome, Edge, Firefox, Safari)

### 1. Clone

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

### 2. Backend setup

```bash
cd awaaz_backend
python -m venv venv

# Windows
.\venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

python -m pip install -r requirements.txt
python scripts/seed_demo_data.py     # optional demo data
```

### 3. Frontend setup

```bash
cd ../awaaz_pakistan
npm install
```

---

## Configuration

Copy the example environment file and adjust it. Never commit real secrets.

```bash
cp .env.example .env
```

Typical settings (names may differ slightly; check `.env.example`):

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing key (use a long random value) |
| `DATABASE_URL` | Database connection string |
| `OLLAMA_URL` | Ollama server address (default `http://localhost:11434`) |
| `OLLAMA_MODEL` | LLM name, e.g. `qwen2.5:1.5b` |
| `WHISPER_MODEL` | Whisper size, e.g. `small` |
| `ALLOWED_ORIGINS` | CORS origins for the frontend |
| `MAX_AUDIO_SECONDS` | Maximum accepted recording length |
| `VITE_API_URL` | Backend URL used by the frontend |

---

## Running the Project

Use two terminals.

**Terminal 1: Ollama**

```bash
ollama serve
```

**Terminal 2: Backend** (from `awaaz_backend/`, venv activated)

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 3: Frontend** (from `awaaz_pakistan/`)

```bash
npm run dev
```

- Frontend: http://localhost:5173
- API docs (Swagger): http://localhost:8000/docs

---

## API Overview

Interactive documentation is available at `/docs` once the backend is running. The main areas are:

| Area | Purpose |
|---|---|
| Auth | Register, log in, refresh tokens |
| Complaints | Submit voice complaints, list, filter, and view details |
| Admin | Update status, review flagged complaints, view analytics |
| Dashboard | Aggregated, region-level data for the 3D view |

Voice submissions are sent as `multipart/form-data` containing the audio file and optional location fields.

---

## AI Pipeline Details

### Speech-to-text
- Whisper with audio preprocessing (16 kHz mono, normalization, silence trimming).
- Language auto-detection with an optional user hint.
- Civic vocabulary prompting (roads, sewage, electricity, water supply, load shedding, WASA, WAPDA, SNGPL, LESCO, and similar terms).
- Confidence signals are stored. Low-confidence transcripts are flagged for review.

### Intent extraction
The pipeline returns structured output:

```json
{
  "category": "water_supply",
  "sub_category": "...",
  "urgency": "high",
  "language": "ur",
  "summary_en": "...",
  "summary_ur": "...",
  "location_text": "...",
  "entities": [],
  "confidence": 0.0
}
```

- Rules handle emergencies and high-precision patterns first.
- The LLM handles ambiguous cases using schema-constrained output with retries.
- If the LLM output is invalid or Ollama is down, the rule engine produces the result.

### Known limitations
- Whisper accuracy for regional languages (Punjabi, Sindhi, Pashto, Balochi) is weaker than for Urdu and English.
- A 1.5B-parameter LLM can be unreliable on complex or noisy text, which is why validation, retries, and rule fallbacks exist.

---

## GPS & Geolocation

- Browser Geolocation API with high-accuracy mode, timeout, and clear permission states.
- Captures latitude, longitude, accuracy, and timestamp.
- Warns the user when accuracy is poor.
- Fallbacks: manual map pin, or province / district / city selection.
- Backend validates coordinates against Pakistan's bounds and rejects impossible values.
- Spoken location and GPS location are stored separately and flagged when they conflict.
- Public views can coarsen coordinates, while admins see precise values.

---

## Design System

| Token | Value |
|---|---|
| Primary emerald | `#006633` |
| Deep emerald | `#004D25` |
| Text | White on dark backgrounds |
| Glass panels | `backdrop-blur-md bg-white/10 border border-white/20` |

Design principles: voice-first flow, mobile-first layout, RTL support with the Noto Nastaliq Urdu font, keyboard-accessible controls, and reduced-motion support for 3D animations. Visual changes are checked against the screenshots in `awaaz_pakistan/ui-baseline/`.

---

## Testing & Evaluation

```bash
# Backend tests
cd awaaz_backend
python -m pytest

# Frontend tests
cd awaaz_pakistan
npm test
```

The `eval/` harness measures speech and NLP quality, including word error rate, per-category precision / recall / F1, urgency accuracy, JSON validity rate, and fallback rate. Synthetic test samples are labeled as synthetic. Real Urdu recordings placed in `awaaz_backend/bench/fixtures/` give more meaningful accuracy numbers.

---

## Security & Privacy

- JWT authentication with role-based access (citizen / admin).
- Explicit CORS origins, input validation, and upload type checks by content.
- Transcripts and model output are sanitized before storage and display.
- Voice recordings are sensitive: consent messaging, configurable retention, and an admin audit log are part of the design.
- Do not commit `.env`, `awaaz.db`, `venv/`, `node_modules/`, or audio files.

---

## Troubleshooting

**`pip.exe` / `uvicorn.exe` blocked by an Application Control policy (Windows)**
Run the tools through Python instead:
```bash
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

**`npm error enoent` (package.json not found)**
Run npm commands inside `awaaz_pakistan/`, not `awaaz_backend/`.

**LLM results missing or falling back to rules**
Make sure Ollama is running (`ollama serve`) and the model is pulled (`ollama pull qwen2.5:1.5b`).

**Microphone or location not working**
Allow permissions in the browser. Microphone access requires `localhost` or HTTPS.

---

## Roadmap

- [x] Voice recording and upload flow
- [x] Whisper + Qwen + rule-engine pipeline
- [x] JWT auth and admin controls
- [x] 3D dashboard
- [ ] Faster-whisper and audio preprocessing improvements
- [ ] Async job queue for AI processing
- [ ] Evaluation harness with labeled Urdu data
- [ ] Offline reverse geocoding with Pakistan boundaries
- [ ] PostgreSQL migration and Docker setup
- [ ] Offline submission queue for low-connectivity areas
- [ ] 2D fallback for low-end devices

---

## Contributing

Contributions are welcome, including during Hacktoberfest.

1. Fork the repository.
2. Create a branch: `git checkout -b feature/your-feature`.
3. Keep backend changes in `awaaz_backend/` and frontend changes in `awaaz_pakistan/`.
4. Do not change the visual identity without discussion.
5. Add or update tests where it makes sense.
6. Open a pull request describing what changed and why.

---

## License

Add your chosen license here (for example MIT) and include a `LICENSE` file.

---

## Acknowledgements

Built with FastAPI, React, Three.js, OpenAI Whisper, and Ollama (Qwen 2.5).

**Team / Contact:** add your name, links, and contact details here.
