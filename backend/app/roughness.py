from __future__ import annotations
import math
import numpy as np
import cv2

LABEL_THRESHOLDS = ((20, 'Smooth'), (40, 'Moderate'), (65, 'Rough'))

def label_from_index(index: int) -> str:
    for threshold, label in LABEL_THRESHOLDS:
        if index < threshold:
            return label
    return 'Severe'

def _vector_magnitude(v):
    if not v:
        return None
    vals = [v.get('x'), v.get('y'), v.get('z')]
    if any(x is None for x in vals):
        return None
    return math.sqrt(sum(float(x) ** 2 for x in vals))

def roughness_from_motion(samples: list[dict], gps_points: list[dict] | None = None) -> tuple[int | None, str, dict]:
    rows = []
    for s in samples or []:
        t = float(s.get('t_ms', 0)) / 1000.0
        acc = _vector_magnitude(s.get('acceleration'))
        if acc is None:
            acc = _vector_magnitude(s.get('accelerationIncludingGravity'))
        rot = s.get('rotationRate') or {}
        rot_vals = [rot.get('alpha'), rot.get('beta'), rot.get('gamma')]
        rot_vals = [float(x) for x in rot_vals if x is not None]
        gyro_mag = math.sqrt(sum(x*x for x in rot_vals)) if rot_vals else 0.0
        if acc is not None:
            rows.append((t, acc, gyro_mag))
    if len(rows) < 20:
        return None, 'Unavailable', {'reason': 'not_enough_motion_samples'}

    t = np.array([r[0] for r in rows], dtype=float)
    a = np.array([r[1] for r in rows], dtype=float)
    g = np.array([r[2] for r in rows], dtype=float)

    # Remove gravity / steady mounting bias with a robust center.
    a_res = a - np.median(a)
    rms = float(np.sqrt(np.mean(a_res ** 2)))
    p95 = float(np.percentile(np.abs(a_res), 95))
    dt = np.diff(t)
    da = np.diff(a)
    valid = dt > 1e-3
    jerk = np.abs(da[valid] / dt[valid]) if np.any(valid) else np.array([0.0])
    jerk95 = float(np.percentile(jerk, 95))
    gyro_rms = float(np.sqrt(np.mean(g ** 2)))

    # Prototype score: intentionally bounded and labeled as non-IRI.
    raw = 9.0 * rms + 2.5 * p95 + 0.025 * jerk95 + 0.035 * gyro_rms
    index = int(np.clip(raw * 10.0, 0, 100))
    return index, label_from_index(index), {
        'accel_rms': rms,
        'accel_p95': p95,
        'jerk_p95': jerk95,
        'gyro_rms': gyro_rms,
    }

def camera_motion_value(prev_gray, gray) -> float | None:
    pts0 = cv2.goodFeaturesToTrack(prev_gray, maxCorners=250, qualityLevel=0.01, minDistance=20, blockSize=7)
    if pts0 is None or len(pts0) < 10:
        return None
    pts1, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, gray, pts0, None)
    if pts1 is None or status is None:
        return None
    good0 = pts0[status.flatten() == 1]
    good1 = pts1[status.flatten() == 1]
    if len(good0) < 10:
        return None
    M, _ = cv2.estimateAffinePartial2D(good0, good1, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if M is None:
        return None
    dx, dy = float(M[0, 2]), float(M[1, 2])
    angle = float(np.arctan2(M[1, 0], M[0, 0]))
    h, w = gray.shape
    diagonal = max(np.hypot(w, h), 1.0)
    return float(np.hypot(dx, dy) / diagonal + abs(angle))

def roughness_from_video_motion(values: list[float]) -> tuple[int | None, str, dict]:
    arr = np.asarray([x for x in values if x is not None], dtype=float)
    if len(arr) < 8:
        return None, 'Unavailable', {'reason': 'not_enough_video_motion'}
    window = min(9, len(arr))
    trend = np.convolve(arr, np.ones(window) / window, mode='same')
    residual = np.abs(arr - trend)
    raw = float(np.median(residual))
    index = int(np.clip(raw * 5000.0, 0, 100))
    return index, label_from_index(index), {'median_high_frequency_camera_motion': raw}
