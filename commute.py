import googlemaps
import time
import re
import functools

from extra_programs import distanceGPS
def retry_on_api_error(max_retries=3, initial_delay=1):
    """A decorator to retry a function call on specific Google API errors with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except googlemaps.exceptions.ApiError as e:
                    if e.status in ["REQUEST_DENIED", "OVER_QUERY_LIMIT"]:
                        if attempt < max_retries - 1:
                            print(f"API Error ({e.status}) on attempt {attempt + 1} for {func.__name__}. Retrying in {delay}s...")
                            time.sleep(delay)
                            delay *= 2  # Exponential backoff
                        else:
                            print(f"API Error ({e.status}) on final attempt for {func.__name__}. Failing gracefully.")
                    else:
                        print(f"Unrecoverable API Error in {func.__name__}: {e}")
                except Exception as e:
                    print(f"An unexpected error occurred in {func.__name__}: {e}")
            
            # Return a default empty value if all retries fail or an unrecoverable error occurs
            if "directions" in func.__name__:
                return {"COMMUTE_TIME": None, "COMMUTE_STEPS": None, "COMMUTE_NUM_STEPS": None, "WALKING_TIME": None, "USES_BROWN_LINE": False, "USES_RED_LINE": False, "USES_BLUE_LINE": False, "USES_PINK_LINE": False, "USES_GREEN_LINE": False, "USES_ORANGE_LINE": False, "USES_PURPLE_LINE": False}
            else:
                return {}
        return wrapper
    return decorator

@retry_on_api_error()
def get_directions_from_google_api(gmaps, origin, location_address, mode='transit', departure_time=None):
    """
    Get directions from Google Maps API
    
    Args:
        gmaps (googlemaps.Client): An initialized Google Maps client.
        origin (str): Home address
        location_address (str): Destination address
        mode (str): 'transit' or 'driving'
        departure_time (datetime.datetime or str): The desired departure time.
            Can be a datetime object, or "now". If None, defaults are used.
    
    Returns:
        dict: Commute information including time, steps, and walking time
    """
    # Set default departure time if not provided
    if departure_time is None:
        departure_time = "now" if mode == 'transit' else None

    # Get directions
    directions_result = gmaps.directions(
        origin,
        location_address,
        mode=mode,
        departure_time=departure_time
    )
    
    if not directions_result:
        return {"COMMUTE_TIME": None, "COMMUTE_STEPS": None, "COMMUTE_NUM_STEPS": None, "COMMUTE_NUM_STEPS": None, "WALKING_TIME": None, "USES_BROWN_LINE": False, "USES_RED_LINE": False, "USES_BLUE_LINE": False, "USES_PINK_LINE": False, "USES_GREEN_LINE": False, "USES_ORANGE_LINE": False, "USES_PURPLE_LINE": False}
    
    # Get the first route
    route = directions_result[0]
    leg = route['legs'][0]
    
    # Get total duration
    duration = leg['duration']['text']
    
    # Get cleaned steps
    steps = []
    uses_brown_line = False
    uses_red_line = False
    uses_blue_line = False
    uses_pink_line = False
    uses_green_line = False
    uses_orange_line = False
    uses_purple_line = False
    for step in leg['steps']:
        # Default instruction is the HTML-stripped one, good for walking/driving
        instruction = re.sub('<[^<]+?>', '', step.get('html_instructions', ''))

        # For transit, build a more descriptive instruction and detect train lines
        if step['travel_mode'] == 'TRANSIT' and 'transit_details' in step:
            details = step['transit_details']
            line = details.get('line', {})
            vehicle = line.get('vehicle', {})
            
            line_name = line.get('name', '')
            line_short_name = line.get('short_name', '')
            headsign = details.get('headsign', '')
            vehicle_type = vehicle.get('type', '')  # e.g., 'BUS', 'SUBWAY'

            # Build a more descriptive instruction string
            instruction_parts = ["Take"]
            if vehicle_type == 'BUS' and line_short_name:
                instruction_parts.append(f"bus {line_short_name}")
            elif vehicle_type in ['SUBWAY', 'HEAVY_RAIL'] and line_name:
                instruction_parts.append(f"the {line_name}")
            elif line_name:  # Fallback for other transit types
                instruction_parts.append(f"the {line_name}")
            else:  # Fallback if no line name
                instruction_parts.append("the transit")
            
            if headsign:
                instruction_parts.append(f"towards {headsign}")
            
            instruction = " ".join(instruction_parts)

            # Detect which train lines are used
            line_name_lower = line_name.lower()
            line_short_name_lower = line_short_name.lower()
            
            if 'brown' in line_name_lower or 'brn' in line_short_name_lower:
                uses_brown_line = True
            if 'red' in line_name_lower:
                uses_red_line = True
            if 'blue' in line_name_lower:
                uses_blue_line = True
            if 'pink' in line_name_lower:
                uses_pink_line = True
            if 'green' in line_name_lower:
                uses_green_line = True
            if 'orange' in line_name_lower:
                uses_orange_line = True
            if 'purple' in line_name_lower:
                uses_purple_line = True
        
        steps.append(instruction)
    
    # Get walking time if available
    walking_time_str = None
    if mode == 'transit':
        total_walking_seconds = 0
        for step in leg['steps']:
            if step['travel_mode'] == 'WALKING':
                total_walking_seconds += step['duration']['value']
        if total_walking_seconds > 0:
            walking_minutes = round(total_walking_seconds / 60)
            walking_time_str = f"{walking_minutes} mins"
    
    return {"COMMUTE_TIME": duration, "COMMUTE_STEPS": ", ".join(steps), "COMMUTE_NUM_STEPS": len(steps), "WALKING_TIME": walking_time_str, "USES_BROWN_LINE": uses_brown_line, "USES_RED_LINE": uses_red_line, "USES_BLUE_LINE": uses_blue_line, "USES_PINK_LINE": uses_pink_line, "USES_GREEN_LINE": uses_green_line, "USES_ORANGE_LINE": uses_orange_line, "USES_PURPLE_LINE": uses_purple_line}

@retry_on_api_error()
def get_nearby_places(gmaps, location, place_type, radius_meters=3200):
    """
    Finds nearby amenities, including the closest, a count within walking distance,
    and a list of all found amenities with their distances.
    
    Args:
        gmaps (googlemaps.Client): An initialized Google Maps client.
        location (tuple): (latitude, longitude) of the location.
        place_type (str): Type of place to search for.
        radius_meters (int): Search radius in meters. Default is 3200m (~2 miles).
    
    Returns:
        dict: A dictionary containing details about nearby places.
    """
    search_params = {'location': location, 'radius': radius_meters}
    if place_type in ["Whole Foods", "Trader Joe's", "Chicago Public Library"]:
        search_params['keyword'] = place_type
    else:
        search_params['type'] = place_type

    # --- 1. Find all places within the given radius ---
    try:
        nearby_results = gmaps.places_nearby(**search_params)
        all_places = nearby_results.get('results', [])
        # Handle pagination to get more results (up to 60)
        if 'next_page_token' in nearby_results:
            time.sleep(2)  # Google requires a short delay before using the token
            next_page_results = gmaps.places_nearby(page_token=nearby_results['next_page_token'])
            all_places.extend(next_page_results.get('results', []))
    except googlemaps.exceptions.ApiError as e:
        print(f"Warning: Could not get nearby places for {place_type}. Error: {e.status}")
        all_places = []

    if not all_places:
        return {}

    # --- 2. Calculate distance for each place and gather data ---
    home_lat, home_lon = location
    places_with_distance = []
    for place in all_places:
        try:
            place_lat = place['geometry']['location']['lat']
            place_lon = place['geometry']['location']['lng']
            dist_miles = distanceGPS(home_lat, home_lon, place_lat, place_lon)
            places_with_distance.append({
                'name': place.get('name'),
                'distance_miles': dist_miles,
                'location': (place_lat, place_lon)
            })
        except (KeyError, TypeError):
            continue
    
    places_with_distance.sort(key=lambda p: p['distance_miles'])

    # --- 3. Get walking duration for the single closest place ---
    closest_place = places_with_distance[0] if places_with_distance else None
    closest_walk_duration = None
    if closest_place:
        try:
            walk_matrix = gmaps.distance_matrix(origins=[location], destinations=[closest_place['location']], mode='walking')
            if walk_matrix['rows'][0]['elements'][0]['status'] == 'OK':
                closest_walk_duration = walk_matrix['rows'][0]['elements'][0]['duration']['text']
        except googlemaps.exceptions.ApiError as e:
            print(f"Warning: Could not get walking duration for {closest_place.get('name')}. Error: {e.status}")

    # --- 4. Count places within 0.5 miles and prepare final list ---
    count_within_half_mile = sum(1 for p in places_with_distance if p['distance_miles'] <= 0.5)
    nearby_places_list = [{'name': p['name'], 'distance': f"{p['distance_miles']:.2f} mi"} for p in places_with_distance]

    return {
        'closest_name': closest_place['name'] if closest_place else None,
        'closest_distance_miles': closest_place['distance_miles'] if closest_place else None,
        'closest_walk_duration': closest_walk_duration,
        'count_within_half_mile': count_within_half_mile,
        'nearby_places_list': nearby_places_list
    }