
import extra_programs as helper
import pandas as pd 
from math import exp 
import numpy as np
def get_afford_features(redfinHome_LatLon, affordSet):
    """
    ##################################################################
    ###    This code calculates if housing developments are near
    ###    the home, using Chicago Data Portal. 
    ###    _________________________________________________________
    ###    INPUT:    redfinHome_LatLon - List of latitude / longitude
    ###              affordSet - Pandas DataFrame of affordable homes 
    ###    OUTPUT:   Dictionary
    ###################################################################
    """
    home_lat, home_lon = redfinHome_LatLon

    # Vectorized distance calculation
    R = 6373.0 * 0.62137  # Earth radius in miles
    lat1_rad = np.radians(home_lat)
    lon1_rad = np.radians(home_lon)
    lat2_rad = np.radians(affordSet['LATITUDE'].values)
    lon2_rad = np.radians(affordSet['LONGITUDE'].values)

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = np.sin(dlat / 2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    distances = R * c

    # Create a temporary DataFrame with distances
    tempDistance = affordSet[['DESCRIPTION']].copy()
    tempDistance['DISTANCE'] = distances

    # Restrict homes to 0.5 Miles
    tempDistance = tempDistance[tempDistance['DISTANCE'] < 0.5]
    unique_types = tempDistance["DESCRIPTION"].unique()

    return {"NUM_AFFORDABLE_HOMES": len(tempDistance),
            "AFFORDABLE_DESC": ",".join(unique_types)}
