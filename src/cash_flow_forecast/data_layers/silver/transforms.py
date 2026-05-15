from __future__ import annotations
import pandas as pd


NULL_TOKENS = {"", "na", "null", "none", "nan"}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with stripped uppercase column names."""

    normalized = df.copy()
    normalized.columns = [str(column).strip().upper() for column in normalized.columns]
    return normalized


def clean_text(series: pd.Series) -> pd.Series:
    """Normalize raw string content into a nullable pandas string series."""

    text = series.astype("string").str.strip()
    lowered = text.str.lower()
    text = text.mask(lowered.isin(NULL_TOKENS), pd.NA)
    return text


def to_float(series: pd.Series) -> pd.Series:
    """Parse string values into nullable floating point values."""

    text = clean_text(series)
    text = text.str.replace("\u00A0", "", regex=False)
    text = text.str.replace(" ", "", regex=False)
    text = text.str.replace(",", ".", regex=False)
    return pd.to_numeric(text, errors="coerce").astype("Float64")


def to_int(series: pd.Series) -> pd.Series:
    """Parse string values into nullable integer values."""

    return to_float(series).round().astype("Int64")


def to_date(series: pd.Series) -> pd.Series:
    """Parse date-like values into normalized pandas timestamps."""

    text = clean_text(series)
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    iso_mask = text.str.fullmatch(r"\d{4}-\d{2}-\d{2}").fillna(False)
    parsed.loc[iso_mask] = pd.to_datetime(
        text.loc[iso_mask],
        errors="coerce",
        format="%Y-%m-%d",
    )
    remaining_mask = parsed.isna() & text.notna()
    parsed.loc[remaining_mask] = pd.to_datetime(
        text.loc[remaining_mask],
        errors="coerce",
        format="mixed",
        dayfirst=True,
    )
    return parsed.dt.tz_localize(None).dt.normalize()