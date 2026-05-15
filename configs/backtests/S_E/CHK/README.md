# S_E CHK Backtest Config Pack

This folder contains broad CHK experiments for the S_E sequence:

- entity: `OAE850`
- currency: `EUR`
- movement scope: `CHK+`

Run one config locally:

```bash
uv run run-backtest --config-path configs/S_E/CHK/10_lightgbm_grid.yaml
```

Override paths for temporary or cloud-mounted runs:

```bash
uv run run-backtest \
  --config-path configs/S_E/CHK/00_tabular_baselines.yaml \
  --input-path data/gold \
  --output-path data/backtests \
  --ruleset-path configs/rulesets/loreal_cash_in_v1.yaml
```

The `60_*`, `61_*`, and `62_*` configs are intentionally short-window experiments because neural and foundation models can be slow and may download public model weights on first use.

Quantile LightGBM entries are normal backtest runs with grouped `custom_name` values such as `quantile/95_lower`; they are not interval sidecar artifacts.
