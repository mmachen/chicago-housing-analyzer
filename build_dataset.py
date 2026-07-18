"""Build the enriched housing dataset (output/final_data.csv).

Reads the raw Redfin export, merges in previously generated data, then fills
in commute times, nearby amenities, crime scores, and affordable-housing
proximity for each property. Google Maps responses are cached in SQLite, so
re-runs only pay for new or stale data.

Usage:
    python build_dataset.py [--skip-commute] [--skip-places] [--mls 123,456] ...

Run with --help for the full list of options.
"""

from __future__ import annotations

import argparse
import datetime
import json
import time

import pandas as pd

from housing import affordable_housing, google_maps, scoring
from housing import crime as crime_module
from housing.cache import Cache
from housing.config import (
    AFFORDABLE_HOUSING_CSV,
    AMENITY_TYPES,
    CACHE_DB,
    COMMUTE_DESTINATIONS,
    COMMUTE_LOGIC_VERSION,
    COMMUTE_REQUIREMENTS,
    CRIME_RECENT_CSV,
    CTA_TRAIN_LINES,
    DEFAULT_CACHE_TTL_DAYS,
    DEFAULT_SCORE_WEIGHTS,
    DRIVING_DESTINATIONS,
    FINAL_DATA_CSV,
    GOOGLE_QUERIES_PER_SECOND,
    KEYWORD_AMENITIES,
    LANGUAGES_CSV,
    PLACES_LOGIC_VERSION,
    REDFIN_COLUMNS,
    REDFIN_RAW_CSV,
    SOCIOECONOMIC_CSV,
    crime_csv_path,
    load_google_api_key,
)
from housing.crime import CRIME_SCORE_COLUMNS
from housing.scoring import minmax_normalize


# --- CLI -------------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the housing dataset with optional sections and caching.")
    parser.add_argument("--mls", type=str, default="",
                        help="Comma-separated MLS IDs to process (others skipped).")
    parser.add_argument("--mls-file", type=str, default="",
                        help="Path to file with MLS IDs (one per line).")
    parser.add_argument("--skip-commute", action="store_true",
                        help="Skip commute time calculations.")
    parser.add_argument("--skip-places", action="store_true",
                        help="Skip nearby places/amenities calculations.")
    parser.add_argument("--skip-crime", action="store_true",
                        help="Skip crime score calculations.")
    parser.add_argument("--skip-affordable", action="store_true",
                        help="Skip affordable housing proximity calculations.")
    parser.add_argument("--force-crime", action="store_true",
                        help="Recompute crime scores even if already present "
                             "(use after running update_crime_data.py).")
    parser.add_argument("--ttl-days", type=int, default=DEFAULT_CACHE_TTL_DAYS,
                        help="TTL for cache entries in days.")
    parser.add_argument("--w-commute", type=float,
                        default=DEFAULT_SCORE_WEIGHTS["commute"],
                        help="Weight for commute score (0-1).")
    parser.add_argument("--w-crime", type=float,
                        default=DEFAULT_SCORE_WEIGHTS["crime"],
                        help="Weight for crime safety (0-1).")
    parser.add_argument("--w-amenities", type=float,
                        default=DEFAULT_SCORE_WEIGHTS["amenities"],
                        help="Weight for amenities (0-1).")
    parser.add_argument("--w-price", type=float,
                        default=DEFAULT_SCORE_WEIGHTS["price"],
                        help="Weight for value (inverse price per sqft) (0-1).")
    parser.add_argument("--w-bars", type=float,
                        default=DEFAULT_SCORE_WEIGHTS["bars"],
                        help="Penalty weight for nearby bar density (0-1).")
    parser.add_argument("--w-gun", type=float,
                        default=DEFAULT_SCORE_WEIGHTS["gun"],
                        help="Penalty weight for nearby gun incidents (0-1).")
    args, _ = parser.parse_known_args(argv)
    return args


def read_mls_filter(args: argparse.Namespace) -> set[str]:
    """Return the set of MLS IDs to process. Empty set means process all."""
    mls_ids: set[str] = set()
    if args.mls:
        mls_ids.update(x.strip() for x in args.mls.split(",") if x.strip())
    if args.mls_file:
        try:
            with open(args.mls_file, "r", encoding="utf-8") as f:
                mls_ids.update(line.strip() for line in f if line.strip())
        except OSError as e:
            print(f"Warning: failed to read MLS file {args.mls_file}: {e}")
    return mls_ids


# --- Data loading ----------------------------------------------------------

def standardize_location(location):
    """Normalize community area names for merging: 'CHI - Loop' -> 'loop'."""
    if pd.isna(location):
        return location
    location = str(location).lower()
    if location.startswith("chi - "):
        return location[6:]
    return location


