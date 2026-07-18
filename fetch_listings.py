"""Pull the latest Redfin listings for the configured search.

Downloads the search defined in housing/config.py (region, price, beds,
baths, garage) and replaces data_sets/RedFin_raw_data.csv, reporting which
listings are new and which dropped off since the last pull. Previously
computed data (commutes, scores, ...) is preserved by MLS ID the next time
build_dataset.py runs.

Usage:
    python fetch_listings.py [--dry-run]
"""

from __future__ import annotations

import argparse

import pandas as pd

from housing.config import REDFIN_RAW_CSV, REDFIN_SEARCH_FILTERS
from housing.redfin import download_listings

# Raw-CSV header names used for the summary (before pipeline renaming).
_MLS_COL = "MLS#"
_ADDRESS_COL = "ADDRESS"
_PRICE_COL = "PRICE"
_LOCATION_COL = "LOCATION"


def _summarize(listings: pd.DataFrame, label: str) -> None:
    print(f"\n{label} ({len(listings)}):")
    for _, row in listings.iterrows():
        price = row.get(_PRICE_COL)
        price_str = f"${price:,.0f}" if pd.notna(price) else "N/A"
        print(f"  {row.get(_ADDRESS_COL)} ({row.get(_LOCATION_COL)}) — {price_str}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Download the latest Redfin listings for the configured search.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what changed without writing the file.")
    args = parser.parse_args(argv)

    filters = ", ".join(f"{k}={v}" for k, v in REDFIN_SEARCH_FILTERS.items())
    print(f"Fetching Redfin listings ({filters})...")
    new_df = download_listings()
    print(f"Downloaded {len(new_df)} listings.")

    try:
        old_df = pd.read_csv(REDFIN_RAW_CSV)
        old_df.columns = new_df.columns  # same positional schema
        old_mls = set(old_df[_MLS_COL].astype(str))
        new_mls = set(new_df[_MLS_COL].astype(str))

        added = new_df[~new_df[_MLS_COL].astype(str).isin(old_mls)]
        removed = old_df[~old_df[_MLS_COL].astype(str).isin(new_mls)]
        if not added.empty:
            _summarize(added, "New listings")
        if not removed.empty:
            _summarize(removed, "No longer listed")
        if added.empty and removed.empty:
            print("No changes since the last pull.")
    except FileNotFoundError:
        print("No previous raw data file; everything is new.")

    if args.dry_run:
        print("\nDry run: file not written.")
        return

    new_df.to_csv(REDFIN_RAW_CSV, index=False)
    print(f"\nSaved to {REDFIN_RAW_CSV}")
    print("Next step: python build_dataset.py  (add --skip-commute "
          "--skip-places to avoid Google API calls)")


if __name__ == "__main__":
    main()
