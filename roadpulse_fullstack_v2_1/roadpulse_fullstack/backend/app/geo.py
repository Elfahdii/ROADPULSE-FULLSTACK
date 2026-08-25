from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import httpx

from .config import GOOGLE_MAPS_API_KEY

ISO6709_RE = re.compile(r'([+-]\d{1,3}(?:\.\d+)?)([+-]\d{1,3}(?:\.\d+)?)')
ISO6709_BYTES_RE = re.compile(
    rb'([+-](?:90(?:\.0+)?|(?:[0-8]?\d)(?:\.\d+)?))'
    rb'([+-](?:180(?:\.0+)?|(?:1[0-7]\d|0?\d?\d)(?:\.\d+)?))'
    rb'(?:[+-]\d+(?:\.\d+)?)?/'
)


def _valid(lat, lon):
    return lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180


def _find_location_string(meta: dict):
    candidates = [
        'GPSCoordinates', 'GPSPosition', 'Location', 'LocationInformation',
        'LocationCreatedGPSCoordinates', 'com.apple.quicktime.location.ISO6709',
        'location', 'location-eng', 'xyz', '©xyz',
    ]
    # Exact matches first.
    for key in candidates:
        if key in meta and meta[key]:
            yield key, str(meta[key])
    # Then catch namespaced/variant keys returned by different tools.
    lowered = {str(k).lower(): k for k in meta}
    for lower, original in lowered.items():
        if any(token.lower() in lower for token in ('iso6709', 'gpsposition', 'gpscoordinates', 'location')):
            value = meta.get(original)
            if value:
                yield str(original), str(value)


def parse_location_string(text: str):
    if not text:
        return None
    m = ISO6709_RE.search(str(text))
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if _valid(lat, lon):
            return lat, lon
    nums = re.findall(r'[-+]?\d+(?:\.\d+)?', str(text))
    if len(nums) >= 2:
        lat, lon = float(nums[0]), float(nums[1])
        if _valid(lat, lon):
            return lat, lon
    return None


def gps_tool_status() -> dict:
    return {
        'exiftool_available': shutil.which('exiftool') is not None,
        'ffprobe_available': shutil.which('ffprobe') is not None,
        'raw_iso6709_scan_available': True,
        'google_maps_key_configured': bool(GOOGLE_MAPS_API_KEY),
    }


def _scan_raw_iso6709(video_path: Path) -> tuple[float, float] | None:
    """Find QuickTime ISO6709 coordinates without requiring ExifTool/FFprobe.

    iPhone/QuickTime files commonly keep a coordinate string such as
    +26.223500+050.587600+000.000/ inside a metadata atom. Scanning the raw
    bytes is intentionally only a fallback and only accepts valid ISO6709-like
    signed latitude/longitude values ending with '/'.
    """
    overlap = b''
    try:
        with video_path.open('rb') as f:
            while True:
                chunk = f.read(4 * 1024 * 1024)
                if not chunk:
                    break
                data = overlap + chunk
                for m in ISO6709_BYTES_RE.finditer(data):
                    try:
                        lat = float(m.group(1).decode('ascii'))
                        lon = float(m.group(2).decode('ascii'))
                    except Exception:
                        continue
                    if _valid(lat, lon):
                        return lat, lon
                overlap = data[-256:]
    except Exception:
        return None
    return None


