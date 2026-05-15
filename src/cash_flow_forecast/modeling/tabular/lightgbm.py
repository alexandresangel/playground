from __future__ import annotations
import pandas as pd

from cash_flow_forecast.contracts.builders import ModelInfo
from cash_flow_forecast.contracts.enums import DatasetKind
from cash_flow_forecast.data_layers.gold.builder import TARGET_AMOUNT_COLUMN
from cash_flow_forecast.modeling.base import ForecastModel
from cash_flow_forecast.modeling.features import PREDICTION_COLUMN, feature_frame, numeric_feature_columns


class LightGBMRegressorModel(ForecastModel):
    """LightGBM regressor wrapper for tabular point-in-time features."""

    dataset_kind = DatasetKind.TABULAR

    def __init__(self, **parameters: object) -> None:
        self.parameters = {
            "n_estimators": 100,
            "num_leaves": 31,
            "learning_rate": 0.05,
            "random_state": 0,
            "n_jobs": 1,
            "verbosity": -1,
        }
        self.parameters.update(parameters)
        self.feature_columns_: list[str] = []
        self.global_fallback_ = 0.0
        self.model_: object | None = None

    def fit(self, training_frame: pd.DataFrame) -> "LightGBMRegressorModel":
        if not training_frame.empty:
            self.global_fallback_ = float(training_frame[TARGET_AMOUNT_COLUMN].mean())
        self.feature_columns_ = numeric_feature_columns(training_frame)
        if training_frame.empty or not self.feature_columns_:
            return self

        try:
            from lightgbm import LGBMRegressor
        except ImportError as exc:
            raise RuntimeError("LightGBMRegressorModel requires `lightgbm`. Install project dependencies first.") from exc

        x_train = feature_frame(training_frame, self.feature_columns_)
        y_train = training_frame[TARGET_AMOUNT_COLUMN].astype(float)
        self.model_ = LGBMRegressor(**self.parameters)
        try:
            self.model_.fit(x_train, y_train)
        except Exception as exc:
            self.model_ = None
            raise RuntimeError(
                "LightGBMRegressorModel failed to fit. Check the model parameters "
                "and training feature values."
            ) from exc
        return self

    def predict(self, inference_frame: pd.DataFrame) -> pd.DataFrame:
        predictions = inference_frame.copy()
        if self.model_ is None or not self.feature_columns_:
            predictions[PREDICTION_COLUMN] = self.global_fallback_
            return predictions

        x_inference = feature_frame(predictions, self.feature_columns_)
        predictions[PREDICTION_COLUMN] = self.model_.predict(x_inference).astype(float)
        return predictions

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            model_name="lightgbm_regressor",
            dataset_kind=self.dataset_kind,
            description="LightGBM regressor trained on numeric tabular point-in-time features.",
            parameters=self.parameters,
        )
