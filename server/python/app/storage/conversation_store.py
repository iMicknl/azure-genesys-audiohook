import os

from ..models import Conversation
from .cosmos_db_conversation_store import CosmosDBConversationStore
from .in_memory_conversation_store import InMemoryConversationStore


class ConversationStore:
    """
    Interface for storing and retrieving conversations.
    This is an abstract class that defines the methods for
    getting, setting, deleting, and listing conversations.
    """

    async def get(self, conversation_id: str) -> Conversation | None:
        raise NotImplementedError

    async def set(self, conversation: Conversation):
        raise NotImplementedError

    async def delete(self, conversation_id: str):
        raise NotImplementedError

    async def list(self) -> list[Conversation]:
        raise NotImplementedError

    async def get_by_session_id(self, session_id: str) -> Conversation | None:
        raise NotImplementedError


def get_conversations_store():
    """
    Factory to select CosmosDB or in-memory store based on environment variables.
    """
    if os.environ.get("AZURE_COSMOSDB_ENDPOINT") or os.environ.get(
        "AZURE_COSMOSDB_CONNECTION_STRING"
    ):
        return CosmosDBConversationStore()
    # Fallback to in-memory store if no CosmosDB credentials are provided
    return InMemoryConversationStore()
