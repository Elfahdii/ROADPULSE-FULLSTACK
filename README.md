# RoadPulse Full-Stack Dashboard v2.1

React/Vite + FastAPI RoadPulse MVP for road-damage detection, automatic GPS road identification, roughness estimation and Road Health scoring.

My project is called RoadPulse. The problem I wanted to address is that inspecting roads manually takes time, and defects can be missed or recorded inconsistently. RoadPulse allows a user to upload or record a road video. The system analyzes one frame per second, detects cracks and potholes, identifies the road location when GPS data is available, and gives the road a health score. The results are presented on a dashboard with road rankings, a map, defect evidence, history, and downloadable reports.

## What is implemented

- Professional dark React dashboard with sidebar navigation inspired by a municipal operations console.
- Upload-video mode and direct phone-recording mode.
- FastAPI background job API with live progress polling.
- Your trained Ultralytics `best.pt` model is loaded server-side.
- Automatic YOLO settings: users do not set confidence or frame stride in the UI.
- One YOLO analysis frame per source-video second (a 30 FPS video analyzes one frame and skips 29), low model confidence threshold (`0.05` by default), 640px inference.
- Lightweight temporal deduplication so the same visible defect is not counted every frame.
- Evidence images, defect table, defect distribution chart and downloadable CSV report.
- Persistent SQLite analysis history: completed road analyses survive **New Video Analysis**, browser refreshes and backend restarts.
- Unified **Dashboard** with road rankings, all-road map, selected-road results and filterable defect intelligence.
- Combined **History & Reports** page for reopening saved analyses and downloading the selected CSV report.
- Uploaded-video GPS: backend checks ExifTool/FFprobe metadata and also includes a built-in raw QuickTime ISO6709 scanner, so common phone GPS metadata can still be found on Windows even when those command-line tools are missing.
- Optional synchronized GPS JSON sidecar can be attached when an export stripped the video metadata.
- Phone survey GPS: browser requires an initial high-accuracy GPS fix before recording, then records a timestamped `watchPosition()` track while video is recorded.
- Road name/road number is never typed manually. With `GOOGLE_MAPS_API_KEY`, the backend snaps GPS to the Google road network and reverse-geocodes it. During local development, OpenStreetMap/Nominatim is used as a best-effort road-name fallback when Google is not configured; exact road snapping still requires Google Roads API.
- Roughness is automatic: synchronized phone accelerometer/gyroscope data is preferred; uploaded-video analysis falls back to a clearly labelled camera-motion proxy.
- Interactive OpenStreetMap/Leaflet map with route and defect locations.

## What changed in v2.1

1. **GPS reliability:** built-in QuickTime ISO6709 scan, clearer GPS diagnostics, an optional synchronized GPS JSON fallback, and phone mode now waits for a real GPS fix before recording.
2. **Analysis persistence:** results are stored in `data/roadpulse.db` using SQLite and exposed through the compatible `/api/surveys` API.
3. **Unified operations view:** dashboard, road rankings, network map and defects now share one page; saved analysis history and reports share a second page.
4. **Predictable video sampling:** YOLO runs at one frame per video second, regardless of the source frame rate.

## Accuracy / honesty constraints

1. A video with no embedded GPS cannot reveal its exact recording location from pixels alone. RoadPulse reports location unavailable instead of guessing.
2. Phone-recording mode is the most reliable workflow because video, GPS and motion are captured on the same clock.
3. The RoadPulse Roughness Index is not IRI. It requires calibration on labelled Bahrain roads before engineering use.
4. The Road Health Score is a RoadPulse prototype index, not PCI.

## Required model

Copy your trained four-class road-damage model to:

```text
models/best.pt
```

Expected semantic classes:

- longitudinal_crack
- transverse_crack
- fatigue_crack (or alligator_crack)
- pothole

If the model has exactly four classes but different display names, the backend falls back to the RDD2022 class order `D00, D10, D20, D40`.

## Google APIs

Enable in one Google Cloud project:

- Roads API
- Geocoding API
- Billing

Keep the API key only in the backend environment:

```bash
export GOOGLE_MAPS_API_KEY="your_key"
```

Without the key, RoadPulse can still show available GPS coordinates and will attempt a best-effort OpenStreetMap/Nominatim road-name lookup. Google Roads snapping and the preferred exact road lookup still require the Google key.

## Run locally

### Backend

Use Python 3.11 or 3.12 for the most predictable ML package compatibility.

```bash
cd backend
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

export ROADPULSE_MODEL_PATH="../models/best.pt"
export GOOGLE_MAPS_API_KEY="your_key"
export FRONTEND_ORIGIN="http://localhost:5173"
uvicorn app.main:app --reload --port 8000
```

Check `http://localhost:8000/api/health`. It should report `model_loaded: true`, four model classes, and a `gps_capabilities` object.

Saved analyses are available at `http://localhost:8000/api/surveys` (the internal API route is retained for compatibility).

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open `http://localhost:5173`.

## Docker

Put `best.pt` in `models/`, then:

```bash
GOOGLE_MAPS_API_KEY="your_key" docker compose up --build
```

Open `http://localhost:3000`.

## Phone recording requirements

Phone recording needs HTTPS in production because browser geolocation and motion sensors are secure-context features. On iPhone/iPad, motion permission must be requested from a user action; RoadPulse requests it when **Start road video** is pressed.

## Uploaded video location

RoadPulse tries ExifTool first, then FFprobe, for GPS tags such as QuickTime ISO6709. If an export, social-media app or messenger stripped location metadata, upload mode will correctly report location unavailable. Direct phone recording avoids this by collecting GPS separately.

## Developer-only automatic analysis tuning

The normal dashboard exposes no model thresholds. Developers can override the detection-confidence default with a backend environment variable. Frame sampling is fixed at one analyzed frame per video second:

```text
ROADPULSE_DETECTION_CONFIDENCE=0.05
```

## Validation performed

- Python backend compiles successfully.
- Backend unit tests pass (`5 passed`).
- React/JSX source was syntax-checked with the TypeScript parser.
- A full `npm install`/production build still needs to run on a machine with normal npm registry access.
