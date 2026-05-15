from __future__ import annotations
from abc import abstractmethod
import math
from typing import Any, Iterable
import warnings
import pandas as pd

from cash_flow_forecast.contracts.builders import ModelInfo
from cash_flow_forecast.data_layers.gold.builder import TARGET_AMOUNT_COLUMN
from cash_flow_forecast.contracts.enums import DatasetKind
from cash_flow_forecast.modeling.base import ForecastModel
from cash_flow_forecast.modeling.features import (
    PREDICTION_COLUMN,
    forecast_steps_from_training,
    mean_training_value,
    training_series,
)
from cash_flow_forecast.modeling.prediction_intervals import interval_lower_column, interval_upper_column


class SktimeForecasterAdapter(ForecastModel):
    """Base adapter for one-sequence sktime forecasters."""

    dataset_kind = DatasetKind.TIME_SERIES
    model_name: str
    description: str
    default_parameters: dict[str, Any] = {}
    default_min_observations: int = 2

    def __init__(self, min_observations: int | None = None, **parameters: object) -> None:
        self.min_observations = int(
            self.default_min_observations if min_observations is None else min_observations
        )
        self.parameters = dict(self.default_parameters)
        self.parameters.update(parameters)
        self.fallback_ = 0.0
        self.training_frame_ = pd.DataFrame()
        self.training_series_ = pd.Series(dtype="float64")
        self.training_y_: pd.Series | pd.DataFrame = pd.Series(dtype="float64")
        self.last_date_: pd.Timestamp | None = None
        self.forecaster_: object | None = None
        self.fit_requires_fh_ = False
        self.forecaster_is_fitted_ = False
        self.fitted_steps_ = 0
        self.use_dataframe_y_ = False
        self.supports_prediction_intervals_: bool | None = None

    def fit(self, training_frame: pd.DataFrame) -> "SktimeForecasterAdapter":
        self.training_frame_ = training_frame.copy()
        self.fallback_ = mean_training_value(training_frame)
        self.training_series_ = _sktime_series(training_frame)
        self.training_y_ = self.training_series_
        self.forecaster_ = None
        self.fit_requires_fh_ = False
        self.forecaster_is_fitted_ = False
        self.fitted_steps_ = 0
        self.use_dataframe_y_ = False
        self.supports_prediction_intervals_ = None
        if self.training_series_.empty:
            return self
        self.last_date_ = pd.Timestamp(self.training_series_.index.max()).normalize()
        if len(self.training_series_) < self.min_observations:
            return self

        try:
            self.forecaster_ = self._make_forecaster()
        except ImportError as exc:
            raise RuntimeError(
                f"{self.model_name} requires sktime and its model dependencies. "
                "Run `uv sync` before fitting sktime models."
            ) from exc
        except TypeError as exc:
            raise ValueError(
                f"Invalid parameters for {self.model_name}: {sorted(self.parameters)}. "
                "Use the sktime parameter names documented for this model."
            ) from exc

        self._configure_forecaster()
        if self.fit_requires_fh_:
            return self
        self._fit_forecaster()
        return self

    def predict(self, inference_frame: pd.DataFrame) -> pd.DataFrame:
        predictions = inference_frame.copy()
        if self.forecaster_ is None or self.last_date_ is None or self.training_frame_.empty:
            predictions[PREDICTION_COLUMN] = self.fallback_
            return predictions

        steps = forecast_steps_from_training(self.training_frame_, predictions)
        if not self._ensure_forecaster_is_fitted(steps):
            predictions[PREDICTION_COLUMN] = self.fallback_
            return predictions

        try:
            forecast = self.forecaster_.predict(fh=list(range(1, steps + 1)))
            forecast_values = _forecast_values(forecast)
            forecast_dates = pd.date_range(
                self.last_date_ + pd.Timedelta(days=1),
                periods=steps,
                freq="D",
            )
            forecast_map = {
                date.normalize(): float(value)
                for date, value in zip(forecast_dates, forecast_values, strict=False)
            }
            prediction_dates = pd.to_datetime(predictions["FORECAST_DATE"]).dt.normalize()
            predictions[PREDICTION_COLUMN] = [
                forecast_map.get(pd.Timestamp(forecast_date).normalize(), self.fallback_)
                for forecast_date in prediction_dates
            ]
        except Exception:
            predictions[PREDICTION_COLUMN] = self.fallback_
        return predictions

    def predict_interval(self, inference_frame: pd.DataFrame, coverages: list[float]) -> pd.DataFrame:
        """Return point predictions plus native sktime interval columns."""

        predictions = self.predict(inference_frame)
        if not coverages:
            return predictions
        if self.supports_prediction_intervals_ is False:
            raise ValueError(
                f"{self.model_name} does not provide native sktime prediction intervals. "
                "Remove `prediction_intervals_coverage` or choose an interval-capable sktime model."
            )
        if self.forecaster_ is None or self.last_date_ is None or self.training_frame_.empty:
            return _fill_degenerate_intervals(predictions, coverages)

        steps = forecast_steps_from_training(self.training_frame_, predictions)
        try:
            interval_forecast = self.forecaster_.predict_interval(
                fh=list(range(1, steps + 1)),
                coverage=coverages,
            )
            forecast_dates = pd.date_range(
                self.last_date_ + pd.Timedelta(days=1),
                periods=steps,
                freq="D",
            )
            prediction_dates = pd.to_datetime(predictions["FORECAST_DATE"]).dt.normalize()
            point = pd.to_numeric(predictions[PREDICTION_COLUMN], errors="coerce").fillna(self.fallback_)
            for coverage in coverages:
                lower_values = _interval_map(interval_forecast, forecast_dates, coverage, "lower")
                upper_values = _interval_map(interval_forecast, forecast_dates, coverage, "upper")
                predictions[interval_lower_column(coverage)] = [
                    lower_values.get(pd.Timestamp(forecast_date).normalize(), float(point.iloc[index]))
                    for index, forecast_date in enumerate(prediction_dates)
                ]
                predictions[interval_upper_column(coverage)] = [
                    upper_values.get(pd.Timestamp(forecast_date).normalize(), float(point.iloc[index]))
                    for index, forecast_date in enumerate(prediction_dates)
                ]
        except Exception:
            return _fill_degenerate_intervals(predictions, coverages)
        return predictions

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            model_name=self.model_name,
            dataset_kind=self.dataset_kind,
            description=self.description,
            parameters={
                "min_observations": self.min_observations,
                **self.parameters,
            },
        )

    @abstractmethod
    def _make_forecaster(self) -> object:
        """Build the concrete sktime forecaster."""

    def _configure_forecaster(self) -> None:
        """Read sktime tags needed by the generic one-sequence adapter."""

        if self.forecaster_ is None:
            return
        self.use_dataframe_y_ = _forecaster_wants_dataframe_y(self.forecaster_)
        self.training_y_ = _sktime_frame(self.training_series_) if self.use_dataframe_y_ else self.training_series_
        self.fit_requires_fh_ = bool(_forecaster_tag(self.forecaster_, "requires-fh-in-fit", False))
        self.supports_prediction_intervals_ = bool(
            _forecaster_tag(self.forecaster_, "capability:pred_int", False)
        )

    def _ensure_forecaster_is_fitted(self, steps: int) -> bool:
        if self.forecaster_ is None:
            return False
        if self.forecaster_is_fitted_ and (not self.fit_requires_fh_ or steps <= self.fitted_steps_):
            return True
        return self._fit_forecaster(steps if self.fit_requires_fh_ else None)

    def _fit_forecaster(self, steps: int | None = None) -> bool:
        if self.forecaster_ is None:
            return False
        fit_kwargs: dict[str, object] = {}
        if steps is not None:
            fit_kwargs["fh"] = list(range(1, steps + 1))
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self.forecaster_.fit(self.training_y_, **fit_kwargs)
        except Exception:
            self.forecaster_ = None
            self.forecaster_is_fitted_ = False
            return False
        self.forecaster_is_fitted_ = True
        self.fitted_steps_ = max(self.fitted_steps_, int(steps or 0))
        return True


