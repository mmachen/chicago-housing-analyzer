"""Per-home neighborhood features computed from free local datasets.

Everything here is local math over already-downloaded data (see
update_area_data.py) -- no paid API calls. Each ``add_*`` function fills
columns on the property DataFrame in place.
"""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from housing.config import (
    BUS_STOP_RADIUS_MILES,
    CRIME_TREND_RADIUS_MILES,
    CTA_LINES_GEOJSON,
    NEAR_L_TRACKS_MILES,
    RODENT_RADIUS_MILES,
)
from housing.geo import haversine_miles

# --- Facing direction -------------------------------------------------------

# Streets that cut diagonally across the grid, where the even/odd rule
# doesn't map to a compass direction.
_DIAGONAL_STREETS = (
    "lincoln", "milwaukee", "elston", "clybourn", "ogden", "archer", "grand",
    "ridge", "clark", "broadway", "vincennes", "south chicago", "ewing",
    "higgins", "caldwell", "northwest hwy",
)

_ADDRESS_RE = re.compile(r"^\s*(\d+)\s+([NSEW])\s+(.+)$", re.IGNORECASE)


def facing_direction(address) -> str:
    """Infer which way a home faces from Chicago's street grid.

    Chicago's 1909 renumbering puts even addresses on the west side of
    north-south streets and the north side of east-west streets, and streets
    prefixed N/S run north-south while E/W streets run east-west. So an
    even-numbered home on a N-S street sits on the west side and faces east.
    A heuristic: diagonal streets are flagged, and condo units within a
    building can face any direction.
    """
    if not isinstance(address, str):
        return ""
    match = _ADDRESS_RE.match(address)
    if not match:
        return ""
    number, prefix = int(match.group(1)), match.group(2).upper()
    street = match.group(3).lower()
    if any(diag in street for diag in _DIAGONAL_STREETS):
        return "Diagonal street"
    even = number % 2 == 0
    if prefix in ("N", "S"):  # north-south street
        return "East" if even else "West"
    return "South" if even else "North"  # east-west street


def add_facing_direction(prop_df: pd.DataFrame) -> None:
    prop_df["FACING"] = prop_df["ADDRESS"].apply(facing_direction)


# --- O'Hare noise (heuristic) -----------------------------------------------

_OHARE_LAT, _OHARE_LON = 41.9803, -87.9090


def ohare_noise(lat, lon) -> str:
    """Rough O'Hare jet-noise exposure.

    O'Hare's parallel runways run east-west, so arrival/departure paths
    extend east over the northwest side, roughly between latitudes 41.94
    and 42.01. Distance plus that corridor gives a coarse High/Moderate/Low
    label -- an approximation, not official noise-contour data.
    """
    if pd.isna(lat) or pd.isna(lon):
        return ""
    distance = float(haversine_miles(_OHARE_LAT, _OHARE_LON, lat, lon))
    in_corridor = 41.94 <= lat <= 42.01 and lon > _OHARE_LON
    if in_corridor and distance < 6:
        return "High (approx)"
    if in_corridor and distance < 11:
        return "Moderate (approx)"
    return "Low"


def add_ohare_noise(prop_df: pd.DataFrame) -> None:
    prop_df["OHARE_NOISE"] = [
        ohare_noise(lat, lon)
        for lat, lon in zip(prop_df["LATITUDE"], prop_df["LONGITUDE"])
    ]


# --- Bus / Metra / schools / rodents (nearest-point features) ---------------

def _each_home(prop_df):
    for i in prop_df.index:
        lat, lon = prop_df.at[i, "LATITUDE"], prop_df.at[i, "LONGITUDE"]
        if pd.notna(lat) and pd.notna(lon):
            yield i, lat, lon


def add_bus_features(prop_df: pd.DataFrame, bus_df: pd.DataFrame) -> None:
    lats, lons = bus_df["LATITUDE"].values, bus_df["LONGITUDE"].values
    for i, lat, lon in _each_home(prop_df):
        distances = haversine_miles(lat, lon, lats, lons)
        nearby = distances <= BUS_STOP_RADIUS_MILES
        routes: set[str] = set()
        for stop_routes in bus_df.loc[nearby, "ROUTES"].dropna():
            routes.update(str(stop_routes).split(","))
        prop_df.at[i, "BUS_STOPS_NEARBY"] = int(nearby.sum())
        prop_df.at[i, "BUS_STOP_CLOSEST_DST"] = round(float(distances.min()), 3)
        prop_df.at[i, "BUS_ROUTES_NEARBY"] = ",".join(
            sorted(routes, key=lambda r: (len(r), r)))


def add_metra_features(prop_df: pd.DataFrame, metra_df: pd.DataFrame) -> None:
    lats, lons = metra_df["LATITUDE"].values, metra_df["LONGITUDE"].values
    for i, lat, lon in _each_home(prop_df):
        distances = haversine_miles(lat, lon, lats, lons)
        closest = int(np.argmin(distances))
        prop_df.at[i, "METRA_CLOSEST"] = metra_df["STATION"].iloc[closest]
        prop_df.at[i, "METRA_CLOSEST_DST"] = round(float(distances[closest]), 2)


