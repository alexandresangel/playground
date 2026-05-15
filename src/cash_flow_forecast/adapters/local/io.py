from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

from cash_flow_forecast.adapters.base import ForecastingStorageAdapter
from cash_flow_forecast.contracts.builders import (
    BacktestResult,
    BronzeTablePayload,
    DatasetBuildResult,
    GoldBuildResult,
    SilverBuildResult,
)


def read_bronze_tables(input_path: str | Path) -> list[BronzeTablePayload]:
    """Load raw CSV files from a local file or directory."""
    source_path = Path(input_path)
    csv_paths = [source_path] if source_path.is_file() else sorted(source_path.glob("*.csv"))
    payloads = []
    for csv_path in csv_paths:
        dataframe = pd.read_csv(
            csv_path,
            sep=";",
            dtype="string",
            keep_default_na=False,
        )
        payloads.append(BronzeTablePayload(source_name=csv_path.name, dataframe=dataframe))
    return payloads


def read_silver_tables(input_path: str | Path) -> dict[str, pd.DataFrame]:
    """Load Silver entity tables from parquet files."""

    source_path = Path(input_path)
    tables = {}
    for parquet_path in sorted(source_path.glob("*.parquet")):
        if parquet_path.name == "_manifest.parquet":
            continue
        entity_name = parquet_path.stem
        tables[entity_name] = pd.read_parquet(parquet_path)
    return tables


def read_gold_outputs(input_path: str | Path) -> GoldBuildResult:
    """Load Gold outputs from a local directory."""

    source_path = Path(input_path)
    manifest_path = source_path / "manifest.json"
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest_payload = json.load(handle)
    from cash_flow_forecast.contracts.builders import BuildManifest  # local import avoids cycle

    return GoldBuildResult(
        realized_cash_in=pd.read_parquet(source_path / "realized_cash_in.parquet"),
        known_movements_daily=pd.read_parquet(source_path / "known_movements_daily.parquet"),
        sequence_reference=pd.read_parquet(source_path / "sequence_reference.parquet"),
        calendar_daily=pd.read_parquet(source_path / "calendar_daily.parquet"),
        manifest=BuildManifest.model_validate(manifest_payload),
    )


def write_silver_result(output_path: str | Path, result: SilverBuildResult) -> None:
    """Persist Silver entity tables plus manifest and reports."""

    destination = Path(output_path)
    destination.mkdir(parents=True, exist_ok=True)
    for entity_name, dataframe in result.entity_tables.items():
        dataframe.to_parquet(destination / f"{entity_name}.parquet", index=False)
    _write_json(destination / "manifest.json", result.manifest.model_dump(mode="json"))
    reports = {
        entity_name: report.model_dump(mode="json")
        for entity_name, report in result.entity_reports.items()
    }
    _write_json(destination / "reports.json", reports)


def write_gold_result(output_path: str | Path, result: GoldBuildResult) -> None:
    """Persist Gold outputs plus manifest."""

    destination = Path(output_path)
    destination.mkdir(parents=True, exist_ok=True)
    result.realized_cash_in.to_parquet(destination / "realized_cash_in.parquet", index=False)
    result.known_movements_daily.to_parquet(
        destination / "known_movements_daily.parquet",
        index=False,
    )
    result.sequence_reference.to_parquet(destination / "sequence_reference.parquet", index=False)
    result.calendar_daily.to_parquet(destination / "calendar_daily.parquet", index=False)
    _write_json(destination / "manifest.json", result.manifest.model_dump(mode="json"))


def write_dataset_result(output_path: str | Path, result: DatasetBuildResult) -> None:
    """Persist one built dataset and its manifest."""

    destination = Path(output_path)
    destination.mkdir(parents=True, exist_ok=True)
    result.dataframe.to_parquet(destination / "dataset.parquet", index=False)
    _write_json(destination / "manifest.json", result.manifest.model_dump(mode="json"))


def write_backtest_result(output_path: str | Path, result: BacktestResult) -> None:
    """Persist backtest predictions, model metadata, config, and audit report."""

    destination = Path(output_path)
    destination.mkdir(parents=True, exist_ok=True)
    _remove_legacy_backtest_artifacts(destination)
    result.predictions.to_parquet(destination / "predictions.parquet", index=False)
    _write_json(destination / "model_info.json", result.model_info.model_dump(mode="json"))
    _write_json(destination / "config.json", result.config.model_dump(mode="json"))
    _write_json(destination / "run_report.json", result.run_report.model_dump(mode="json"))


def write_forecast_result(output_path: str | Path, forecasts: pd.DataFrame) -> None:
    """Persist daily forecast rows."""

    destination = Path(output_path)
    destination.mkdir(parents=True, exist_ok=True)
    forecasts.to_parquet(destination / "forecasts.parquet", index=False)


class LocalForecastingStorageAdapter(ForecastingStorageAdapter):
    """Filesystem-backed storage adapter for local paths and mounted cloud folders."""

    def read_bronze_tables(self, input_path: str | Path) -> list[BronzeTablePayload]:
        return read_bronze_tables(input_path)

    def read_silver_tables(self, input_path: str | Path) -> dict[str, pd.DataFrame]:
        return read_silver_tables(input_path)

    def read_gold_outputs(self, input_path: str | Path) -> GoldBuildResult:
        return read_gold_outputs(input_path)

    def write_silver_result(self, output_path: str | Path, result: SilverBuildResult) -> None:
        write_silver_result(output_path, result)

    def write_gold_result(self, output_path: str | Path, result: GoldBuildResult) -> None:
        write_gold_result(output_path, result)

    def write_dataset_result(self, output_path: str | Path, result: DatasetBuildResult) -> None:
        write_dataset_result(output_path, result)

    def write_backtest_result(self, output_path: str | Path, result: BacktestResult) -> None:
        write_backtest_result(output_path, result)

    def write_forecast_result(self, output_path: str | Path, forecasts: pd.DataFrame) -> None:
        write_forecast_result(output_path, forecasts)


def _write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)


def _remove_legacy_backtest_artifacts(destination: Path) -> None:
    for filename in [
        "metrics.json",
        "metrics_by_cutoff.parquet",
        "interval_predictions.parquet",
        "interval_metrics_by_cutoff.parquet",
        "interval_metrics.json",
        "interval_model_info.json",
        "interval_config.json",
        "interval_run_report.json",
    ]:
        (destination / filename).unlink(missing_ok=True)
