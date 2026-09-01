import numpy as np

from app.video_analysis import (
    _deduplicate_frame_detections,
    _draw_active_tracks,
    _match_tracks,
    _motion_sampling_stride,
    _prepare_motion_frame,
    _predicted_box,
    _scaled_video_dimensions,
)


def detection(box, confidence=0.8, class_name='longitudinal_crack'):
    return {
        'box': [float(value) for value in box],
        'confidence': confidence,
        'class_name': class_name,
    }


def test_same_crack_keeps_one_identity_as_it_moves_toward_camera():
    tracks = {}
    _match_tracks(
        [detection([300, 80, 370, 145], confidence=0.72)],
        tracks,
        frame_idx=0,
        frame_width=640,
        frame_height=480,
        max_age_frames=48,
    )
    first_id = next(iter(tracks))

    # One second later the same road crack is lower and much larger. The old
    # center-only matcher treated this as a second defect.
    _match_tracks(
        [detection([265, 235, 430, 390], confidence=0.91)],
        tracks,
        frame_idx=30,
        frame_width=640,
        frame_height=480,
        max_age_frames=48,
    )

    assert list(tracks) == [first_id]
    assert tracks[first_id]['hits'] == 2
    assert tracks[first_id]['best']['confidence'] == 0.91
    assert _predicted_box(tracks[first_id], 31) != tracks[first_id]['box']


def test_new_crack_entering_from_top_is_not_merged_with_departing_crack():
    tracks = {}
    _match_tracks(
        [detection([300, 80, 370, 145])],
        tracks,
        frame_idx=0,
        frame_width=640,
        frame_height=480,
        max_age_frames=48,
    )
    _match_tracks(
        [detection([265, 235, 430, 390])],
        tracks,
        frame_idx=30,
        frame_width=640,
        frame_height=480,
        max_age_frames=48,
    )
    _match_tracks(
        [detection([295, 55, 365, 120])],
        tracks,
        frame_idx=60,
        frame_width=640,
        frame_height=480,
        max_age_frames=48,
    )

    assert len(tracks) == 2


def test_two_visible_cracks_keep_separate_tracks():
    tracks = {}
    _match_tracks(
        [
            detection([80, 120, 155, 190]),
            detection([430, 115, 510, 190]),
        ],
        tracks,
        frame_idx=0,
        frame_width=640,
        frame_height=480,
        max_age_frames=48,
    )
    _match_tracks(
        [
            detection([65, 235, 180, 350]),
            detection([410, 230, 535, 350]),
        ],
        tracks,
        frame_idx=30,
        frame_width=640,
        frame_height=480,
        max_age_frames=48,
    )

    assert len(tracks) == 2
    assert sorted(track['hits'] for track in tracks.values()) == [2, 2]


def test_same_crack_is_not_duplicated_when_model_changes_crack_subtype():
    tracks = {}
    _match_tracks(
        [detection([300, 80, 370, 145], class_name='longitudinal_crack')],
        tracks,
        frame_idx=0,
        frame_width=640,
        frame_height=480,
        max_age_frames=48,
    )
    _match_tracks(
        [detection([265, 235, 430, 390], confidence=0.92, class_name='fatigue_crack')],
        tracks,
        frame_idx=30,
        frame_width=640,
        frame_height=480,
        max_age_frames=48,
    )

    assert len(tracks) == 1
    assert next(iter(tracks.values()))['class_name'] == 'fatigue_crack'


def test_box_stays_visible_between_samples_then_leaves_after_track_expires():
    tracks = {}
    _match_tracks(
        [detection([30, 30, 90, 90])],
        tracks,
        frame_idx=0,
        frame_width=160,
        frame_height=120,
        max_age_frames=48,
    )
    blank = np.zeros((120, 160, 3), dtype=np.uint8)

    assert _draw_active_tracks(blank, tracks, frame_idx=20, max_age_frames=48).any()
    assert not _draw_active_tracks(blank, tracks, frame_idx=49, max_age_frames=48).any()


def test_nested_boxes_in_one_frame_count_as_one_crack():
    detections = [
        detection([250, 180, 430, 390], confidence=0.34),
        detection([285, 215, 395, 355], confidence=0.08),
    ]

    deduplicated = _deduplicate_frame_detections(detections)

    assert len(deduplicated) == 1
    assert deduplicated[0]['confidence'] == 0.34


def test_separate_boxes_in_one_frame_remain_separate_cracks():
    detections = [
        detection([70, 180, 160, 300], confidence=0.34),
        detection([430, 180, 520, 300], confidence=0.30),
    ]

    assert len(_deduplicate_frame_detections(detections)) == 2


def test_roughness_motion_uses_five_samples_per_second():
    assert _motion_sampling_stride(30.0) == 6
    assert _motion_sampling_stride(25.0) == 5
    assert _motion_sampling_stride(4.0) == 1


def test_roughness_motion_frame_is_small_and_grayscale():
    portrait_frame = np.zeros((1920, 1080, 3), dtype=np.uint8)

    gray = _prepare_motion_frame(portrait_frame)

    assert gray.ndim == 2
    assert gray.shape == (480, 270)


def test_large_video_is_scaled_to_memory_safe_even_dimensions():
    assert _scaled_video_dimensions(1280, 720, max_dimension=960) == (960, 540)
    assert _scaled_video_dimensions(1080, 1920, max_dimension=960) == (540, 960)


def test_small_video_dimensions_are_preserved():
    assert _scaled_video_dimensions(640, 360, max_dimension=960) == (640, 360)
