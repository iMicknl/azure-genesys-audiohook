import dataclasses
import os
from typing import List, Optional

from azure.cosmos import PartitionKey
from azure.cosmos.aio import CosmosClient

from .models import Conversation


class ConversationsStore:
    async def get(self, conversation_id: str) -> Optional[Conversation]:
        raise NotImplementedError

    async def set(self, conversation_id: str, conversation: Conversation):
        raise NotImplementedError

    async def delete(self, conversation_id: str):
        raise NotImplementedError

    async def list(self) -> List[Conversation]:
        raise NotImplementedError

    async def get_by_session_id(self, session_id: str) -> Optional[Conversation]:
        raise NotImplementedError


class CosmosDBConversationsStore(ConversationsStore):
    def __init__(self):
        endpoint = os.environ["COSMOSDB_ENDPOINT"]
        key = os.environ["COSMOSDB_KEY"]
        database_name = os.environ.get("COSMOSDB_DATABASE", "audiohook")
        container_name = os.environ.get("COSMOSDB_CONTAINER", "conversations")
        self.client = CosmosClient(endpoint, key)
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
                partition_key=PartitionKey(path="/conversation_id"),
            )
        return self._container

    async def get(self, conversation_id: str) -> Optional[Conversation]:
        container = await self._get_container()
        try:
            item = await container.read_item(
                conversation_id, partition_key=conversation_id
            )
            return Conversation(**item)
        except Exception:
            return None

    async def set(self, conversation_id: str, conversation: Conversation):
        container = await self._get_container()
        data = dataclasses.asdict(conversation)
        data["id"] = conversation_id
        data["conversation_id"] = conversation_id
        await container.upsert_item(data)

    async def delete(self, conversation_id: str):
        container = await self._get_container()
        await container.delete_item(conversation_id, partition_key=conversation_id)

    async def list(self) -> List[Conversation]:
        container = await self._get_container()
        query = "SELECT * FROM c"
        items = container.query_items(query, enable_cross_partition_query=True)
        return [Conversation(**item) async for item in items]

    async def get_by_session_id(self, session_id: str) -> Optional[Conversation]:
        container = await self._get_container()
        query = "SELECT * FROM c WHERE c.session_id = @session_id"
        params = [{"name": "@session_id", "value": session_id}]
        items = container.query_items(
            query, parameters=params, enable_cross_partition_query=True
        )
        async for item in items:
            return Conversation(**item)
        return None


class InMemoryConversationsStore(ConversationsStore):
    def __init__(self):
        self._store = {}

    async def get(self, conversation_id: str) -> Optional[Conversation]:
        return self._store.get(conversation_id)

    async def set(self, conversation_id: str, conversation: Conversation):
        self._store[conversation_id] = conversation

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
    if os.environ.get("COSMOSDB_ENDPOINT") and os.environ.get("COSMOSDB_KEY"):
        return CosmosDBConversationsStore()
    return InMemoryConversationsStore()