def add_school_features(prop_df: pd.DataFrame, schools_df: pd.DataFrame) -> None:
    """Nearest CPS elementary that has an attendance boundary -- in Chicago's
    grid this is usually (not always) the assigned neighborhood school."""
    boundary_schools = schools_df[schools_df["HAS_BOUNDARY"]].reset_index(drop=True)
    if boundary_schools.empty:
        return
    lats = boundary_schools["LATITUDE"].values
    lons = boundary_schools["LONGITUDE"].values
    for i, lat, lon in _each_home(prop_df):
        distances = haversine_miles(lat, lon, lats, lons)
        closest = int(np.argmin(distances))
        prop_df.at[i, "NEAREST_ELEMENTARY"] = boundary_schools["SCHOOL"].iloc[closest]
        prop_df.at[i, "NEAREST_ELEMENTARY_RATING"] = boundary_schools["RATING"].iloc[closest]
        prop_df.at[i, "NEAREST_ELEMENTARY_DST"] = round(float(distances[closest]), 2)


def add_rodent_features(prop_df: pd.DataFrame, rodent_df: pd.DataFrame) -> None:
    lats, lons = rodent_df["LATITUDE"].values, rodent_df["LONGITUDE"].values
    for i, lat, lon in _each_home(prop_df):
        distances = haversine_miles(lat, lon, lats, lons)
        prop_df.at[i, "RODENT_NUM"] = int((distances <= RODENT_RADIUS_MILES).sum())


# --- Distance to CTA 'L' tracks ---------------------------------------------

def load_l_track_segments():
    """Return (A, B) arrays of segment endpoints (lon, lat) for all L tracks."""
    data = json.loads(CTA_LINES_GEOJSON.read_text(encoding="utf-8"))
    starts, ends = [], []
    for feature in data["features"]:
        geometry = feature.get("geometry") or {}
        lines = (geometry.get("coordinates", [])
                 if geometry.get("type") == "MultiLineString"
                 else [geometry.get("coordinates", [])])
        for line in lines:
            arr = np.asarray(line, dtype=float)
            if len(arr) >= 2:
                starts.append(arr[:-1])
                ends.append(arr[1:])
    return np.vstack(starts), np.vstack(ends)


def add_l_track_distance(prop_df: pd.DataFrame, segments) -> None:
    """Minimum distance from each home to any L track segment.

    Uses a local equirectangular projection (miles) around each home, which
    is accurate at these distances.
    """
    A, B = segments
    for i, lat, lon in _each_home(prop_df):
        kx = 69.17 * np.cos(np.radians(lat))  # miles per degree longitude
        ky = 69.05                            # miles per degree latitude
        ax, ay = (A[:, 0] - lon) * kx, (A[:, 1] - lat) * ky
        bx, by = (B[:, 0] - lon) * kx, (B[:, 1] - lat) * ky
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        t = np.clip(-(ax * dx + ay * dy) / np.where(length_sq == 0, 1, length_sq), 0, 1)
        cx, cy = ax + t * dx, ay + t * dy
        distance = float(np.sqrt(cx * cx + cy * cy).min())
        prop_df.at[i, "L_TRACK_DST_MI"] = round(distance, 3)
        prop_df.at[i, "NEAR_L_TRACKS"] = bool(distance <= NEAR_L_TRACKS_MILES)


# --- Crime trend -------------------------------------------------------------

def add_crime_trend(prop_df: pd.DataFrame, crime_df: pd.DataFrame) -> None:
    """Year-over-year change in incidents within CRIME_TREND_RADIUS_MILES.

    Needs ~24 months of crime data (run update_crime_data.py); with less
    history the columns are left empty rather than computed misleadingly.
    """
    if "Date" not in crime_df.columns:
        return
    dates = pd.to_datetime(crime_df["Date"], errors="coerce")
    latest = dates.max()
    if pd.isna(latest):
        return
    recent_mask = (dates > latest - pd.DateOffset(months=12)).values
    prior_mask = ((dates <= latest - pd.DateOffset(months=12))
                  & (dates > latest - pd.DateOffset(months=24))).values
    if prior_mask.sum() < 1000:  # not enough history for a fair comparison
        print("Crime trend skipped: need ~24 months of crime data "
              "(python update_crime_data.py --months 24).")
        return

    lats, lons = crime_df["Latitude"].values, crime_df["Longitude"].values
    for i, lat, lon in _each_home(prop_df):
        within = haversine_miles(lat, lon, lats, lons) <= CRIME_TREND_RADIUS_MILES
        recent = int((within & recent_mask).sum())
        prior = int((within & prior_mask).sum())
        if prior > 0:
            prop_df.at[i, "CRIME_TREND_PCT"] = round((recent - prior) / prior * 100, 1)
