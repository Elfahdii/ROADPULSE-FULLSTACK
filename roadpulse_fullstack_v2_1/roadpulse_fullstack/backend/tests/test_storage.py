from app import storage


def test_survey_persistence(tmp_path, monkeypatch):
    db_path = tmp_path / 'roadpulse.db'
    monkeypatch.setattr(storage, 'DB_PATH', db_path)
    sample = {
        'summary': {
            'health_score': 76,
            'status': 'Fair',
            'total_defects': 2,
            'roughness_index': 42,
            'roughness_label': 'Rough',
        },
        'location': {
            'road_name': 'Test Road',
            'formatted_address': 'Test Road, Bahrain',
            'source': 'phone_gps_track',
        },
        'video': {
            'filename': 'survey.mp4',
            'processed_at': '2026-08-25T12:00:00+00:00',
        },
        'defects': [],
    }
    storage.save_survey('survey-1', sample)
    rows = storage.list_surveys()
    assert rows[0]['survey_id'] == 'survey-1'
    assert rows[0]['road_name'] == 'Test Road'
    loaded = storage.get_survey('survey-1')
    assert loaded['result']['summary']['health_score'] == 76
