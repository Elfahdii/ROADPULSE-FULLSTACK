import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv('ROADPULSE_DATA_DIR', BASE_DIR / 'data')).resolve()
UPLOAD_DIR = DATA_DIR / 'uploads'
EVIDENCE_DIR = DATA_DIR / 'evidence'
MODEL_PATH = Path(os.getenv('ROADPULSE_MODEL_PATH', BASE_DIR / 'models' / 'best.pt')).resolve()
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY', '').strip()
FRONTEND_ORIGIN = os.getenv('FRONTEND_ORIGIN', 'http://localhost:5173').strip()

# User-facing analysis settings are automatic. These can be tuned by the developer
# through environment variables without exposing sliders in the dashboard.
DETECTION_CONFIDENCE = float(os.getenv('ROADPULSE_DETECTION_CONFIDENCE', '0.05'))
SHORT_VIDEO_STRIDE = int(os.getenv('ROADPULSE_SHORT_VIDEO_STRIDE', '1'))
MEDIUM_VIDEO_STRIDE = int(os.getenv('ROADPULSE_MEDIUM_VIDEO_STRIDE', '2'))
LONG_VIDEO_STRIDE = int(os.getenv('ROADPULSE_LONG_VIDEO_STRIDE', '3'))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
