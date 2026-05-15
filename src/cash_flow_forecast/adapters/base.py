from __future__ import annotations
from pathlib import Path
from typing import Protocol
import pandas as pd

from cash_flow_forecast.contracts.builders import (
    BacktestResult,
    BronzeTablePayload,
    DatasetBuildResult,
    GoldBuildResult,
    SilverBuildResult,
)


class ForecastingStorageAdapter(Protocol):

    def read_bronze_tables(self, input_path: str | Path) -> list[BronzeTablePayload]:
        """Load raw bronze table payloads."""

    def read_silver_tables(self, input_path: str | Path) -> dict[str, pd.DataFrame]:
        """Load Silver entity tables."""

    def read_gold_outputs(self, input_path: str | Path) -> GoldBuildResult:
        """Load Gold outputs."""

    def write_silver_result(self, output_path: str | Path, result: SilverBuildResult) -> None:
        """Persist Silver outputs."""

    def write_gold_result(self, output_path: str | Path, result: GoldBuildResult) -> None:
        """Persist Gold outputs."""

    def write_dataset_result(self, output_path: str | Path, result: DatasetBuildResult) -> None:
        """Persist dataset outputs."""

    def write_backtest_result(self, output_path: str | Path, result: BacktestResult) -> None:
        """Persist backtest outputs."""

    def write_forecast_result(self, output_path: str | Path, forecasts: pd.DataFrame) -> None:
        """Persist forecast outputs."""
