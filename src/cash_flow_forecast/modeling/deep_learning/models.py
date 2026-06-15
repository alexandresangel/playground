from __future__ import annotations

from copy import deepcopy
from typing import Any

from cash_flow_forecast.modeling.sktime import SktimeForecasterAdapter


def _pytorch_forecasting_defaults() -> dict[str, Any]:
    return {
        "dataset_params": {
            "max_encoder_length": 28,
        },
        "train_to_dataloader_params": {
            "train": True,
            "batch_size": 32,
            "num_workers": 0,
        },
        "validation_to_dataloader_params": {
            "train": False,
            "batch_size": 32,
            "num_workers": 0,
        },
        "trainer_params": {
            "accelerator": "cpu",
            "max_epochs": 5,
            "enable_checkpointing": False,
            "enable_progress_bar": False,
            "logger": False,
        },
    }


def _deep_merge(
    defaults: dict[str, Any],
    overrides: dict[str, object],
) -> dict[str, Any]:
    result = deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class DeepSktimeForecasterAdapter(SktimeForecasterAdapter):
    """Base adapter for sktime neural forecasters with per-instance parameters."""

    default_min_observations = 29

    def __init__(self, min_observations: int | None = None, **parameters: object) -> None:
        super().__init__(min_observations=min_observations, **parameters)
        self.parameters = _deep_merge(self.default_parameters, parameters)


