"""Storage utilities for the server."""

# from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import BlobServiceClient, ContentSettings


async def upload_blob_file(
    blob_service_client: BlobServiceClient,
    container_name: str,
    file_name: str,
    data: bytes,
    content_type: str | None = None,
    overwrite: bool = True,
) -> None:
    """Uploads a file to a blob storage container."""

    blob_client = blob_service_client.get_blob_client(
        container=container_name,
        blob=file_name,
    )

    # TODO Rewrite to async version
    # Async version dead-locks and not sure yet where the culprit is
    blob_client.upload_blob(
        data,
        blob_type="BlockBlob",
        overwrite=overwrite,
        content_settings=(
            ContentSettings(content_type=content_type) if content_type else None
        ),
        timeout=120,
    )
