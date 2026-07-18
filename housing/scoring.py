"""Normalization helpers and the weighted OVERALL_SCORE calculation.

Each component score is normalized to a 0-1 scale where higher is better,
then combined with user-supplied weights (see ``compute_overall_score``).
"""

from __future__ import annotations

import pandas as pd

from housing.config import SCORED_AMENITIES, SCORED_COMMUTE_DESTINATIONS
from housing.crime import CRIME_SCORE_COLUMNS


def minmax_normalize(series: pd.Series, degenerate_fill: float) -> pd.Series:
    """Scale a series to 0-1. If the series has no spread (or is all-NA),
    return a constant series of ``degenerate_fill``."""
    s = series.astype(float)
    s_min, s_max = s.min(), s.max()
    denom = s_max - s_min
    if pd.isna(s_min) or pd.isna(s_max) or denom == 0:
        return pd.Series([degenerate_fill] * len(s), index=s.index)
    return (s - s_min) / denom


def _extract_minutes(text) -> float | None:
    """Parse the leading minutes value from a duration like '42 mins'."""
    try:
        if isinstance(text, str) and "min" in text:
            return float(text.split()[0])
    except (ValueError, IndexError):
        return None
    return None


def commute_score(df: pd.DataFrame) -> pd.Series:
    """Score commutes: lower total transit time across the scored
    destinations is better."""
    total_minutes = sum(
        (df[f"COMMUTE_TIME_{dest}"].apply(_extract_minutes).fillna(0)
         for dest in SCORED_COMMUTE_DESTINATIONS),
        start=pd.Series(0.0, index=df.index),
    )
    return 1 - minmax_normalize(total_minutes.replace(0, pd.NA), 0.5)


def crime_safety_score(df: pd.DataFrame) -> pd.Series:
    """Score safety: lower combined crime risk is better."""
    risk = sum(
        minmax_normalize(df[col].fillna(0), 0.0) for col in CRIME_SCORE_COLUMNS
    ) / len(CRIME_SCORE_COLUMNS)
    return 1 - risk


def amenities_score(df: pd.DataFrame) -> pd.Series:
    """Score amenities: more walkable places nearby is better."""
    total = sum(
        (df[f"{amenity.upper()}_WALK_NUM"].fillna(0)
         for amenity in SCORED_AMENITIES),
        start=pd.Series(0.0, index=df.index),
    )
    return minmax_normalize(total, 0.5)


def value_score(df: pd.DataFrame) -> pd.Series:
    """Score value: lower price per square foot is better."""
    price_per_sqft = df["PRICE"].replace(0, pd.NA) / df["SQFT"].replace(0, pd.NA)
    return minmax_normalize(1 / price_per_sqft, 0.5)


def compute_overall_score(df: pd.DataFrame, weights: dict) -> pd.Series:
    """Combine component scores using ``weights`` (keys: commute, crime,
    amenities, price). Rows missing a component get a neutral value."""
    return (
        weights["commute"] * commute_score(df).fillna(0.5)
        + weights["crime"] * crime_safety_score(df).fillna(0.5)
        + weights["amenities"] * amenities_score(df).fillna(0.0)
        + weights["price"] * value_score(df).fillna(0.0)
    )
