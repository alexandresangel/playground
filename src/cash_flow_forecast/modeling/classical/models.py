from __future__ import annotations

from cash_flow_forecast.modeling.sktime import SktimeForecasterAdapter


class AutoArimaModel(SktimeForecasterAdapter):
    """sktime AutoARIMA for one selected D+1 sequence."""

    model_name = "auto_arima"
    description = "sktime AutoARIMA fitted on one selected sequence."
    default_parameters = {
        "sp": 7,
        "seasonal": True,
        "suppress_warnings": True,
        "error_action": "ignore",
        "n_jobs": 1,
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.arima import AutoARIMA

        return AutoARIMA(**self.parameters)


class SarimaModel(SktimeForecasterAdapter):
    """sktime SARIMAX wrapper for explicit SARIMA orders."""

    model_name = "sarima"
    description = "sktime SARIMAX fitted on one selected sequence."
    default_parameters = {
        "order": (1, 0, 0),
        "seasonal_order": (0, 0, 0, 0),
        "trend": None,
        "enforce_stationarity": False,
        "enforce_invertibility": False,
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.sarimax import SARIMAX

        return SARIMAX(**self.parameters)


class ThetaModel(SktimeForecasterAdapter):
    """sktime Theta forecaster for one selected D+1 sequence."""

    model_name = "theta"
    description = "sktime Theta forecaster fitted on one selected sequence."
    default_parameters = {"sp": 7}

    def _make_forecaster(self) -> object:
        from sktime.forecasting.theta import ThetaForecaster

        return ThetaForecaster(**self.parameters)


class TbatsModel(SktimeForecasterAdapter):
    """sktime TBATS forecaster for one selected D+1 sequence."""

    model_name = "tbats"
    description = "sktime TBATS fitted on one selected sequence."
    default_parameters = {
        "sp": 7,
        "use_box_cox": False,
        "show_warnings": False,
        "n_jobs": 1,
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.tbats import TBATS

        return TBATS(**self.parameters)


class ProphetModel(SktimeForecasterAdapter):
    """sktime Prophet wrapper for one selected D+1 sequence."""

    model_name = "prophet"
    description = "sktime Prophet fitted on one selected sequence."
    default_parameters = {
        "freq": "D",
        "weekly_seasonality": True,
        "yearly_seasonality": False,
        "daily_seasonality": False,
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.fbprophet import Prophet

        return Prophet(**self.parameters)


class ProphetverseModel(SktimeForecasterAdapter):
    """sktime Prophetverse wrapper for one selected D+1 sequence."""

    model_name = "prophetverse"
    description = "sktime Prophetverse fitted on one selected sequence."
    default_parameters = {
        "trend": "linear",
        "likelihood": "normal",
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.prophetverse import Prophetverse

        return Prophetverse(**self.parameters)
