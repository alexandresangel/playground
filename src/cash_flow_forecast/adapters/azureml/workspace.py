from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field


class AzureMLWorkspaceConfig(BaseModel):
    """Azure ML workspace coordinates."""

    subscription_id: str = Field(min_length=1)
    resource_group_name: str = Field(min_length=1)
    workspace_name: str = Field(min_length=1)

    @classmethod
    def from_env(cls) -> "AzureMLWorkspaceConfig":
        """Create config from standard Azure ML environment variables."""

        payload = {
            "subscription_id": os.getenv("AZUREML_SUBSCRIPTION_ID"),
            "resource_group_name": os.getenv("AZUREML_RESOURCE_GROUP_NAME"),
            "workspace_name": os.getenv("AZUREML_WORKSPACE_NAME"),
        }
        missing = [key for key, value in payload.items() if not value]
        if missing:
            env_names = ", ".join(f"AZUREML_{key.upper()}" for key in missing)
            raise ValueError(f"Missing Azure ML workspace environment variables: {env_names}.")
        return cls.model_validate(payload)


class AzureMLWorkspaceAdapter:
    """Thin wrapper around Azure ML SDK v2 operations."""

    def __init__(
        self,
        config: AzureMLWorkspaceConfig,
        ml_client: Any | None = None,
        data_asset_cls: type | None = None,
        load_job_func: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config
        self.ml_client = ml_client or self._build_ml_client(config)
        self._data_asset_cls = data_asset_cls
        self._load_job_func = load_job_func

    @staticmethod
    def _build_ml_client(config: AzureMLWorkspaceConfig):
        try:
            from azure.ai.ml import MLClient
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise RuntimeError(
                "AzureMLWorkspaceAdapter requires `azure-ai-ml` and `azure-identity`. "
                "Install the Azure ML SDK dependencies in your execution environment."
            ) from exc

        return MLClient(
            DefaultAzureCredential(),
            config.subscription_id,
            config.resource_group_name,
            config.workspace_name,
        )

    def register_data_asset(
        self,
        name: str,
        version: str,
        path: str | Path,
        *,
        asset_type: str = "uri_folder",
        description: str | None = None,
    ):
        """Register a local or cloud path as an Azure ML data asset."""

        Data = self._data_asset_cls or self._load_data_asset_class()

        data_asset = Data(
            name=name,
            version=version,
            path=str(path),
            type=asset_type,
            description=description,
        )
        return self.ml_client.data.create_or_update(data_asset)

    def get_data_asset(
        self,
        name: str,
        version: str | None = None,
        label: str | None = None,
    ):
        """Get an Azure ML data asset by version or label."""

        return self.ml_client.data.get(name=name, version=version, label=label)

    def submit_job(
        self,
        job_yaml_path: str | Path,
        *,
        experiment_name: str | None = None,
        params_override: list[dict[str, object]] | None = None,
        stream: bool = False,
    ):
        """Submit a command or pipeline job YAML to Azure ML."""

        load_job = self._load_job_func or self._load_job_function()

        job = load_job(source=str(job_yaml_path), params_override=params_override)
        submitted_job = self.ml_client.jobs.create_or_update(
            job,
            experiment_name=experiment_name,
        )
        if stream:
            self.stream_job(submitted_job.name)
        return submitted_job

    def stream_job(self, job_name: str) -> None:
        """Stream logs for a submitted Azure ML job."""

        self.ml_client.jobs.stream(job_name)

    def download_job_outputs(
        self,
        job_name: str,
        download_path: str | Path,
        *,
        output_name: str | None = None,
        all_outputs: bool = False,
    ) -> None:
        """Download logs or outputs for an Azure ML job."""

        self.ml_client.jobs.download(
            name=job_name,
            download_path=str(download_path),
            output_name=output_name,
            all=all_outputs,
        )

    @staticmethod
    def _load_data_asset_class():
        try:
            from azure.ai.ml.entities import Data
        except ImportError as exc:
            raise RuntimeError(
                "Registering Azure ML data assets requires `azure-ai-ml`."
            ) from exc
        return Data

    @staticmethod
    def _load_job_function():
        try:
            from azure.ai.ml import load_job
        except ImportError as exc:
            raise RuntimeError("Submitting Azure ML jobs requires `azure-ai-ml`.") from exc
        return load_job