def extract_embedded_gps(video_path: Path) -> tuple[float | None, float | None, str | None, dict]:
    status = gps_tool_status()
    diagnostic = {
        **status,
        'method': None,
        'metadata_gps_found': False,
    }

    # ExifTool is strongest for QuickTime/phone metadata when installed.
    if status['exiftool_available']:
        try:
            p = subprocess.run(
                ['exiftool', '-j', '-n', str(video_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if p.returncode == 0 and p.stdout.strip():
                meta = json.loads(p.stdout)[0]
                try:
                    lat = float(meta.get('GPSLatitude'))
                    lon = float(meta.get('GPSLongitude'))
                    if _valid(lat, lon):
                        diagnostic.update(method='exiftool', metadata_gps_found=True)
                        return lat, lon, 'video_metadata', diagnostic
                except Exception:
                    pass
                for _, value in _find_location_string(meta):
                    parsed = parse_location_string(value)
                    if parsed:
                        diagnostic.update(method='exiftool', metadata_gps_found=True)
                        return parsed[0], parsed[1], 'video_metadata', diagnostic
        except Exception as e:
            diagnostic['exiftool_error'] = str(e)

    # FFprobe fallback. Check both container and stream tags because camera
    # vendors do not all store QuickTime metadata at the same level.
    if status['ffprobe_available']:
        try:
            p = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', str(video_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if p.returncode == 0 and p.stdout.strip():
                data = json.loads(p.stdout)
                groups = [((data.get('format') or {}).get('tags') or {})]
                groups.extend((stream.get('tags') or {}) for stream in (data.get('streams') or []))
                for tags in groups:
                    for _, value in _find_location_string(tags):
                        parsed = parse_location_string(value)
                        if parsed:
                            diagnostic.update(method='ffprobe', metadata_gps_found=True)
                            return parsed[0], parsed[1], 'video_metadata', diagnostic
        except Exception as e:
            diagnostic['ffprobe_error'] = str(e)

    # Pure-Python/raw-file fallback for common QuickTime ISO6709 atoms. This
    # makes local Windows testing work even if ExifTool/FFprobe are not on PATH.
    parsed = _scan_raw_iso6709(video_path)
    if parsed:
        diagnostic.update(method='raw_iso6709_scan', metadata_gps_found=True)
        return parsed[0], parsed[1], 'video_metadata', diagnostic

    return None, None, None, diagnostic


def normalize_gps_points(points: list[dict]) -> list[dict]:
    cleaned = []
    for p in points or []:
        try:
            lat = float(p['latitude'])
            lon = float(p['longitude'])
            if not _valid(lat, lon):
                continue
            cleaned.append({
                't_ms': float(p.get('t_ms', 0)),
                'latitude': lat,
                'longitude': lon,
                'accuracy': p.get('accuracy'),
                'speed': p.get('speed'),
                'heading': p.get('heading'),
            })
        except Exception:
            continue
    cleaned.sort(key=lambda x: x['t_ms'])
    return cleaned


def nearest_gps(points: list[dict], t_sec: float) -> dict | None:
    if not points:
        return None
    target = t_sec * 1000.0
    return min(points, key=lambda p: abs(p['t_ms'] - target))


def _chunks(seq, n=100):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def snap_route(points: list[dict]) -> tuple[list[dict], list[str]]:
    warnings = []
    if not points:
        return [], warnings
    if not GOOGLE_MAPS_API_KEY:
        warnings.append(
            'Google Roads API is not configured. RoadPulse is showing the raw GPS track; '
            'road snapping is unavailable until a Google Maps API key is added.'
        )
        return [{'latitude': p['latitude'], 'longitude': p['longitude']} for p in points], warnings

    snapped = []
    try:
        with httpx.Client(timeout=20) as client:
            for chunk in _chunks(points, 100):
                path = '|'.join(f"{p['latitude']},{p['longitude']}" for p in chunk)
                if len(chunk) == 1:
                    url = 'https://roads.googleapis.com/v1/nearestRoads'
                    params = {'points': path, 'key': GOOGLE_MAPS_API_KEY}
                else:
                    url = 'https://roads.googleapis.com/v1/snapToRoads'
                    params = {'path': path, 'interpolate': 'false', 'key': GOOGLE_MAPS_API_KEY}
                r = client.get(url, params=params)
                r.raise_for_status()
                for item in r.json().get('snappedPoints', []):
                    loc = item.get('location') or {}
                    if 'latitude' in loc and 'longitude' in loc:
                        snapped.append({
                            'latitude': float(loc['latitude']),
                            'longitude': float(loc['longitude']),
                            'place_id': item.get('placeId'),
                        })
    except Exception as e:
        warnings.append(f'Google Roads API failed: {e}')
        snapped = [{'latitude': p['latitude'], 'longitude': p['longitude']} for p in points]
    return snapped, warnings


def _google_reverse_geocode(lat: float, lon: float) -> tuple[str | None, str | None, str | None]:
    if not GOOGLE_MAPS_API_KEY:
        return None, None, None
    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(
                'https://maps.googleapis.com/maps/api/geocode/json',
                params={'latlng': f'{lat},{lon}', 'key': GOOGLE_MAPS_API_KEY},
            )
            r.raise_for_status()
            data = r.json()
            if data.get('status') != 'OK' or not data.get('results'):
                return None, None, None
            best = data['results'][0]
            route = None
            for result in data['results']:
                for comp in result.get('address_components', []):
                    if 'route' in comp.get('types', []):
                        route = comp.get('long_name')
                        best = result
                        break
                if route:
                    break
            return route, best.get('formatted_address'), best.get('place_id')
    except Exception:
        return None, None, None


def _nominatim_reverse_geocode(lat: float, lon: float) -> tuple[str | None, str | None, str | None]:
    """Best-effort road-name fallback for development when Google is not configured."""
    try:
        headers = {'User-Agent': 'RoadPulse-Capstone/2.1 (road-condition-research)'}
        with httpx.Client(timeout=15, headers=headers) as client:
            r = client.get(
                'https://nominatim.openstreetmap.org/reverse',
                params={
                    'lat': lat,
                    'lon': lon,
                    'format': 'jsonv2',
                    'zoom': 18,
                    'addressdetails': 1,
                },
            )
            r.raise_for_status()
            data = r.json()
            address = data.get('address') or {}
            road = (
                address.get('road')
                or address.get('pedestrian')
                or address.get('residential')
                or address.get('highway')
                or address.get('path')
            )
            # OSM sometimes exposes a road reference separately from the name.
            ref = address.get('road_reference') or address.get('ref')
            if road and ref and str(ref).lower() not in str(road).lower():
                road = f'{road} ({ref})'
            return road, data.get('display_name'), str(data.get('place_id')) if data.get('place_id') else None
    except Exception:
        return None, None, None


def reverse_geocode(lat: float, lon: float) -> tuple[str | None, str | None, str | None]:
    if not _valid(lat, lon):
        return None, None, None
    if GOOGLE_MAPS_API_KEY:
        google = _google_reverse_geocode(lat, lon)
        if google[0] or google[1]:
            return google
    return _nominatim_reverse_geocode(lat, lon)


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))
