"""Resolving a dropped pin to a service area."""

from decimal import Decimal

from app.domain.geo import GeoPoint, nearest_point, to_float

# Real Tashkent district centroids, roughly.
CHILONZOR = GeoPoint(id=1, lat=41.2750, lng=69.2050)
YUNUSOBOD = GeoPoint(id=2, lat=41.3670, lng=69.2890)
SERGELI = GeoPoint(id=3, lat=41.2230, lng=69.2200)
DISTRICTS = [CHILONZOR, YUNUSOBOD, SERGELI]


def test_pin_resolves_to_the_containing_district() -> None:
    assert nearest_point(41.2760, 69.2060, DISTRICTS) == CHILONZOR.id


def test_pin_resolves_to_a_different_district() -> None:
    assert nearest_point(41.3660, 69.2880, DISTRICTS) == YUNUSOBOD.id


def test_no_candidates_yields_none() -> None:
    assert nearest_point(41.2750, 69.2050, []) is None


def test_pin_outside_the_service_area_is_refused() -> None:
    """Samarkand is 270 km away -- it must not snap to a Tashkent district."""
    assert nearest_point(39.6270, 66.9750, DISTRICTS, max_km=40.0) is None


def test_pin_inside_the_radius_is_accepted() -> None:
    assert nearest_point(41.2760, 69.2060, DISTRICTS, max_km=40.0) == CHILONZOR.id


def test_result_is_deterministic_regardless_of_candidate_order() -> None:
    forward = nearest_point(41.3000, 69.2500, DISTRICTS)
    backward = nearest_point(41.3000, 69.2500, list(reversed(DISTRICTS)))
    assert forward == backward


def test_to_float_handles_decimal_and_none() -> None:
    assert to_float(Decimal("41.2750")) == 41.275
    assert to_float(41.275) == 41.275
    assert to_float(None) is None
