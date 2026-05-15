# Cash Flow Forecast

This project builds a point-in-time safe D+1 cash-in forecasting pipeline. The current modeling process is intentionally simple at the orchestration level: one sequence per run, one forecast horizon, and one fresh model fit per backtest cutoff.

## Data Layers

Silver outputs one cleaned parquet file per entity.

Gold outputs the forecasting-ready tables:

- `known_movements_daily.parquet`: `TRADE_DATE`, `VALUE_DATE`, sequence keys, `KNOWN_AMOUNT`, and `KNOWN_COUNT`.
- `realized_cash_in.parquet`: final realized `VALUE_DATE` totals used for prediction errors.
- `calendar_daily.parquet`: deterministic calendar features.
- `sequence_reference.parquet`: entity, currency, movement scope, and `SEQUENCE_ID`.

## Local Runs

```bash
uv sync

uv run build-silver --input-path data/bronze --output-path data/silver

uv run build-gold --input-path data/silver --output-path data/gold --ruleset-path configs/rulesets/loreal_cash_in_v1.yaml

uv run run-backtest \
  --config-path configs/backtests/loreal_S_E_CHK_xgb.yaml \
  --input-path data/gold \
  --output-path data/backtests \
  --ruleset-path configs/rulesets/loreal_cash_in_v1.yaml
```

Backtests infer the dataset family from the selected model registry entries, then build point-in-time datasets live from Gold for every fold. Saved datasets are not consumed by model development.

Local YAML files may still define `input_path`, `output_path`, and `ruleset_path`; CLI values override them. Local backtest artifacts are written below `data/backtests/<entity>_<currency>/<movement_scope>/<model_name>_<custom_name>/`.

For diagnostics, `snapshot-dataset` can write the configured one-sequence cutoff range to `data/datasets/snapshots`:

```bash
uv run snapshot-dataset \
  --config-path configs/backtests/loreal_S_E_CHK_xgb.yaml \
  --input-path data/gold \
  --ruleset-path configs/rulesets/loreal_cash_in_v1.yaml
```

Snapshot parquet files are for inspecting feature rows only.

## Configuration Convention

Backtest configs live in `configs/backtests/` and are run with `run-backtest`. Every model entry must include a `custom_name`; it is used in the result folder so several parameterizations of the same model can be run from one YAML.

The broad CHK experiment pack lives in `configs/S_E/CHK/` so larger exploratory runs stay separate from the smaller baseline examples.

```yaml
models:
  - name: lightgbm_regressor
    custom_name: tweedie1000
    parameters:
      objective: tweedie
      n_estimators: 1000
      num_leaves: 100
      learning_rate: 0.03
      random_state: 0
```

For native sktime intervals, add top-level coverage values to a normal backtest YAML:

```yaml
prediction_intervals_coverage: [0.8, 0.95]
```

This is supported for sktime-backed models such as AutoARIMA, SARIMA, Theta, and TBATS. Tabular quantile experiments should be declared as separate model entries with their own parameters and `custom_name`.

Examples:

```bash
uv run run-backtest --config-path configs/backtests/loreal_S_E_CHK_classical.yaml
```

Each run folder contains only `config.json`, `model_info.json`, `run_report.json`, and `predictions.parquet`.

To compare runs without bringing metric artifacts back into the core pipeline, use the external diagnostic ranking script:

```bash
uv run python eda/rank_backtests.py --backtests-path data/backtests
```

Python callers can keep storage out of model-development code by passing already-loaded objects:

```python
from cash_flow_forecast.model_development import BacktestBatchRunner, parse_backtest_definition

definition = parse_backtest_definition(payload)
runs = BacktestBatchRunner().run(definition, gold_outputs, ruleset)
```

## Model Development Reference

The deep methodology reference is [Model Development, Training, And Backtesting](docs/deliverables/03_model_development_training_backtesting.md). It explains the rolling-origin backtest logic, the point-in-time leakage controls, and the model families.

Fixed modeling assumptions:

- Every modeling run resolves exactly one `SEQUENCE_ID`.
- The forecast horizon is fixed to D+1: `FORECAST_DATE = CUTOFF_DATE + 1 day`.
- Features are point-in-time safe: `TRADE_DATE <= CUTOFF_DATE`.
- Training labels are as-of the fold evaluation cutoff: `TRADE_DATE <= EVALUATION_CUTOFF`.
- Prediction errors compare predictions to final realized `VALUE_DATE` totals only after prediction.
- Forecasts are raw model outputs; the model layer does not clip negative values.
- `dataset.target_transform` defaults to `none`. Available values are `log1p`, `box_cox`, and `yeo_johnson`.
- When a target transform is enabled, target-derived features stay in the same modeling unit: lags, rolling mean/std, and known D+1 amount features use the fold-local transformed target space.
- `box_cox` and `yeo_johnson` are fitted per training fold. Box-Cox uses an automatic positive shift so zero-heavy cash-flow series can run.
- Backtest predictions are inverse-transformed back to original amount units before persistence.

Time-series models use `sktime` as the primary backend for AutoARIMA, SARIMA/SARIMAX, Theta, Croston, TBATS, Prophet, Prophetverse, NeuralForecast RNN/LSTM, PyTorch Forecasting TFT/DeepAR/N-HiTS/N-BEATS, PyKAN, and foundation forecasters from Hugging Face/Chronos/MOIRAI/TinyTimeMixer. `imapa` remains the StatsForecast-backed exception because current sktime releases do not expose a stable compatible IMAPA forecaster.

