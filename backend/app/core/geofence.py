"""Server-side geofence logic (DB-agnostic; reference geofence 50 m)."""
from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres between two WGS84 points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def distance_to_point_m(
    lat: float, lng: float, centre_lat: float, centre_lng: float
) -> float:
    return haversine_m(lat, lng, centre_lat, centre_lng)


def within_geofence(
    lat: float,
    lng: float,
    centre_lat: float,
    centre_lng: float,
    radius_m: float = 50.0,
) -> tuple[bool, float]:
    """Return (inside, distance_m) for a point against a circular geofence."""
    dist = haversine_m(lat, lng, centre_lat, centre_lng)
    return dist <= radius_m, dist


def validate_lat_lng(lat: float, lng: float) -> bool:
    return -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0
