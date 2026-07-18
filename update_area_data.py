"""Download the neighborhood datasets used to enrich each home.

Fetches (all free, no API keys):
    - CTA bus stops with routes served       -> data_sets/cta_bus_stops.csv
    - Metra stations (GTFS)                  -> data_sets/metra_stations.csv
    - CPS elementary schools with ratings    -> data_sets/cps_schools.csv
    - 311 rodent complaints (last 12 months) -> data_sets/rodent_complaints.csv

Bus stops, Metra stations, and schools rarely change, so they are only
downloaded if missing (use --force to refresh them). Rodent complaints are
refreshed on every run.

Usage:
    python update_area_data.py [--force]
"""

from __future__ import annotations

import argparse

from housing import area_data
from housing.config import (
    CPS_SCHOOLS_CSV,
    CTA_BUS_STOPS_CSV,
    METRA_STATIONS_CSV,
)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Download neighborhood datasets (bus, Metra, schools, 311).")
    parser.add_argument("--force", action="store_true",
                        help="Redownload the rarely-changing datasets too.")
    args = parser.parse_args(argv)

    steps = [
        ("CTA bus stops", CTA_BUS_STOPS_CSV, area_data.download_bus_stops),
        ("Metra stations", METRA_STATIONS_CSV, area_data.download_metra_stations),
        ("CPS elementary schools", CPS_SCHOOLS_CSV, area_data.download_schools),
        ("311 rodent complaints", None, area_data.download_rodent_complaints),
    ]
    for label, path, func in steps:
        if path is not None and path.exists() and not args.force:
            print(f"{label}: already downloaded ({path.name}); use --force to refresh.")
            continue
        print(f"{label}: downloading...")
        try:
            df = func()
            print(f"{label}: saved {len(df):,} rows.")
        except Exception as e:
            print(f"WARNING: {label} download failed ({e}). Continuing.")

    print("\nArea data update complete. Rebuild scores with:\n"
          "  python build_dataset.py --skip-commute --skip-places")


if __name__ == "__main__":
    main()
