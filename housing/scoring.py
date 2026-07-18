"""Normalization helpers and the weighted OVERALL_SCORE calculation.

Each component score is normalized to a 0-1 scale where higher is better,
then combined with user-supplied weights (see ``compute_overall_score``).
"""

from __future__ import annotations

import re

import pandas as pd

from housing.config import COMMUTE_REQUIREMENTS, HOA_PRICE_EQUIVALENT, SCORED_AMENITIES
from housing.crime import CRIME_SCORE_COLUMNS

_HOURS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*hour")
_MINS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*min")


def minmax_normalize(series: pd.Series, degenerate_fill: float) -> pd.Series:
    """Scale a series to 0-1. If the series has no spread (or is all-NA),
    return a constant series of ``degenerate_fill``."""
    # to_numeric handles pd.NA safely; plain astype(float) raises on NAType.
    s = pd.to_numeric(series, errors="coerce").astype(float)
    s_min, s_max = s.min(), s.max()
    denom = s_max - s_min
    if pd.isna(s_min) or pd.isna(s_max) or denom == 0:
        return pd.Series([degenerate_fill] * len(s), index=s.index)
    return (s - s_min) / denom


def duration_to_minutes(text) -> float | None:
    """Parse a Google duration like '42 mins', '1 hour 5 mins', or '2 hours'
    into total minutes. (Naively taking the first number would read
    '2 hours 3 mins' as 2 minutes.)"""
    if not isinstance(text, str):
        return None
    minutes = 0.0
    hours_match = _HOURS_RE.search(text)
    if hours_match:
        minutes += float(hours_match.group(1)) * 60
    mins_match = _MINS_RE.search(text)
    if mins_match:
        minutes += float(mins_match.group(1))
    return minutes if minutes > 0 else None


def commute_score(df: pd.DataFrame) -> pd.Series:
    """Score commutes against the per-destination requirements in
    ``COMMUTE_REQUIREMENTS``.

    Each destination scores 1.0 at or under its target time, falling
    linearly to 0.0 at its max. The home's commute score is the minimum
    across destinations: every commute has to be acceptable, and one
    terrible commute can't be offset by two great ones. Homes with no
    commute data yet score NaN (filled neutrally later). Each requirement's
    "mode" picks the judged time: transit or driving.
    """
    destination_scores = []
    for dest, req in COMMUTE_REQUIREMENTS.items():
        col = (f"DRIVE_TIME_{dest}" if req.get("mode") == "drive"
               else f"COMMUTE_TIME_{dest}")
        minutes = pd.to_numeric(df[col].apply(duration_to_minutes),
                                errors="coerce")
        over_target = (minutes - req["target"]).clip(lower=0)
        score = 1 - over_target / (req["max"] - req["target"])
        destination_scores.append(score.clip(lower=0.0, upper=1.0))
    return pd.concat(destination_scores, axis=1).min(axis=1)


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
    """Score value: lower effective price per square foot is better.

    HOA fees are folded in as price-equivalent (each $1/month of HOA
    reduces buying power like ~$HOA_PRICE_EQUIVALENT of price), so a condo
    with steep assessments scores like the pricier home it effectively is.
    """
    hoa = pd.to_numeric(df.get("HOA"), errors="coerce").fillna(0)
    effective_price = (df["PRICE"].replace(0, pd.NA)
                       + hoa * HOA_PRICE_EQUIVALENT)
    price_per_sqft = effective_price / df["SQFT"].replace(0, pd.NA)
    return minmax_normalize(1 / price_per_sqft, 0.5)


def bars_density_penalty(df: pd.DataFrame) -> pd.Series:
    """Penalty for homes near many bars (0 = fewest bars, 1 = most)."""
    return minmax_normalize(df["BARS_WALK_NUM"].fillna(0), 0.0)


def gun_risk_penalty(df: pd.DataFrame) -> pd.Series:
    """Penalty for homes near gun incidents (0 = safest, 1 = highest risk).

    Gun crime already feeds crime_safety_score as one of six categories;
    this dedicated penalty weights it more heavily on top of that.
    """
    return minmax_normalize(df["GUN_SCORE"].fillna(0), 0.0)


def compute_overall_score(df: pd.DataFrame, weights: dict) -> pd.Series:
    """Combine component scores using ``weights``.

    Positive components (commute, crime, amenities, price) add to the score;
    penalty components (bars, gun) subtract from it. Rows missing a component
    get a neutral value.
    """
    return (
        weights["commute"] * commute_score(df).fillna(0.5)
        + weights["crime"] * crime_safety_score(df).fillna(0.5)
        + weights["amenities"] * amenities_score(df).fillna(0.0)
        + weights["price"] * value_score(df).fillna(0.0)
        - weights.get("bars", 0.0) * bars_density_penalty(df).fillna(0.0)
        - weights.get("gun", 0.0) * gun_risk_penalty(df).fillna(0.0)
    )
