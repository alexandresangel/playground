from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator

from cash_flow_forecast.contracts import BacktestConfig, DatasetConfig
from cash_flow_forecast.contracts.builders import GoldBuildResult, ModelSpec
from cash_flow_forecast.contracts.enums import DatasetKind
from cash_flow_forecast.contracts.rules import Ruleset
from cash_flow_forecast.data_layers.gold.builder import SEQUENCE_ID_COLUMN
from cash_flow_forecast.modeling.composites import SPECIAL_MODEL_NAMES, STACKING_MODEL_NAME
from cash_flow_forecast.modeling.registry import model_spec_for_name
from cash_flow_forecast.modeling.supervised import supervised_estimator_role


LOCAL_ADAPTER_KEYS = {"input_path", "output_path", "ruleset_path"}
TOP_LEVEL_CONFIG_KEYS = {
    "dataset",
    "evaluation",
    "log_level",
    "models",
    "prediction_intervals_coverage",
    "sequence",
    *LOCAL_ADAPTER_KEYS,
}
EVALUATION_CONFIG_KEYS = {
    "cutoff_start",
    "cutoff_end",
    "log_every_n_cutoffs",
    "train_window_days",
}
SEQUENCE_CONFIG_KEYS = {
    "currency",
    "entity",
    "filters",
    "movement_type",
    "sequence_id",
}
RAW_TARGET_REGIME_MODEL_NAMES = {"lightgbm_zero_aware", "occurrence_spike_cascade"}


class BacktestModelConfig(BaseModel):
    """One model declaration from YAML."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    custom_name: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("custom_name")
    @classmethod
    def _validate_custom_name(cls, value: str) -> str:
        _custom_name_parts(value)
        return value


class NestedForecastModelConfig(BaseModel):
    """One nested forecasting model declaration inside a composite model."""

    model_config = ConfigDict(extra="forbid")

    alias: str = Field(min_length=1)
    name: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    dataset: dict[str, Any] = Field(default_factory=dict)

    @field_validator("alias")
    @classmethod
    def _validate_alias(cls, value: str) -> str:
        return _safe_custom_path_part(value)


class SupervisedEstimatorConfig(BaseModel):
    """One supervised estimator declaration inside a composite model."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class StackingEnsembleParametersConfig(BaseModel):
    """Validated YAML parameters for stacking_ensemble."""

    model_config = ConfigDict(extra="forbid")

    anchor_model_alias: str = Field(min_length=1)
    base_models: list[NestedForecastModelConfig] = Field(min_length=2)
    meta_model: SupervisedEstimatorConfig
    oof: dict[str, Any] = Field(default_factory=dict)
    passthrough_features: bool = False

    @field_validator("anchor_model_alias")
    @classmethod
    def _validate_anchor_alias(cls, value: str) -> str:
        return _safe_custom_path_part(value)


class SpikeConfig(BaseModel):
    """Spike-label construction for occurrence_spike_cascade."""

    model_config = ConfigDict(extra="forbid")

    method: str = "training_quantile"
    quantile: float = Field(default=0.90, gt=0.0, lt=1.0)
    min_spike_rows: int = Field(default=10, ge=1)
    min_normal_rows: int = Field(default=10, ge=1)


class CascadeRoutingConfig(BaseModel):
    """Routing policy for occurrence_spike_cascade."""

    model_config = ConfigDict(extra="forbid")

    mode: str = "soft"
    occurrence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    spike_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class OccurrenceSpikeCascadeParametersConfig(BaseModel):
    """Validated YAML parameters for occurrence_spike_cascade."""

    model_config = ConfigDict(extra="forbid")

    spike: SpikeConfig = Field(default_factory=SpikeConfig)
    routing: CascadeRoutingConfig = Field(default_factory=CascadeRoutingConfig)
    occurrence_model: SupervisedEstimatorConfig = Field(
        default_factory=lambda: SupervisedEstimatorConfig(name="lightgbm_classifier")
    )
    spike_model: SupervisedEstimatorConfig = Field(
        default_factory=lambda: SupervisedEstimatorConfig(name="lightgbm_classifier")
    )
    normal_magnitude_model: SupervisedEstimatorConfig = Field(
        default_factory=lambda: SupervisedEstimatorConfig(name="lightgbm_regressor")
    )
    spike_magnitude_model: SupervisedEstimatorConfig = Field(
        default_factory=lambda: SupervisedEstimatorConfig(name="lightgbm_regressor")
    )


@dataclass(frozen=True)
class BacktestEvaluationConfig:
    """D+1 rolling-origin evaluation settings."""

    cutoff_start: str
    cutoff_end: str
    train_window_days: int
    log_every_n_cutoffs: int = 7


