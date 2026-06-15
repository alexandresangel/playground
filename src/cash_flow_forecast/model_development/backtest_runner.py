from __future__ import annotations

from dataclasses import dataclass

from cash_flow_forecast.contracts.builders import BacktestConfig, BacktestResult, GoldBuildResult, ModelSpec
from cash_flow_forecast.contracts.rules import Ruleset
from cash_flow_forecast.model_development.backtest_config import (
    BacktestDefinition,
    BacktestModelConfig,
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
        records: list[BacktestRunRecord] = []

        for model_config, model_spec in zip(definition.models, definition.model_specs, strict=True):
            backtest_config = to_backtest_config(definition, model_spec, model_config)
            result = self.engine.run(
                gold_outputs=gold_outputs,
                ruleset=ruleset,
                model=model_spec,
                config=backtest_config,
                log_every_n_cutoffs=definition.evaluation.log_every_n_cutoffs,
            )
            records.append(
                BacktestRunRecord(
                    model_config=model_config,
                    model_spec=model_spec,
                    config=backtest_config,
                    result=result,
                )
            )

        return records
