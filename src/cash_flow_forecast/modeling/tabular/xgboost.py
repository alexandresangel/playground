from __future__ import annotations
import pandas as pd

from cash_flow_forecast.contracts.builders import ModelInfo
from cash_flow_forecast.contracts.enums import DatasetKind
from cash_flow_forecast.data_layers.gold.builder import TARGET_AMOUNT_COLUMN
from cash_flow_forecast.modeling.base import ForecastModel
from cash_flow_forecast.modeling.features import PREDICTION_COLUMN, feature_frame, numeric_feature_columns


class XGBoostRegressorModel(ForecastModel):
    """XGBoost regressor wrapper for tabular point-in-time features."""

    dataset_kind = DatasetKind.TABULAR

    def __init__(self, **parameters: object) -> None:
        self.parameters = {
            "n_estimators": 50,
            "max_depth": 3,
            "learning_rate": 0.05,
            "objective": "reg:squarederror",
            "random_state": 0,
            "n_jobs": 1,
            "verbosity": 0,
        }
        self.parameters.update(parameters)
        self.feature_columns_: list[str] = []
        self.global_fallback_ = 0.0
        self.model_: object | None = None

    def fit(self, training_frame: pd.DataFrame) -> "XGBoostRegressorModel":
        if not training_frame.empty:
            self.global_fallback_ = float(training_frame[TARGET_AMOUNT_COLUMN].mean())
        self.feature_columns_ = numeric_feature_columns(training_frame)
        if training_frame.empty or not self.feature_columns_:
            return self

        try:
            import xgboost as xgb
        except ImportError as exc:
            raise RuntimeError("XGBoostRegressorModel requires `xgboost`. Install project dependencies first.") from exc

        x_train = feature_frame(training_frame, self.feature_columns_)
        y_train = training_frame[TARGET_AMOUNT_COLUMN].astype(float)
        train_matrix = xgb.DMatrix(x_train, label=y_train)
        try:
            self.model_ = xgb.train(
                params=self._native_parameters(),
                dtrain=train_matrix,
                num_boost_round=int(self.parameters["n_estimators"]),
            )
        except Exception as exc:
            self.model_ = None
            raise RuntimeError(
                "XGBoostRegressorModel failed to fit. Check the model parameters "
                "and training feature values."
            ) from exc
        return self

    def predict(self, inference_frame: pd.DataFrame) -> pd.DataFrame:
        predictions = inference_frame.copy()
        if self.model_ is None or not self.feature_columns_:
            predictions[PREDICTION_COLUMN] = self.global_fallback_
            return predictions

        import xgboost as xgb

        x_inference = feature_frame(predictions, self.feature_columns_)
        predictions[PREDICTION_COLUMN] = self.model_.predict(xgb.DMatrix(x_inference)).astype(float)
        return predictions

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            model_name="xgboost_regressor",
            dataset_kind=self.dataset_kind,
            description="XGBoost regressor trained on numeric tabular point-in-time features.",
            parameters=self.parameters,
        )

    def _native_parameters(self) -> dict[str, object]:
        return {
            "max_depth": self.parameters["max_depth"],
            "eta": self.parameters["learning_rate"],
            "objective": self.parameters["objective"],
            "seed": self.parameters["random_state"],
            "nthread": self.parameters["n_jobs"],
            "verbosity": self.parameters["verbosity"],
        }
