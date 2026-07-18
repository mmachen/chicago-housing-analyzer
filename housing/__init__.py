"""Housing analysis toolkit for the Chicago home search.

Modules:
    config              -- paths, destinations, amenities, and scoring settings
    cache               -- SQLite-backed cache for Google Maps API responses
    geo                 -- geodesic distance helpers
    google_maps         -- Directions / Places API wrappers with retry logic
    crime               -- crime-density scores from Chicago Data Portal data
    affordable_housing  -- affordable-housing proximity features
    scoring             -- normalization and the weighted OVERALL_SCORE
"""