def load_property_data() -> pd.DataFrame:
    """Load the raw Redfin export and merge in previously generated columns.

    Keeps all rows from the new export; expensive generated data (commutes,
    crime scores, ...) from the previous run is carried over by MLS ID so it
    doesn't have to be recomputed.
    """
    raw_df = pd.read_csv(REDFIN_RAW_CSV)
    raw_df.columns = REDFIN_COLUMNS
    # Keep MLS as a string to avoid scientific-notation/float issues.
    raw_df["MLS"] = raw_df["MLS"].astype(str)
    raw_df = raw_df[raw_df["ADDRESS"].notna() & raw_df["CITY"].notna()]

    try:
        out_df = pd.read_csv(FINAL_DATA_CSV, dtype={"MLS": str})
        generated_columns = out_df.columns.difference(raw_df.columns).tolist()
        if generated_columns:
            prop_df = pd.merge(out_df[generated_columns + ["MLS"]], raw_df,
                               on="MLS", how="right")
        else:
            prop_df = raw_df
    except FileNotFoundError:
        print("No existing output file found. Starting fresh with raw data.")
        prop_df = raw_df
    except Exception as e:
        print(f"Error reading output file: {e}\nStarting fresh with raw data.")
        prop_df = raw_df

    return prop_df.reset_index(drop=True)


def load_crime_data() -> pd.DataFrame:
    path = crime_csv_path()
    crime_df = pd.read_csv(path)
    crime_df.dropna(inplace=True)
    crime_df = crime_df.reset_index(drop=True)
    if path == CRIME_RECENT_CSV and "Date" in crime_df.columns:
        print(f"Crime data: {len(crime_df):,} incidents from {path.name} "
              f"({str(crime_df['Date'].min())[:10]} to "
              f"{str(crime_df['Date'].max())[:10]})")
    else:
        print(f"Crime data: {len(crime_df):,} incidents from {path.name} "
              f"(static extract -- run update_crime_data.py for fresh data)")
    return crime_df


def load_affordable_housing_data() -> pd.DataFrame:
    df = pd.read_csv(AFFORDABLE_HOUSING_CSV)
    df = df[["Address", "Property Type", "Latitude", "Longitude"]]
    df.columns = ["ADDRESS", "DESCRIPTION", "LATITUDE", "LONGITUDE"]
    df.dropna(inplace=True)
    # keep=False drops every row sharing a location, preventing over-counting.
    df.drop_duplicates(subset=["LATITUDE", "LONGITUDE"], keep=False, inplace=True)
    return df.reset_index(drop=True)


# --- Generated columns -----------------------------------------------------

def generated_column_dtypes() -> dict[str, str]:
    """Map every pipeline-generated column to its intended dtype."""
    columns: dict[str, str] = {}

    for dest in COMMUTE_DESTINATIONS:
        columns[f"COMMUTE_TIME_{dest}"] = "object"
        columns[f"COMMUTE_STEPS_{dest}"] = "object"
        columns[f"COMMUTE_NUM_STEPS_{dest}"] = "float"
        columns[f"WALKING_TIME_{dest}"] = "object"
        for line in CTA_TRAIN_LINES:
            columns[f"USES_{line}_LINE_{dest}"] = "bool"
        columns[f"COMMUTE_VERSION_{dest}"] = "int"
    for dest in DRIVING_DESTINATIONS:
        columns[f"DRIVE_TIME_{dest}"] = "object"

    for amenity in AMENITY_TYPES:
        prefix = amenity.upper()
        columns[f"{prefix}_CLOSEST"] = "object"
        columns[f"{prefix}_CLOSEST_DST"] = "float"
        columns[f"{prefix}_CLOSEST_WALK_TIME"] = "object"
        columns[f"{prefix}_WALK_NUM"] = "float"
        columns[f"{prefix}_LIST"] = "object"

    columns["AFFORDABLE_NUM"] = "float"
    columns["AFFORDABLE_DESC"] = "object"
    for col in CRIME_SCORE_COLUMNS:
        columns[col] = "float"
    columns["TOP_LANGUAGES"] = "object"
    return columns


