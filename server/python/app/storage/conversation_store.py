import os

from .cosmos_db_conversation_store import CosmosDBConversationStore
from .in_memory_conversation_store import InMemoryConversationStore


def get_conversation_store():
    """
    Factory to select CosmosDB or in-memory store based on environment variables.
    """
    if os.environ.get("AZURE_COSMOSDB_ENDPOINT") or os.environ.get(
        "AZURE_COSMOSDB_CONNECTION_STRING"
    ):
        return CosmosDBConversationStore()

    # Fallback to in-memory store if no CosmosDB credentials are provided
    return InMemoryConversationStore()