@dataclass(frozen=True)
class BacktestSequenceConfig:
    """Sequence-selection settings resolved to exactly one sequence."""

    sequence_id: str | None = None
    entity: str | list[str] | None = None
    currency: str | list[str] | None = None
    movement_type: str | None = None
    filters: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestDefinition:
    """Pure top-level backtest definition independent from storage adapters."""

    dataset: DatasetConfig
    evaluation: BacktestEvaluationConfig
    prediction_intervals_coverage: list[float]
    models: list[BacktestModelConfig]
    model_specs: list[ModelSpec]
    sequence: BacktestSequenceConfig
    log_level: str = "INFO"


def parse_backtest_definition(raw_mapping: Mapping[str, Any]) -> BacktestDefinition:
    """Validate a backtest definition from an already-loaded mapping."""

    raw = dict(raw_mapping or {})
    if not isinstance(raw, dict):
        raise ValueError("Backtest config must be a mapping.")
    if "model" in raw:
        raise ValueError("Backtest YAML must use `models:`; the singular `model:` key is not supported.")
    if "dataset_kind" in raw:
        raise ValueError("Backtest YAML infers dataset kind from `models:`; remove top-level `dataset_kind`.")
    if "horizon_days" in raw:
        raise ValueError("D+1 forecasting is fixed; remove top-level `horizon_days` from the config.")
    if "prediction_intervals" in raw:
        raise ValueError("Use top-level `prediction_intervals_coverage`, not legacy `prediction_intervals`.")
    if "enable_mlflow" in raw:
        raise ValueError("Backtest YAML no longer supports `enable_mlflow`; metric logging has been removed.")
    _reject_unknown_keys(raw, TOP_LEVEL_CONFIG_KEYS, "Backtest YAML")

    dataset_raw = raw.get("dataset")
    if not isinstance(dataset_raw, dict):
        raise ValueError("Backtest YAML must define a `dataset:` mapping.")
    if "kind" in dataset_raw:
        raise ValueError("Backtest YAML infers `dataset.kind` from `models:`; remove `dataset.kind`.")

    model_raw = raw.get("models") or []
    if not isinstance(model_raw, list) or not model_raw:
        raise ValueError("Backtest YAML must define a non-empty `models:` list.")
    models = [BacktestModelConfig.model_validate(item) for item in model_raw]
    initial_model_specs = [
        model_spec_for_name(model.name, parameters=model.parameters)
        for model in models
    ]
    dataset_kind = _single_model_dataset_kind(initial_model_specs)
    _validate_unique_run_leaves(models)

    evaluation_raw = raw.get("evaluation") or {}
    if "horizon_days" in evaluation_raw:
        raise ValueError("D+1 forecasting is fixed; remove `evaluation.horizon_days` from the config.")
    if "history_window_days" in evaluation_raw:
        raise ValueError("Backtest YAML must use `dataset.history_window_days`, not `evaluation.history_window_days`.")
    _reject_unknown_keys(evaluation_raw, EVALUATION_CONFIG_KEYS, "`evaluation`")

    sequence_raw = raw.get("sequence") or {}
    if "movement_types" in sequence_raw:
        raise ValueError("Use a single `movement_type`; multi-sequence backtests are not supported.")
    _reject_unknown_keys(sequence_raw, SEQUENCE_CONFIG_KEYS, "`sequence`")

    dataset = DatasetConfig.model_validate({**dataset_raw, "kind": dataset_kind})
    model_specs = [
        model_spec_for_name(
            model.name,
            parameters=_normalize_model_parameters(model, dataset),
        )
        for model in models
    ]

    return BacktestDefinition(
        dataset=dataset,
        evaluation=BacktestEvaluationConfig(
            cutoff_start=str(evaluation_raw["cutoff_start"]),
            cutoff_end=str(evaluation_raw["cutoff_end"]),
            train_window_days=int(evaluation_raw["train_window_days"]),
            log_every_n_cutoffs=int(evaluation_raw.get("log_every_n_cutoffs", 7)),
        ),
        prediction_intervals_coverage=_normalize_prediction_intervals_coverage(
            raw.get("prediction_intervals_coverage") or []
        ),
        models=models,
        model_specs=model_specs,
        sequence=BacktestSequenceConfig(
            sequence_id=_as_optional_str(sequence_raw.get("sequence_id")),
            entity=_as_str_or_list(sequence_raw.get("entity")),
            currency=_as_str_or_list(sequence_raw.get("currency")),
            movement_type=_as_optional_str(sequence_raw.get("movement_type")),
            filters={key: _as_list(value) for key, value in (sequence_raw.get("filters") or {}).items()},
        ),
        log_level=str(raw.get("log_level", "INFO")),
    )


