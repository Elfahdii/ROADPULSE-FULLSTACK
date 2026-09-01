import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv('ROADPULSE_DATA_DIR', BASE_DIR / 'data')).resolve()
UPLOAD_DIR = DATA_DIR / 'uploads'
EVIDENCE_DIR = DATA_DIR / 'evidence'
MODEL_PATH = Path(os.getenv('ROADPULSE_MODEL_PATH', BASE_DIR / 'models' / 'best.pt')).resolve()
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY', '').strip()
FRONTEND_ORIGIN = os.getenv('FRONTEND_ORIGIN', 'http://localhost:5173').strip()

# User-facing analysis settings are automatic. Detection confidence can be tuned
# by the developer without exposing a slider in the dashboard. Frame sampling is
# fixed at one analyzed frame per source-video second in video_analysis.py.
DETECTION_CONFIDENCE = float(os.getenv('ROADPULSE_DETECTION_CONFIDENCE', '0.05'))
INFERENCE_SIZE = max(256, int(os.getenv('ROADPULSE_INFERENCE_SIZE', '640')))
TORCH_NUM_THREADS = max(1, int(os.getenv('ROADPULSE_TORCH_THREADS', '1')))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
