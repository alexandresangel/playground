from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from cash_flow_forecast.contracts.builders import BacktestConfig, BacktestResult, GoldBuildResult, ModelSpec
from cash_flow_forecast.contracts.rules import Ruleset
from cash_flow_forecast.data_layers.gold.builder import SEQUENCE_ID_COLUMN
from cash_flow_forecast.model_development.backtest_config import (
    BacktestDefinition,
    BacktestModelConfig,
    resolve_single_sequence_row,
    to_backtest_config,
)
from cash_flow_forecast.model_development.backtesting import RollingWindowBacktestEngine


@dataclass(frozen=True)
class BacktestRunRecord:
    """One in-memory backtest result plus routing metadata for adapters."""

    model_config: BacktestModelConfig
    model_spec: ModelSpec
    config: BacktestConfig
    result: BacktestResult
    sequence_id: str
    sequence_row: pd.Series


class BacktestBatchRunner:
    """Run all model entries from a parsed backtest definition in memory."""

    def __init__(self, engine: RollingWindowBacktestEngine | None = None) -> None:
        self.engine = engine or RollingWindowBacktestEngine()

    def run(
        self,
        definition: BacktestDefinition,
        gold_outputs: GoldBuildResult,
        ruleset: Ruleset,
    ) -> list[BacktestRunRecord]:
        sequence_row = resolve_single_sequence_row(gold_outputs, ruleset, definition.sequence)
        sequence_id = str(sequence_row[SEQUENCE_ID_COLUMN])
        records: list[BacktestRunRecord] = []

        for model_config, model_spec in zip(definition.models, definition.model_specs, strict=True):
            backtest_config = to_backtest_config(definition, model_spec, model_config)
            result = self.engine.run(
                gold_outputs=gold_outputs,
                ruleset=ruleset,
                model=model_spec,
                config=backtest_config,
                sequence_id=sequence_id,
                log_every_n_cutoffs=definition.evaluation.log_every_n_cutoffs,
            )
            records.append(
                BacktestRunRecord(
                    model_config=model_config,
                    model_spec=model_spec,
                    config=backtest_config,
                    result=result,
                    sequence_id=sequence_id,
                    sequence_row=sequence_row,
                )
            )

        return records
