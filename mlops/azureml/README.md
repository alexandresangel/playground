# Azure ML Scaffold

This folder contains Azure ML v2 scaffolding only. It is designed to keep the cloud orchestration thin: each component installs the local package and calls the same CLI entrypoints used during local development.

## Contents

- `environments/`: reusable Python environment definition.
- `components/`: command components for Silver, Gold, optional dataset snapshots, backtesting, and inference.
- `pipelines/`: pipeline job templates and the daily inference pipeline component used by the batch endpoint.
- `endpoints/`: batch endpoint and pipeline deployment templates for daily inference.
- `schedules/`: time-based schedule templates.

## Intended Flow

1. Register or create the environment.
2. Register components when the workspace is available.
3. Submit `pipelines/training_backtesting.yml` for model-development runs.
4. Treat daily inference as a placeholder until a `run-inference` CLI is implemented. The component currently fails fast with that message instead of calling a missing command.

Backtest and snapshot components accept mounted `gold_path` and `ruleset_path` inputs and pass them as CLI overrides, so cloud jobs do not rely on local paths embedded in YAML configs.

No file in this scaffold contains secrets or workspace-specific identifiers. Fill datastore paths, compute names, and workspace configuration in the deployment environment rather than hardcoding them here.
