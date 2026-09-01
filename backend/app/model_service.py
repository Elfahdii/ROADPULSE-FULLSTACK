from __future__ import annotations
from pathlib import Path
from threading import Lock
from .config import INFERENCE_SIZE, MODEL_PATH, TORCH_NUM_THREADS

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
        self._warmup_lock = Lock()
        self._warmed_up = False
        self.error = None
        self.warmup_error = None

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
                import torch

                # Small cloud instances cannot afford PyTorch's default CPU
                # worker pools. One thread is also appropriate for a service
                # with less than one vCPU.
                torch.set_num_threads(TORCH_NUM_THREADS)
                try:
                    torch.set_num_interop_threads(TORCH_NUM_THREADS)
                except RuntimeError:
                    pass

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

    def warmup(self):
        """Load the model and run one blank inference before the first upload."""
        model = self.load()
        if model is None:
            return False
        if self._warmed_up:
            return True

        with self._warmup_lock:
            if self._warmed_up:
                return True
            try:
                import numpy as np

                blank_frame = np.zeros((INFERENCE_SIZE, INFERENCE_SIZE, 3), dtype=np.uint8)
                model.predict(blank_frame, conf=0.001, imgsz=INFERENCE_SIZE, verbose=False)
                self._warmed_up = True
                self.warmup_error = None
            except Exception as e:
                # A warm-up failure must not stop the API from starting; the
                # normal analysis path can still report the underlying error.
                self.warmup_error = str(e)
                return False
        return True

    @property
    def model(self):
        return self.load()

    @property
    def warmed_up(self):
        return self._warmed_up

detector = DetectorService()