def ensure_generated_columns(prop_df: pd.DataFrame) -> pd.DataFrame:
    """Create any missing generated columns and fix dtypes on existing ones.

    Pre-allocating columns with correct dtypes avoids pandas fragmentation
    warnings and dtype errors during row-by-row assignment. Nullable pandas
    dtypes (boolean/Int64) are used so missing values are representable.
    """
    for col, dtype in generated_column_dtypes().items():
        if dtype == "bool":
            final_dtype = "boolean"
        elif dtype == "int":
            final_dtype = "Int64"
        else:
            final_dtype = dtype

        if col not in prop_df.columns:
            prop_df[col] = pd.Series(dtype=final_dtype)
        elif str(prop_df[col].dtype) != str(final_dtype):
            prop_df[col] = prop_df[col].astype(final_dtype)

    # De-fragment after adding many columns.
    return prop_df.copy()


# --- Per-property updates --------------------------------------------------

def _next_monday_5pm() -> datetime.datetime:
    """Next Monday at 5 PM, for a peak-traffic driving estimate."""
    today = datetime.date.today()
    days_ahead = (0 - today.weekday() + 7) % 7  # 0 while it's still Monday
    if days_ahead == 0 and datetime.datetime.now().time() > datetime.time(17, 0):
        days_ahead = 7
    return datetime.datetime.combine(today + datetime.timedelta(days=days_ahead),
                                     datetime.time(17, 0))


def update_commutes(prop_df, i, home, gmaps, cache) -> int:
    """Fill missing/outdated commute data for row ``i``. Returns API calls made."""
    api_calls = 0
    for dest_name, dest_address in COMMUTE_DESTINATIONS.items():
        version_col = f"COMMUTE_VERSION_{dest_name}"
        current_version = prop_df.at[i, version_col]
        needs_update = (pd.isna(current_version)
                        or current_version < COMMUTE_LOGIC_VERSION)

        if needs_update:
            cache_key = f"v{COMMUTE_LOGIC_VERSION}|{home}|{dest_name}|transit"
            commute_info = cache.get(cache_key)

            # Entries cached before the train-line flags existed are stale.
            if commute_info and "USES_PINK_LINE" not in commute_info:
                print(f"  > Found old commute cache for {dest_name}. Refetching...")
                commute_info = None

            if commute_info is None:
                print(f"  > Cache miss for commute to {dest_name}. Calling API...")
                commute_info = google_maps.get_directions(
                    gmaps=gmaps, origin=home, destination=dest_address,
                    mode="transit")
                cache.set(cache_key, commute_info)
                api_calls += 1

            prop_df.at[i, version_col] = COMMUTE_LOGIC_VERSION
            prop_df.at[i, f"COMMUTE_TIME_{dest_name}"] = commute_info.get("COMMUTE_TIME")
            prop_df.at[i, f"COMMUTE_STEPS_{dest_name}"] = commute_info.get("COMMUTE_STEPS")
            prop_df.at[i, f"COMMUTE_NUM_STEPS_{dest_name}"] = commute_info.get("COMMUTE_NUM_STEPS")
            prop_df.at[i, f"WALKING_TIME_{dest_name}"] = commute_info.get("WALKING_TIME")
            for line in CTA_TRAIN_LINES:
                prop_df.at[i, f"USES_{line}_LINE_{dest_name}"] = \
                    commute_info.get(f"USES_{line}_LINE", False)

        # Some destinations also get a rush-hour driving estimate.
        if dest_name in DRIVING_DESTINATIONS:
            drive_col = f"DRIVE_TIME_{dest_name}"
            if pd.isnull(prop_df.at[i, drive_col]):
                cache_key = f"v{COMMUTE_LOGIC_VERSION}|{home}|{dest_name}|driving_5pm"
                drive_info = cache.get(cache_key)
                if drive_info is None:
                    drive_info = google_maps.get_directions(
                        gmaps=gmaps, origin=home, destination=dest_address,
                        mode="driving", departure_time=_next_monday_5pm())
                    cache.set(cache_key, drive_info)
                    api_calls += 1
                prop_df.at[i, drive_col] = drive_info.get("COMMUTE_TIME")

    return api_calls


def _is_amenity_missing(prop_df, i, prefix: str) -> bool:
    """True if any key amenity field is missing for row ``i``."""
    for suffix in ("_CLOSEST", "_CLOSEST_DST", "_CLOSEST_WALK_TIME",
                   "_WALK_NUM", "_LIST"):
        col = prefix + suffix
        if col not in prop_df.columns or pd.isna(prop_df.at[i, col]):
            return True
    return False


