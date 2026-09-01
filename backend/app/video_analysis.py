from __future__ import annotations

import json
import math
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from .config import (
    DETECTION_CONFIDENCE,
    EVIDENCE_DIR,
    GOOGLE_MAPS_API_KEY,
)
from .geo import extract_embedded_gps, normalize_gps_points, nearest_gps, reverse_geocode, snap_route
from .health import calculate_health
from .model_service import detector
from .roughness import camera_motion_value, roughness_from_motion, roughness_from_video_motion

CANONICAL_CLASSES = {
    'longitudinal_crack': 'longitudinal_crack',
    'transverse_crack': 'transverse_crack',
    'fatigue_crack': 'fatigue_crack',
    'alligator_crack': 'fatigue_crack',
    'pothole': 'pothole',
}

MOTION_SAMPLE_FPS = 5.0
MOTION_MAX_DIMENSION = 480


def _ffmpeg_executable() -> str | None:
    """Return a usable FFmpeg binary for browser-compatible video output."""
    system_ffmpeg = shutil.which('ffmpeg')
    if system_ffmpeg:
        return system_ffmpeg

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


class _FFmpegVideoWriter:
    """Encode browser-compatible H.264 directly from OpenCV BGR frames."""

    def __init__(self, output_path: Path, fps: float, frame_width: int, frame_height: int):
        ffmpeg_executable = _ffmpeg_executable()
        if not ffmpeg_executable:
            raise RuntimeError('FFmpeg is unavailable.')

        self._process = subprocess.Popen(
            [
                ffmpeg_executable,
                '-y',
                '-loglevel',
                'error',
                '-f',
                'rawvideo',
                '-pix_fmt',
                'bgr24',
                '-video_size',
                f'{frame_width}x{frame_height}',
                '-framerate',
                f'{fps:.6f}',
                '-i',
                'pipe:0',
                '-an',
                '-c:v',
                'libx264',
                '-preset',
                'veryfast',
                '-crf',
                '23',
                '-pix_fmt',
                'yuv420p',
                '-tag:v',
                'avc1',
                '-movflags',
                '+faststart',
                str(output_path),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            bufsize=1024 * 1024,
        )
        self._closed = False

    def isOpened(self):
        return not self._closed and self._process.poll() is None and self._process.stdin is not None

    def write(self, frame):
        if not self.isOpened():
            raise RuntimeError('FFmpeg video encoder stopped unexpectedly.')
        self._process.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())

    def release(self):
        if self._closed:
            return
        self._closed = True
        if self._process.stdin is not None:
            self._process.stdin.close()
        return_code = self._process.wait()
        if return_code != 0:
            raise RuntimeError(f'FFmpeg video encoder exited with code {return_code}.')


def _motion_sampling_stride(fps: float, target_fps: float = MOTION_SAMPLE_FPS) -> int:
    """Return a source-frame stride close to the requested motion sample rate."""
    if fps <= 0 or target_fps <= 0:
        return 1
    return max(1, int(round(fps / target_fps)))