Registered time-series model names:

- `naive_last_day`, `seasonal_naive_weekly`, `moving_average`
- `auto_arima`, `sarima`, `theta`, `tbats`, `croston`, `imapa`
- `prophet`, `prophetverse`
- `neuralforecast_rnn`, `neuralforecast_lstm`
- `pytorch_forecasting_tft`, `pytorch_forecasting_deepar`, `pytorch_forecasting_nhits`, `nbeats`, `pykan_forecaster`
- `hf_transformers`, `chronos`, `moirai`, `tiny_time_mixer`

`hierarchical_prophet` is intentionally not registered yet because the current runner fits exactly one resolved `SEQUENCE_ID` per run.
`timesfm` is intentionally not registered yet because its current sktime dependency stack does not resolve cleanly on this project's Python 3.12 environment.

Foundation forecasters may download public Hugging Face model weights the first time a real backtest uses them.

Native interval output is optional in the normal backtest runner. Unsupported interval models fail clearly when `prediction_intervals_coverage` is configured.

Registered tabular and composite model names:

- `known_amount_d1`, `lightgbm_regressor`, `lightgbm_zero_aware`, `xgboost_regressor`
- `occurrence_spike_cascade`, `stacking_ensemble`

`occurrence_spike_cascade` is a tabular two-stage model for weird sparse or spiky series: it estimates occurrence, conditional spike probability, normal magnitude, and spike magnitude, then combines them with soft routing by default.

`stacking_ensemble` can combine nested tabular and time-series models in one run. It trains the meta model on time-ordered out-of-fold base predictions only, then refits base models on the full outer training fold before prediction.

Time-series dataset/model example:

```yaml
dataset:
  history_window_days: 90
  features:
    target_lags: [1, 7]
    rolling_windows:
      - days: 7
        aggregations: [mean]
models:
  - name: auto_arima
    custom_name: default
    parameters:
      sp: 7
  - name: tbats
    custom_name: default
    parameters:
      sp: 7
      use_box_cox: false
  - name: moving_average
    custom_name: default
    parameters:
      window_days: 7
  - name: prophet
    custom_name: weekly
    parameters:
      weekly_seasonality: true
  - name: neuralforecast_lstm
    custom_name: short
    parameters:
      max_steps: 50
      trainer_kwargs:
        enable_progress_bar: false
        logger: false
  - name: nbeats
    custom_name: default
    parameters:
      trainer_params:
        max_epochs: 5
      dataset_params:
        max_encoder_length: 28
  - name: chronos
    custom_name: bolt_tiny
    parameters:
      config:
        device_map: cpu
  - name: moirai
    custom_name: small
    parameters:
      context_length: 90
      num_samples: 20
  - name: tiny_time_mixer
    custom_name: zero_shot
    parameters:
      fit_strategy: zero-shot
  - name: hf_transformers
    custom_name: informer
    parameters:
      config:
        context_length: 28
        prediction_length: 1
      training_args:
        num_train_epochs: 1
```

Tabular dataset/model example:

```yaml
dataset:
  history_window_days: 90
  features:
    calendar: true
    known_d1: true
    target_lags: [1, 7, 14, 28]
    rolling_windows:
      - days: 7
        aggregations: [mean]
      - days: 28
        aggregations: [mean, std, non_zero_ratio]
    cross_movement_known:
      enabled: false
models:
  - name: lightgbm_regressor
    custom_name: tweedie1000
    parameters:
      n_estimators: 200
      learning_rate: 0.03
  - name: lightgbm_zero_aware
    custom_name: default
    parameters:
      classifier_parameters:
        n_estimators: 100
      regressor_parameters:
        n_estimators: 100
  - name: occurrence_spike_cascade
    custom_name: q90_soft
    parameters:
      spike:
        method: training_quantile
        quantile: 0.90
        min_spike_rows: 10
        min_normal_rows: 10
      routing:
        mode: soft
      occurrence_model:
        name: lightgbm_classifier
      spike_model:
        name: lightgbm_classifier
      normal_magnitude_model:
        name: lightgbm_regressor
      spike_magnitude_model:
        name: lightgbm_regressor
```

Mixed-kind stacking example:

```yaml
dataset:
  history_window_days: 90
  features:
    calendar: true
    known_d1: true
    target_lags: [1, 7, 14, 28]
    rolling_windows:
      - days: 7
        aggregations: [mean]
models:
  - name: stacking_ensemble
    custom_name: lgb_tbats_ridge
    parameters:
      anchor_model_alias: lgb
      oof:
        max_folds: 5
        min_train_window_days: 90
        validation_window_days: 14
        step_days: 14
        min_oof_rows: 30
      base_models:
        - alias: lgb
          name: lightgbm_regressor
          parameters:
            n_estimators: 300
        - alias: tbats
          name: tbats
          dataset:
            history_window_days: 365
            features:
              target_lags: []
              rolling_windows: []
      meta_model:
        name: sklearn_ridge_regressor
        parameters:
          alpha: 1.0
      passthrough_features: false
```

## EDA

```bash
uv run eda/export_gold_business_eda.py --gold-path data/gold --silver-path data/silver --ruleset-path configs/rulesets/loreal_cash_in_v1.yaml --out-path reports/gold_eda --entities all --windows "full,365d,180d,90d"
```
