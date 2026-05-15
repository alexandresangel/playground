from __future__ import annotations
import pandas as pd

from cash_flow_forecast.data_layers.gold.builder import SEQUENCE_ID_COLUMN
from cash_flow_forecast.data_layers.gold.builder import TARGET_AMOUNT_COLUMN

PREDICTION_COLUMN = "PREDICTION"
DEFAULT_UNIQUE_ID = "series"

NON_FEATURE_COLUMNS = {
    "ABS_ERROR",
    "POINT_FORECAST",
    PREDICTION_COLUMN,
    "RULESET_ID",
    "TRAIN_CUTOFF_END",
    "TRAIN_CUTOFF_START",
    TARGET_AMOUNT_COLUMN,
}
NON_FEATURE_PREFIXES = ("PREDICTION_LOWER_", "PREDICTION_UPPER_")


def numeric_feature_columns(frame: pd.DataFrame) -> list[str]:
    """Return stable numeric feature columns usable by tabular estimators."""

    numeric_columns = frame.select_dtypes(include=["number", "bool"]).columns
    return [
        column
        for column in numeric_columns
        if column not in NON_FEATURE_COLUMNS
        and not any(str(column).startswith(prefix) for prefix in NON_FEATURE_PREFIXES)
    ]


def feature_frame(frame: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    """Return a float feature matrix aligned to the fitted columns."""

    aligned = frame.reindex(columns=feature_columns, fill_value=0.0)
    return aligned.astype(float).fillna(0.0)


def training_series(frame: pd.DataFrame) -> pd.Series:
    """Return one sorted target series indexed by forecast date."""

    if frame.empty:
        return pd.Series(dtype="float64")
    ordered = frame.sort_values("FORECAST_DATE")
    series = ordered.set_index(pd.to_datetime(ordered["FORECAST_DATE"]))[TARGET_AMOUNT_COLUMN]
    return pd.to_numeric(series, errors="coerce").fillna(0.0).astype(float)


def last_training_value(frame: pd.DataFrame) -> float:
    """Return the last target value available in a training frame."""

    series = training_series(frame)
    if series.empty:
        return 0.0
    return float(series.iloc[-1])


def mean_training_value(frame: pd.DataFrame) -> float:
    """Return the mean target value available in a training frame."""

    series = training_series(frame)
    if series.empty:
        return 0.0
    return float(series.mean())


def nixtla_frame(frame: pd.DataFrame, unique_id: str | None = None) -> pd.DataFrame:
    """Return a one-sequence frame using Nixtla's unique_id/ds/y schema."""

    if frame.empty:
        return pd.DataFrame(columns=["unique_id", "ds", "y"])
    ordered = frame.sort_values("FORECAST_DATE")
    series_id = unique_id or _sequence_id(frame)
    result = pd.DataFrame(
        {
            "unique_id": series_id,
            "ds": pd.to_datetime(ordered["FORECAST_DATE"]).dt.normalize(),
            "y": pd.to_numeric(ordered[TARGET_AMOUNT_COLUMN], errors="coerce").fillna(0.0).astype(float),
        }
    )
    return result.drop_duplicates(subset=["unique_id", "ds"], keep="last").reset_index(drop=True)


def forecast_steps_from_training(training_frame: pd.DataFrame, inference_frame: pd.DataFrame) -> int:
    """Return the number of daily steps needed from training end to inference end."""

    if training_frame.empty or inference_frame.empty:
        return 1
    last_training_date = pd.to_datetime(training_frame["FORECAST_DATE"]).max().normalize()
    max_forecast_date = pd.to_datetime(inference_frame["FORECAST_DATE"]).max().normalize()
    return max(1, int((max_forecast_date - last_training_date).days))


def forecast_column(frame: pd.DataFrame) -> str:
    """Find the first model output column in a Nixtla forecast dataframe."""

    candidates = [column for column in frame.columns if column not in {"unique_id", "ds"}]
    if not candidates:
        raise ValueError("Forecast output does not contain a model prediction column.")
    return candidates[0]


def _sequence_id(frame: pd.DataFrame) -> str:
    if SEQUENCE_ID_COLUMN in frame.columns and not frame.empty:
        return str(frame[SEQUENCE_ID_COLUMN].iloc[0])
    return DEFAULT_UNIQUE_ID
