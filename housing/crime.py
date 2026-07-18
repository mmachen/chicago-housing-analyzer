"""Crime-density scores from a Chicago Data Portal crime extract.

Each home gets one score per crime category. A score sums ``exp(-distance)``
over all matching incidents within CRIME_RADIUS_MILES, so nearby incidents
count more than distant ones. Raw scores are normalized later in the pipeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from housing.config import CRIME_RADIUS_MILES
from housing.geo import haversine_miles

CRIME_SCORE_COLUMNS = (
    "GUN_SCORE", "DRUG_SCORE", "MURDER_SCORE",
    "THEFT_SCORE", "HUMAN_SCORE", "OTHER_SCORE",
)

_GUN_TYPES = ("WEAPONS VIOLATION", "CONCEALED CARRY LICENSE VIOLATION")
_GUN_DESCRIPTION_PATTERN = "HANDGUN|ARMOR|GUN|FIREARM|AMMO|AMMUNITION|RIFLE"
_DRUG_TYPES = ("NARCOTICS", "OTHER NARCOTIC VIOLATION")
_THEFT_TYPES = ("BURGLARY", "CRIM SEXUAL ASSAULT", "ASSAULT", "BATTERY",
                "ROBBERY", "MOTOR VEHICLE THEFT", "THEFT")
_HUMAN_TYPES = ("OFFENSE INVOLVING CHILDREN", "SEX OFFENSE", "OBSCENITY",
                "KIDNAPPING", "PROSTITUTION", "HUMAN TRAFFICKING",
                "PUBLIC INDECENCY", "STALKING")


def get_crime_features(home_lat_lon, crime_df: pd.DataFrame) -> dict:
    """Compute distance-weighted crime scores for one home.

    Args:
        home_lat_lon: (latitude, longitude) of the home.
        crime_df: Crime incidents with 'Primary Type', 'Description',
            'Latitude', and 'Longitude' columns.

    Returns:
        Dict with one value per column in CRIME_SCORE_COLUMNS.
    """
    home_lat, home_lon = home_lat_lon

    distances = haversine_miles(home_lat, home_lon,
                                crime_df["Latitude"].values,
                                crime_df["Longitude"].values)

    nearby = pd.DataFrame({
        "TYPE": crime_df["Primary Type"].values,
        "DESCRIPTION": crime_df["Description"].values,
        "DISTANCE": distances,
    })
    nearby = nearby[nearby["DISTANCE"] < CRIME_RADIUS_MILES]

    if nearby.empty:
        return {col: 0 for col in CRIME_SCORE_COLUMNS}

    # Closer incidents contribute more: weight = exp(-distance in miles).
    decay = np.exp(-nearby["DISTANCE"])

    gun_mask = (nearby["TYPE"].isin(_GUN_TYPES)
                | nearby["DESCRIPTION"].str.contains(_GUN_DESCRIPTION_PATTERN,
                                                     na=False, case=False))
    drug_mask = nearby["TYPE"].isin(_DRUG_TYPES)
    murder_mask = nearby["TYPE"] == "HOMICIDE"
    theft_mask = nearby["TYPE"].isin(_THEFT_TYPES)
    human_mask = nearby["TYPE"].isin(_HUMAN_TYPES)
    other_mask = ~(gun_mask | drug_mask | murder_mask | theft_mask | human_mask)

    return {
        "GUN_SCORE": decay[gun_mask].sum(),
        "DRUG_SCORE": decay[drug_mask].sum(),
        "MURDER_SCORE": decay[murder_mask].sum(),
        "THEFT_SCORE": decay[theft_mask].sum(),
        "HUMAN_SCORE": decay[human_mask].sum(),
        "OTHER_SCORE": decay[other_mask].sum(),
    }
