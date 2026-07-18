"""Geodesic distance helpers shared across the pipeline."""

from __future__ import annotations

import numpy as np

EARTH_RADIUS_MILES = 6373.0 * 0.62137


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles between two points.

    Accepts scalars or numpy arrays, so a single home can be compared against
    an entire column of coordinates in one call.
    """
    lat1_rad, lon1_rad = np.radians(lat1), np.radians(lon1)
    lat2_rad, lon2_rad = np.radians(lat2), np.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return EARTH_RADIUS_MILES * c
