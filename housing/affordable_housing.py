"""Affordable-housing proximity features from the Chicago Data Portal."""

from __future__ import annotations

import pandas as pd

from housing.config import AFFORDABLE_RADIUS_MILES
from housing.geo import haversine_miles


def get_afford_features(home_lat_lon, afford_df: pd.DataFrame) -> dict:
    """Count affordable-housing developments near one home.

    Args:
        home_lat_lon: (latitude, longitude) of the home.
        afford_df: Developments with 'DESCRIPTION', 'LATITUDE', and
            'LONGITUDE' columns.

    Returns:
        Dict with the number of developments within AFFORDABLE_RADIUS_MILES
        and a comma-separated list of their unique types.
    """
    home_lat, home_lon = home_lat_lon

    distances = haversine_miles(home_lat, home_lon,
                                afford_df["LATITUDE"].values,
                                afford_df["LONGITUDE"].values)

    nearby = afford_df.loc[distances < AFFORDABLE_RADIUS_MILES, "DESCRIPTION"]

    return {
        "NUM_AFFORDABLE_HOMES": len(nearby),
        "AFFORDABLE_DESC": ",".join(nearby.unique()),
    }
