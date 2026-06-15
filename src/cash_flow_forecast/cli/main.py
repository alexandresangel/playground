from __future__ import annotations
import argparse
from pathlib import Path
import re

from cash_flow_forecast.adapters.local import (
    load_local_backtest_yaml,
    load_ruleset_from_yaml,
    read_bronze_tables,
    read_gold_outputs,
    read_silver_tables,
    run_local_backtest_from_yaml,
    write_dataset_result,
    write_gold_result,
    write_silver_result,
)
from cash_flow_forecast.contracts import (
    DatasetBuildRequest,
    GoldBuildRequest,
    SilverBuildRequest,
    build_default_schema,
)
from cash_flow_forecast.data_layers.gold import GoldBuilder
from cash_flow_forecast.data_layers.gold.builder import SEQUENCE_ID_COLUMN
from cash_flow_forecast.data_layers.silver import SilverBuilder
from cash_flow_forecast.dataset_building import DatasetBuilder
from cash_flow_forecast.model_development.backtest_config import resolve_single_sequence_row


DEFAULT_RULESET_PATH = Path("configs/rulesets/loreal_cash_in_v1.yaml")


def build_silver_main(argv: list[str] | None = None) -> int:
    """Build Silver tables from local bronze CSV inputs."""

    parser = argparse.ArgumentParser(description="Build Silver entity tables.")
    parser.add_argument("--input-path", default="data/bronze")
    parser.add_argument("--output-path", default="data/silver")
    args = parser.parse_args(argv)

    schema = build_default_schema()
    builder = SilverBuilder(schema)
    bronze_tables = read_bronze_tables(args.input_path)
    result = builder.build(SilverBuildRequest(bronze_tables=bronze_tables, schema=schema))
    write_silver_result(args.output_path, result)
    return 0


def build_gold_main(argv: list[str] | None = None) -> int:
    """Build Gold outputs from local Silver parquet inputs."""

    parser = argparse.ArgumentParser(description="Build Gold outputs.")
    parser.add_argument("--input-path", default="data/silver")
    parser.add_argument("--output-path", default="data/gold")
    parser.add_argument("--ruleset-path", default=str(DEFAULT_RULESET_PATH))
    args = parser.parse_args(argv)

    silver_tables = read_silver_tables(args.input_path)
    ruleset = load_ruleset_from_yaml(args.ruleset_path)
    builder = GoldBuilder(ruleset)
    result = builder.build(GoldBuildRequest(silver_tables=silver_tables, ruleset=ruleset))
    write_gold_result(args.output_path, result)
    return 0


def snapshot_dataset_main(argv: list[str] | None = None) -> int:
    """Write a diagnostic one-sequence dataset snapshot from a backtest YAML."""

    parser = argparse.ArgumentParser(
        description=(
            "Write a local diagnostic dataset snapshot. Backtests build datasets live "
            "and never read these snapshot artifacts."
        )
    )
    parser.add_argument("--config-path", required=True, help="Backtest YAML containing dataset settings.")
    parser.add_argument("--input-path", help="Override the YAML single-series Gold input folder.")
    parser.add_argument("--ruleset-path", help="Override the YAML ruleset path.")
    parser.add_argument("--output-root", default="data/datasets/snapshots")
    args = parser.parse_args(argv)

    config_path = Path(args.config_path)
    local_config = load_local_backtest_yaml(
        config_path,
        input_path=args.input_path,
        ruleset_path=args.ruleset_path,
    )
    config = local_config.definition
    ruleset = load_ruleset_from_yaml(local_config.ruleset_path)
    gold_outputs = read_gold_outputs(local_config.input_path)
    sequence_row = resolve_single_sequence_row(gold_outputs, ruleset, config.sequence)
    cutoff_dates = _date_range(config.evaluation.cutoff_start, config.evaluation.cutoff_end)
    label_as_of_date = _parse_date(config.evaluation.cutoff_end)
    builder = DatasetBuilder()
    result = builder.build(
        DatasetBuildRequest(
            gold_outputs=gold_outputs,
            ruleset=ruleset,
            dataset=config.dataset,
            cutoff_dates=cutoff_dates,
            sequence_id=str(sequence_row[SEQUENCE_ID_COLUMN]),
            label_as_of_date=label_as_of_date,
        )
    )
    snapshot_output_path = _snapshot_output_path(
        args.output_root,
        sequence_id=str(sequence_row[SEQUENCE_ID_COLUMN]),
        dataset_kind=config.dataset.kind.value,
        config_name=config_path.stem,
    )
    write_dataset_result(snapshot_output_path, result)
    return 0


def run_backtest_main(argv: list[str] | None = None) -> int:
    """Run a local rolling-origin backtest."""

    parser = argparse.ArgumentParser(description="Run a local backtest.")
    parser.add_argument("--config-path", required=True, help="YAML config for single-series D+1 backtests.")
    parser.add_argument("--input-path", help="Override the YAML single-series Gold input folder.")
    parser.add_argument("--output-path", help="Override the YAML backtest output path.")
    parser.add_argument("--ruleset-path", help="Override the YAML ruleset path.")
    args = parser.parse_args(argv)

    run_local_backtest_from_yaml(
        args.config_path,
        input_path=args.input_path,
        output_path=args.output_path,
        ruleset_path=args.ruleset_path,
    )
    return 0


def build_silver_entrypoint() -> int:
    """Console script entrypoint."""

    return build_silver_main()


def build_gold_entrypoint() -> int:
    """Console script entrypoint."""

    return build_gold_main()


def snapshot_dataset_entrypoint() -> int:
    """Console script entrypoint."""

    return snapshot_dataset_main()


def run_backtest_entrypoint() -> int:
    """Console script entrypoint."""

    return run_backtest_main()


def _date_range(start: str, end: str) -> list:
    return [timestamp.date() for timestamp in _timestamp_range(start, end)]


def _timestamp_range(start: str, end: str):
    import pandas as pd

    return pd.date_range(start=start, end=end, freq="D")


def _parse_date(value: str):
    import pandas as pd

    return pd.Timestamp(value).date()


def _snapshot_output_path(
    output_root: str | Path,
    *,
    sequence_id: str,
    dataset_kind: str,
    config_name: str,
) -> Path:
    """Return the local diagnostic snapshot folder for one sequence and config."""

    return (
        Path(output_root)
        / _safe_path_part(sequence_id)
        / _safe_path_part(dataset_kind)
        / _safe_path_part(config_name)
    )


def _safe_path_part(value: str) -> str:
    normalized = value.replace("+", "_plus").replace("-", "_minus")
    return re.sub(r"[^A-Za-z0-9_.=]+", "_", normalized).strip("_") or "unknown"
