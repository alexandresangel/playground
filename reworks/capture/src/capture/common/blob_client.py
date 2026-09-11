"""Azure Blob access: managed identity in Azure; Azure CLI locally (not deploy SP env)."""

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

    # Local: AzureCliCredential first — EnvironmentCredential would pick AZURE_CLIENT_*
    # from deploy scripts (SP without Blob Data Reader). Azure: DefaultAzureCredential (MI).
    if _running_in_azure():
        cred_chain = ((DefaultAzureCredential, "DefaultAzureCredential"),)
    else:
        cred_chain = (
            (AzureCliCredential, "AzureCliCredential"),
            (lambda: DefaultAzureCredential(exclude_environment_credential=True), "DefaultAzureCredential"),
        )

    for cred_factory, label in cred_chain:
        try:
            client = BlobServiceClient(account_url=url, credential=cred_factory())
            container_client = client.get_container_client(container)
            try:
                container_client.get_container_properties()
            except ResourceNotFoundError:
                pass
            except HttpResponseError as exc:
                if exc.status_code in (401, 403):
                    raise
            return client, container_client, label
        except Exception as exc:
            failures.append(f"{label}: {exc}")

    raise RuntimeError(
        f"Cannot access {account_name}/{container}. Tried: {'; '.join(failures)}"
    )


def read_blob_bytes(account_name: str, container: str, blob_name: str) -> bytes:
    _, container_client, _ = connect_blob(account_name, container)
    return container_client.download_blob(blob_name.strip()).readall()


def read_blob_text(account_name: str, container: str, blob_name: str) -> str:
    text = read_blob_bytes(account_name, container, blob_name).decode("utf-8")
    if not text.strip():
        raise RuntimeError(f"Empty blob {container}/{blob_name}")
    return text