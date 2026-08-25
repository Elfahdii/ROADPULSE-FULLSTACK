DEFECT_PENALTIES = {
    'longitudinal_crack': 2,
    'transverse_crack': 3,
    'fatigue_crack': 8,
    'pothole': 12,
}
ROUGHNESS_PENALTIES = {
    'Smooth': 0,
    'Moderate': 8,
    'Rough': 15,
    'Severe': 30,
    'Unavailable': 0,
}

def status_from_score(score: int) -> str:
    if score >= 80:
        return 'Good'
    if score >= 60:
        return 'Fair'
    if score >= 40:
        return 'Poor'
    return 'Critical'

def calculate_health(counts: dict[str, int], roughness_label: str) -> tuple[int, str]:
    score = 100
    for name, count in counts.items():
        score -= DEFECT_PENALTIES.get(name, 0) * int(count)
    score -= ROUGHNESS_PENALTIES.get(roughness_label, 0)
    score = max(0, min(100, int(score)))
    return score, status_from_score(score)
