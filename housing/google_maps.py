"""Google Maps API wrappers: transit/driving directions and nearby places.

All functions take an initialized ``googlemaps.Client`` and are wrapped with
retry logic for rate-limit errors. On unrecoverable failure they return an
empty result rather than raising, so one bad property doesn't kill a long
pipeline run.
"""

from __future__ import annotations

import functools
import re
import time

import googlemaps

from housing.config import CTA_TRAIN_LINES, PLACES_SEARCH_RADIUS_METERS, WALKABLE_RADIUS_MILES
from housing.geo import haversine_miles

_HTML_TAG_RE = re.compile(r"<[^<]+?>")

# Result returned when directions cannot be fetched.
EMPTY_DIRECTIONS = {
    "COMMUTE_TIME": None,
    "COMMUTE_STEPS": None,
    "COMMUTE_NUM_STEPS": None,
    "WALKING_TIME": None,
    **{f"USES_{line}_LINE": False for line in CTA_TRAIN_LINES},
}


def retry_on_api_error(max_retries: int = 3, initial_delay: float = 1):
    """Retry on Google rate-limit/denial errors with exponential backoff.

    If all retries fail, returns an empty result appropriate for the wrapped
    function instead of raising.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except googlemaps.exceptions.ApiError as e:
                    if e.status in ("REQUEST_DENIED", "OVER_QUERY_LIMIT"):
                        if attempt < max_retries - 1:
                            print(f"API error ({e.status}) on attempt {attempt + 1} "
                                  f"for {func.__name__}. Retrying in {delay}s...")
                            time.sleep(delay)
                            delay *= 2
                        else:
                            print(f"API error ({e.status}) on final attempt "
                                  f"for {func.__name__}. Failing gracefully.")
                    else:
                        print(f"Unrecoverable API error in {func.__name__}: {e}")
                except Exception as e:
                    print(f"Unexpected error in {func.__name__}: {e}")

            return dict(EMPTY_DIRECTIONS) if "directions" in func.__name__ else {}
        return wrapper
    return decorator


def _transit_step_instruction(step: dict) -> tuple[str, str, str]:
    """Build a readable instruction for a transit step.

    Returns (instruction, line_name_lower, line_short_name_lower).
    """
    details = step["transit_details"]
    line = details.get("line", {})
    vehicle_type = line.get("vehicle", {}).get("type", "")  # e.g. 'BUS', 'SUBWAY'

    line_name = line.get("name", "")
    line_short_name = line.get("short_name", "")
    headsign = details.get("headsign", "")

    parts = ["Take"]
    if vehicle_type == "BUS" and line_short_name:
        parts.append(f"bus {line_short_name}")
    elif line_name:
        parts.append(f"the {line_name}")
    else:
        parts.append("the transit")
    if headsign:
        parts.append(f"towards {headsign}")

    return " ".join(parts), line_name.lower(), line_short_name.lower()


@retry_on_api_error()
def get_directions(gmaps: googlemaps.Client, origin: str, destination: str,
                   mode: str = "transit", departure_time=None) -> dict:
    """Fetch directions and summarize them for the dataset.

    Args:
        gmaps: An initialized Google Maps client.
        origin: Home address.
        destination: Destination address.
        mode: 'transit' or 'driving'.
        departure_time: Optional datetime (or "now") for traffic/schedule
            estimates. Defaults to "now" for transit.

    Returns:
        Dict with total time, step-by-step summary, walking time, and a
        USES_<line>_LINE flag for each CTA train line.
    """
    if departure_time is None:
        departure_time = "now" if mode == "transit" else None

    directions = gmaps.directions(origin, destination, mode=mode,
                                  departure_time=departure_time)
    if not directions:
        return dict(EMPTY_DIRECTIONS)

    leg = directions[0]["legs"][0]

    steps = []
    line_flags = {line: False for line in CTA_TRAIN_LINES}
    total_walking_seconds = 0

    for step in leg["steps"]:
        instruction = _HTML_TAG_RE.sub("", step.get("html_instructions", ""))

        if step["travel_mode"] == "TRANSIT" and "transit_details" in step:
            instruction, line_name, line_short_name = _transit_step_instruction(step)
            for line in CTA_TRAIN_LINES:
                if line.lower() in line_name:
                    line_flags[line] = True
            if "brn" in line_short_name:  # CTA abbreviates Brown as "Brn"
                line_flags["BROWN"] = True
        elif step["travel_mode"] == "WALKING":
            total_walking_seconds += step["duration"]["value"]

        steps.append(instruction)

    walking_time = None
    if mode == "transit" and total_walking_seconds > 0:
        walking_time = f"{round(total_walking_seconds / 60)} mins"

    return {
        "COMMUTE_TIME": leg["duration"]["text"],
        "COMMUTE_STEPS": ", ".join(steps),
        "COMMUTE_NUM_STEPS": len(steps),
        "WALKING_TIME": walking_time,
        **{f"USES_{line}_LINE": flag for line, flag in line_flags.items()},
    }


@retry_on_api_error()
def get_nearby_places(gmaps: googlemaps.Client, location, query: str,
                      keyword_search: bool = False,
                      radius_meters: int = PLACES_SEARCH_RADIUS_METERS) -> dict:
    """Find nearby amenities of one type around a location.

    Args:
        gmaps: An initialized Google Maps client.
        location: (latitude, longitude) of the home.
        query: Places "type" (e.g. 'grocery_or_supermarket') or, when
            ``keyword_search`` is True, a keyword such as a brand name.
        keyword_search: Use a keyword search instead of a type search.
        radius_meters: Search radius. Defaults to ~2 miles.

    Returns:
        Dict with the closest place (name, distance, walking time), a count of
        places within walking distance, and the full list found. Empty dict if
        nothing was found.
    """
    search_params = {"location": location, "radius": radius_meters}
    search_params["keyword" if keyword_search else "type"] = query

    # 1. Find all places within the radius (following one page of pagination).
    try:
        response = gmaps.places_nearby(**search_params)
        all_places = response.get("results", [])
        if "next_page_token" in response:
            time.sleep(2)  # Google requires a short delay before using the token
            next_page = gmaps.places_nearby(page_token=response["next_page_token"])
            all_places.extend(next_page.get("results", []))
    except googlemaps.exceptions.ApiError as e:
        print(f"Warning: could not get nearby places for {query!r}. Error: {e.status}")
        all_places = []

    if not all_places:
        return {}

    # 2. Compute straight-line distance to each place.
    home_lat, home_lon = location
    places = []
    for place in all_places:
        try:
            lat = place["geometry"]["location"]["lat"]
            lon = place["geometry"]["location"]["lng"]
        except (KeyError, TypeError):
            continue
        places.append({
            "name": place.get("name"),
            "distance_miles": float(haversine_miles(home_lat, home_lon, lat, lon)),
            "location": (lat, lon),
        })
    places.sort(key=lambda p: p["distance_miles"])

    if not places:
        return {}
    closest = places[0]

    # 3. Get the walking duration to the closest place only (1 API call).
    closest_walk_duration = None
    try:
        matrix = gmaps.distance_matrix(origins=[location],
                                       destinations=[closest["location"]],
                                       mode="walking")
        element = matrix["rows"][0]["elements"][0]
        if element["status"] == "OK":
            closest_walk_duration = element["duration"]["text"]
    except googlemaps.exceptions.ApiError as e:
        print(f"Warning: could not get walking duration for "
              f"{closest.get('name')!r}. Error: {e.status}")

    return {
        "closest_name": closest["name"],
        "closest_distance_miles": closest["distance_miles"],
        "closest_walk_duration": closest_walk_duration,
        "count_within_half_mile": sum(
            1 for p in places if p["distance_miles"] <= WALKABLE_RADIUS_MILES),
        "nearby_places_list": [
            {"name": p["name"], "distance": f"{p['distance_miles']:.2f} mi"}
            for p in places
        ],
    }
