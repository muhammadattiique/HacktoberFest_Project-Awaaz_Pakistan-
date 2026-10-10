# UI Baseline Screenshot Index

Captured before Phase 0 measurements with Playwright 1.49.1 using installed Microsoft Edge 155.0.4283.45 in headless mode. Viewports are 390×844, 768×1024, and 1440×900. Each capture waits for network idle (when reachable) and then a fixed 1.5-second settling delay. The backend was started with `DATABASE_URL` pointing to a temporary SQLite database seeded by `awaaz_backend/scripts/seed_demo_data.py`; the repository database was not used or modified.

## Routes and states

Each row represents three files, suffixed `_390.png`, `_768.png`, and `_1440.png`.

| Files | Route/state | How the state was produced |
|---|---|---|
| `home_{width}.png` | `/` — home | Loaded the root route, waited for network idle plus 1.5 seconds, and captured the full page. |
| `recording_{width}.png` | `/` — recording | Scrolled `#report` into view, supplied Playwright-injected `getUserMedia`, `MediaRecorder`, and `AudioContext` fakes, clicked the accessible “Start Recording Voice Complaint” button, then captured the recording state. No app code was changed. |
| `uploading_{width}.png` | `/` — uploading/processing | Selected the report form’s text tab, entered a fixed civic complaint, intercepted `POST /api/complaints/text`, delayed its successful response by five seconds, submitted, and captured while the processing control was visible. |
| `success_{width}.png` | `/` — success | Allowed the delayed intercepted submission to return a deterministic successful overpricing complaint (`baseline-success-001`), then captured the resulting verdict card. |
| `error_{width}.png` | `/` — error | Replaced the text-submission intercept with HTTP 422, submitted fixed text, and captured the rendered validation-error state. HTTP 422 was used because server/network failures intentionally activate the app’s demo-success fallback. |
| `admin_{width}.png` | `/admin` — admin | Seeded `sessionStorage.awaaz_admin_key` with the documented demo key before navigation, loaded `/admin`, and captured the authorized administrative portal. Data comes from the temporary seeded backend when available and the app’s built-in demo fallback otherwise. |
| `dashboard_{width}.png` | `/admin` — dashboard | Captured the same authorized admin route after a separate settle interval as the project’s current dashboard view; the app has no separate public `/dashboard` route. |
| `not-found_{width}.png` | wildcard route | Loaded `/baseline-not-a-route`, exercising the router’s `*` route and `NotFound` page. |

## Complete file list

- `home_390.png`, `home_768.png`, `home_1440.png`
- `recording_390.png`, `recording_768.png`, `recording_1440.png`
- `uploading_390.png`, `uploading_768.png`, `uploading_1440.png`
- `success_390.png`, `success_768.png`, `success_1440.png`
- `error_390.png`, `error_768.png`, `error_1440.png`
- `admin_390.png`, `admin_768.png`, `admin_1440.png`
- `dashboard_390.png`, `dashboard_768.png`, `dashboard_1440.png`
- `not-found_390.png`, `not-found_768.png`, `not-found_1440.png`

## Reproduction

Install Playwright ephemerally outside the project, start the frontend and backend, and run:

```powershell
$env:PLAYWRIGHT_MODULE = "$env:TEMP\awaaz_pw\node_modules\playwright"
$env:AWAAZ_BASE_URL = "http://127.0.0.1:5173"
node .\ui-baseline\scripts\capture.mjs
```

The script defaults to installed Edge at `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`; override `EDGE_PATH` if needed. It does not require Playwright in project dependencies.

## Variance and omissions

No requested route or key state was omitted. The WebGL/Three.js canvas can differ frame-to-frame because animation timing, GPU rendering, and particle placement are not pixel-deterministic. The fixed delay and reduced-motion browser context reduce, but cannot eliminate, this variance.
