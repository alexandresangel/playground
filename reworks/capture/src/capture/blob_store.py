"""Azure Blob reads: managed identity in ACA and Azure CLI credentials locally."""

from __future__ import annotations

import os


def _running_in_azure() -> bool:
    return bool(os.environ.get("IDENTITY_ENDPOINT") or os.environ.get("MSI_ENDPOINT"))


def connect_blob(account_name: str, container: str) -> tuple[object, object, str]:
    from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
    from azure.identity import AzureCliCredential, DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    url = f"https://{account_name.strip()}.blob.core.windows.net"
    failures: list[str] = []
    if _running_in_azure():
        credential_chain = ((DefaultAzureCredential, "DefaultAzureCredential"),)
    else:
        credential_chain = (
            (AzureCliCredential, "AzureCliCredential"),
            (
                lambda: DefaultAzureCredential(exclude_environment_credential=True),
                "DefaultAzureCredential",
            ),
        )

    for credential_factory, label in credential_chain:
        try:
            client = BlobServiceClient(account_url=url, credential=credential_factory())
            container_client = client.get_container_client(container)
            try:
                container_client.get_container_properties()
            except ResourceNotFoundError:
                pass
            except HttpResponseError as exc:
                if exc.status_code in (401, 403):
                    raise
            return client, container_client, label
        except Exception as exc:  # pragma: no cover - depends on credential chain
            failures.append(f"{label}: {exc}")

    raise RuntimeError(f"Cannot access {account_name}/{container}. Tried: {'; '.join(failures)}")


def read_blob_text(account_name: str, container: str, blob_name: str) -> str:
    _, container_client, _ = connect_blob(account_name, container)
    raw = container_client.download_blob(blob_name.strip()).readall().decode("utf-8")
    if not raw.strip():
        raise RuntimeError(f"Empty blob {container}/{blob_name}")
    return raw