def update_amenities(prop_df, i, home_lat_lon, gmaps, cache) -> int:
    """Fill missing amenity data for row ``i``. Returns API calls made."""
    api_calls = 0
    for amenity, query in AMENITY_TYPES.items():
        prefix = amenity.upper()
        if not _is_amenity_missing(prop_df, i, prefix):
            continue
        try:
            cache_key = (f"v{PLACES_LOGIC_VERSION}|{round(home_lat_lon[0], 6)}"
                         f"|{round(home_lat_lon[1], 6)}|{amenity}")
            places_data = cache.get(cache_key)

            # Old cache entries stored a bare list; treat those as misses.
            if places_data is None or isinstance(places_data, list):
                if isinstance(places_data, list):
                    print(f"  > Found old cache format for {amenity}. Refetching...")
                else:
                    print(f"  > Cache miss for amenity '{amenity}'. Calling API...")
                places_data = google_maps.get_nearby_places(
                    gmaps=gmaps, location=home_lat_lon, query=query,
                    keyword_search=amenity in KEYWORD_AMENITIES)
                cache.set(cache_key, places_data)
                api_calls += 2  # nearby search + distance matrix
                time.sleep(0.25)

            if places_data:
                prop_df.at[i, f"{prefix}_CLOSEST"] = places_data.get("closest_name")
                prop_df.at[i, f"{prefix}_CLOSEST_DST"] = places_data.get("closest_distance_miles")
                prop_df.at[i, f"{prefix}_CLOSEST_WALK_TIME"] = places_data.get("closest_walk_duration")
                prop_df.at[i, f"{prefix}_WALK_NUM"] = places_data.get("count_within_half_mile", 0)
                nearby_list = places_data.get("nearby_places_list", [])
                prop_df.at[i, f"{prefix}_LIST"] = json.dumps(nearby_list) if nearby_list else None
            else:  # No places found at all.
                prop_df.at[i, f"{prefix}_CLOSEST"] = ""
                prop_df.at[i, f"{prefix}_CLOSEST_DST"] = None
                prop_df.at[i, f"{prefix}_CLOSEST_WALK_TIME"] = None
                prop_df.at[i, f"{prefix}_WALK_NUM"] = 0
                prop_df.at[i, f"{prefix}_LIST"] = None
        except Exception as e:
            print(f"Error processing {amenity}: {e}")
            prop_df.at[i, f"{prefix}_CLOSEST"] = ""
            prop_df.at[i, f"{prefix}_CLOSEST_DST"] = None
            prop_df.at[i, f"{prefix}_CLOSEST_WALK_TIME"] = None
            prop_df.at[i, f"{prefix}_WALK_NUM"] = 0
            prop_df.at[i, f"{prefix}_LIST"] = None

    return api_calls


# --- Community-area enrichment ---------------------------------------------

def _top_languages(row, language_cols) -> str:
    """Format the top 2 languages by share of the community-area population."""
    total_population = row.get("TOTAL")
    if pd.isna(total_population) or total_population <= 0:
        return ""

    shares = []
    for col in language_cols:
        value = row.get(col)
        if pd.notna(value):
            try:
                shares.append((col, float(value) / total_population * 100))
            except (ValueError, TypeError):
                continue

    shares.sort(key=lambda x: x[1], reverse=True)
    return ", ".join(f"{lang} ({pct:.1f}%)" for lang, pct in shares[:2])


def enrich_with_community_data(prop_df: pd.DataFrame) -> pd.DataFrame:
    """Merge socioeconomic and language data by community area, then compute
    the TOP_LANGUAGES summary."""
    eco_df = pd.read_csv(SOCIOECONOMIC_CSV)
    eco_df["COMMUNITY AREA NAME"] = eco_df["COMMUNITY AREA NAME"].apply(standardize_location)

    lang_df = pd.read_csv(LANGUAGES_CSV)
    lang_df["Community Area Name"] = lang_df["Community Area Name"].apply(standardize_location)

    prop_df = pd.merge(prop_df, eco_df, left_on="LOCATION",
                       right_on="COMMUNITY AREA NAME", how="left",
                       suffixes=("", "_eco"))
    prop_df.drop(columns=[c for c in prop_df if c.endswith("_eco")], inplace=True)

    prop_df = pd.merge(prop_df, lang_df, left_on="LOCATION",
                       right_on="Community Area Name", how="left",
                       suffixes=("", "_lang"))
    prop_df.drop(columns=[c for c in prop_df if c.endswith("_lang")], inplace=True)

    language_cols = [c for c in lang_df.columns
                     if c not in ("Community Area Name", "Community Area Number",
                                  "TOTAL", "ENGLISH", "NON-ENGLISH")]
    prop_df["TOP_LANGUAGES"] = prop_df.apply(
        lambda row: _top_languages(row, language_cols), axis=1)

    return prop_df


# --- Main pipeline ---------------------------------------------------------