def _sktime_series(frame: pd.DataFrame) -> pd.Series:
    series = training_series(frame)
    if series.empty:
        return series
    series.index = pd.to_datetime(series.index).normalize()
    series = series.groupby(level=0).last().sort_index()
    series = pd.to_numeric(series, errors="coerce").fillna(0.0).astype(float)
    return series.asfreq("D").fillna(0.0)


def _sktime_frame(series: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({TARGET_AMOUNT_COLUMN: series})


def _forecast_values(forecast: object) -> list[float]:
    if isinstance(forecast, pd.DataFrame):
        if forecast.empty:
            return []
        values = forecast.iloc[:, 0]
    elif isinstance(forecast, pd.Series):
        values = forecast
    else:
        values = pd.Series(forecast)
    return pd.to_numeric(values, errors="coerce").fillna(0.0).astype(float).tolist()


def _forecaster_tag(forecaster: object, tag: str, default: object) -> object:
    get_tag = getattr(forecaster, "get_tag", None)
    if callable(get_tag):
        try:
            return get_tag(tag, default)
        except TypeError:
            try:
                return get_tag(tag)
            except (KeyError, ValueError):
                return default
    get_tags = getattr(forecaster, "get_tags", None)
    if callable(get_tags):
        try:
            return get_tags().get(tag, default)
        except AttributeError:
            return default
    return default


def _forecaster_wants_dataframe_y(forecaster: object) -> bool:
    y_inner_mtype = _forecaster_tag(forecaster, "y_inner_mtype", "")
    values = y_inner_mtype if isinstance(y_inner_mtype, list) else [y_inner_mtype]
    normalized = {str(value) for value in values}
    accepts_dataframe = "pd.DataFrame" in normalized
    accepts_series = "pd.Series" in normalized
    return accepts_dataframe and not accepts_series


def _fill_degenerate_intervals(predictions: pd.DataFrame, coverages: list[float]) -> pd.DataFrame:
    result = predictions.copy()
    point = pd.to_numeric(result[PREDICTION_COLUMN], errors="coerce").fillna(0.0).astype(float)
    for coverage in coverages:
        result[interval_lower_column(coverage)] = point
        result[interval_upper_column(coverage)] = point
    return result


def _interval_map(
    interval_forecast: pd.DataFrame,
    forecast_dates: pd.DatetimeIndex,
    coverage: float,
    bound: str,
) -> dict[pd.Timestamp, float]:
    column = _find_interval_column(interval_forecast.columns, coverage, bound)
    if column is None:
        return {}
    values = pd.to_numeric(interval_forecast[column], errors="coerce").fillna(0.0).astype(float).tolist()
    return {
        date.normalize(): float(value)
        for date, value in zip(forecast_dates, values, strict=False)
    }


def _find_interval_column(columns: Iterable[object], coverage: float, bound: str) -> object | None:
    fallback: object | None = None
    for column in columns:
        parts = column if isinstance(column, tuple) else (column,)
        if not _has_bound(parts, bound):
            continue
        if _has_coverage(parts, coverage):
            return column
        fallback = column
    return fallback


def _has_bound(parts: tuple[object, ...], bound: str) -> bool:
    return any(bound in str(part).lower() for part in parts)


def _has_coverage(parts: tuple[object, ...], coverage: float) -> bool:
    for part in parts:
        try:
            if math.isclose(float(part), float(coverage), rel_tol=1e-9, abs_tol=1e-9):
                return True
        except (TypeError, ValueError):
            continue
    return False