class NeuralForecastRNNModel(DeepSktimeForecasterAdapter):
    """sktime NeuralForecast RNN wrapper for one D+1 Gold series."""

    model_name = "neuralforecast_rnn"
    description = "sktime NeuralForecast RNN fitted on one Gold series."
    default_parameters = {
        "freq": "D",
        "input_size": 28,
        "inference_input_size": 28,
        "encoder_n_layers": 1,
        "encoder_hidden_size": 64,
        "decoder_layers": 1,
        "decoder_hidden_size": 64,
        "context_size": 10,
        "max_steps": 50,
        "batch_size": 32,
        "scaler_type": "robust",
        "random_seed": 1,
        "num_workers_loader": 0,
        "verbose_fit": False,
        "verbose_predict": False,
        "trainer_kwargs": {
            "enable_checkpointing": False,
            "enable_progress_bar": False,
            "logger": False,
        },
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.neuralforecast import NeuralForecastRNN

        return NeuralForecastRNN(**self.parameters)


class NeuralForecastLSTMModel(DeepSktimeForecasterAdapter):
    """sktime NeuralForecast LSTM wrapper for one D+1 Gold series."""

    model_name = "neuralforecast_lstm"
    description = "sktime NeuralForecast LSTM fitted on one Gold series."
    default_parameters = {
        "freq": "D",
        "input_size": 28,
        "inference_input_size": 28,
        "encoder_n_layers": 1,
        "encoder_hidden_size": 64,
        "decoder_layers": 1,
        "decoder_hidden_size": 64,
        "context_size": 10,
        "max_steps": 50,
        "batch_size": 32,
        "scaler_type": "robust",
        "random_seed": 1,
        "num_workers_loader": 0,
        "verbose_fit": False,
        "verbose_predict": False,
        "trainer_kwargs": {
            "enable_checkpointing": False,
            "enable_progress_bar": False,
            "logger": False,
        },
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.neuralforecast import NeuralForecastLSTM

        return NeuralForecastLSTM(**self.parameters)


class PytorchForecastingTFTModel(DeepSktimeForecasterAdapter):
    """sktime PyTorch Forecasting TFT wrapper for one D+1 Gold series."""

    model_name = "pytorch_forecasting_tft"
    description = "sktime PyTorch Forecasting TFT fitted on one Gold series."
    default_parameters = {
        **_pytorch_forecasting_defaults(),
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.pytorchforecasting import PytorchForecastingTFT

        return PytorchForecastingTFT(**self.parameters)


class PytorchForecastingDeepARModel(DeepSktimeForecasterAdapter):
    """sktime PyTorch Forecasting DeepAR wrapper for one D+1 Gold series."""

    model_name = "pytorch_forecasting_deepar"
    description = "sktime PyTorch Forecasting DeepAR fitted on one Gold series."
    default_parameters = {
        **_pytorch_forecasting_defaults(),
        "deterministic": True,
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.pytorchforecasting import PytorchForecastingDeepAR

        return PytorchForecastingDeepAR(**self.parameters)


class PytorchForecastingNHiTSModel(DeepSktimeForecasterAdapter):
    """sktime PyTorch Forecasting N-HiTS wrapper for one D+1 Gold series."""

    model_name = "pytorch_forecasting_nhits"
    description = "sktime PyTorch Forecasting N-HiTS fitted on one Gold series."
    default_parameters = {
        **_pytorch_forecasting_defaults(),
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.pytorchforecasting import PytorchForecastingNHiTS

        return PytorchForecastingNHiTS(**self.parameters)


class NBeatsModel(DeepSktimeForecasterAdapter):
    """sktime PyTorch Forecasting N-BEATS wrapper for one D+1 Gold series."""

    model_name = "nbeats"
    description = "sktime PyTorch Forecasting N-BEATS fitted on one Gold series."
    default_parameters = {
        **_pytorch_forecasting_defaults(),
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.pytorchforecasting import PytorchForecastingNBeats

        return PytorchForecastingNBeats(**self.parameters)


class HFTransformersModel(DeepSktimeForecasterAdapter):
    """sktime Hugging Face Transformers wrapper for one D+1 Gold series."""

    model_name = "hf_transformers"
    description = "sktime Hugging Face Transformers forecaster fitted on one Gold series."
    default_parameters = {
        "model_path": "huggingface/informer-tourism-monthly",
        "fit_strategy": "minimal",
        "validation_split": 0.2,
        "deterministic": True,
        "config": {
            "context_length": 28,
            "prediction_length": 1,
            "lags_sequence": [1, 2, 7, 14],
            "use_cpu": True,
        },
        "training_args": {
            "num_train_epochs": 1,
            "output_dir": ".cache/cash_flow_forecast/hf_transformers",
            "per_device_train_batch_size": 32,
            "per_device_eval_batch_size": 32,
            "use_cpu": True,
            "disable_tqdm": True,
            "report_to": [],
            "save_strategy": "no",
            "logging_strategy": "no",
        },
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.hf_transformers_forecaster import HFTransformersForecaster

        return HFTransformersForecaster(**self.parameters)


class ChronosModel(DeepSktimeForecasterAdapter):
    """sktime Chronos wrapper for one D+1 Gold series."""

    model_name = "chronos"
    description = "sktime Chronos forecaster fitted on one Gold series."
    default_parameters = {
        "model_path": "amazon/chronos-bolt-tiny",
        "seed": 1,
        "use_source_package": False,
        "ignore_deps": False,
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.chronos import ChronosForecaster

        return ChronosForecaster(**self.parameters)


class MOIRAIModel(DeepSktimeForecasterAdapter):
    """sktime MOIRAI wrapper for one D+1 Gold series."""

    model_name = "moirai"
    description = "sktime MOIRAI forecaster fitted on one Gold series."
    default_min_observations = 90
    default_parameters = {
        "checkpoint_path": "sktime/moirai-1.0-R-small",
        "context_length": 90,
        "patch_size": 32,
        "num_samples": 20,
        "target_dim": 1,
        "map_location": "cpu",
        "deterministic": True,
        "batch_size": 32,
        "use_source_package": False,
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.moirai_forecaster import MOIRAIForecaster

        return MOIRAIForecaster(**self.parameters)


class TinyTimeMixerModel(DeepSktimeForecasterAdapter):
    """sktime TinyTimeMixer wrapper for one D+1 Gold series."""

    model_name = "tiny_time_mixer"
    description = "sktime TinyTimeMixer forecaster fitted on one Gold series."
    default_parameters = {
        "model_path": "ibm/TTM",
        "revision": "main",
        "fit_strategy": "zero-shot",
        "validation_split": 0.2,
        "broadcasting": False,
        "use_source_package": False,
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.ttm import TinyTimeMixerForecaster

        return TinyTimeMixerForecaster(**self.parameters)


class PyKANForecasterModel(DeepSktimeForecasterAdapter):
    """sktime PyKAN wrapper for one D+1 Gold series."""

    model_name = "pykan_forecaster"
    description = "sktime PyKAN forecaster fitted on one Gold series."
    default_parameters = {
        "hidden_layers": (1, 1),
        "input_layer_size": 2,
        "model_params": {"k": 2},
        "fit_params": {"steps": 20},
        "val_size": 0.2,
        "device": "cpu",
    }

    def _make_forecaster(self) -> object:
        from sktime.forecasting.pykan_forecaster import PyKANForecaster

        return PyKANForecaster(**self.parameters)
