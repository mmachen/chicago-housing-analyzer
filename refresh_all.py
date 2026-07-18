"""Run the full ongoing refresh routine in one command.

The routine this script automates (each step can also be run by hand):

    1. python fetch_listings.py      -- pull the latest Redfin listings for
                                        the configured search (free)
    2. python update_crime_data.py   -- refresh crime data from the Chicago
                                        Data Portal (free)
    3. python build_dataset.py       -- enrich + score everything; only NEW
                                        homes cost Google API calls, results
                                        are cached afterwards
    4. python app.py                 -- browse the dashboard at
                                        http://localhost:5000

Usage:

    python refresh_all.py               # steps 1-3 (Google APIs for new homes)
    python refresh_all.py --no-google   # steps 1-3 free: skip all commute and
                                        # amenity API calls (zero cost)
    python refresh_all.py --serve       # steps 1-3, then start the dashboard

Steps 1 and 2 are non-fatal: if Redfin or the Data Portal is unreachable, the
script warns, keeps the existing data files, and continues.

--- Tuning the score ---------------------------------------------------------

Any build_dataset.py weight flag is passed straight through. The score is:

    commute + crime + amenities + price   (positive components, weights sum ~1)
    - bars - gun                          (penalties, subtracted)

Examples:

    # Punish homes near gun incidents even harder (default penalty 0.15):
    python refresh_all.py --w-gun 0.25

    # ...and homes near many bars (default penalty 0.10):
    python refresh_all.py --w-gun 0.25 --w-bars 0.15

    # Care more about commutes, less about price per sqft:
    python refresh_all.py --w-commute 0.5 --w-price 0.05

To re-score with new weights WITHOUT downloading anything (instant, free),
skip this script and run build_dataset.py directly on the cached data:

    python build_dataset.py --skip-commute --skip-places --w-gun 0.25

Weight defaults live in housing/config.py (DEFAULT_SCORE_WEIGHTS); edit them
there to change your preferences permanently instead of per-run.
"""

from __future__ import annotations

import argparse
import sys

import build_dataset
import fetch_listings
import update_crime_data


def _run_step(number: int, title: str, func, *func_args) -> bool:
    """Run one step with a visible header. Returns True on success."""
    print(f"\n{'=' * 60}\nStep {number}: {title}\n{'=' * 60}")
    try:
        func(*func_args)
        return True
    except (Exception, SystemExit) as e:
        print(f"WARNING: {title} failed ({e}). Continuing with existing data.")
        return False


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Run the full refresh routine: listings + crime + build. "
                    "Unrecognized flags (e.g. --w-gun 0.25) are passed "
                    "through to build_dataset.py.")
    parser.add_argument("--no-google", action="store_true",
                        help="Skip all Google API calls (commutes/amenities); "
                             "the run is completely free.")
    parser.add_argument("--serve", action="store_true",
                        help="Start the dashboard after the data refresh.")
    args, build_args = parser.parse_known_args(argv)

    if args.no_google:
        build_args = build_args + ["--skip-commute", "--skip-places"]

    ok_listings = _run_step(1, "Fetch Redfin listings", fetch_listings.main, [])
    ok_crime = _run_step(2, "Refresh crime data", update_crime_data.main, [])

    # The build is the point of the routine; let a failure here surface fully.
    print(f"\n{'=' * 60}\nStep 3: Build dataset "
          f"({'free mode, no Google APIs' if args.no_google else 'Google APIs for new homes'})"
          f"\n{'=' * 60}")
    build_dataset.main(build_args)

    print(f"\n{'=' * 60}\nRefresh complete"
          + ("" if ok_listings else " (listings step failed)")
          + ("" if ok_crime else " (crime step failed)")
          + f"\n{'=' * 60}")

    if args.serve:
        # Imported here so the dashboard loads the freshly built dataset.
        import app
        app.main()
    else:
        print("Browse the results with: python app.py")


if __name__ == "__main__":
    sys.exit(main())
