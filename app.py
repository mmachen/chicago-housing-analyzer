"""Flask dashboard for browsing the enriched housing dataset.

Serves the property list, filters, and map at http://localhost:5000. Expects
output/final_data.csv to exist (run build_dataset.py first).

Set FLASK_DEBUG=1 to enable debug mode and auto-reload during development.
"""

from __future__ import annotations

import logging
import os
import socket

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request

from housing.config import COMMUTE_DESTINATIONS, DESTINATION_MARKERS, FINAL_DATA_CSV

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

# Upper bound sentinel meaning "$1M and above" in the price filter.
PRICE_CAP_SENTINEL = 1_000_001

PRICE_RANGES = [
    (0, 300_000), (300_000, 400_000), (400_000, 500_000), (500_000, 600_000),
    (600_000, 700_000), (700_000, 800_000), (800_000, 900_000),
    (900_000, 1_000_000), (1_000_000, PRICE_CAP_SENTINEL),
]


def load_properties() -> pd.DataFrame:
    try:
        df = pd.read_csv(FINAL_DATA_CSV)
        log.info("Loaded %d properties from %s", len(df), FINAL_DATA_CSV)
        return df
    except Exception as e:
        log.error("Could not load %s: %s -- run build_dataset.py first.",
                  FINAL_DATA_CSV, e)
        return pd.DataFrame()


df = load_properties()


def _to_json_safe_records(frame: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame to records with numpy/NaN values made JSON-safe."""
    records = frame.to_dict("records")
    for record in records:
        for key, value in record.items():
            if isinstance(value, (np.integer, np.floating)):
                record[key] = value.item()
            elif isinstance(value, np.ndarray):
                record[key] = value.tolist()
            elif pd.isna(value):
                record[key] = None
    return records


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/initial-data")
def get_initial_data():
    try:
        locations = (sorted(df["LOCATION"].dropna().unique().astype(str).tolist())
                     if not df.empty and "LOCATION" in df.columns else [])
    except Exception:
        locations = []

    try:
        property_types = (sorted(df["PROPERTY_TYPE"].dropna().unique()
                                 .astype(str).tolist())
                          if not df.empty and "PROPERTY_TYPE" in df.columns
                          else [])
    except Exception:
        property_types = []

    destinations = [
        {"name": name, "address": COMMUTE_DESTINATIONS.get(name, ""), **marker}
        for name, marker in DESTINATION_MARKERS.items()
    ]
    return jsonify({"locations": locations, "price_ranges": PRICE_RANGES,
                    "property_types": property_types,
                    "destinations": destinations})


@app.route("/api/properties")
def get_properties():
    try:
        location = request.args.get("location", "")
        price_min = request.args.get("price_min", type=float)
        price_max = request.args.get("price_max", type=float)
        sort_by = request.args.get("sort_by", "PRICE")
        sort_order = request.args.get("sort_order", "asc")

        filtered = df
        if location and location in filtered["LOCATION"].unique():
            filtered = filtered[filtered["LOCATION"] == location]
        # Comma-separated list supports multi-selection in the UI.
        property_type = request.args.get("property_type", "")
        if property_type and "PROPERTY_TYPE" in filtered.columns:
            selected = [t for t in property_type.split(",") if t]
            filtered = filtered[filtered["PROPERTY_TYPE"].isin(selected)]

        # Hide homes whose school drive exceeds the slider; homes without
        # drive data yet are kept visible.
        max_drive = request.args.get("max_drive", type=float)
        if max_drive is not None and "DRIVE_MINUTES_school_Hana" in filtered.columns:
            drive = filtered["DRIVE_MINUTES_school_Hana"]
            filtered = filtered[drive.isna() | (drive <= max_drive)]
        if price_min is not None:
            filtered = filtered[filtered["PRICE"] >= price_min]
        if price_max is not None:
            if price_max == PRICE_CAP_SENTINEL:
                filtered = filtered[filtered["PRICE"] >= 1_000_000]
            else:
                filtered = filtered[filtered["PRICE"] <= price_max]

        if sort_by not in filtered.columns:
            sort_by = "PRICE"
        ascending = str(sort_order).lower() != "desc"
        try:
            filtered = filtered.sort_values(by=sort_by, ascending=ascending)
        except Exception:
            # Fall back to PRICE if the requested column has mixed dtypes.
            if "PRICE" in filtered.columns:
                filtered = filtered.sort_values(by="PRICE", ascending=ascending)

        return jsonify(_to_json_safe_records(filtered))
    except Exception as e:
        log.error("Error in get_properties: %s", e)
        return jsonify([])


def _local_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "unknown"


def main() -> None:
    print("\nAccess the application at:")
    print("  Local:   http://localhost:5000")
    print(f"  Network: http://{_local_ip()}:5000\n")

    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug)


if __name__ == "__main__":
    main()
