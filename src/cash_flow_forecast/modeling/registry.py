from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from cash_flow_forecast.contracts.builders import ModelSpec
from cash_flow_forecast.contracts.enums import DatasetKind
from cash_flow_forecast.modeling.base import ForecastModel
from cash_flow_forecast.modeling.baselines import (
    KnownAmountD1BaselineModel,
    MovingAverageModel,
    NaiveLastDayModel,
    SeasonalNaiveWeeklyModel,
)
from cash_flow_forecast.modeling.classical import (
    AutoArimaModel,
    ProphetModel,
    ProphetverseModel,
    SarimaModel,
    TbatsModel,
    ThetaModel,
)
from cash_flow_forecast.modeling.composites import (
    OccurrenceSpikeCascadeModel,
    StackingEnsembleModel,
)
from cash_flow_forecast.modeling.deep_learning import (
    ChronosModel,
    HFTransformersModel,
    MOIRAIModel,
    NBeatsModel,
    NeuralForecastLSTMModel,
    NeuralForecastRNNModel,
    PyKANForecasterModel,
    PytorchForecastingDeepARModel,
    PytorchForecastingNHiTSModel,
    PytorchForecastingTFTModel,
    TinyTimeMixerModel,
)
from cash_flow_forecast.modeling.intermittent import CrostonModel, ImapaModel
from cash_flow_forecast.modeling.tabular import (
    LightGBMRegressorModel,
    LightGBMZeroAwareModel,
    XGBoostRegressorModel,
)


ModelFactory = Callable[[], ForecastModel]


@dataclass(frozen=True)
class RegisteredModel:
    """Factory metadata for one selectable model."""

    dataset_kind: DatasetKind
    factory: Callable[..., ForecastModel]


MODEL_REGISTRY: dict[str, RegisteredModel] = {
    "naive_last_day": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=NaiveLastDayModel,
    ),
    "seasonal_naive_weekly": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=SeasonalNaiveWeeklyModel,
    ),
    "moving_average": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=MovingAverageModel,
    ),
    "known_amount_d1": RegisteredModel(
        dataset_kind=DatasetKind.TABULAR,
        factory=KnownAmountD1BaselineModel,
    ),
    "auto_arima": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=AutoArimaModel,
    ),
    "sarima": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=SarimaModel,
    ),
    "theta": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=ThetaModel,
    ),
    "tbats": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=TbatsModel,
    ),
    "prophet": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=ProphetModel,
    ),
    "prophetverse": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=ProphetverseModel,
    ),
    "croston": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=CrostonModel,
    ),
    "imapa": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=ImapaModel,
    ),
    "lightgbm_regressor": RegisteredModel(
        dataset_kind=DatasetKind.TABULAR,
        factory=LightGBMRegressorModel,
    ),
    "lightgbm_zero_aware": RegisteredModel(
        dataset_kind=DatasetKind.TABULAR,
        factory=LightGBMZeroAwareModel,
    ),
    "occurrence_spike_cascade": RegisteredModel(
        dataset_kind=DatasetKind.TABULAR,
        factory=OccurrenceSpikeCascadeModel,
    ),
    "xgboost_regressor": RegisteredModel(
        dataset_kind=DatasetKind.TABULAR,
        factory=XGBoostRegressorModel,
    ),
    "stacking_ensemble": RegisteredModel(
        dataset_kind=DatasetKind.TABULAR,
        factory=StackingEnsembleModel,
    ),
    "nbeats": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=NBeatsModel,
    ),
    "hf_transformers": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=HFTransformersModel,
    ),
    "chronos": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=ChronosModel,
    ),
    "moirai": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=MOIRAIModel,
    ),
    "tiny_time_mixer": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=TinyTimeMixerModel,
    ),
    "neuralforecast_rnn": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=NeuralForecastRNNModel,
    ),
    "neuralforecast_lstm": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=NeuralForecastLSTMModel,
    ),
    "pytorch_forecasting_tft": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=PytorchForecastingTFTModel,
    ),
    "pytorch_forecasting_deepar": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=PytorchForecastingDeepARModel,
    ),
    "pytorch_forecasting_nhits": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=PytorchForecastingNHiTSModel,
    ),
    "pykan_forecaster": RegisteredModel(
        dataset_kind=DatasetKind.TIME_SERIES,
        factory=PyKANForecasterModel,
    ),
}

DEFAULT_MODEL_BY_KIND = {
    DatasetKind.TIME_SERIES: "naive_last_day",
    DatasetKind.TABULAR: "known_amount_d1",
}


def available_model_names(dataset_kind: DatasetKind | None = None) -> list[str]:
    """Return registered model names, optionally filtered by dataset kind."""

    return [
        name
        for name, registered in MODEL_REGISTRY.items()
        if dataset_kind is None or registered.dataset_kind == dataset_kind
    ]


def default_model_name(dataset_kind: DatasetKind) -> str:
    """Return the default baseline model for a dataset kind."""

    return DEFAULT_MODEL_BY_KIND[dataset_kind]


def model_spec_for_name(
    model_name: str,
    dataset_kind: DatasetKind | None = None,
    parameters: dict[str, object] | None = None,
) -> ModelSpec:
    """Build a validated model spec from a registered model name."""

    registered = _registered_model(model_name)
    if dataset_kind is not None and registered.dataset_kind != dataset_kind:
        raise ValueError(
            f"Model {model_name!r} expects {registered.dataset_kind.value} datasets, "
            f"not {dataset_kind.value}."
        )
    return ModelSpec(
        model_name=model_name,
        dataset_kind=registered.dataset_kind,
        parameters=parameters or {},
    )


def create_model(spec: ModelSpec | str, dataset_kind: DatasetKind | None = None) -> ForecastModel:
    """Instantiate a forecasting model from a spec or registered model name."""

    model_spec = (
        model_spec_for_name(spec, dataset_kind=dataset_kind)
        if isinstance(spec, str)
        else spec
    )
    registered = _registered_model(model_spec.model_name)
    if registered.dataset_kind != model_spec.dataset_kind:
        raise ValueError(
            f"Model spec {model_spec.model_name!r} declares {model_spec.dataset_kind.value}, "
            f"but the registry declares {registered.dataset_kind.value}."
        )
    if dataset_kind is not None and model_spec.dataset_kind != dataset_kind:
        raise ValueError(
            f"Model {model_spec.model_name!r} expects {model_spec.dataset_kind.value} datasets, "
            f"not {dataset_kind.value}."
        )
    return registered.factory(**model_spec.parameters)


def _registered_model(model_name: str) -> RegisteredModel:
    try:
        return MODEL_REGISTRY[model_name]
    except KeyError as exc:
        options = ", ".join(sorted(MODEL_REGISTRY))
        raise ValueError(f"Unknown model {model_name!r}. Available models: {options}.") from exc
