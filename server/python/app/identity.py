"""Identity utilities for the server."""

from azure.core.credentials import AccessToken
from azure.identity import DefaultAzureCredential
from azure.identity.aio import DefaultAzureCredential as DefaultAzureCredentialAsync


def get_azure_credential() -> DefaultAzureCredential:
    """Get Azure credential."""

    return DefaultAzureCredential()


def get_azure_credential_async() -> DefaultAzureCredentialAsync:
    """Get async Azure credential."""

    return DefaultAzureCredentialAsync()


# TODO add cache for lifetime of token
def get_access_token(
    scope: str = "https://cognitiveservices.azure.com/.default",
) -> AccessToken:
    """Get Microsoft Entra access token for scope."""

    token_credential = get_azure_credential()
    token = token_credential.get_token(scope)

    return token


def get_speech_token(resource_id: str) -> str:
    """Create Azure Speech service token."""

    access_token = get_access_token()
    # For Azure Speech we need to include the "aad#" prefix and the "#" (hash) separator between resource ID and Microsoft Entra access token.
    authorization_token = "aad#" + resource_id + "#" + access_token.token

    return authorization_token
