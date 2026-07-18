"""Central configuration for the housing pipeline and web app.

File paths, commute destinations, amenity definitions, and scoring defaults
all live here so they can be tuned without touching the pipeline code.

Note: commute destination names and amenity names become part of the generated
column names (e.g. ``COMMUTE_TIME_work_Mike``, ``GROCERY_CLOSEST``), which the
dashboard template reads. Renaming an entry orphans previously generated data.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Directories and files -------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data_sets"
OUTPUT_DIR = PROJECT_ROOT / "output"
CACHE_DIR = PROJECT_ROOT / "cache"

REDFIN_RAW_CSV = DATA_DIR / "RedFin_raw_data.csv"
CRIME_CSV = DATA_DIR / "Crimes_-_202103.csv"  # static fallback extract
CRIME_RECENT_CSV = DATA_DIR / "Crimes_recent.csv"  # written by update_crime_data.py
AFFORDABLE_HOUSING_CSV = DATA_DIR / "Affordable_Rental_Housing_Developments.csv"
SOCIOECONOMIC_CSV = DATA_DIR / "socioeconomic_indicators.csv"
LANGUAGES_CSV = DATA_DIR / "languages_spoken.csv"

FINAL_DATA_CSV = OUTPUT_DIR / "final_data.csv"
CACHE_DB = CACHE_DIR / "cache.db"


def crime_csv_path() -> Path:
    """Prefer the refreshed portal download; fall back to the static extract."""
    return CRIME_RECENT_CSV if CRIME_RECENT_CSV.exists() else CRIME_CSV

# Column names assigned to the raw Redfin export, in file order.
REDFIN_COLUMNS = [
    "SALE_TYPE", "SOLD_DATE", "PROPERTY_TYPE", "ADDRESS", "CITY", "STATE",
    "ZIP", "PRICE", "BEDS", "BATHS", "LOCATION", "SQFT", "LOT_SIZE", "YEAR",
    "DAY_ON_MARKET", "PRICE_PER_SQFT", "HOA", "STATUS", "NEXT_OPEN_S",
    "NEXT_OPEN_E", "URL", "SOURCE", "MLS", "FAVORITE", "INTERESTED",
    "LATITUDE", "LONGITUDE",
]

# --- Redfin search ---------------------------------------------------------

# Region for automated listing pulls (redfin.com/city/29470/IL/Chicago).
REDFIN_REGION_ID = 29470
REDFIN_REGION_TYPE = 6  # 6 = city

# Search filters applied server-side by Redfin. Garage must be filtered here
# because the CSV export has no parking column.
REDFIN_SEARCH_FILTERS = {
    "min_price": 700_000,
    "max_price": 1_400_000,
    "num_beds": 3,   # minimum bedrooms
    "num_baths": 2,  # minimum bathrooms
    "gar": "true",   # must have a garage
}

# Property types to include: 1=house, 2=condo, 3=townhouse, 4=multi-family.
REDFIN_PROPERTY_TYPES = "1,2,3,4"

# --- Google Maps API -------------------------------------------------------

API_KEY_ENV_VAR = "GOOGLE_MAPS_API_KEY"
API_KEY_FILE = PROJECT_ROOT / "delete" / "input.txt"
GOOGLE_QUERIES_PER_SECOND = 15


def load_google_api_key() -> str:
    """Return the Google Maps API key from the environment or the key file."""
    key = os.environ.get(API_KEY_ENV_VAR, "").strip()
    if key:
        return key
    try:
        return API_KEY_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise RuntimeError(
            f"Google Maps API key not found. Set the {API_KEY_ENV_VAR} "
            f"environment variable or create {API_KEY_FILE} containing the key."
        ) from None


# --- Commutes --------------------------------------------------------------

COMMUTE_DESTINATIONS = {
    "work_Mike": "320 S Canal St, Chicago, IL",
    "work_Xixi": "100 N Carpenter St, Chicago, IL",
    "school_Hana": "4929 N Sawyer Ave, Chicago, IL",
}

# Destinations that also get a rush-hour driving estimate (DRIVE_TIME_<name>).
DRIVING_DESTINATIONS = ("school_Hana",)

# Destinations whose transit time feeds the commute part of OVERALL_SCORE.
SCORED_COMMUTE_DESTINATIONS = ("work_Mike", "work_Xixi", "school_Hana")

# CTA train lines flagged per commute (USES_<line>_LINE_<destination>).
CTA_TRAIN_LINES = ("BROWN", "RED", "BLUE", "PINK", "GREEN", "ORANGE", "PURPLE")

# Bump to force a refresh of all commute data on the next pipeline run.
COMMUTE_LOGIC_VERSION = 2

# --- Amenities -------------------------------------------------------------

# Internal name -> Google Places query. Names listed in KEYWORD_AMENITIES are
# searched by keyword (brand names); the rest use a Places "type" search.
AMENITY_TYPES = {
    "grocery": "grocery_or_supermarket",
    "restaurant": "restaurant",
    "liquor": "liquor_store",
    "bars": "bar",
    "parks": "park",
    "chicago_public_library": "Chicago Public Library",
    "whole_foods": "Whole Foods",
    "trader_joes": "Trader Joe's",
}

KEYWORD_AMENITIES = {"chicago_public_library", "whole_foods", "trader_joes"}

# Amenities counted toward the amenities part of OVERALL_SCORE.
SCORED_AMENITIES = ("grocery", "restaurant", "parks", "chicago_public_library")

# Bump to force a refresh of all places/amenity data on the next pipeline run.
PLACES_LOGIC_VERSION = 2

PLACES_SEARCH_RADIUS_METERS = 3200  # ~2 miles
WALKABLE_RADIUS_MILES = 0.5

# --- Local dataset radii ---------------------------------------------------

CRIME_RADIUS_MILES = 2.0
AFFORDABLE_RADIUS_MILES = 0.5

# --- Caching and scoring ---------------------------------------------------

DEFAULT_CACHE_TTL_DAYS = 14

# Positive components sum to 1; "bars" and "gun" are penalties subtracted
# from the total (avoid homes near bars and gun incidents).
DEFAULT_SCORE_WEIGHTS = {
    "commute": 0.4,
    "crime": 0.3,
    "amenities": 0.2,
    "price": 0.1,
    "bars": 0.1,
    "gun": 0.15,
}
