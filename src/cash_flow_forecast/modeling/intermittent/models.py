from __future__ import annotations

from cash_flow_forecast.modeling.nixtla import StatsForecastAdapter
from cash_flow_forecast.modeling.sktime import SktimeForecasterAdapter


class CrostonModel(SktimeForecasterAdapter):
    """sktime Croston model for intermittent one-sequence demand."""

    model_name = "croston"
    description = "sktime Croston fitted on one selected sparse sequence."
    default_parameters: dict[str, object] = {"smoothing": 0.1}

    def _make_forecaster(self) -> object:
        from sktime.forecasting.croston import Croston

        return Croston(**self.parameters)


class ImapaModel(StatsForecastAdapter):
    """StatsForecast IMAPA model for intermittent one-sequence demand."""

    model_name = "imapa"
    description = "StatsForecast IMAPA fitted on one selected sparse sequence."
    default_parameters: dict[str, object] = {}

    def _make_model(self) -> object:
        from statsforecast.models import IMAPA

        return IMAPA(**self.parameters)
