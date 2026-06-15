from __future__ import annotations
import copy
from collections import Counter
from collections.abc import Callable
from typing import Any
import pandas as pd
from loguru import logger

from cash_flow_forecast.contracts.builders import (
    BacktestConfig,
    BacktestResult,
    BacktestRunReport,
    DatasetConfig,
    DatasetBuildRequest,
    GoldBuildResult,
    ModelInfo,
    ModelSpec,
)
from cash_flow_forecast.contracts.rules import Ruleset
from cash_flow_forecast.dataset_building import DatasetBuilder
from cash_flow_forecast.dataset_building.builder import (
    FORECAST_HORIZON_DAYS,
)
from cash_flow_forecast.dataset_building.target_transforms import (
    FittedTargetTransformer,
    TARGET_TRANSFORM_NONE,
    fit_target_transformer,
    inverse_transform_target_series,
    requires_fitted_target_transformer,
)
from cash_flow_forecast.data_layers.gold.builder import TARGET_AMOUNT_COLUMN
from cash_flow_forecast.modeling import ForecastModel, PREDICTION_COLUMN
from cash_flow_forecast.modeling.composites import CompositeForecastModel
from cash_flow_forecast.modeling.prediction_intervals import interval_columns
from cash_flow_forecast.modeling.registry import create_model, model_spec_for_name


ModelSource = ForecastModel | Callable[[], ForecastModel] | ModelSpec | str


