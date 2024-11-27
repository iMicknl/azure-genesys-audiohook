"""Storage utilities for the server."""

from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import ContentSettings


async def upload_blob_file(
    blob_service_client: BlobServiceClient,
    container_name: str,
    file_name: str,
    data: bytes,
    content_type: str | None = None,
    overwrite: bool = True,
):
    """Uploads a file to a blob storage container."""
    container_client = blob_service_client.get_container_client(
        container=container_name
    )

    content_settings = None
    if content_type:
        content_settings = ContentSettings(content_type=content_type)

    await container_client.upload_blob(
        name=file_name,
        data=data,
        overwrite=overwrite,
        content_settings=content_settings,
    )
