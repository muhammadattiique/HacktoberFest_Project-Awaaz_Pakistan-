# Awaaz Pakistan – Voice Governance & Price Intelligence

A citizen voice-governance platform where citizens report commodity price gouging simply by speaking in Urdu, Punjabi, Pashto, or English. Designed with the dark, 3D, motion-rich visual language of the **VoxAI** design system (https://voxai.framer.ai/).

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Node.js 18+ (tested on Node 20 / 22 / 26)
- Python 3.10+ with `virtualenv`

### 2. Backend Setup & Run
From the project root:
```bash
# Activate the backend virtual environment
.\awaaz_backend\venv\Scripts\activate

# Start the FastAPI backend from the actual backend folder
cd awaaz_backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
The backend API is now live at `http://localhost:8000` (`docs at http://localhost:8000/docs`).

### 3. Frontend Setup & Run
From the actual frontend folder:
```bash
cd awaaz_pakistan
npm install --legacy-peer-deps
npm run dev
```
The application will launch on `http://localhost:5173`.

---

## 🎭 3D Avatar Customization

A real-time 3D AI avatar is rendered using `@react-three/fiber`. It tracks mouse/touch movement, leans in when listening, orbits particle halos when thinking, and animates mouth aperture from live audio via the Web Audio `AnalyserNode`.

### How to Swap in Your Custom Avatar Model:
1. Export your 3D model as a `.glb` or `.vrm` file with facial blendshapes.
2. Rename the file to:
   ```
   awaaz.glb
   ```
3. Place it inside the public avatar directory:
   ```
   awaaz_pakistan/public/avatar/awaaz.glb
   ```
4. Refresh your browser. `AvatarCanvas` automatically checks for this file and mounts it; if omitted, the stylized cybernetic procedural hologram is rendered.
5. Users on low-end devices or with `prefers-reduced-motion` can toggle **2D Lite Mode** with the button in the avatar corner.

---

## 🗺️ GPS Location Capture (Citizen Side)

- **Purpose**: The pin records the exact vendor location where overcharging took place, never the citizen's residence.
- **Privacy Gate**: Unchecked "I agree to attach the incident location" checkbox gates all geolocation actions.
- **Accuracy**: Uses `navigator.geolocation.getCurrentPosition` (high accuracy, 10s timeout). If accuracy is low (>100m) or user needs adjustments, the red pin is freely draggable on the dark CartoDB Leaflet map.
- **Fallback**: Citizens can choose an Islamabad/Rawalpindi market area from the dropdown or skip location entirely. Coordinates are **never** transmitted without consent.

---

## 🛡️ Admin Command Portal (`/admin`)

The Administrative Map Portal is isolated from the public single-page site (no public navbar/footer link).

### Access Gate & API Key:
1. Navigate directly to `http://localhost:5173/admin`.
2. Enter the administrative API key:
   - **Default Demo Key**: `awaaz-admin-2024`
   - Key is stored in transient `sessionStorage` and transmitted via the `X-API-Key` HTTP header.
3. Every located complaint is plotted as a **RED DOT** (`#E5484D`) at its exact GPS coordinate with soft ambient glow and pulse animation for high-urgency reports.
4. Approximate area reports appear as hollow red dashed rings; unlocated complaints are queued in the side panel.
5. **Live Polling**: Background refresh polls every 10 seconds and animates new complaints without resetting user zoom or pan.
6. **Detail Drawer**: Click any red dot to view full transcript, price comparison, vendor repeat offender history, mini map, and Google Maps direct dispatch link. Change resolution status or add magistrate notes with instant optimistic map updates.

---

## 📋 Backend Integration (Implemented)

The FastAPI backend in `./awaaz_backend` implements full administrative parity:

1. **`GET /api/complaints` with Query Filters**
   - Supported parameters: `bbox` (spatial bounding box), `authority`, `date_from`, `date_to`, `shop`, plus `category`, `urgency`, `status`, `needs_review`, `location_area`, and `search`.
2. **`PATCH /api/admin/complaints/{id}` Authority Assignment**
   - Send `assigned_authority` alongside `status` and `admin_notes`; the portal's "Assign Authority" dropdown persists through this field.
3. **`GET /api/admin/shops/{shop_name}`**
   - Returns total citations, historical overcharge average, peak overcharge, estimated excess charged, and repeat-offender flags.
4. **`GET /api/admin/export`**
   - Server-side CSV generation with an Excel-safe UTF-8 BOM. The portal prefers this endpoint and transparently falls back to the client-side generator when offline.
5. **`GET /api/map/points`**
   - Coarse/obfuscated public spatial points (rounded to 3 decimal places) for public macro heatmaps while preserving vendor/citizen privacy.

### 🔐 Administrative API Key (enforced server-side)
The admin gate is backed by a real credential check, not just a hidden URL. The
portal transmits the key in the `X-API-Key` header; the backend validates it with
a constant-time comparison:

- Missing key → `401 Unauthorized`
- Wrong key → `403 Forbidden`
- **Default demo key:** `awaaz-admin-2024`
- Override in production with the `AWAAZ_ADMIN_API_KEY` environment variable.

`GET /api/admin/health` is intentionally public so container health probes and the
citizen status badge keep working without credentials.
