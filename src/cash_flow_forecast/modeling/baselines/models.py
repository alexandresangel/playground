from __future__ import annotations
import pandas as pd

from cash_flow_forecast.contracts.builders import ModelInfo
from cash_flow_forecast.contracts.enums import DatasetKind
from cash_flow_forecast.data_layers.gold.builder import TARGET_AMOUNT_COLUMN
from cash_flow_forecast.modeling.base import ForecastModel
from cash_flow_forecast.modeling.features import (
    PREDICTION_COLUMN,
    last_training_value,
    mean_training_value,
    training_series,
)


class NaiveLastDayModel(ForecastModel):
    """Naive D+1 baseline that predicts the last available target value."""

    dataset_kind = DatasetKind.TIME_SERIES

    def __init__(self) -> None:
        self.fallback_ = 0.0

    def fit(self, training_frame: pd.DataFrame) -> "NaiveLastDayModel":
        self.fallback_ = last_training_value(training_frame)
        return self

    def predict(self, inference_frame: pd.DataFrame) -> pd.DataFrame:
        predictions = inference_frame.copy()
        if "TARGET_LAG_1" in predictions.columns:
            predictions[PREDICTION_COLUMN] = (
                pd.to_numeric(predictions["TARGET_LAG_1"], errors="coerce")
                .fillna(self.fallback_)
                .astype(float)
            )
        else:
            predictions[PREDICTION_COLUMN] = self.fallback_
        return predictions

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            model_name="naive_last_day",
            dataset_kind=self.dataset_kind,
            description="Predicts D+1 from the last day available at the cutoff.",
        )


class SeasonalNaiveWeeklyModel(ForecastModel):
    """Seasonal naive baseline that predicts the same weekday from last week."""

    dataset_kind = DatasetKind.TIME_SERIES

    def __init__(self) -> None:
        self.fallback_ = 0.0

    def fit(self, training_frame: pd.DataFrame) -> "SeasonalNaiveWeeklyModel":
        self.fallback_ = last_training_value(training_frame)
        return self

    def predict(self, inference_frame: pd.DataFrame) -> pd.DataFrame:
        predictions = inference_frame.copy()
        if "TARGET_LAG_7" in predictions.columns:
            predictions[PREDICTION_COLUMN] = (
                pd.to_numeric(predictions["TARGET_LAG_7"], errors="coerce")
                .fillna(self.fallback_)
                .astype(float)
            )
        else:
            predictions[PREDICTION_COLUMN] = self.fallback_
        return predictions

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            model_name="seasonal_naive_weekly",
            dataset_kind=self.dataset_kind,
            description="Predicts D+1 from the same weekday one week earlier.",
        )


class MovingAverageModel(ForecastModel):
    """Moving-average baseline over the latest available training targets."""

    dataset_kind = DatasetKind.TIME_SERIES

    def __init__(self, window_days: int = 7) -> None:
        if window_days < 1:
            raise ValueError("window_days must be at least 1.")
        self.window_days = int(window_days)
        self.fallback_ = 0.0

    def fit(self, training_frame: pd.DataFrame) -> "MovingAverageModel":
        series = training_series(training_frame)
        if series.empty:
            self.fallback_ = 0.0
        else:
            self.fallback_ = float(series.tail(self.window_days).mean())
        return self

    def predict(self, inference_frame: pd.DataFrame) -> pd.DataFrame:
        predictions = inference_frame.copy()
        rolling_column = f"TARGET_ROLLING_MEAN_{self.window_days}"
        if rolling_column in predictions.columns:
            values = pd.to_numeric(predictions[rolling_column], errors="coerce")
            predictions[PREDICTION_COLUMN] = values.fillna(self.fallback_).astype(float)
        elif self.window_days == 7 and "TARGET_ROLLING_MEAN_7" in predictions.columns:
            values = pd.to_numeric(predictions["TARGET_ROLLING_MEAN_7"], errors="coerce")
            predictions[PREDICTION_COLUMN] = values.fillna(self.fallback_).astype(float)
        else:
            predictions[PREDICTION_COLUMN] = self.fallback_
        return predictions

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            model_name="moving_average",
            dataset_kind=self.dataset_kind,
            description="Predicts from a recent moving average of available targets.",
            parameters={"window_days": self.window_days},
        )


class KnownAmountD1BaselineModel(ForecastModel):
    """Business baseline that predicts the amount already known for D+1."""

    dataset_kind = DatasetKind.TABULAR

    def __init__(self) -> None:
        self.global_fallback_ = 0.0

    def fit(self, training_frame: pd.DataFrame) -> "KnownAmountD1BaselineModel":
        self.global_fallback_ = mean_training_value(training_frame)
        return self

    def predict(self, inference_frame: pd.DataFrame) -> pd.DataFrame:
        predictions = inference_frame.copy()
        if "KNOWN_AMOUNT_D1" not in predictions.columns:
            predictions[PREDICTION_COLUMN] = self.global_fallback_
            return predictions
        predictions[PREDICTION_COLUMN] = (
            pd.to_numeric(predictions["KNOWN_AMOUNT_D1"], errors="coerce")
            .fillna(self.global_fallback_)
            .astype(float)
        )
        return predictions

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            model_name="known_amount_d1",
            dataset_kind=self.dataset_kind,
            description="Predicts the D+1 amount already known at the cutoff.",
        )
