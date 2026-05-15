from __future__ import annotations
import pandas as pd

from cash_flow_forecast.contracts.builders import ModelInfo
from cash_flow_forecast.contracts.enums import DatasetKind
from cash_flow_forecast.data_layers.gold.builder import TARGET_AMOUNT_COLUMN
from cash_flow_forecast.modeling.base import ForecastModel
from cash_flow_forecast.modeling.features import PREDICTION_COLUMN, feature_frame, numeric_feature_columns


class LightGBMZeroAwareModel(ForecastModel):
    """Two-stage LightGBM model: occurrence probability times cash magnitude."""

    dataset_kind = DatasetKind.TABULAR

    def __init__(
        self,
        classifier_parameters: dict[str, object] | None = None,
        regressor_parameters: dict[str, object] | None = None,
    ) -> None:
        self.classifier_parameters = {
            "n_estimators": 100,
            "num_leaves": 31,
            "learning_rate": 0.05,
            "random_state": 0,
            "n_jobs": 1,
            "verbosity": -1,
        }
        self.classifier_parameters.update(classifier_parameters or {})
        self.regressor_parameters = {
            "n_estimators": 100,
            "num_leaves": 31,
            "learning_rate": 0.05,
            "random_state": 0,
            "n_jobs": 1,
            "verbosity": -1,
        }
        self.regressor_parameters.update(regressor_parameters or {})
        self.feature_columns_: list[str] = []
        self.occurrence_probability_ = 0.0
        self.magnitude_fallback_ = 0.0
        self.classifier_: object | None = None
        self.regressor_: object | None = None

    def fit(self, training_frame: pd.DataFrame) -> "LightGBMZeroAwareModel":
        self.feature_columns_ = numeric_feature_columns(training_frame)
        if training_frame.empty:
            return self

        target = training_frame[TARGET_AMOUNT_COLUMN].astype(float)
        occurrence = target.ne(0).astype(int)
        self.occurrence_probability_ = float(occurrence.mean())
        non_zero_target = target.loc[target.ne(0)]
        self.magnitude_fallback_ = float(non_zero_target.mean()) if not non_zero_target.empty else 0.0
        if not self.feature_columns_:
            return self

        try:
            from lightgbm import LGBMClassifier, LGBMRegressor
        except ImportError as exc:
            raise RuntimeError("LightGBMZeroAwareModel requires `lightgbm`. Install project dependencies first.") from exc

        x_train = feature_frame(training_frame, self.feature_columns_)
        if occurrence.nunique() == 2:
            try:
                self.classifier_ = LGBMClassifier(**self.classifier_parameters)
                self.classifier_.fit(x_train, occurrence)
            except Exception as exc:
                self.classifier_ = None
                raise RuntimeError(
                    "LightGBMZeroAwareModel occurrence classifier failed to fit. "
                    "Check classifier_parameters and training feature values."
                ) from exc

        non_zero_rows = target.ne(0)
        if non_zero_rows.any():
            try:
                self.regressor_ = LGBMRegressor(**self.regressor_parameters)
                self.regressor_.fit(x_train.loc[non_zero_rows], target.loc[non_zero_rows])
            except Exception as exc:
                self.regressor_ = None
                raise RuntimeError(
                    "LightGBMZeroAwareModel magnitude regressor failed to fit. "
                    "Check regressor_parameters and non-zero training targets."
                ) from exc
        return self

    def predict(self, inference_frame: pd.DataFrame) -> pd.DataFrame:
        predictions = inference_frame.copy()
        if not self.feature_columns_:
            predictions[PREDICTION_COLUMN] = self.occurrence_probability_ * self.magnitude_fallback_
            return predictions

        x_inference = feature_frame(predictions, self.feature_columns_)
        if self.classifier_ is None:
            occurrence_probability = pd.Series(self.occurrence_probability_, index=predictions.index, dtype="float64")
        else:
            occurrence_probability = pd.Series(
                self.classifier_.predict_proba(x_inference)[:, 1],
                index=predictions.index,
                dtype="float64",
            )

        if self.regressor_ is None:
            magnitude = pd.Series(self.magnitude_fallback_, index=predictions.index, dtype="float64")
        else:
            magnitude = pd.Series(
                self.regressor_.predict(x_inference),
                index=predictions.index,
                dtype="float64",
            )

        predictions[PREDICTION_COLUMN] = occurrence_probability * magnitude
        return predictions

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            model_name="lightgbm_zero_aware",
            dataset_kind=self.dataset_kind,
            description="Two-stage LightGBM model: occurrence classifier times magnitude regressor.",
            parameters={
                "classifier_parameters": self.classifier_parameters,
                "regressor_parameters": self.regressor_parameters,
            },
        )
