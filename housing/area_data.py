"""Downloaders for neighborhood datasets (all free, no API keys).

Sources:
    CTA bus stops        -- Chicago Data Portal (qs84-j7wh)
    Metra stations       -- Metra GTFS schedule feed
    CPS schools          -- Chicago Data Portal school profiles (9a5f-2r4p)
    Rodent complaints    -- Chicago Data Portal 311 requests (v6vf-nfxy)

Each function writes a CSV under data_sets/ that build_dataset.py picks up.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import urllib.parse
import urllib.request
import zipfile

import pandas as pd

from housing.config import (
    CPS_SCHOOLS_CSV,
    CTA_BUS_STOPS_CSV,
    METRA_STATIONS_CSV,
    RODENT_CSV,
)

_USER_AGENT = "housing-app/1.0"
_PAGE_SIZE = 50_000

BUS_STOPS_URL = "https://data.cityofchicago.org/resource/qs84-j7wh.json"
SCHOOLS_URL = "https://data.cityofchicago.org/resource/9a5f-2r4p.json"
SERVICE_311_URL = "https://data.cityofchicago.org/resource/v6vf-nfxy.json"
METRA_GTFS_URL = "https://schedules.metrarail.com/gtfs/schedule.zip"


def _fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def _fetch_all_pages(base_url: str, params: dict) -> list[dict]:
    """Page through a Socrata endpoint until all rows are fetched."""
    rows: list[dict] = []
    offset = 0
    while True:
        query = urllib.parse.urlencode(
            {**params, "$limit": _PAGE_SIZE, "$offset": offset})
        page = _fetch_json(f"{base_url}?{query}")
        rows.extend(page)
        if len(page) < _PAGE_SIZE:
            return rows
        offset += _PAGE_SIZE


def download_bus_stops() -> pd.DataFrame:
    """All CTA bus stops with the routes that serve each stop."""
    rows = _fetch_all_pages(BUS_STOPS_URL, {
        "$select": "systemstop,public_nam,routesstpg,the_geom"})
    records = []
    for row in rows:
        geom = row.get("the_geom") or {}
        coords = geom.get("coordinates")
        if not coords:
            continue
        routes = (row.get("routesstpg") or "").replace(" ", ",")
        routes = ",".join(sorted({r for r in routes.split(",") if r}))
        records.append({
            "STOP_NAME": row.get("public_nam"),
            "ROUTES": routes,
            "LATITUDE": coords[1],
            "LONGITUDE": coords[0],
        })
    df = pd.DataFrame(records).dropna(subset=["LATITUDE", "LONGITUDE"])
    df.to_csv(CTA_BUS_STOPS_CSV, index=False)
    return df


def download_metra_stations() -> pd.DataFrame:
    """All Metra stations from the public GTFS schedule feed."""
    req = urllib.request.Request(METRA_GTFS_URL,
                                 headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as response:
        payload = response.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
        with bundle.open("stops.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
            # Metra's feed pads its CSV header/values with spaces.
            reader.fieldnames = [name.strip() for name in reader.fieldnames]
            records = []
            for row in reader:
                row = {k: (v.strip() if isinstance(v, str) else v)
                       for k, v in row.items()}
                if row.get("stop_lat"):
                    records.append({
                        "STATION": row.get("stop_name"),
                        "LATITUDE": float(row["stop_lat"]),
                        "LONGITUDE": float(row["stop_lon"]),
                    })
    df = (pd.DataFrame(records)
          .drop_duplicates(subset=["STATION"])
          .dropna(subset=["LATITUDE", "LONGITUDE"]))
    df.to_csv(METRA_STATIONS_CSV, index=False)
    return df


def _flag_is_true(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper().isin(["Y", "TRUE", "1"])


def download_schools() -> pd.DataFrame:
    """CPS elementary schools with ratings and attendance-boundary flags."""
    rows = _fetch_all_pages(SCHOOLS_URL, {
        "$select": ("short_name,long_name,overall_rating,rating_statement,"
                    "is_elementary_school,attendance_boundaries,"
                    "student_count_total,school_latitude,school_longitude")})
    df = pd.DataFrame(rows)
    df = df[_flag_is_true(df["is_elementary_school"])]
    df = df.rename(columns={
        "short_name": "SCHOOL", "long_name": "SCHOOL_FULL_NAME",
        "overall_rating": "RATING", "rating_statement": "RATING_STATEMENT",
        "student_count_total": "STUDENTS",
        "school_latitude": "LATITUDE", "school_longitude": "LONGITUDE",
    })
    df["HAS_BOUNDARY"] = _flag_is_true(df["attendance_boundaries"])
    df["LATITUDE"] = pd.to_numeric(df["LATITUDE"], errors="coerce")
    df["LONGITUDE"] = pd.to_numeric(df["LONGITUDE"], errors="coerce")
    df = df.dropna(subset=["LATITUDE", "LONGITUDE"])
    keep = ["SCHOOL", "SCHOOL_FULL_NAME", "RATING", "RATING_STATEMENT",
            "STUDENTS", "HAS_BOUNDARY", "LATITUDE", "LONGITUDE"]
    df = df[keep]
    df.to_csv(CPS_SCHOOLS_CSV, index=False)
    return df


def download_rodent_complaints(months: int = 12) -> pd.DataFrame:
    """311 rodent-baiting/rat complaints from the last ``months`` months."""
    cutoff = (datetime.date.today()
              - datetime.timedelta(days=round(months * 30.44)))
    rows = _fetch_all_pages(SERVICE_311_URL, {
        "$select": "created_date,latitude,longitude",
        "$where": ("sr_type='Rodent Baiting/Rat Complaint' AND "
                   f"created_date > '{cutoff.isoformat()}T00:00:00'"),
        "$order": ":id",
    })
    df = pd.DataFrame(rows).rename(columns={
        "created_date": "DATE", "latitude": "LATITUDE",
        "longitude": "LONGITUDE"})
    df["LATITUDE"] = pd.to_numeric(df["LATITUDE"], errors="coerce")
    df["LONGITUDE"] = pd.to_numeric(df["LONGITUDE"], errors="coerce")
    df = df.dropna(subset=["LATITUDE", "LONGITUDE"])
    df.to_csv(RODENT_CSV, index=False)
    return df