def _prepare_motion_frame(frame: np.ndarray, max_dimension: int = MOTION_MAX_DIMENSION) -> np.ndarray:
    """Create a small grayscale frame for the optical-flow roughness proxy."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    longest_side = max(height, width)
    if max_dimension > 0 and longest_side > max_dimension:
        scale = max_dimension / longest_side
        gray = cv2.resize(
            gray,
            (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
            interpolation=cv2.INTER_AREA,
        )
    return gray


def _read_json(path: Path | None):
    if not path or not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _canonical_model_names(model):
    result = {}
    for k, v in model.names.items():
        clean = str(v).strip().lower().replace(' ', '_')
        if clean in CANONICAL_CLASSES:
            result[int(k)] = CANONICAL_CLASSES[clean]

    if len(result) != 4:
        # RDD2022 fallback only when the model itself has exactly four output classes.
        if len(model.names) == 4:
            result = {
                0: 'longitudinal_crack',
                1: 'transverse_crack',
                2: 'fatigue_crack',
                3: 'pothole',
            }
        else:
            raise RuntimeError(f'Unexpected model classes: {model.names}')
    return result


def _center(box):
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _box_area(box):
    x1, y1, x2, y2 = box
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _intersection_over_smaller(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    smaller = min(_box_area(a), _box_area(b))
    return intersection / smaller if smaller > 0 else 0.0


def _predicted_box(track, frame_idx):
    """Move a track using its last measured box velocity."""
    gap = max(0, frame_idx - track['last_frame'])
    velocity = track.get('velocity') or [0.0, 0.0, 0.0, 0.0]
    return [float(value + speed * gap) for value, speed in zip(track['box'], velocity)]


def _clip_box(box, frame_width, frame_height):
    x1, y1, x2, y2 = box
    x1 = max(0.0, min(float(frame_width - 1), x1))
    y1 = max(0.0, min(float(frame_height - 1), y1))
    x2 = max(0.0, min(float(frame_width - 1), x2))
    y2 = max(0.0, min(float(frame_height - 1), y2))
    if x2 - x1 < 3 or y2 - y1 < 3:
        return None
    return [x1, y1, x2, y2]


def _compatible_track_class(track_class, detection_class):
    if track_class == detection_class:
        return True
    crack_classes = {
        'longitudinal_crack',
        'transverse_crack',
        'fatigue_crack',
    }
    return track_class in crack_classes and detection_class in crack_classes


def _deduplicate_frame_detections(detections):
    """Suppress nested/overlapping YOLO boxes for the same visible defect."""
    kept = []
    for detection in sorted(detections, key=lambda item: item['confidence'], reverse=True):
        duplicate = any(
            _compatible_track_class(existing['class_name'], detection['class_name'])
            and (
                _iou(existing['box'], detection['box']) >= 0.15
                or _intersection_over_smaller(existing['box'], detection['box']) >= 0.60
            )
            for existing in kept
        )
        if not duplicate:
            kept.append(detection)
    return kept


def _match_tracks(detections, tracks, frame_idx, frame_width, frame_height, max_age_frames):
    """Assign detections to persistent road-defect tracks.

    A forward-facing road camera makes a crack move mostly downward and grow
    between one-second samples. Matching only by IoU or a small center radius
    therefore counted the same crack more than once. This matcher predicts the
    previous track's motion and also accepts plausible perspective movement.
    """
    frame_diag = math.hypot(frame_width, frame_height)
    candidates = []

    for det_index, det in enumerate(detections):
        det_center = _center(det['box'])
        det_area = max(_box_area(det['box']), 1.0)

        for track_id, track in tracks.items():
            if not _compatible_track_class(track['class_name'], det['class_name']):
                continue

            gap = frame_idx - track['last_frame']
            if gap <= 0 or gap > max_age_frames:
                continue

            predicted = _predicted_box(track, frame_idx)
            predicted_center = _center(predicted)
            previous_center = _center(track['box'])
            predicted_distance = math.hypot(
                det_center[0] - predicted_center[0],
                det_center[1] - predicted_center[1],
            ) / max(frame_diag, 1.0)
            previous_distance = math.hypot(
                det_center[0] - previous_center[0],
                det_center[1] - previous_center[1],
            ) / max(frame_diag, 1.0)
            x_shift = abs(det_center[0] - previous_center[0]) / max(frame_width, 1.0)
            y_shift = (det_center[1] - previous_center[1]) / max(frame_height, 1.0)
            area_ratio = det_area / max(_box_area(track['box']), 1.0)
            overlap = max(_iou(det['box'], predicted), _iou(det['box'], track['box']))

            plausible_road_motion = (
                x_shift <= 0.28
                and -0.10 <= y_shift <= 0.70
                and 0.12 <= area_ratio <= 12.0
            )
            if overlap < 0.02 and predicted_distance > 0.28 and not plausible_road_motion:
                continue

            size_penalty = abs(math.log(max(area_ratio, 1e-6)))
            score = (
                overlap * 3.0
                + max(0.0, 1.0 - predicted_distance)
                + 0.45 * max(0.0, 1.0 - previous_distance)
                + (0.35 if plausible_road_motion else 0.0)
                - 0.08 * size_penalty
            )
            candidates.append((score, det_index, track_id))

    assignments = {}
    used_tracks = set()
    for _, det_index, track_id in sorted(candidates, reverse=True):
        if det_index in assignments or track_id in used_tracks:
            continue
        assignments[det_index] = track_id
        used_tracks.add(track_id)

    for det_index, det in enumerate(detections):
        track_id = assignments.get(det_index)
        if track_id is None:
            track_id = str(uuid.uuid4())
            tracks[track_id] = {
                'class_name': det['class_name'],
                'box': det['box'],
                'last_frame': frame_idx,
                'velocity': [0.0, 0.0, 0.0, 0.0],
                'hits': 1,
                'best': det,
            }
            continue

        track = tracks[track_id]
        gap = max(1, frame_idx - track['last_frame'])
        measured_velocity = [
            (new_value - old_value) / gap
            for new_value, old_value in zip(det['box'], track['box'])
        ]
        if track.get('hits', 1) <= 1:
            velocity = measured_velocity
        else:
            previous_velocity = track.get('velocity') or [0.0, 0.0, 0.0, 0.0]
            velocity = [
                0.65 * measured + 0.35 * previous
                for measured, previous in zip(measured_velocity, previous_velocity)
            ]

        track['box'] = det['box']
        track['last_frame'] = frame_idx
        track['velocity'] = velocity
        track['hits'] = track.get('hits', 1) + 1
        if det['confidence'] > track['best']['confidence']:
            track['best'] = det
            track['class_name'] = det['class_name']


def _draw_active_tracks(frame, tracks, frame_idx, max_age_frames):
    """Draw each recent track between YOLO samples until it leaves the view."""
    height, width = frame.shape[:2]
    annotated = frame.copy()
    for track in tracks.values():
        if frame_idx - track['last_frame'] > max_age_frames:
            continue
        box = _clip_box(_predicted_box(track, frame_idx), width, height)
        if box is None:
            continue
        x1, y1, x2, y2 = [int(round(value)) for value in box]
        color = (70, 90, 255) if track['class_name'] == 'pothole' else (30, 180, 255)
        confidence = float(track['best']['confidence'])
        label = f"{track['class_name'].replace('_', ' ')} {confidence:.2f}"
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
        cv2.putText(
            annotated,
            label,
            (max(0, x1), max(24, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            color,
            2,
            cv2.LINE_AA,
        )
    return annotated


def _gps_accuracy(points: list[dict]) -> float | None:
    values = []
    for p in points:
        try:
            value = float(p.get('accuracy'))
            if math.isfinite(value) and value >= 0:
                values.append(value)
        except Exception:
            pass
    if not values:
        return None
    return float(np.median(values))


def _draw_evidence(det: dict) -> np.ndarray:
    frame = det['frame'].copy()
    x1, y1, x2, y2 = [int(round(v)) for v in det['box']]
    color = (70, 90, 255) if det['class_name'] == 'pothole' else (30, 180, 255)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
    label = f"{det['class_name'].replace('_', ' ')} {det['confidence']:.2f}"
    cv2.putText(
        frame,
        label,
        (max(0, x1), max(24, y1 - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        color,
        2,
        cv2.LINE_AA,
    )
    return frame


def analyze_video(
    video_path: Path,
    gps_json: Path | None,
    motion_json: Path | None,
    job_id: str,
    original_filename: str,
    progress_cb=None,
):
    model = detector.load()
    if model is None:
        raise RuntimeError(detector.error or 'RoadPulse model could not be loaded.')

    class_names = _canonical_model_names(model)
    gps_points = normalize_gps_points(_read_json(gps_json))
    motion_samples = _read_json(motion_json)
    warnings = []

    embedded_lat, embedded_lon, embedded_source, gps_diagnostic = extract_embedded_gps(video_path)
    if gps_points:
        location_source = 'phone_gps_track'
    elif embedded_lat is not None and embedded_lon is not None:
        gps_points = [{
            't_ms': 0.0,
            'latitude': embedded_lat,
            'longitude': embedded_lon,
            'accuracy': None,
            'speed': None,
            'heading': None,
        }]
        location_source = embedded_source or 'video_metadata'
    else:
        location_source = 'none'
        if not gps_diagnostic.get('exiftool_available') and not gps_diagnostic.get('ffprobe_available'):
            warnings.append(
                'No GPS track was supplied and no embedded GPS was found. ExifTool and FFprobe are not on PATH, '
                'but RoadPulse also ran its built-in QuickTime ISO6709 scan. This file appears to contain no usable GPS metadata.'
            )
        else:
            warnings.append(
                'No embedded video GPS or synchronized phone GPS was found. This usually means the video file does not contain '
                'location metadata (for example after export, messaging, or social-media compression). RoadPulse will not guess the location.'
            )

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError('The uploaded video could not be decoded by OpenCV/FFmpeg.')

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if fps <= 0:
        fps = 30.0
        warnings.append('Video FPS metadata was unavailable; 30 FPS was used as a timing fallback.')

    duration = total_frames / fps if total_frames and fps else None
    confidence = float(np.clip(DETECTION_CONFIDENCE, 0.001, 0.95))
    # Run inference once per second of source video. For a 30 FPS recording this
    # analyzes frame 0, skips the following 29 frames, then analyzes frame 30.
    frame_stride = max(1, int(round(fps)))
    analysis_sampling_fps = fps / frame_stride

    evidence_dir = EVIDENCE_DIR / job_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    # Create a full analyzed output video
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

    final_annotated_path = evidence_dir / "annotated.mp4"

    annotated_video_url = None
    video_writer = None

    if frame_width > 0 and frame_height > 0:
        try:
            # Feed annotated BGR frames directly to FFmpeg. This creates the
            # browser-compatible H.264 file in one encoding pass instead of
            # writing an intermediate MP4 and transcoding the whole video.
            video_writer = _FFmpegVideoWriter(
                final_annotated_path,
                fps,
                frame_width,
                frame_height,
            )
        except Exception:
            # Keep a best-effort OpenCV fallback for environments where FFmpeg
            # is unavailable. It is single-pass, but browser support may vary.
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video_writer = cv2.VideoWriter(
                str(final_annotated_path),
                fourcc,
                fps,
                (frame_width, frame_height),
            )
            if not video_writer.isOpened():
                video_writer.release()
                video_writer = None
                warnings.append('The analyzed video could not be created.')

    tracks = {}
    motion_values = []
    prev_motion_gray = None
    analyzed = 0
    frame_idx = 0

    # Keep an identity through the next one-second YOLO sample and briefly
    # bridge a missed detection. Motion prediction makes the box leave the
    # frame naturally instead of creating another count for the same crack.
    max_age_frames = max(8, int(round(fps * 1.6)))
    # Five small grayscale samples per second are enough for the prototype
    # roughness proxy. YOLO remains independently sampled at one frame/second.
    motion_stride = _motion_sampling_stride(fps)

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        # Roughness proxy from camera motion, independent of detector stride.
        if frame_idx % motion_stride == 0:
            gray = _prepare_motion_frame(frame)
            if prev_motion_gray is not None:
                val = camera_motion_value(prev_motion_gray, gray)
                if val is not None:
                    # Normalize across motion sampling intervals so long videos do not
                    # appear rougher merely because every second frame was sampled.
                    motion_values.append(val / motion_stride)
            prev_motion_gray = gray

        if frame_idx % frame_stride != 0:
            if video_writer is not None:
                video_writer.write(
                    _draw_active_tracks(frame, tracks, frame_idx, max_age_frames)
                )

            frame_idx += 1
            continue

        analyzed += 1
        t_sec = frame_idx / fps
        result = model.predict(frame, conf=confidence, imgsz=640, verbose=False)[0]
        detections = []

        if result.boxes is not None and len(result.boxes) > 0:
            cls_ids = result.boxes.cls.int().cpu().tolist()
            confs = result.boxes.conf.cpu().tolist()
            boxes = result.boxes.xyxy.cpu().tolist()

            for cls_id, conf, box in zip(cls_ids, confs, boxes):
                if cls_id not in class_names:
                    continue
                point = nearest_gps(gps_points, t_sec)
                detections.append({
                    'class_name': class_names[cls_id],
                    'confidence': float(conf),
                    'box': [float(x) for x in box],
                    't_sec': float(t_sec),
                    'latitude': point['latitude'] if point else None,
                    'longitude': point['longitude'] if point else None,
                    'frame': frame.copy(),
                })

        detections = _deduplicate_frame_detections(detections)
        _match_tracks(
            detections,
            tracks,
            frame_idx,
            frame.shape[1],
            frame.shape[0],
            max_age_frames=max_age_frames,
        )

        if video_writer is not None:
            video_writer.write(
                _draw_active_tracks(frame, tracks, frame_idx, max_age_frames)
            )

        frame_idx += 1
        if progress_cb and total_frames > 0 and analyzed % 3 == 0:
            progress_cb(
                min(88.0, 8.0 + (frame_idx / total_frames) * 80.0),
                'Running YOLO at one frame per second and synchronizing detections…',
            )

    cap.release()
    if video_writer is not None:
        if progress_cb:
            progress_cb(89, 'Finalizing browser-compatible video…')
        try:
            video_writer.release()
            if final_annotated_path.exists() and final_annotated_path.stat().st_size > 0:
                annotated_video_url = f'/evidence/{job_id}/annotated.mp4'
            else:
                warnings.append('The analyzed video encoder produced an empty file.')
        except Exception:
            final_annotated_path.unlink(missing_ok=True)
            warnings.append('The analyzed video could not be finalized.')

    defects = []
    counts = {
        'longitudinal_crack': 0,
        'transverse_crack': 0,
        'fatigue_crack': 0,
        'pothole': 0,
    }

    for i, (tid, tr) in enumerate(tracks.items(), start=1):
        det = tr['best']
        counts[det['class_name']] += 1
        evidence_name = f'{i:04d}_{det["class_name"]}.jpg'
        annotated = _draw_evidence(det)
        cv2.imwrite(str(evidence_dir / evidence_name), annotated)
        defects.append({
            'id': tid,
            'class_name': det['class_name'],
            'confidence': det['confidence'],
            't_sec': det['t_sec'],
            'latitude': det['latitude'],
            'longitude': det['longitude'],
            'road_name': None,
            'evidence_url': f'/evidence/{job_id}/{evidence_name}',
        })

    if progress_cb:
        progress_cb(90, 'Estimating roughness…')

    if motion_samples:
        r_index, r_label, r_features = roughness_from_motion(motion_samples, gps_points)
        r_source = 'phone_motion_sensors'
        if r_index is None:
            warnings.append(
                'Phone motion data was present but insufficient for a stable roughness estimate; '
                'the video-motion proxy was used instead.'
            )
            r_index, r_label, r_features = roughness_from_video_motion(motion_values)
            r_source = 'video_motion_proxy'
    else:
        r_index, r_label, r_features = roughness_from_video_motion(motion_values)
        r_source = 'video_motion_proxy'
        warnings.append(
            'Roughness was estimated from camera motion because synchronized phone motion samples '
            'were not available. This is a RoadPulse prototype roughness index, not IRI.'
        )

    if r_index is None:
        r_label = 'Unavailable'

    if progress_cb:
        progress_cb(94, 'Resolving GPS and road name…')

    route_points, geo_warnings = snap_route(gps_points)
    warnings.extend(geo_warnings)

    # Use a real point on the snapped route, not the arithmetic mean, for road lookup.
    lookup_points = route_points or gps_points
    if lookup_points:
        middle = lookup_points[len(lookup_points) // 2]
        center_lat = float(middle['latitude'])
        center_lon = float(middle['longitude'])
    else:
        center_lat = center_lon = None

    road_name = formatted_address = place_id = None
    if center_lat is not None:
        road_name, formatted_address, place_id = reverse_geocode(center_lat, center_lon)
        if not road_name:
            warnings.append(
                'GPS coordinates were available, but an exact road name was not returned. '
                'Verify the Google Maps API key, billing, and Roads/Geocoding API enablement.'
            )

    # Resolve each defect to the road at its own GPS coordinate when Google is configured.
    # The OpenStreetMap/Nominatim development fallback is intentionally not called once per defect
    # because its public service is rate-limited; those defects inherit the survey road name.
    cache = {}
    for d in defects:
        if d['latitude'] is None or d['longitude'] is None:
            continue
        if GOOGLE_MAPS_API_KEY:
            key = (round(d['latitude'], 5), round(d['longitude'], 5))
            if key not in cache:
                cache[key] = reverse_geocode(d['latitude'], d['longitude'])[0]
            d['road_name'] = cache[key] or road_name
        else:
            d['road_name'] = road_name

    score, status = calculate_health(counts, r_label)
    accuracy_m = _gps_accuracy(gps_points)

    if progress_cb:
        progress_cb(100, 'Analysis complete')

    return {
        'summary': {
            'health_score': score,
            'status': status,
            'total_defects': sum(counts.values()),
            'counts': counts,
            'roughness_index': r_index,
            'roughness_label': r_label,
            'roughness_source': r_source,
            'roughness_features': r_features,
        },
        'location': {
            'source': location_source,
            'accuracy_m': accuracy_m,
            'center_lat': center_lat,
            'center_lon': center_lon,
            'road_name': road_name,
            'formatted_address': formatted_address,
            'place_id': place_id,
            'route_points': route_points,
            'gps_diagnostic': gps_diagnostic,
        },
        'video': {
            'filename': original_filename,
            'fps': fps,
            'duration_sec': duration,
            'frames_analyzed': analyzed,
            'total_frames': total_frames,
            'analysis_frame_stride': frame_stride,
            'analysis_sampling_fps': analysis_sampling_fps,
            'detection_confidence': confidence,
            'annotated_video_url': annotated_video_url,
            'processed_at': datetime.now(timezone.utc).isoformat(),
        },
        'defects': defects,
        'warnings': list(dict.fromkeys(warnings)),
    }