def resolve_single_sequence_row(
    gold_outputs: GoldBuildResult,
    ruleset: Ruleset,
    sequence_config: BacktestSequenceConfig,
) -> pd.Series:
    """Return the only sequence row from already-filtered Gold outputs."""

    _ = (ruleset, sequence_config)
    sequence_reference = gold_outputs.sequence_reference.copy()
    if sequence_reference.empty:
        raise ValueError(
            "Single-series Gold input must contain exactly one sequence in sequence_reference; got 0."
        )
    if SEQUENCE_ID_COLUMN not in sequence_reference.columns:
        raise ValueError(
            f"Single-series Gold input is missing {SEQUENCE_ID_COLUMN!r} in sequence_reference."
        )

    sequence_reference = sequence_reference.drop_duplicates(subset=[SEQUENCE_ID_COLUMN]).reset_index(drop=True)
    if len(sequence_reference) != 1:
        sequence_ids = sequence_reference[SEQUENCE_ID_COLUMN].astype(str).head(20).tolist()
        raise ValueError(
            "Single-series Gold input must contain exactly one sequence in sequence_reference; "
            f"got {len(sequence_reference)}. Matched sequence ids: {sequence_ids}"
        )
    return sequence_reference.iloc[0]


def to_backtest_config(
    config: BacktestDefinition,
    model_spec: ModelSpec,
    model_config: BacktestModelConfig,
) -> BacktestConfig:
    return BacktestConfig(
        dataset=config.dataset,
        evaluation_cutoff_start=pd.Timestamp(config.evaluation.cutoff_start).date(),
        evaluation_cutoff_end=pd.Timestamp(config.evaluation.cutoff_end).date(),
        train_window_days=config.evaluation.train_window_days,
        custom_name=model_config.custom_name,
        prediction_intervals_coverage=config.prediction_intervals_coverage,
        model_spec=model_spec,
    )


def _single_model_dataset_kind(model_specs: list[ModelSpec]):
    dataset_kinds = {spec.dataset_kind for spec in model_specs}
    if len(dataset_kinds) == 1:
        return next(iter(dataset_kinds))
    model_kinds = ", ".join(
        f"{spec.model_name}={spec.dataset_kind.value}"
        for spec in model_specs
    )
    raise ValueError(
        "One backtest YAML must use models from one dataset kind. "
        f"Got: {model_kinds}."
    )


def _normalize_model_parameters(
    model: BacktestModelConfig,
    dataset: DatasetConfig,
) -> dict[str, Any]:
    _validate_raw_target_regime_model_transform(model.name, dataset.target_transform)
    if model.name == STACKING_MODEL_NAME:
        return _normalize_stacking_parameters(model.parameters, dataset)
    if model.name == "occurrence_spike_cascade":
        return _normalize_occurrence_spike_cascade_parameters(model.parameters)
    return model.parameters


def _normalize_stacking_parameters(parameters: dict[str, Any], dataset: DatasetConfig) -> dict[str, Any]:
    config = StackingEnsembleParametersConfig.model_validate(parameters)
    aliases = [item.alias for item in config.base_models]
    duplicates = sorted({alias for alias in aliases if aliases.count(alias) > 1})
    if duplicates:
        raise ValueError(f"stacking_ensemble base model aliases must be unique; duplicates: {duplicates}.")
    if config.anchor_model_alias not in aliases:
        raise ValueError("stacking_ensemble anchor_model_alias must match one base model alias.")
    _validate_supervised_role(config.meta_model, "regressor", "stacking_ensemble.meta_model")

    normalized_base_models: list[dict[str, Any]] = []
    for base_model in config.base_models:
        if base_model.name in SPECIAL_MODEL_NAMES:
            raise ValueError("Nested composite models are not supported inside stacking_ensemble.base_models.")
        nested_spec = model_spec_for_name(base_model.name, parameters=base_model.parameters)
        nested_dataset = _nested_dataset(dataset, base_model.dataset, nested_spec.dataset_kind)
        _validate_raw_target_regime_model_transform(base_model.name, nested_dataset.target_transform)
        normalized_base_models.append(
            {
                "alias": base_model.alias,
                "name": base_model.name,
                "parameters": base_model.parameters,
                "dataset": nested_dataset.model_dump(mode="json"),
                "model_spec": nested_spec.model_dump(mode="json"),
            }
        )

    return {
        "anchor_model_alias": config.anchor_model_alias,
        "base_models": normalized_base_models,
        "meta_model": config.meta_model.model_dump(mode="json"),
        "oof": config.oof,
        "passthrough_features": config.passthrough_features,
    }