class RollingWindowBacktestEngine:
    """Run D+1 rolling-origin backtests from one Gold dataset."""

    def __init__(self, dataset_builder: DatasetBuilder | None = None):
        self.dataset_builder = dataset_builder or DatasetBuilder()

    def run(
        self,
        gold_outputs: GoldBuildResult,
        ruleset: Ruleset,
        model: ModelSource,
        config: BacktestConfig,
        *,
        log_every_n_cutoffs: int = 1,
    ) -> BacktestResult:
        """Run one rolling-origin backtest."""

        model_factory, model_info, result_config = self._prepare_model(model, config)
        coverages = result_config.prediction_intervals_coverage
        log_every_n_cutoffs = max(int(log_every_n_cutoffs), 1)

        predictions_by_cutoff: list[pd.DataFrame] = []
        feature_columns: set[str] = set()
        skipped_reasons: Counter[str] = Counter()
        total_training_rows = 0
        total_inference_rows = 0
        completed_folds = 0
        evaluation_cutoffs = pd.date_range(
            result_config.evaluation_cutoff_start,
            result_config.evaluation_cutoff_end,
            freq="D",
        )

        logger.info(
            "Starting D+1 backtest | model={} | dataset_kind={} | "
            "cutoffs={} -> {} | train_window_days={} | history_window_days={}",
            model_info.model_name,
            result_config.dataset.kind.value,
            result_config.evaluation_cutoff_start,
            result_config.evaluation_cutoff_end,
            result_config.train_window_days,
            result_config.dataset.history_window_days,
        )

        total_cutoffs = len(evaluation_cutoffs)
        skipped_empty = 0
        for fold_index, cutoff in enumerate(evaluation_cutoffs, start=1):
            train_cutoff_end = cutoff - pd.Timedelta(days=FORECAST_HORIZON_DAYS)
            train_cutoff_start = train_cutoff_end - pd.Timedelta(days=result_config.train_window_days - 1)
            training_cutoffs = pd.date_range(train_cutoff_start, train_cutoff_end, freq="D")
            if training_cutoffs.empty:
                reason = "empty_training_cutoffs"
                skipped_reasons[reason] += 1
                skipped_empty += 1
                continue

            should_log_fold = (
                fold_index == 1
                or fold_index == total_cutoffs
                or fold_index % log_every_n_cutoffs == 0
            )
            if should_log_fold:
                logger.info(
                    "Fold {}/{} | eval_cutoff={} | train_cutoffs={} -> {}",
                    fold_index,
                    total_cutoffs,
                    cutoff.date(),
                    train_cutoff_start.date(),
                    train_cutoff_end.date(),
                )

            fold_model = model_factory()
            self._validate_model_compatibility(fold_model, result_config)
            if isinstance(fold_model, CompositeForecastModel):
                (
                    composite_training_frames,
                    composite_inference_frames,
                    composite_target_transformers,
                    fold_features,
                    fold_training_rows,
                    fold_inference_rows,
                ) = self._build_composite_fold_frames(
                    model=fold_model,
                    gold_outputs=gold_outputs,
                    ruleset=ruleset,
                    cutoff=cutoff,
                    training_cutoffs=training_cutoffs,
                )
                feature_columns.update(fold_features)
                training_frame = composite_training_frames.get(fold_model.anchor_alias, pd.DataFrame())
                inference_frame = composite_inference_frames.get(fold_model.anchor_alias, pd.DataFrame())
                fold_target_transformer = composite_target_transformers[fold_model.anchor_alias]
                total_training_rows += fold_training_rows
                total_inference_rows += fold_inference_rows
                fold_feature_count = len(fold_features)
                if any(frame.empty for frame in composite_training_frames.values()) or any(
                    frame.empty for frame in composite_inference_frames.values()
                ):
                    training_frame = pd.DataFrame()
                    inference_frame = pd.DataFrame()
            else:
                fold_target_transformer = self._fit_fold_target_transformer(
                    gold_outputs=gold_outputs,
                    ruleset=ruleset,
                    dataset=result_config.dataset,
                    training_cutoffs=training_cutoffs,
                    label_as_of_date=cutoff.date(),
                )
                training_dataset = self.dataset_builder.build(
                    DatasetBuildRequest(
                        gold_outputs=gold_outputs,
                        ruleset=ruleset,
                        dataset=result_config.dataset,
                        cutoff_dates=[cutoff_date.date() for cutoff_date in training_cutoffs],
                        label_as_of_date=cutoff.date(),
                        target_transformer=fold_target_transformer,
                    )
                )
                inference_dataset = self.dataset_builder.build(
                    DatasetBuildRequest(
                        gold_outputs=gold_outputs,
                        ruleset=ruleset,
                        dataset=result_config.dataset,
                        cutoff_dates=[cutoff.date()],
                        label_as_of_date=None,
                        target_transformer=fold_target_transformer,
                    )
                )
                feature_columns.update(training_dataset.manifest.feature_columns)
                feature_columns.update(inference_dataset.manifest.feature_columns)

                training_frame = training_dataset.dataframe
                inference_frame = inference_dataset.dataframe
                total_training_rows += len(training_frame)
                total_inference_rows += len(inference_frame)
                fold_feature_count = len(
                    set(training_dataset.manifest.feature_columns)
                    | set(inference_dataset.manifest.feature_columns)
                )
            if training_frame.empty or inference_frame.empty:
                reason = self._skip_reason(training_frame, inference_frame)
                skipped_reasons[reason] += 1
                skipped_empty += 1
                if should_log_fold:
                    logger.warning(
                        "Skipping fold {} | reason={} | training_rows={} | inference_rows={}",
                        cutoff.date(),
                        reason,
                        len(training_frame),
                        len(inference_frame),
                    )
                continue

            if isinstance(fold_model, CompositeForecastModel):
                if coverages:
                    raise ValueError("prediction_intervals_coverage is not supported for composite models.")
                fold_model.fit_composite(composite_training_frames)
                predictions = fold_model.predict_composite(composite_inference_frames)
                self._validate_predictions(predictions)
            else:
                fold_model.fit(training_frame)
            if coverages and not isinstance(fold_model, CompositeForecastModel):
                predictions = fold_model.predict_interval(inference_frame, coverages)
                self._validate_interval_predictions(predictions, coverages)
            elif not isinstance(fold_model, CompositeForecastModel):
                predictions = fold_model.predict(inference_frame)
                self._validate_predictions(predictions)

            predictions = predictions.copy()
            predictions = self._original_scale_predictions(
                predictions,
                fold_target_transformer,
                coverages,
            )
            predictions["ABS_ERROR"] = (
                predictions[PREDICTION_COLUMN] - predictions[TARGET_AMOUNT_COLUMN]
            ).abs()
            predictions["EVALUATION_CUTOFF"] = cutoff
            predictions["TRAIN_CUTOFF_START"] = train_cutoff_start
            predictions["TRAIN_CUTOFF_END"] = train_cutoff_end
            predictions = self._select_prediction_columns(predictions, coverages)
            predictions_by_cutoff.append(predictions)
            completed_folds += 1

            if should_log_fold:
                logger.info(
                    "Fold {}/{} data | eval_cutoff={} | training_rows={} | inference_rows={} | features={}",
                    fold_index,
                    total_cutoffs,
                    cutoff.date(),
                    len(training_frame),
                    len(inference_frame),
                    fold_feature_count,
                )

        combined_predictions = (
            pd.concat(predictions_by_cutoff, ignore_index=True, sort=False)
            if predictions_by_cutoff
            else pd.DataFrame(columns=self._prediction_columns(coverages))
        )
        if skipped_empty:
            logger.warning("Skipped {} fold(s): {}", skipped_empty, dict(skipped_reasons))
        logger.info(
            "Finished backtest | model={} | custom_name={} | prediction_rows={}",
            model_info.model_name,
            result_config.custom_name,
            len(combined_predictions),
        )
        run_report = BacktestRunReport(
            model_info=model_info,
            custom_name=result_config.custom_name,
            dataset_kind=model_info.dataset_kind,
            dataset_config=result_config.dataset,
            ruleset_id=ruleset.ruleset_id,
            evaluation_cutoff_start=result_config.evaluation_cutoff_start,
            evaluation_cutoff_end=result_config.evaluation_cutoff_end,
            train_window_days=result_config.train_window_days,
            prediction_intervals_coverage=coverages,
            forecast_horizon_days=FORECAST_HORIZON_DAYS,
            cutoff_count=total_cutoffs,
            completed_folds=completed_folds,
            skipped_folds=sum(skipped_reasons.values()),
            skipped_reasons=dict(skipped_reasons),
            source_row_counts=self._source_row_counts(gold_outputs),
            training_row_count=total_training_rows,
            inference_row_count=total_inference_rows,
            prediction_row_count=len(combined_predictions),
            feature_columns=sorted(feature_columns),
            training_budget=self._training_budget(model_info.parameters),
        )

        return BacktestResult(
            predictions=combined_predictions,
            model_info=model_info,
            config=result_config,
            run_report=run_report,
        )

    @staticmethod
    def _prepare_model(
        model: ModelSource,
        config: BacktestConfig,
    ) -> tuple[Callable[[], ForecastModel], ModelInfo, BacktestConfig]:
        """Return a fresh-model factory plus metadata for the result contract."""

        result_config = config
        if isinstance(model, str):
            model_spec = model_spec_for_name(model, dataset_kind=config.dataset.kind)
            result_config = config.model_copy(update={"model_spec": model_spec})
            factory = lambda: create_model(model_spec, dataset_kind=config.dataset.kind)
        elif isinstance(model, ModelSpec):
            if model.dataset_kind != config.dataset.kind:
                raise ValueError("model.dataset_kind must match BacktestConfig.dataset.kind.")
            result_config = config.model_copy(update={"model_spec": model})
            factory = lambda: create_model(model, dataset_kind=config.dataset.kind)
        elif isinstance(model, ForecastModel):
            prototype = copy.deepcopy(model)
            model_info = prototype.model_info()
            model_spec = ModelSpec(
                model_name=model_info.model_name,
                dataset_kind=model_info.dataset_kind,
                parameters=model_info.parameters,
            )
            result_config = config.model_copy(update={"model_spec": model_spec})
            factory = lambda: copy.deepcopy(prototype)
        elif callable(model):
            factory = model
        else:
            raise TypeError("model must be a ForecastModel, ModelSpec, model name, or factory.")

        sample_model = factory()
        if not isinstance(sample_model, ForecastModel):
            raise TypeError("model factory must return a ForecastModel.")
        RollingWindowBacktestEngine._validate_model_compatibility(sample_model, result_config)
        if result_config.prediction_intervals_coverage and not hasattr(sample_model, "predict_interval"):
            raise ValueError(
                "prediction_intervals_coverage is only supported by sktime-backed models "
                f"in the normal backtest runner; {sample_model.model_info().model_name!r} does not support it."
            )
        model_info = sample_model.model_info()
        if result_config.model_spec is None:
            result_config = config.model_copy(
                update={
                    "model_spec": ModelSpec(
                        model_name=model_info.model_name,
                        dataset_kind=model_info.dataset_kind,
                        parameters=model_info.parameters,
                    )
                }
            )
        return factory, model_info, result_config

    def _build_composite_fold_frames(
        self,
        *,
        model: CompositeForecastModel,
        gold_outputs: GoldBuildResult,
        ruleset: Ruleset,
        cutoff: pd.Timestamp,
        training_cutoffs: pd.DatetimeIndex,
    ) -> tuple[
        dict[str, pd.DataFrame],
        dict[str, pd.DataFrame],
        dict[str, FittedTargetTransformer],
        set[str],
        int,
        int,
    ]:
        training_frames: dict[str, pd.DataFrame] = {}
        inference_frames: dict[str, pd.DataFrame] = {}
        target_transformers: dict[str, FittedTargetTransformer] = {}
        feature_columns: set[str] = set()
        training_rows = 0
        inference_rows = 0

        for alias, spec in model.composite_dataset_specs().items():
            target_transformer = self._fit_fold_target_transformer(
                gold_outputs=gold_outputs,
                ruleset=ruleset,
                dataset=spec.dataset,
                training_cutoffs=training_cutoffs,
                label_as_of_date=cutoff.date(),
            )
            training_dataset = self.dataset_builder.build(
                DatasetBuildRequest(
                    gold_outputs=gold_outputs,
                    ruleset=ruleset,
                    dataset=spec.dataset,
                    cutoff_dates=[cutoff_date.date() for cutoff_date in training_cutoffs],
                    label_as_of_date=cutoff.date(),
                    target_transformer=target_transformer,
                )
            )
            inference_dataset = self.dataset_builder.build(
                DatasetBuildRequest(
                    gold_outputs=gold_outputs,
                    ruleset=ruleset,
                    dataset=spec.dataset,
                    cutoff_dates=[cutoff.date()],
                    label_as_of_date=None,
                    target_transformer=target_transformer,
                )
            )
            training_frames[alias] = training_dataset.dataframe
            inference_frames[alias] = inference_dataset.dataframe
            target_transformers[alias] = target_transformer
            feature_columns.update(training_dataset.manifest.feature_columns)
            feature_columns.update(inference_dataset.manifest.feature_columns)
            training_rows += len(training_dataset.dataframe)
            inference_rows += len(inference_dataset.dataframe)

        return training_frames, inference_frames, target_transformers, feature_columns, training_rows, inference_rows

    def _fit_fold_target_transformer(
        self,
        *,
        gold_outputs: GoldBuildResult,
        ruleset: Ruleset,
        dataset: DatasetConfig,
        training_cutoffs: pd.DatetimeIndex,
        label_as_of_date: object,
    ) -> FittedTargetTransformer:
        if not requires_fitted_target_transformer(dataset.target_transform):
            return fit_target_transformer(pd.Series(dtype="float64"), dataset.target_transform)

        raw_dataset = dataset.model_copy(update={"target_transform": TARGET_TRANSFORM_NONE})
        raw_training_dataset = self.dataset_builder.build(
            DatasetBuildRequest(
                gold_outputs=gold_outputs,
                ruleset=ruleset,
                dataset=raw_dataset,
                cutoff_dates=[cutoff_date.date() for cutoff_date in training_cutoffs],
                label_as_of_date=label_as_of_date,
            )
        )
        raw_target = (
            raw_training_dataset.dataframe[TARGET_AMOUNT_COLUMN]
            if TARGET_AMOUNT_COLUMN in raw_training_dataset.dataframe.columns
            else pd.Series(dtype="float64")
        )
        return fit_target_transformer(raw_target, dataset.target_transform)

    @staticmethod
    def _original_scale_predictions(
        predictions: pd.DataFrame,
        target_transformer: FittedTargetTransformer,
        coverages: list[float],
    ) -> pd.DataFrame:
        result = predictions.copy()
        for column in [PREDICTION_COLUMN, TARGET_AMOUNT_COLUMN, *interval_columns(coverages)]:
            result[column] = inverse_transform_target_series(
                result[column],
                target_transformer.name,
                target_transformer,
            )
        return result

    @staticmethod
    def _select_prediction_columns(predictions: pd.DataFrame, coverages: list[float]) -> pd.DataFrame:
        columns = RollingWindowBacktestEngine._prediction_columns(coverages)
        missing_columns = [column for column in columns if column not in predictions.columns]
        if missing_columns:
            raise ValueError(f"Prediction output is missing required columns: {missing_columns}.")
        return predictions.loc[:, columns]

    @staticmethod
    def _prediction_columns(coverages: list[float]) -> list[str]:
        return [
            "CUTOFF_DATE",
            "FORECAST_DATE",
            TARGET_AMOUNT_COLUMN,
            PREDICTION_COLUMN,
            "ABS_ERROR",
            "EVALUATION_CUTOFF",
            "TRAIN_CUTOFF_START",
            "TRAIN_CUTOFF_END",
            *interval_columns(coverages),
        ]

    @staticmethod
    def _skip_reason(training_frame: pd.DataFrame, inference_frame: pd.DataFrame) -> str:
        if training_frame.empty and inference_frame.empty:
            return "empty_training_and_inference_data"
        if training_frame.empty:
            return "empty_training_data"
        return "empty_inference_data"

    @staticmethod
    def _source_row_counts(gold_outputs: GoldBuildResult) -> dict[str, int]:
        return {
            "realized_cash_in": len(gold_outputs.realized_cash_in),
            "known_movements_daily": len(gold_outputs.known_movements_daily),
        }

    @staticmethod
    def _training_budget(parameters: dict[str, Any]) -> dict[str, Any]:
        budget_keys = {
            "n_estimators",
            "max_steps",
            "min_observations",
            "input_size",
            "batch_size",
            "windows_batch_size",
            "n_jobs",
        }
        budget: dict[str, Any] = {}

        def collect(payload: dict[str, Any], prefix: str = "") -> None:
            for key, value in payload.items():
                name = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    collect(value, name)
                elif key in budget_keys:
                    budget[name] = RollingWindowBacktestEngine._json_scalar(value)

        collect(parameters)
        return budget

    @staticmethod
    def _json_scalar(value: object) -> object:
        if pd.isna(value):
            return None
        if hasattr(value, "item"):
            return value.item()
        return value

    @staticmethod
    def _validate_model_compatibility(model: ForecastModel, config: BacktestConfig) -> None:
        model_info = model.model_info()
        if model_info.dataset_kind != config.dataset.kind:
            raise ValueError(
                f"Model {model_info.model_name!r} expects {model_info.dataset_kind.value} "
                f"datasets, not {config.dataset.kind.value}."
            )

    @staticmethod
    def _validate_predictions(predictions: pd.DataFrame) -> None:
        missing_columns = [
            column
            for column in [PREDICTION_COLUMN, TARGET_AMOUNT_COLUMN]
            if column not in predictions.columns
        ]
        if missing_columns:
            raise ValueError(f"Prediction output is missing required columns: {missing_columns}.")

    @staticmethod
    def _validate_interval_predictions(predictions: pd.DataFrame, coverages: list[float]) -> None:
        required_columns = [PREDICTION_COLUMN, TARGET_AMOUNT_COLUMN, *interval_columns(coverages)]
        missing_columns = [
            column
            for column in required_columns
            if column not in predictions.columns
        ]
        if missing_columns:
            raise ValueError(f"Interval prediction output is missing required columns: {missing_columns}.")
