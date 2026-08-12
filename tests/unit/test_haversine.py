from app.domain.optimizer.haversine import haversine_km


def test_haversine_identical_coordinates() -> None:
    dist = haversine_km(41.2995, 69.2401, 41.2995, 69.2401)
    assert dist == 0.0


def test_haversine_tashkent_districts() -> None:
    # Amir Timur Square (41.3111, 69.2797) to Chilonzor Metro (41.2721, 69.2045) ~7.7 km
    dist = haversine_km(41.3111, 69.2797, 41.2721, 69.2045)
    assert dist is not None
    assert 7.0 <= dist <= 8.5


def test_haversine_missing_coordinates() -> None:
    assert haversine_km(None, 69.2401, 41.2995, 69.2401) is None
    assert haversine_km(41.2995, None, 41.2995, 69.2401) is None
    assert haversine_km(41.2995, 69.2401, None, 69.2401) is None
    assert haversine_km(41.2995, 69.2401, 41.2995, None) is None
