import os
from typing import List, Optional

from azure.cosmos import PartitionKey
from azure.cosmos.aio import CosmosClient

from .identity import get_azure_credential_async
from .models import Conversation


class ConversationsStore:
    async def get(self, conversation_id: str) -> Optional[Conversation]:
        raise NotImplementedError

    async def set(self, conversation: Conversation):
        raise NotImplementedError

    async def delete(self, conversation_id: str):
        raise NotImplementedError

    async def list(self) -> List[Conversation]:
        raise NotImplementedError

    async def get_by_session_id(self, session_id: str) -> Optional[Conversation]:
        raise NotImplementedError


class CosmosDBConversationsStore(ConversationsStore):
    def __init__(self):
        if endpoint := os.getenv("AZURE_COSMOSDB_ENDPOINT"):
            self.client = CosmosClient(
                url=endpoint,
                credential=get_azure_credential_async(),
            )
        elif connection_string := os.getenv("AZURE_COSMOSDB_CONNECTION_STRING"):
            self.client = CosmosClient.from_connection_string(connection_string)

        database_name = os.environ.get("AZURE_COSMOSDB_DATABASE", "audiohook")
        container_name = os.environ.get("AZURE_COSMOSDB_CONTAINER", "conversations")

        self.database_name = database_name
        self.container_name = container_name
        self._db = None
        self._container = None

    async def _get_container(self):
        if not self._container:
            if not self._db:
                self._db = await self.client.create_database_if_not_exists(
                    self.database_name
                )
            self._container = await self._db.create_container_if_not_exists(
                id=self.container_name,
                partition_key=PartitionKey(path="/id"),
                indexing_policy={
                    "indexingMode": "consistent",
                    "includedPaths": [
                        {"path": "/id/?"},
                        {"path": "/session_id/?"},
                        {"path": "/active/?"},
                        {"path": "/ani/?"},
                        {"path": "/ani_name/?"},
                        {"path": "/dnis/?"},
                    ],
                    "excludedPaths": [{"path": "/*"}],
                },
            )
        return self._container

    async def get(self, conversation_id: str) -> Optional[Conversation]:
        container = await self._get_container()
        item = await container.read_item(conversation_id, partition_key=conversation_id)
        return Conversation(**item)

    async def set(self, conversation: Conversation):
        container = await self._get_container()
        data = conversation.model_dump()

        # TODO use patch instead of upsert for certain operations (e.g. transcript/rtt)
        # to avoid overwriting the entire document
        await container.upsert_item(data)

    async def delete(self, conversation_id: str):
        container = await self._get_container()
        await container.delete_item(conversation_id, partition_key=conversation_id)

    async def list(self) -> List[Conversation]:
        container = await self._get_container()
        query = "SELECT * FROM c"
        items = container.query_items(query)
        return [Conversation(**item) async for item in items]

    async def get_by_session_id(self, session_id: str) -> Optional[Conversation]:
        container = await self._get_container()
        query = "SELECT * FROM c WHERE c.session_id = @session_id"
        params = [{"name": "@session_id", "value": session_id}]
        items = container.query_items(query, parameters=params)
        async for item in items:
            return Conversation(**item)
        return None


class InMemoryConversationsStore(ConversationsStore):
    def __init__(self):
        self._store = {}

    async def get(self, conversation_id: str) -> Optional[Conversation]:
        return self._store.get(conversation_id)

    async def set(self, conversation: Conversation):
        self._store[conversation.id] = conversation

    async def delete(self, conversation_id: str):
        if conversation_id in self._store:
            del self._store[conversation_id]

    async def list(self) -> List[Conversation]:
        return list(self._store.values())

    async def get_by_session_id(self, session_id: str) -> Optional[Conversation]:
        for conversation in self._store.values():
            if conversation.session_id == session_id:
                return conversation
        return None


def get_conversations_store():
    """
    Factory to select CosmosDB or in-memory store based on environment variables.
    """
    if os.environ.get("AZURE_COSMOSDB_ENDPOINT") or os.environ.get(
        "AZURE_COSMOSDB_CONNECTION_STRING"
    ):
        return CosmosDBConversationsStore()

    # Fallback to in-memory store if no CosmosDB credentials are provided
    return InMemoryConversationsStore()