def main(argv=None) -> None:
    args = parse_args(argv)
    mls_filter = read_mls_filter(args)

    prop_df = load_property_data()
    prop_df["LOCATION"] = prop_df["LOCATION"].apply(standardize_location)
    prop_df = ensure_generated_columns(prop_df)

    crime_df = None if args.skip_crime else load_crime_data()
    affordable_df = None if args.skip_affordable else load_affordable_housing_data()

    # The Google Maps client (and API key) is only needed for commutes/places.
    gmaps = None
    if not (args.skip_commute and args.skip_places):
        import googlemaps
        try:
            api_key = load_google_api_key()
        except RuntimeError as e:
            raise SystemExit(f"Error: {e}")
        gmaps = googlemaps.Client(key=api_key,
                                  queries_per_second=GOOGLE_QUERIES_PER_SECOND)

    commute_cache = Cache(db_path=CACHE_DB, table="commute_cache",
                          ttl_days=args.ttl_days)
    places_cache = Cache(db_path=CACHE_DB, table="places_cache",
                         ttl_days=args.ttl_days)

    n = len(prop_df)
    for i in range(n):
        if mls_filter and str(prop_df.at[i, "MLS"]) not in mls_filter:
            continue

        print(f"Percentage Complete: {round((i + 1) / n * 100, 2)}%")
        print(f"Processing property {i + 1} of {n}", flush=True)

        api_calls = 0
        home_address = f"{prop_df['ADDRESS'][i]} {prop_df['CITY'][i]}"
        home_lat_lon = [prop_df["LATITUDE"][i], prop_df["LONGITUDE"][i]]

        if not args.skip_commute:
            api_calls += update_commutes(prop_df, i, home_address, gmaps,
                                         commute_cache)
        if not args.skip_places:
            api_calls += update_amenities(prop_df, i, home_lat_lon, gmaps,
                                          places_cache)
        print(f"Total API calls for property {i + 1}: {api_calls}", flush=True)

        # Local (non-API) calculations, only done when data is missing.
        if not args.skip_affordable and pd.isnull(prop_df.at[i, "AFFORDABLE_NUM"]):
            features = affordable_housing.get_afford_features(home_lat_lon,
                                                              affordable_df)
            prop_df.at[i, "AFFORDABLE_NUM"] = features["NUM_AFFORDABLE_HOMES"]
            prop_df.at[i, "AFFORDABLE_DESC"] = features["AFFORDABLE_DESC"]

        if not args.skip_crime and (args.force_crime
                                    or pd.isnull(prop_df.at[i, "GUN_SCORE"])):
            features = crime_module.get_crime_features(home_lat_lon, crime_df)
            for col in CRIME_SCORE_COLUMNS:
                prop_df.at[i, col] = features[col]

    # Normalized 0-1 crime columns (1 = highest density in the dataset).
    for col in CRIME_SCORE_COLUMNS:
        prop_df[f"CRIME_{col.removesuffix('_SCORE')}"] = \
            minmax_normalize(prop_df[col], 0.0)

    prop_df = enrich_with_community_data(prop_df)

    # Drop legacy columns from older pipeline versions.
    legacy_cols = [c for c in prop_df.columns
                   if "_DRIVE" in c or "_SECOND_CLOSEST" in c]
    prop_df.drop(columns=legacy_cols, inplace=True, errors="ignore")

    # Numeric commute columns so the dashboard can sort on them.
    for dest in COMMUTE_REQUIREMENTS:
        prop_df[f"WALK_MINUTES_{dest}"] = pd.to_numeric(
            prop_df[f"WALKING_TIME_{dest}"].apply(scoring.duration_to_minutes),
            errors="coerce")
    for dest in DRIVING_DESTINATIONS:
        prop_df[f"DRIVE_MINUTES_{dest}"] = pd.to_numeric(
            prop_df[f"DRIVE_TIME_{dest}"].apply(scoring.duration_to_minutes),
            errors="coerce")
    transit_walk_cols = [f"WALK_MINUTES_{dest}"
                         for dest, req in COMMUTE_REQUIREMENTS.items()
                         if req.get("mode") != "drive"]
    prop_df["MAX_WALK_MINUTES"] = prop_df[transit_walk_cols].max(axis=1)

    weights = {"commute": args.w_commute, "crime": args.w_crime,
               "amenities": args.w_amenities, "price": args.w_price,
               "bars": args.w_bars, "gun": args.w_gun}
    prop_df["OVERALL_SCORE"] = scoring.compute_overall_score(prop_df, weights)

    FINAL_DATA_CSV.parent.mkdir(parents=True, exist_ok=True)
    prop_df.to_csv(FINAL_DATA_CSV, index=False)
    print("Data update complete!")


if __name__ == "__main__":
    main()
