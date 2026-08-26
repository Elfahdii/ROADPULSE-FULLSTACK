from app.geo import parse_location_string, normalize_gps_points, nearest_gps

def test_iso6709():
    lat, lon = parse_location_string('+26.223500+050.587600/')
    assert round(lat, 6) == 26.2235
    assert round(lon, 6) == 50.5876

def test_nearest_gps():
    pts = normalize_gps_points([
        {'t_ms':0,'latitude':26.0,'longitude':50.0},
        {'t_ms':2000,'latitude':26.1,'longitude':50.1},
    ])
    p = nearest_gps(pts, 1.8)
    assert p['latitude'] == 26.1


def test_raw_iso6709_fallback(tmp_path):
    from app.geo import extract_embedded_gps
    video = tmp_path / 'sample.mov'
    video.write_bytes(b'xxxxcom.apple.quicktime.location.ISO6709xxxx+26.223500+050.587600+000.000/xxxx')
    lat, lon, source, diagnostic = extract_embedded_gps(video)
    assert round(lat, 6) == 26.2235
    assert round(lon, 6) == 50.5876
    assert source == 'video_metadata'
    assert diagnostic['metadata_gps_found'] is True
