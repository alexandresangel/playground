from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {"TARGET_AMOUNT", "PREDICTION"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rank backtest run folders from predictions.parquet without adding core metric artifacts."
    )
    parser.add_argument("--backtests-path", default="data/backtests", help="Root folder containing backtest runs.")
    parser.add_argument("--output-path", help="Optional CSV path for the ranking table.")
    args = parser.parse_args(argv)

    ranking = rank_backtest_predictions(Path(args.backtests_path))
    if ranking.empty:
        print("No predictions.parquet files found.")
        return 1

    print(ranking.to_string(index=False))
    if args.output_path:
        output_path = Path(args.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ranking.to_csv(output_path, index=False)
    return 0


def rank_backtest_predictions(backtests_path: Path) -> pd.DataFrame:
    rows = []
    for predictions_path in sorted(backtests_path.rglob("predictions.parquet")):
        predictions = pd.read_parquet(predictions_path)
        _validate_predictions(predictions_path, predictions)
        abs_error = _abs_error(predictions)
        rows.append(
            {
                "run_path": predictions_path.parent.as_posix(),
                "prediction_rows": int(len(predictions)),
                "mae": float(abs_error.mean()),
                "median_ae": float(abs_error.median()),
                "p90_ae": float(abs_error.quantile(0.90)),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["run_path", "prediction_rows", "mae", "median_ae", "p90_ae"])
    return pd.DataFrame(rows).sort_values(["mae", "p90_ae", "median_ae", "run_path"]).reset_index(drop=True)


def _validate_predictions(predictions_path: Path, predictions: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS - set(predictions.columns)
    if missing:
        raise ValueError(f"{predictions_path} is missing required column(s): {sorted(missing)}.")


def _abs_error(predictions: pd.DataFrame) -> pd.Series:
    if "ABS_ERROR" in predictions.columns:
        return pd.to_numeric(predictions["ABS_ERROR"], errors="coerce").fillna(0.0).astype(float)
    target = pd.to_numeric(predictions["TARGET_AMOUNT"], errors="coerce").fillna(0.0).astype(float)
    forecast = pd.to_numeric(predictions["PREDICTION"], errors="coerce").fillna(0.0).astype(float)
    return (forecast - target).abs()


if __name__ == "__main__":
    raise SystemExit(main())
