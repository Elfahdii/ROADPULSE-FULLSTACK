from app.health import calculate_health, status_from_score

def test_health_score():
    counts = {'longitudinal_crack':2,'transverse_crack':1,'fatigue_crack':1,'pothole':1}
    score, status = calculate_health(counts, 'Rough')
    assert score == 58
    assert status == 'Poor'

def test_status_boundaries():
    assert status_from_score(80) == 'Good'
    assert status_from_score(60) == 'Fair'
    assert status_from_score(40) == 'Poor'
    assert status_from_score(39) == 'Critical'
