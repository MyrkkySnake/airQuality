"""
Geographic utility functions.
Haversine distance, nearest-sensor lookup, IDW interpolation.
"""

import math
from typing import Optional


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Return great-circle distance in kilometres between two WGS-84 points.
    Uses the Haversine formula — accurate for distances < few thousand km.
    """
    R = 6371.0  # Earth radius km

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def find_nearest_sensor(user_lat: float, user_lon: float, sensors: list[dict]) -> Optional[dict]:
    """
    Given a list of sensor dicts with keys {lat, lon, ...}, return the one
    closest to (user_lat, user_lon).  Returns None if list is empty.
    """
    if not sensors:
        return None

    return min(
        sensors,
        key=lambda s: haversine_km(user_lat, user_lon, s["lat"], s["lon"]),
    )


def idw_interpolate(
    query_lat: float,
    query_lon: float,
    points: list[dict],  # [{lat, lon, value}]
    power: float = 2.0,
    max_distance_km: float = 10.0,
) -> Optional[float]:
    """
    Inverse Distance Weighting interpolation.

    Args:
        query_lat / query_lon: target location.
        points: list of dicts with lat, lon, value keys.
        power: IDW exponent (2 is standard).
        max_distance_km: ignore points beyond this radius.

    Returns:
        Interpolated value, or None if no nearby points exist.
    """
    weighted_sum = 0.0
    weight_total = 0.0

    for p in points:
        d = haversine_km(query_lat, query_lon, p["lat"], p["lon"])
        if d > max_distance_km:
            continue
        if d < 1e-6:          # Query is on top of a sensor — return its value
            return p["value"]
        w = 1.0 / (d ** power)
        weighted_sum += w * p["value"]
        weight_total += w

    if weight_total == 0:
        return None

    return weighted_sum / weight_total
