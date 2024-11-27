"""Storage utilities for the server."""

from azure.storage.blob.aio import BlobServiceClient


async def upload_blob_file(
    blob_service_client: BlobServiceClient,
    container_name: str,
    file_name: str,
    data: bytes,
    overwrite: bool = True,
):
    """Uploads a file to a blob storage container."""
    container_client = blob_service_client.get_container_client(
        container=container_name
    )

    await container_client.upload_blob(name=file_name, data=data, overwrite=overwrite)
