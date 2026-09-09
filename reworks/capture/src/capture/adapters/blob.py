"""The existing Diapason Azure Blob credential policy, reusable across apps."""

import os
from typing import Any


def _running_in_azure() -> bool:
    return bool(os.environ.get("IDENTITY_ENDPOINT") or os.environ.get("MSI_ENDPOINT"))


def connect_blob(account_name: str, container: str) -> tuple[Any, Any, str]:
    from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
    from azure.identity import AzureCliCredential, DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    url = f"https://{account_name.strip()}.blob.core.windows.net"
    # Preserve the original policy: deployment service-principal environment
    # variables must not displace the developer's Azure CLI identity locally.
    chain = (
        ((DefaultAzureCredential, "DefaultAzureCredential"),)
        if _running_in_azure()
        else (
            (AzureCliCredential, "AzureCliCredential"),
            (
                lambda: DefaultAzureCredential(exclude_environment_credential=True),
                "DefaultAzureCredential",
            ),
        )
    )
    failures = []
    for factory, label in chain:
        credential, client = None, None
        try:
            credential = factory()
            client = BlobServiceClient(account_url=url, credential=credential)
            target = client.get_container_client(container)
            try:
                target.get_container_properties()
            except ResourceNotFoundError:
                pass
            except HttpResponseError as exc:
                if exc.status_code in (401, 403):
                    raise
            return client, target, label
        except Exception as exc:
            # Never propagate credential/SDK exception bodies to logs or callers.
            failures.append(f"{label}:{type(exc).__name__}")
            if client is not None:
                client.close()
            if credential is not None:
                credential.close()
    raise RuntimeError("Blob credential chain unavailable (" + ", ".join(failures) + ")")


def read_blob_bytes(account_name: str, container: str, blob_name: str) -> bytes:
    client, target, _ = connect_blob(account_name, container)
    try:
        return target.download_blob(blob_name.strip()).readall()
    finally:
        client.close()


def read_blob_text(account_name: str, container: str, blob_name: str) -> str:
    text = read_blob_bytes(account_name, container, blob_name).decode("utf-8")
    if not text.strip():
        raise RuntimeError("The configured Blob text object is empty")
    return text
