from app.roughness import label_from_index

def test_roughness_labels():
    assert label_from_index(0) == 'Smooth'
    assert label_from_index(20) == 'Moderate'
    assert label_from_index(40) == 'Rough'
    assert label_from_index(65) == 'Severe'
