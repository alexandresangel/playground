from __future__ import annotations
from datetime import UTC, date, datetime
from typing import Any, Literal
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cash_flow_forecast.contracts.enums import DatasetKind
from cash_flow_forecast.contracts.rules import Ruleset
from cash_flow_forecast.contracts.schema import TableSchema


class DomainModel(BaseModel):
    """Base model for contracts containing dataframe payloads."""

    model_config = ConfigDict(arbitrary_types_allowed=True)


class BronzeTablePayload(DomainModel):
    """One raw bronze table plus local lineage metadata."""

    source_name: str
    dataframe: pd.DataFrame
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColumnIssueSummary(BaseModel):
    """Count of one issue type for one column."""

    column: str
    issue_type: str
    issue_count: int = Field(ge=0)


class TableBuildReport(BaseModel):
    """Summary report for one logical table build."""

    table_name: str
    row_count: int = Field(ge=0)
    issue_counts: dict[str, int] = Field(default_factory=dict)
    column_issues: list[ColumnIssueSummary] = Field(default_factory=list)


class BuildManifest(BaseModel):
    """Lightweight manifest describing one build output."""

    layer: str
    produced_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    row_count: int = Field(ge=0)
    table_names: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SilverBuildRequest(DomainModel):
    """Input contract for the Silver builder."""

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

    bronze_tables: list[BronzeTablePayload]
    table_schema: TableSchema = Field(alias="schema")


class SilverBuildResult(DomainModel):
    """Output contract for the Silver builder."""

    entity_tables: dict[str, pd.DataFrame]
    entity_reports: dict[str, TableBuildReport]
    manifest: BuildManifest


class GoldBuildRequest(DomainModel):
    """Input contract for the Gold builders."""

    silver_tables: dict[str, pd.DataFrame]
    ruleset: Ruleset


class GoldBuildResult(DomainModel):
    """Output contract for Gold build outputs."""

    realized_cash_in: pd.DataFrame
    known_movements_daily: pd.DataFrame
    manifest: BuildManifest


class RollingWindowFeatureConfig(BaseModel):
    """One rolling target-history feature declaration."""

    model_config = ConfigDict(extra="forbid")

    days: int = Field(ge=1)
    aggregations: list[str] = Field(default_factory=lambda: ["mean"])

    @field_validator("aggregations")
    @classmethod
    def _validate_aggregations(cls, values: list[str]) -> list[str]:
        allowed = {"mean", "std", "non_zero_ratio"}
        normalized = []
        for value in values:
            aggregation = str(value).strip().lower()
            if aggregation not in allowed:
                raise ValueError(
                    "rolling window aggregations must be one of: mean, std, non_zero_ratio."
                )
            if aggregation not in normalized:
                normalized.append(aggregation)
        if not normalized:
            raise ValueError("rolling window aggregations must not be empty.")
        return normalized


