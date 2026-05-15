from __future__ import annotations
from abc import ABC, abstractmethod
import pandas as pd

from cash_flow_forecast.contracts.builders import ModelInfo
from cash_flow_forecast.contracts.enums import DatasetKind


class ForecastModel(ABC):
    """Abstract forecasting model used by the backtesting engine."""

    dataset_kind: DatasetKind

    @abstractmethod
    def fit(self, training_frame: pd.DataFrame) -> "ForecastModel":
        """Fit the model on one point-in-time training dataset."""

    @abstractmethod
    def predict(self, inference_frame: pd.DataFrame) -> pd.DataFrame:
        """Return one prediction per inference row."""

    @abstractmethod
    def model_info(self) -> ModelInfo:
        """Return lightweight metadata for reporting."""