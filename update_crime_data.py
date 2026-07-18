"""Refresh the local crime dataset from the Chicago Data Portal.

Downloads recent incidents into data_sets/Crimes_recent.csv, which the
pipeline automatically prefers over the static extract. After refreshing,
recompute scores with:

    python build_dataset.py --skip-commute --skip-places --force-crime

Usage:
    python update_crime_data.py [--months N]
"""

from __future__ import annotations

import argparse

from housing.config import CRIME_RECENT_CSV
from housing.crime_portal import download_recent_crimes


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Download recent crime data from the Chicago Data Portal.")
    parser.add_argument("--months", type=int, default=24,
                        help="How many months of history to download "
                             "(default: 24; scores use the last 12, the rest "
                             "feeds the year-over-year crime trend).")
    args = parser.parse_args(argv)

    print(f"Downloading crimes from the last {args.months} months "
          f"(this can take a few minutes)...")
    crimes = download_recent_crimes(args.months)
    if crimes.empty:
        raise SystemExit("Download returned no rows; keeping the existing file.")

    CRIME_RECENT_CSV.parent.mkdir(parents=True, exist_ok=True)
    crimes.to_csv(CRIME_RECENT_CSV, index=False)

    print(f"Saved {len(crimes):,} incidents to {CRIME_RECENT_CSV}")
    print(f"Date range: {str(crimes['Date'].min())[:10]} to "
          f"{str(crimes['Date'].max())[:10]}")
    print("\nNext step: python build_dataset.py --skip-commute --skip-places "
          "--force-crime")


if __name__ == "__main__":
    main()