class CrossMovementKnownFeatureConfig(BaseModel):
    """Cross-movement known-state feature settings."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False


class DatasetFeatureConfig(BaseModel):
    """Audited feature blocks available to the live dataset builder."""

    model_config = ConfigDict(extra="forbid")

    calendar: bool = True
    known_d1: bool = True
    target_lags: list[int] = Field(default_factory=lambda: [1, 7])
    rolling_windows: list[RollingWindowFeatureConfig] = Field(
        default_factory=lambda: [
            RollingWindowFeatureConfig(days=7, aggregations=["mean"]),
        ]
    )
    cross_movement_known: CrossMovementKnownFeatureConfig = Field(
        default_factory=CrossMovementKnownFeatureConfig
    )

    @field_validator("target_lags")
    @classmethod
    def _normalize_target_lags(cls, values: list[int]) -> list[int]:
        normalized = sorted({int(value) for value in values})
        if any(value < 1 for value in normalized):
            raise ValueError("target_lags must contain positive day offsets.")
        return normalized


class DatasetConfig(BaseModel):
    """Live dataset assembly settings used by backtests and snapshots."""

    model_config = ConfigDict(extra="forbid")

    kind: DatasetKind
    history_window_days: int = Field(default=90, ge=1)
    target_transform: Literal["none", "log1p", "box_cox", "yeo_johnson"] = "none"
    features: DatasetFeatureConfig = Field(default_factory=DatasetFeatureConfig)


class DatasetBuildRequest(DomainModel):
    """Input contract for dataset assembly."""

    gold_outputs: GoldBuildResult
    ruleset: Ruleset
    dataset: DatasetConfig
    cutoff_dates: list[date]
    label_as_of_date: date | None = None
    target_transformer: Any | None = None

    @field_validator("cutoff_dates")
    @classmethod
    def _sort_cutoffs(cls, values: list[date]) -> list[date]:
        if not values:
            raise ValueError("At least one cutoff date must be provided.")
        return sorted(values)

    @property
    def dataset_kind(self) -> DatasetKind:
        return self.dataset.kind

    @property
    def history_window_days(self) -> int:
        return self.dataset.history_window_days


class DatasetManifest(BaseModel):
    """Metadata persisted alongside a built dataset."""

    dataset_kind: DatasetKind
    ruleset_id: str
    cutoff_dates: list[date]
    forecast_horizon_days: int = Field(default=1, ge=1)
    label_as_of_date: date | None = None
    feature_policy: str
    training_label_policy: str
    history_window_days: int = Field(ge=1)
    target_transform: Literal["none", "log1p", "box_cox", "yeo_johnson"] = "none"
    row_count: int = Field(ge=0)
    feature_columns: list[str] = Field(default_factory=list)
    source_tables: list[str] = Field(default_factory=list)


class DatasetBuildResult(DomainModel):
    """Output of the dataset builder."""

    dataframe: pd.DataFrame
    manifest: DatasetManifest


class ModelInfo(BaseModel):
    """Minimal metadata about one forecasting model."""

    model_name: str
    dataset_kind: DatasetKind
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class ModelSpec(BaseModel):
    """Configuration used to instantiate one forecasting model."""

    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(min_length=1)
    dataset_kind: DatasetKind
    parameters: dict[str, Any] = Field(default_factory=dict)


class BacktestConfig(BaseModel):
    """Rolling-origin backtest configuration."""

    model_config = ConfigDict(extra="forbid")

    dataset: DatasetConfig
    evaluation_cutoff_start: date
    evaluation_cutoff_end: date
    train_window_days: int = Field(ge=1)
    custom_name: str = Field(default="default", min_length=1)
    prediction_intervals_coverage: list[float] = Field(default_factory=list)
    model_spec: ModelSpec | None = None

    @field_validator("prediction_intervals_coverage")
    @classmethod
    def _normalize_prediction_intervals_coverage(cls, values: list[float]) -> list[float]:
        normalized = sorted({float(value) for value in values})
        if any(value <= 0.0 or value >= 1.0 for value in normalized):
            raise ValueError("prediction_intervals_coverage must contain values strictly between 0 and 1.")
        return normalized

    @model_validator(mode="after")
    def _validate_dates_and_model(self) -> "BacktestConfig":
        if self.evaluation_cutoff_start > self.evaluation_cutoff_end:
            raise ValueError("evaluation_cutoff_start must be on or before evaluation_cutoff_end.")
        if self.model_spec and self.model_spec.dataset_kind != self.dataset.kind:
            raise ValueError("model_spec.dataset_kind must match BacktestConfig.dataset.kind.")
        return self

    @property
    def dataset_kind(self) -> DatasetKind:
        return self.dataset.kind

    @property
    def history_window_days(self) -> int:
        return self.dataset.history_window_days


class BacktestRunReport(BaseModel):
    """Compact audit report for one persisted backtest run."""

    model_info: ModelInfo
    custom_name: str = Field(min_length=1)
    dataset_kind: DatasetKind
    dataset_config: DatasetConfig
    ruleset_id: str
    evaluation_cutoff_start: date
    evaluation_cutoff_end: date
    train_window_days: int = Field(ge=1)
    prediction_intervals_coverage: list[float] = Field(default_factory=list)
    forecast_horizon_days: int = Field(default=1, ge=1)
    cutoff_count: int = Field(ge=0)
    completed_folds: int = Field(ge=0)
    skipped_folds: int = Field(ge=0)
    skipped_reasons: dict[str, int] = Field(default_factory=dict)
    source_row_counts: dict[str, int] = Field(default_factory=dict)
    training_row_count: int = Field(ge=0)
    inference_row_count: int = Field(ge=0)
    prediction_row_count: int = Field(ge=0)
    feature_columns: list[str] = Field(default_factory=list)
    training_budget: dict[str, Any] = Field(default_factory=dict)


class BacktestResult(DomainModel):
    """Predictions and audit metadata generated by one backtest run."""

    predictions: pd.DataFrame
    model_info: ModelInfo
    config: BacktestConfig
    run_report: BacktestRunReport
