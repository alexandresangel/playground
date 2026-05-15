from __future__ import annotations
from abc import abstractmethod
from typing import Any
import pandas as pd

from cash_flow_forecast.contracts.builders import ModelInfo
from cash_flow_forecast.contracts.enums import DatasetKind
from cash_flow_forecast.modeling.base import ForecastModel
from cash_flow_forecast.modeling.features import (
    PREDICTION_COLUMN,
    forecast_column,
    forecast_steps_from_training,
    mean_training_value,
    nixtla_frame,
)


class StatsForecastAdapter(ForecastModel):
    """Base adapter for one-sequence StatsForecast models."""

    dataset_kind = DatasetKind.TIME_SERIES
    model_name: str
    description: str
    default_parameters: dict[str, Any] = {}

    def __init__(self, min_observations: int = 2, **parameters: object) -> None:
        self.min_observations = int(min_observations)
        self.parameters = dict(self.default_parameters)
        self.parameters.update(parameters)
        self.fallback_ = 0.0
        self.training_frame_ = pd.DataFrame()
        self.forecaster_: object | None = None
        self.output_column_: str | None = None

    def fit(self, training_frame: pd.DataFrame) -> "StatsForecastAdapter":
        self.training_frame_ = training_frame.copy()
        self.fallback_ = mean_training_value(training_frame)
        nixtla_training = nixtla_frame(training_frame)
        if len(nixtla_training) < self.min_observations:
            return self

        try:
            from statsforecast import StatsForecast

            self.forecaster_ = StatsForecast(
                models=[self._make_model()],
                freq="D",
                n_jobs=1,
            )
            self.forecaster_.fit(df=nixtla_training)
        except Exception:
            self.forecaster_ = None
        return self

    def predict(self, inference_frame: pd.DataFrame) -> pd.DataFrame:
        predictions = inference_frame.copy()
        if self.forecaster_ is None or self.training_frame_.empty:
            predictions[PREDICTION_COLUMN] = self.fallback_
            return predictions

        steps = forecast_steps_from_training(self.training_frame_, predictions)
        try:
            forecast = self.forecaster_.predict(h=steps)
            output_column = forecast_column(forecast)
            forecast_map = {
                pd.Timestamp(row["ds"]).normalize(): float(row[output_column])
                for _, row in forecast.iterrows()
            }
            forecast_dates = pd.to_datetime(predictions["FORECAST_DATE"]).dt.normalize()
            predictions[PREDICTION_COLUMN] = [
                forecast_map.get(pd.Timestamp(forecast_date).normalize(), self.fallback_)
                for forecast_date in forecast_dates
            ]
        except Exception:
            predictions[PREDICTION_COLUMN] = self.fallback_
        return predictions

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            model_name=self.model_name,
            dataset_kind=self.dataset_kind,
            description=self.description,
            parameters={
                "min_observations": self.min_observations,
                **self.parameters,
            },
        )

    @abstractmethod
    def _make_model(self) -> object:
        """Build the concrete StatsForecast model."""