def _normalize_occurrence_spike_cascade_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    config = OccurrenceSpikeCascadeParametersConfig.model_validate(parameters)
    if config.spike.method != "training_quantile":
        raise ValueError("occurrence_spike_cascade spike.method must be 'training_quantile'.")
    if config.routing.mode not in {"soft", "hard"}:
        raise ValueError("occurrence_spike_cascade routing.mode must be 'soft' or 'hard'.")
    _validate_supervised_role(config.occurrence_model, "classifier", "occurrence_model")
    _validate_supervised_role(config.spike_model, "classifier", "spike_model")
    _validate_supervised_role(config.normal_magnitude_model, "regressor", "normal_magnitude_model")
    _validate_supervised_role(config.spike_magnitude_model, "regressor", "spike_magnitude_model")
    return config.model_dump(mode="json")


def _validate_supervised_role(config: SupervisedEstimatorConfig, role: str, path: str) -> None:
    actual_role = supervised_estimator_role(config.name)
    if actual_role != role:
        raise ValueError(f"{path} must be a supervised {role}; {config.name!r} is a {actual_role}.")


def _nested_dataset(
    parent_dataset: DatasetConfig,
    overrides: dict[str, Any],
    dataset_kind: DatasetKind,
) -> DatasetConfig:
    payload = parent_dataset.model_dump(mode="python")
    merged = _deep_merge(payload, overrides)
    merged["kind"] = dataset_kind
    return DatasetConfig.model_validate(merged)


def _deep_merge(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = dict(defaults)
    for key, value in overrides.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _validate_raw_target_regime_model_transform(model_name: str, target_transform: str) -> None:
    if model_name in RAW_TARGET_REGIME_MODEL_NAMES and target_transform != "none":
        raise ValueError(
            f"{model_name} requires dataset.target_transform='none' because its occurrence/spike "
            "labels are defined on raw cash amounts."
        )


def _reject_unknown_keys(payload: Mapping[str, Any], allowed_keys: set[str], context: str) -> None:
    unknown = sorted(set(payload) - allowed_keys)
    if unknown:
        allowed = ", ".join(sorted(allowed_keys))
        raise ValueError(f"{context} contains unsupported key(s): {unknown}. Allowed keys: {allowed}.")


def _validate_unique_run_leaves(models: list[BacktestModelConfig]) -> None:
    leaves = [_model_custom_leaf(model.name, model.custom_name) for model in models]
    duplicates = sorted({leaf for leaf in leaves if leaves.count(leaf) > 1})
    if duplicates:
        raise ValueError(
            "Backtest model output folders must be unique; duplicate model/custom_name leaves: "
            f"{duplicates}."
        )


def _model_custom_leaf(model_name: str, custom_name: str) -> str:
    custom_parts = _custom_name_parts(custom_name)
    return "/".join([f"{_safe_path_part(model_name)}_{custom_parts[0]}", *custom_parts[1:]])


def _custom_name_parts(custom_name: str) -> list[str]:
    if PurePosixPath(custom_name).is_absolute() or PureWindowsPath(custom_name).is_absolute():
        raise ValueError("custom_name must be a relative path fragment.")
    raw_parts = custom_name.replace("\\", "/").split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("custom_name must not contain empty, '.', or '..' path segments.")
    return [_safe_custom_path_part(part) for part in raw_parts]


def _safe_path_part(value: str) -> str:
    normalized = value.replace("+", "_plus").replace("-", "_minus")
    return re.sub(r"[^A-Za-z0-9_.=]+", "_", normalized).strip("_") or "unknown"


def _safe_custom_path_part(value: str) -> str:
    normalized = value.replace("+", "_plus").replace("-", "_minus")
    safe = re.sub(r"[^A-Za-z0-9_.=]+", "_", normalized).strip("_")
    if safe in {"", ".", ".."}:
        raise ValueError("custom_name path segments must contain at least one safe character.")
    return safe


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_str_or_list(value: Any) -> str | list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    return str(value)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _normalize_prediction_intervals_coverage(value: Any) -> list[float]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("prediction_intervals_coverage must be a YAML list of floats.")
    normalized = sorted({float(item) for item in value})
    if any(item <= 0.0 or item >= 1.0 for item in normalized):
        raise ValueError("prediction_intervals_coverage must contain values strictly between 0 and 1.")
    return normalized
