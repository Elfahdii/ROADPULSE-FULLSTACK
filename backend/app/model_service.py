from __future__ import annotations
from pathlib import Path
from threading import Lock
from .config import MODEL_PATH

EXPECTED_ALIASES = {
    'longitudinal_crack': 'longitudinal_crack',
    'transverse_crack': 'transverse_crack',
    'fatigue_crack': 'fatigue_crack',
    'alligator_crack': 'fatigue_crack',
    'pothole': 'pothole',
}

class DetectorService:
    def __init__(self):
        self._model = None
        self._lock = Lock()
        self.error = None

    def load(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            if not MODEL_PATH.exists():
                self.error = f'Model file not found: {MODEL_PATH}'
                return None
            try:
                from ultralytics import YOLO
                model = YOLO(str(MODEL_PATH))
                names = {int(k): str(v).strip().lower().replace(' ', '_') for k, v in model.names.items()}
                if len(names) != 4:
                    raise RuntimeError(f'Expected a 4-class RoadPulse model, found {len(names)} classes: {names}')
                self._model = model
                self.error = None
            except Exception as e:
                self.error = str(e)
                self._model = None
        return self._model

    @property
    def model(self):
        return self.load()

detector = DetectorService()
