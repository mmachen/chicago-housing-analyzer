
import extra_programs as helper
import pandas as pd 
from math import exp 
import numpy as np

def get_crime_features(redfinHome_LatLon, crimeSet):
    """
    ##################################################################
    ###    This code calculates crime scores using Chicago's Data
    ###    Portal API. 
    ###    _________________________________________________________
    ###    INPUT:    redfinHome_LatLon - List of latitude / longitude
    ###              crimeList - Pandas DataFrame of crimes 
    ###    OUTPUT:   Dictionary
    ###################################################################
    """
    home_lat, home_lon = redfinHome_LatLon

    # Vectorized distance calculation
    R = 6373.0 * 0.62137  # Earth radius in miles
    lat1_rad = np.radians(home_lat)
    lon1_rad = np.radians(home_lon)
    lat2_rad = np.radians(crimeSet['Latitude'].values)
    lon2_rad = np.radians(crimeSet['Longitude'].values)

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = np.sin(dlat / 2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    distances = R * c

    # Create a temporary DataFrame with distances
    tempDistance = crimeSet[['Primary Type', 'Description']].copy()
    tempDistance.columns = ['TYPE', 'DESCRIPTION']
    tempDistance['DISTANCE'] = distances

    # Restrict Crimes to 2 Miles
    tempDistance = tempDistance[tempDistance['DISTANCE'] < 2].copy()

    if tempDistance.empty:
        return {"GUN_SCORE": 0, "DRUG_SCORE": 0, "MURDER_SCORE": 0, "THEFT_SCORE": 0, "HUMAN_SCORE": 0, "OTHER_SCORE": 0}

    # Calculate decay factor for all nearby crimes
    tempDistance['DECAY'] = np.exp(-tempDistance['DISTANCE'])

    # Define crime categories using boolean masks
    gun_mask = tempDistance['TYPE'].isin(["WEAPONS VIOLATION", "CONCEALED CARRY LICENSE VIOLATION"]) | \
               tempDistance['DESCRIPTION'].str.contains("HANDGUN|ARMOR|GUN|FIREARM|AMMO|AMMUNITION|RIFLE", na=False, case=False)
    drug_mask = tempDistance['TYPE'].isin(["NARCOTICS", "OTHER NARCOTIC VIOLATION"])
    murder_mask = tempDistance['TYPE'] == "HOMICIDE"
    theft_mask = tempDistance['TYPE'].isin(["BURGLARY", "CRIM SEXUAL ASSAULT", "ASSAULT", "BATTERY", "ROBBERY", "MOTOR VEHICLE THEFT", "THEFT"])
    human_mask = tempDistance['TYPE'].isin(["OFFENSE INVOLVING CHILDREN", "SEX OFFENSE", "OBSCENITY", "KIDNAPPING", "PROSTITUTION", "HUMAN TRAFFICKING", "PUBLIC INDECENCY", "STALKING"])
    
    # Calculate scores by summing the decay factor for each category
    gunScore = tempDistance.loc[gun_mask, 'DECAY'].sum()
    drugScore = tempDistance.loc[drug_mask, 'DECAY'].sum()
    murderScore = tempDistance.loc[murder_mask, 'DECAY'].sum()
    theftScore = tempDistance.loc[theft_mask, 'DECAY'].sum()
    humanScore = tempDistance.loc[human_mask, 'DECAY'].sum()

    # Any crime not in the above categories falls into 'other'
    categorized_mask = gun_mask | drug_mask | murder_mask | theft_mask | human_mask
    otherScore = tempDistance.loc[~categorized_mask, 'DECAY'].sum()

    return {
        "GUN_SCORE": gunScore, "DRUG_SCORE": drugScore, "MURDER_SCORE": murderScore,
        "THEFT_SCORE": theftScore, "HUMAN_SCORE": humanScore, "OTHER_SCORE": otherScore
    }
