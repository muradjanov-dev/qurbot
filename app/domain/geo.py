"""Pure geography helpers.

Kept separate from the optimizer's distance maths because this answers a
different question: not "how far is this shop" but "which of our service areas
is this pin in", which is what turns a dropped location pin into a district and
therefore into delivery rules.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.domain.optimizer.haversine import haversine_km


@dataclass(frozen=True)
class GeoPoint:
    """A named place with coordinates -- a district centroid, typically."""

    id: int
    lat: float
    lng: float


def nearest_point(
    lat: float,
    lng: float,
    candidates: Sequence[GeoPoint],
    max_km: float | None = None,
) -> int | None:
    """Id of the closest candidate, or None if there is none within `max_km`.

    `max_km` guards against silently assigning a pin dropped in another region
    to the nearest Tashkent district: better to have no district and fall back
    to a default delivery rule than to quote a fee for the wrong city.

    Ties resolve to the lowest id so the same pin always yields the same
    district.
    """
    if not candidates:
        return None

    # Sorting by (distance, id) rather than tracking a running minimum keeps
    # the tie-break explicit: equal distances always resolve to the lower id.
    # haversine_km is None-tolerant for missing shop coordinates; here both
    # points are always known, so a None distance would mean bad data and the
    # candidate is skipped rather than ranked as "zero km away".
    measured = [
        (km, p.id)
        for p, km in ((p, haversine_km(lat, lng, p.lat, p.lng)) for p in candidates)
        if km is not None
    ]
    if not measured:
        return None
    ranked = sorted(measured, key=lambda pair: (pair[0], pair[1]))
    best_km, best_id = ranked[0]
    if max_km is not None and best_km > max_km:
        return None
    return best_id


def to_float(value: Decimal | float | None) -> float | None:
    """Coordinates arrive as Decimal from the database and float from Telegram."""
    if value is None:
        return None
    return float(value)
