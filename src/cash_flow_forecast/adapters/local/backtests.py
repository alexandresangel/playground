from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
from typing import Any

from loguru import logger
import yaml

from cash_flow_forecast.adapters.base import ForecastingStorageAdapter
from cash_flow_forecast.adapters.local.io import LocalForecastingStorageAdapter
from cash_flow_forecast.adapters.local.rules import load_ruleset_from_yaml
from cash_flow_forecast.model_development.backtest_config import (
    BacktestDefinition,
    parse_backtest_definition,
)
from cash_flow_forecast.model_development.backtest_runner import (
    BacktestBatchRunner,
    BacktestRunRecord,
)


@dataclass(frozen=True)
class LocalBacktestRunConfig:
    """Local adapter settings plus the pure backtest definition."""

    definition: BacktestDefinition
    input_path: str
    output_path: str
    ruleset_path: str


def load_local_backtest_yaml(
    path: str | Path,
    *,
    input_path: str | Path | None = None,
    output_path: str | Path | None = None,
    ruleset_path: str | Path | None = None,
) -> LocalBacktestRunConfig:
    """Load a local YAML file and split path settings from the pure definition."""

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError("Backtest YAML must define a mapping.")

    definition = parse_backtest_definition(payload)
    return LocalBacktestRunConfig(
        definition=definition,
        input_path=_path_setting(payload, "input_path", input_path, "data/gold"),
        output_path=_path_setting(payload, "output_path", output_path, "data/backtests"),
        ruleset_path=_path_setting(
            payload,
            "ruleset_path",
            ruleset_path,
            "configs/rulesets/loreal_cash_in_v1.yaml",
        ),
    )


def run_local_backtest_from_yaml(
    path: str | Path,
    *,
    input_path: str | Path | None = None,
    output_path: str | Path | None = None,
    ruleset_path: str | Path | None = None,
    storage: ForecastingStorageAdapter | None = None,
    runner: BacktestBatchRunner | None = None,
) -> list[BacktestRunRecord]:
    """Run a local YAML backtest through filesystem storage."""

    local_config = load_local_backtest_yaml(
        path,
        input_path=input_path,
        output_path=output_path,
        ruleset_path=ruleset_path,
    )
    configure_loguru(local_config.definition.log_level)
    storage = storage or LocalForecastingStorageAdapter()
    runner = runner or BacktestBatchRunner()
    ruleset = load_ruleset_from_yaml(local_config.ruleset_path)
    gold_outputs = storage.read_gold_outputs(local_config.input_path)
    records = runner.run(local_config.definition, gold_outputs, ruleset)
    write_local_backtest_records(local_config.output_path, records, storage=storage)
    return records


def write_local_backtest_records(
    output_path: str | Path,
    records: list[BacktestRunRecord],
    *,
    storage: ForecastingStorageAdapter | None = None,
) -> None:
    """Persist in-memory backtest records to the local run folder layout."""

    storage = storage or LocalForecastingStorageAdapter()
    output_root = Path(output_path)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "backtest_runs_summary.csv").unlink(missing_ok=True)
    for record in records:
        run_path = run_output_path(
            output_path,
            model_name=record.model_spec.model_name,
            custom_name=record.model_config.custom_name,
        )
        storage.write_backtest_result(run_path, record.result)
        logger.info("Wrote backtest output to {}", run_path)


def configure_loguru(level: str = "INFO") -> None:
    """Configure local console logging."""

    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}",
    )


def run_output_path(
    output_root: str | Path,
    *,
    model_name: str,
    custom_name: str,
) -> Path:
    """Return the local output folder for one model/custom-name run."""

    return Path(output_root) / _model_custom_leaf(
        model_name,
        custom_name,
    )


def _path_setting(
    payload: dict[str, Any],
    key: str,
    override: str | Path | None,
    default: str,
) -> str:
    value = override if override is not None else payload.get(key, default)
    return str(value)


def _model_custom_leaf(model_name: str, custom_name: str) -> Path:
    custom_parts = _custom_name_parts(custom_name)
    return Path(f"{_safe_path_part(model_name)}_{custom_parts[0]}", *custom_parts[1:])


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
    safe = _safe_path_part(value)
    if safe in {"", ".", ".."}:
        raise ValueError("custom_name path segments must contain at least one safe character.")
    return safe
