from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import pandas as pd

from cash_flow_forecast.contracts.builders import DatasetConfig, ModelInfo, ModelSpec
from cash_flow_forecast.contracts.enums import DatasetKind
from cash_flow_forecast.data_layers.gold.builder import TARGET_AMOUNT_COLUMN
from cash_flow_forecast.modeling.base import ForecastModel
from cash_flow_forecast.modeling.features import PREDICTION_COLUMN, numeric_feature_columns
from cash_flow_forecast.modeling.supervised import (
    SupervisedClassifier,
    SupervisedRegressor,
    create_supervised_classifier,
    create_supervised_regressor,
)


STACKING_MODEL_NAME = "stacking_ensemble"
OCCURRENCE_SPIKE_CASCADE_MODEL_NAME = "occurrence_spike_cascade"
COMPOSITE_MODEL_NAMES = {STACKING_MODEL_NAME}
SPECIAL_MODEL_NAMES = {STACKING_MODEL_NAME, OCCURRENCE_SPIKE_CASCADE_MODEL_NAME}
ALIGNMENT_COLUMNS = ["CUTOFF_DATE", "FORECAST_DATE"]


@dataclass(frozen=True)
class OOFFold:
    """One inner time-ordered fold used to build stacking meta features."""

    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp


@dataclass(frozen=True)
class CompositeDatasetSpec:
    """Dataset and model requirement for one nested forecasting model."""

    alias: str
    model_spec: ModelSpec
    dataset: DatasetConfig


class CompositeForecastModel(ForecastModel):
    """Forecast model that needs multiple dataset views per outer fold."""

    dataset_kind = DatasetKind.TABULAR

    def composite_dataset_specs(self) -> dict[str, CompositeDatasetSpec]:
        raise NotImplementedError

    @property
    def anchor_alias(self) -> str:
        raise NotImplementedError

    def fit_composite(self, training_frames: dict[str, pd.DataFrame]) -> "CompositeForecastModel":
        raise NotImplementedError

    def predict_composite(self, inference_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
        raise NotImplementedError

    def fit(self, training_frame: pd.DataFrame) -> "CompositeForecastModel":
        raise ValueError(f"{self.model_name} must be fitted by the composite backtest path.")

    def predict(self, inference_frame: pd.DataFrame) -> pd.DataFrame:
        raise ValueError(f"{self.model_name} must be predicted by the composite backtest path.")


class StackingEnsembleModel(CompositeForecastModel):
    """Stack base forecasts with a tabular OOF-trained meta regressor."""

    model_name = STACKING_MODEL_NAME

    def __init__(
        self,
        anchor_model_alias: str,
        base_models: list[dict[str, object]],
        meta_model: dict[str, object],
        oof: dict[str, object] | None = None,
        passthrough_features: bool = False,
    ) -> None:
        self.anchor_model_alias = anchor_model_alias
        self.base_model_specs = [_base_model_runtime_spec(item) for item in base_models]
        self.base_model_by_alias = {spec.alias: spec for spec in self.base_model_specs}
        if self.anchor_model_alias not in self.base_model_by_alias:
            raise ValueError(f"anchor_model_alias={self.anchor_model_alias!r} is not in base_models.")
        self.meta_model_config = dict(meta_model)
        self.oof_config = _oof_config(oof or {})
        self.passthrough_features = bool(passthrough_features)
        self.parameters = {
            "anchor_model_alias": self.anchor_model_alias,
            "base_models": base_models,
            "meta_model": meta_model,
            "oof": self.oof_config,
            "passthrough_features": self.passthrough_features,
        }
        self.meta_model_: SupervisedRegressor | None = None
        self.final_base_models_: dict[str, ForecastModel] = {}
        self.meta_feature_columns_: list[str] = []

    @property
    def anchor_alias(self) -> str:
        return self.anchor_model_alias

    def composite_dataset_specs(self) -> dict[str, CompositeDatasetSpec]:
        return dict(self.base_model_by_alias)

    def fit_composite(self, training_frames: dict[str, pd.DataFrame]) -> "StackingEnsembleModel":
        _validate_required_frames(self.base_model_by_alias, training_frames, "training")
        anchor_frame = training_frames[self.anchor_model_alias]
        folds = rolling_oof_folds(anchor_frame, **self.oof_config)
        oof_frames: list[pd.DataFrame] = []

        for fold in folds:
            fold_features = self._oof_fold_features(training_frames, fold)
            if not fold_features.empty:
                oof_frames.append(fold_features)

        oof_frame = pd.concat(oof_frames, ignore_index=True, sort=False) if oof_frames else pd.DataFrame()
        if len(oof_frame) < int(self.oof_config["min_oof_rows"]):
            raise ValueError(
                f"stacking_ensemble needs at least {self.oof_config['min_oof_rows']} OOF rows; "
                f"got {len(oof_frame)}."
            )

        self.meta_model_ = _create_meta_regressor(self.meta_model_config)
        self.meta_model_.fit(oof_frame, oof_frame[TARGET_AMOUNT_COLUMN].astype(float))
        self.meta_feature_columns_ = numeric_feature_columns(oof_frame)
        self.final_base_models_ = {
            spec.alias: _fit_forecast_model(spec.model_spec, training_frames[spec.alias])
            for spec in self.base_model_specs
        }
        return self

    def predict_composite(self, inference_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
        _validate_required_frames(self.base_model_by_alias, inference_frames, "inference")
        if self.meta_model_ is None:
            raise ValueError("stacking_ensemble must be fitted before prediction.")
        meta_frame = self._base_prediction_features(self.final_base_models_, inference_frames)
        if self.passthrough_features:
            meta_frame = _append_passthrough_features(meta_frame, inference_frames[self.anchor_model_alias])
        predictions = inference_frames[self.anchor_model_alias].copy()
        predictions[PREDICTION_COLUMN] = self.meta_model_.predict(
            meta_frame.reindex(columns=self.meta_feature_columns_, fill_value=0.0)
        )
        return predictions

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            model_name=self.model_name,
            dataset_kind=self.dataset_kind,
            description="OOF stacking ensemble over nested forecasting models.",
            parameters=self.parameters,
        )

    def _oof_fold_features(
        self,
        training_frames: dict[str, pd.DataFrame],
        fold: OOFFold,
    ) -> pd.DataFrame:
        fold_models: dict[str, ForecastModel] = {}
        validation_frames: dict[str, pd.DataFrame] = {}
        for spec in self.base_model_specs:
            frame = training_frames[spec.alias]
            train_frame = frame.loc[pd.to_datetime(frame["CUTOFF_DATE"]) <= fold.train_end]
            validation_frame = frame.loc[
                (pd.to_datetime(frame["CUTOFF_DATE"]) >= fold.validation_start)
                & (pd.to_datetime(frame["CUTOFF_DATE"]) <= fold.validation_end)
            ]
            if train_frame.empty or validation_frame.empty:
                return pd.DataFrame()
            fold_models[spec.alias] = _fit_forecast_model(spec.model_spec, train_frame)
            validation_frames[spec.alias] = validation_frame

        meta_frame = self._base_prediction_features(fold_models, validation_frames)
        anchor_validation = validation_frames[self.anchor_model_alias]
        meta_frame = meta_frame.merge(
            anchor_validation[[*ALIGNMENT_COLUMNS, TARGET_AMOUNT_COLUMN]],
            on=ALIGNMENT_COLUMNS,
            how="inner",
        )
        if self.passthrough_features:
            meta_frame = _append_passthrough_features(meta_frame, anchor_validation)
        return meta_frame

    def _base_prediction_features(
        self,
        models: dict[str, ForecastModel],
        frames: dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        combined: pd.DataFrame | None = None
        for alias, model in models.items():
            predictions = model.predict(frames[alias])
            feature = predictions[[*ALIGNMENT_COLUMNS, PREDICTION_COLUMN]].copy()
            feature = feature.rename(columns={PREDICTION_COLUMN: _base_prediction_column(alias)})
            combined = feature if combined is None else combined.merge(feature, on=ALIGNMENT_COLUMNS, how="inner")
        return combined if combined is not None else pd.DataFrame(columns=ALIGNMENT_COLUMNS)


class OccurrenceSpikeCascadeModel(ForecastModel):
    """Occurrence + spike-regime cascade for lumpy tabular cash-flow series."""

    dataset_kind = DatasetKind.TABULAR
    model_name = OCCURRENCE_SPIKE_CASCADE_MODEL_NAME

    def __init__(
        self,
        spike: dict[str, object] | None = None,
        routing: dict[str, object] | None = None,
        occurrence_model: dict[str, object] | None = None,
        spike_model: dict[str, object] | None = None,
        normal_magnitude_model: dict[str, object] | None = None,
        spike_magnitude_model: dict[str, object] | None = None,
    ) -> None:
        self.spike_config = {
            "method": "training_quantile",
            "quantile": 0.90,
            "min_spike_rows": 10,
            "min_normal_rows": 10,
        }
        self.spike_config.update(spike or {})
        self.routing_config = {
            "mode": "soft",
            "occurrence_threshold": 0.5,
            "spike_threshold": 0.5,
        }
        self.routing_config.update(routing or {})
        self.occurrence_model_config = occurrence_model or {"name": "lightgbm_classifier", "parameters": {}}
        self.spike_model_config = spike_model or {"name": "lightgbm_classifier", "parameters": {}}
        self.normal_magnitude_model_config = normal_magnitude_model or {
            "name": "lightgbm_regressor",
            "parameters": {},
        }
        self.spike_magnitude_model_config = spike_magnitude_model or {
            "name": "lightgbm_regressor",
            "parameters": {},
        }
        self.parameters = {
            "spike": self.spike_config,
            "routing": self.routing_config,
            "occurrence_model": self.occurrence_model_config,
            "spike_model": self.spike_model_config,
            "normal_magnitude_model": self.normal_magnitude_model_config,
            "spike_magnitude_model": self.spike_magnitude_model_config,
        }
        self.spike_threshold_ = float("inf")
        self.occurrence_model_: SupervisedClassifier | None = None
        self.spike_model_: SupervisedClassifier | None = None
        self.normal_magnitude_model_: SupervisedRegressor | None = None
        self.spike_magnitude_model_: SupervisedRegressor | None = None
        self.normal_magnitude_fallback_ = 0.0
        self.spike_magnitude_fallback_ = 0.0

    def fit(self, training_frame: pd.DataFrame) -> "OccurrenceSpikeCascadeModel":
        if training_frame.empty:
            return self
        target = pd.to_numeric(training_frame[TARGET_AMOUNT_COLUMN], errors="coerce").fillna(0.0).astype(float)
        occurrence = target.gt(0).astype(int)
        occurred_frame = training_frame.loc[occurrence.eq(1)]
        occurred_target = target.loc[occurred_frame.index]

        self.spike_threshold_ = self._spike_threshold(occurred_target)
        spike_label = occurred_target.gt(self.spike_threshold_).astype(int)
        normal_mask = target.gt(0) & target.le(self.spike_threshold_)
        spike_mask = target.gt(self.spike_threshold_)

        self.normal_magnitude_fallback_ = _mean_or_zero(target.loc[normal_mask])
        self.spike_magnitude_fallback_ = _mean_or_zero(target.loc[spike_mask])
        if self.spike_magnitude_fallback_ == 0.0:
            self.spike_magnitude_fallback_ = self.normal_magnitude_fallback_

        self.occurrence_model_ = _create_classifier(self.occurrence_model_config)
        self.occurrence_model_.fit(training_frame, occurrence)
        self.spike_model_ = _create_classifier(self.spike_model_config)
        self.spike_model_.fit(occurred_frame, spike_label)

        self.normal_magnitude_model_ = self._fit_regime_regressor(
            self.normal_magnitude_model_config,
            training_frame.loc[normal_mask],
            target.loc[normal_mask],
            int(self.spike_config["min_normal_rows"]),
        )
        self.spike_magnitude_model_ = self._fit_regime_regressor(
            self.spike_magnitude_model_config,
            training_frame.loc[spike_mask],
            target.loc[spike_mask],
            int(self.spike_config["min_spike_rows"]),
        )
        return self

    def predict(self, inference_frame: pd.DataFrame) -> pd.DataFrame:
        predictions = inference_frame.copy()
        p_occurrence = self._classifier_probability(self.occurrence_model_, predictions, 0.0)
        p_spike = self._classifier_probability(self.spike_model_, predictions, 0.0)
        normal_magnitude = self._regressor_prediction(
            self.normal_magnitude_model_,
            predictions,
            self.normal_magnitude_fallback_,
        )
        spike_magnitude = self._regressor_prediction(
            self.spike_magnitude_model_,
            predictions,
            self.spike_magnitude_fallback_,
        )

        if self.routing_config["mode"] == "hard":
            occurrence_mask = p_occurrence.ge(float(self.routing_config["occurrence_threshold"]))
            spike_mask = p_spike.ge(float(self.routing_config["spike_threshold"]))
            amount = pd.Series(0.0, index=predictions.index, dtype="float64")
            amount.loc[occurrence_mask & ~spike_mask] = normal_magnitude.loc[occurrence_mask & ~spike_mask]
            amount.loc[occurrence_mask & spike_mask] = spike_magnitude.loc[occurrence_mask & spike_mask]
        else:
            amount = p_occurrence * ((1.0 - p_spike) * normal_magnitude + p_spike * spike_magnitude)

        predictions[PREDICTION_COLUMN] = amount.astype(float)
        return predictions

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            model_name=self.model_name,
            dataset_kind=self.dataset_kind,
            description="Occurrence probability plus spike/normal magnitude cascade.",
            parameters=self.parameters,
        )

    def _spike_threshold(self, occurred_target: pd.Series) -> float:
        if self.spike_config["method"] != "training_quantile":
            raise ValueError("occurrence_spike_cascade only supports spike.method='training_quantile'.")
        if occurred_target.empty:
            return float("inf")
        return float(occurred_target.quantile(float(self.spike_config["quantile"])))

    def _fit_regime_regressor(
        self,
        config: dict[str, object],
        frame: pd.DataFrame,
        target: pd.Series,
        min_rows: int,
    ) -> SupervisedRegressor | None:
        if len(frame) < min_rows:
            return None
        model = _create_regressor(config)
        model.fit(frame, target)
        return model

    @staticmethod
    def _classifier_probability(
        model: SupervisedClassifier | None,
        frame: pd.DataFrame,
        fallback: float,
    ) -> pd.Series:
        if model is None:
            return pd.Series(fallback, index=frame.index, dtype="float64")
        return model.predict_proba_positive(frame)

    @staticmethod
    def _regressor_prediction(
        model: SupervisedRegressor | None,
        frame: pd.DataFrame,
        fallback: float,
    ) -> pd.Series:
        if model is None:
            return pd.Series(fallback, index=frame.index, dtype="float64")
        return model.predict(frame)


def rolling_oof_folds(
    training_frame: pd.DataFrame,
    max_folds: int = 5,
    min_train_window_days: int = 90,
    validation_window_days: int = 14,
    step_days: int = 14,
    min_oof_rows: int = 30,
) -> list[OOFFold]:
    if training_frame.empty:
        return []
    cutoff_dates = pd.to_datetime(training_frame["CUTOFF_DATE"]).dt.normalize().drop_duplicates().sort_values()
    if cutoff_dates.empty:
        return []
    first_cutoff = pd.Timestamp(cutoff_dates.iloc[0]).normalize()
    last_cutoff = pd.Timestamp(cutoff_dates.iloc[-1]).normalize()
    train_end = first_cutoff + pd.Timedelta(days=int(min_train_window_days) - 1)
    folds: list[OOFFold] = []
    while train_end < last_cutoff:
        validation_start = train_end + pd.Timedelta(days=1)
        validation_end = validation_start + pd.Timedelta(days=int(validation_window_days) - 1)
        if validation_start <= last_cutoff:
            folds.append(
                OOFFold(
                    train_end=train_end,
                    validation_start=validation_start,
                    validation_end=min(validation_end, last_cutoff),
                )
            )
        train_end = train_end + pd.Timedelta(days=int(step_days))
    return folds[-int(max_folds) :]


def _base_model_runtime_spec(payload: dict[str, object]) -> CompositeDatasetSpec:
    return CompositeDatasetSpec(
        alias=str(payload["alias"]),
        model_spec=ModelSpec.model_validate(payload["model_spec"]),
        dataset=DatasetConfig.model_validate(payload["dataset"]),
    )


def _oof_config(payload: dict[str, object]) -> dict[str, int]:
    result = {
        "max_folds": 5,
        "min_train_window_days": 90,
        "validation_window_days": 14,
        "step_days": 14,
        "min_oof_rows": 30,
    }
    result.update({key: int(value) for key, value in payload.items()})
    if any(value < 1 for value in result.values()):
        raise ValueError("stacking_ensemble oof values must be positive integers.")
    return result


def _fit_forecast_model(model_spec: ModelSpec, training_frame: pd.DataFrame) -> ForecastModel:
    from cash_flow_forecast.modeling.registry import create_model

    model = create_model(model_spec)
    model.fit(training_frame)
    return model


def _create_meta_regressor(config: dict[str, object]) -> SupervisedRegressor:
    return _create_regressor(config)


def _create_regressor(config: dict[str, object]) -> SupervisedRegressor:
    return create_supervised_regressor(
        str(config["name"]),
        dict(config.get("parameters") or {}),
    )


def _create_classifier(config: dict[str, object]) -> SupervisedClassifier:
    return create_supervised_classifier(
        str(config["name"]),
        dict(config.get("parameters") or {}),
    )


def _base_prediction_column(alias: str) -> str:
    return f"BASE_{alias.upper()}_PREDICTION"


def _append_passthrough_features(meta_frame: pd.DataFrame, anchor_frame: pd.DataFrame) -> pd.DataFrame:
    passthrough_columns = numeric_feature_columns(anchor_frame)
    if not passthrough_columns:
        return meta_frame
    passthrough = anchor_frame[[*ALIGNMENT_COLUMNS, *passthrough_columns]].copy()
    passthrough = passthrough.rename(
        columns={column: f"ANCHOR_{column}" for column in passthrough_columns}
    )
    return meta_frame.merge(passthrough, on=ALIGNMENT_COLUMNS, how="left")


def _validate_required_frames(
    specs: dict[str, CompositeDatasetSpec],
    frames: dict[str, pd.DataFrame],
    frame_name: str,
) -> None:
    missing = sorted(alias for alias in specs if alias not in frames)
    if missing:
        raise ValueError(f"Missing {frame_name} frame(s) for composite aliases: {missing}.")


def _mean_or_zero(values: pd.Series) -> float:
    return float(values.mean()) if not values.empty else 0.0
